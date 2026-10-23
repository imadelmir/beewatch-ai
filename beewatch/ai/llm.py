"""Client dei modelli di linguaggio (M5-T1): Ollama in locale e OpenRouter nel cloud.

    from beewatch.ai.llm import crea_client

    client = crea_client(ottieni().llm)          # il provider lo decide LLM_PROVIDER in .env
    risposta = client.completa("Sei un assistente apistico.", "Com'è la covata?")
    risposta.testo, risposta.provider, risposta.modello, risposta.durata_ms

Si sviluppa gratis in locale (Ollama) e si passa al cloud (OpenRouter) cambiando **una
variabile in `.env`**: il resto del codice parla solo con `LLMClient`.

Scelte che contano:

- **Solo `requests`**, nessun SDK: sono due POST con un JSON. Un SDK in più sarebbe una
  dipendenza da tenere aggiornata per poche righe.
- **Una sola chiamata, non in streaming** (`stream: false`): il riepilogo di un'ispezione si
  valida intero (JSON) e solo allora si mostra; mezzo JSON non serve a nessuno.
- **I campi di `RispostaLLM` hanno i nomi delle colonne di `messaggi`** (provider, modello,
  durata_ms, token_prompt, token_risposta): chi salva la risposta li copia senza tradurre.
- **Ogni errore diventa un `LLMError`** con un messaggio in italiano che dice cosa fare, e
  **nient'altro esce da `completa`**: un'eccezione imprevista viene registrata con il suo stack e
  diventa anch'essa un `LLMError`, così l'interfaccia ha un solo caso da gestire. La chiave API non
  compare mai in un messaggio né nel log; del testo inviato si registra solo la lunghezza (le
  note di ispezione sono dati dell'utente).
- Formati verificati sulla documentazione ufficiale (ottobre 2026): Ollama `POST /api/chat`
  (<https://docs.ollama.com/api/chat>) e OpenRouter `POST /api/v1/chat/completions`
  (<https://openrouter.ai/docs/api-reference/chat-completion>).

Robustezza (M5-T2), in un ciclo senza librerie:

- **Si riprova solo ciò che può passare da solo**: timeout, connessione che non riesce (il
  server si sta avviando), stato 408, 429 e 5xx. 400, 401, 402, 403, 404 non cambiano
  riprovando: `LLMError` subito. Una risposta che arriva ma è inutilizzabile (non JSON, vuota)
  non si ritenta.
- **Backoff esponenziale: 1, 2 e 4 secondi**, al massimo tre nuovi tentativi (quattro in tutto).
  Se il provider manda `Retry-After` (secondi o data HTTP) si aspetta quello, ma mai più di 30
  secondi: se chiede di più si smette e l'errore dice quanto attendere. Un modello che si sta
  caricando può scadere la prima volta e rispondere alla seconda: per questo il timeout si ritenta.
- **Un tetto al tempo complessivo, tre volte il timeout.** Senza, quattro timeout da 60 secondi sono
  quattro minuti di interfaccia ferma. Raggiunto il tetto non si riprova più.
- A ogni tentativo fallito un avviso nel log (provider, tentativo, tipo di errore, attesa); alla
  fine una riga con modello, durata, token e **numero di tentativi**: servono alla presentazione.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import requests

from beewatch.config import OLLAMA_URL_PREDEFINITO, ConfigLLM
from beewatch.exceptions import LLMError
from beewatch.logging_config import ottieni_logger

logger = ottieni_logger(__name__)

URL_OPENROUTER = "https://openrouter.ai/api/v1"
SECONDI_CONNESSIONE = 10  # massimo per aprire la connessione; per rispondere vale LLM_TIMEOUT

# Attese prima del 2°, 3° e 4° tentativo: al massimo tre nuovi tentativi.
ATTESE_RETRY = (1.0, 2.0, 4.0)
ATTESA_MASSIMA_RETRY_AFTER = 30.0  # oltre, non si aspetta: si rinuncia e lo si dice
FATTORE_TETTO_TEMPO = 3  # il tempo complessivo non supera tre volte il timeout
STATI_TRANSITORI = frozenset({408, 429}) | frozenset(range(500, 600))


@dataclass(frozen=True)
class RispostaLLM:
    """Ciò che il modello ha risposto e come: i campi coincidono con le colonne di `messaggi`.

    `tentativi` è in più: non è una colonna, serve al log e alla presentazione.
    """

    testo: str
    provider: str
    modello: str
    durata_ms: int
    token_prompt: int | None  # None se il provider non li dichiara
    token_risposta: int | None
    tentativi: int = 1


class _Transitorio(Exception):
    """Un tentativo fallito per una causa che può passare da sola (uso interno)."""

    def __init__(self, errore: LLMError, causa: str, attesa_richiesta: float | None = None) -> None:
        super().__init__(causa)
        self.errore = errore
        self.causa = causa  # solo il tipo o lo stato: mai testo del provider né dell'utente
        self.attesa_richiesta = attesa_richiesta


class LLMClient(ABC):
    """Un provider di modelli di linguaggio dietro `completa`."""

    provider: str

    def __init__(
        self,
        modello: str,
        timeout: int,
        *,
        attese: tuple[float, ...] = ATTESE_RETRY,
        pausa: Callable[[float], None] = time.sleep,
        orologio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._modello = modello
        self._timeout = timeout
        # `pausa` e `orologio` si sostituiscono nei test: nessuno aspetta secondi veri.
        self._attese = attese
        self._pausa = pausa
        self._orologio = orologio

    def completa(
        self,
        sistema: str,
        utente: str,
        *,
        temperatura: float = 0.2,
        massimo_token: int | None = None,
        risposta_json: bool = False,
    ) -> RispostaLLM:
        """Una risposta del modello a `sistema` (istruzioni) e `utente` (la richiesta).

        Args:
            temperatura: casualità; bassa per un output da validare.
            massimo_token: tetto alla lunghezza della risposta; None = quello del provider.
            risposta_json: chiede al provider di rispondere con JSON valido. È una richiesta,
                non una garanzia: chi la usa valida comunque (M5-T3).

        Raises:
            LLMError: **l'unica eccezione che esce**: il provider non risponde, rifiuta la
                richiesta, risponde in un formato inatteso, o è successo qualcosa di imprevisto
                (in quel caso con lo stack nel log).
        """
        inizio = time.perf_counter()
        try:
            risposta = self._completa(sistema, utente, temperatura, massimo_token, risposta_json)
        except LLMError:
            raise
        except Exception as errore:  # un bug non deve arrivare all'interfaccia come crash
            logger.exception("Errore imprevisto nella chiamata a %s", self.provider)
            raise LLMError(
                "Errore imprevisto nella chiamata al modello. I dettagli sono nel file di log."
            ) from errore
        durata_ms = round((time.perf_counter() - inizio) * 1000)
        risposta = replace(risposta, durata_ms=durata_ms)
        logger.info(
            "LLM %s/%s: %d ms, token %s→%s, %d tentativ%s, richiesta di %d caratteri",
            risposta.provider,
            risposta.modello,
            risposta.durata_ms,
            risposta.token_prompt,
            risposta.token_risposta,
            risposta.tentativi,
            "o" if risposta.tentativi == 1 else "i",
            len(sistema) + len(utente),
        )
        return risposta

    @abstractmethod
    def _completa(
        self,
        sistema: str,
        utente: str,
        temperatura: float,
        massimo_token: int | None,
        risposta_json: bool,
    ) -> RispostaLLM:
        """La chiamata vera al provider. La durata la imposta `completa`."""

    # ----------------------------------------------------------------------- #
    # HTTP, in comune: nuovi tentativi
    # ----------------------------------------------------------------------- #

    def _invia(
        self, url: str, corpo: dict[str, Any], intestazioni: dict[str, str] | None = None
    ) -> tuple[dict[str, Any], int]:
        """Un POST con corpo JSON, riprovando ciò che può passare da solo.

        Returns:
            Il JSON della risposta e il numero di tentativi fatti.

        Raises:
            LLMError: errore non transitorio, tentativi o tempo esauriti, risposta che non è un
                oggetto JSON.
        """
        inizio = self._orologio()
        tentativo = 0
        while True:
            tentativo += 1
            try:
                return self._un_tentativo(url, corpo, intestazioni), tentativo
            except _Transitorio as fallito:
                attesa = self._attesa(tentativo, fallito, self._orologio() - inizio)
                if attesa is None:
                    raise self._definitivo(fallito, tentativo) from fallito.errore.__cause__
                logger.warning(
                    "LLM %s: tentativo %d non riuscito (%s), riprovo fra %.1f s",
                    self.provider,
                    tentativo,
                    fallito.causa,
                    attesa,
                )
                self._pausa(attesa)

    def _attesa(self, tentativo: int, fallito: _Transitorio, trascorso: float) -> float | None:
        """Quanto aspettare prima del prossimo tentativo, o None se non se ne fanno più."""
        if tentativo > len(self._attese):
            return None
        attesa = self._attese[tentativo - 1]
        if fallito.attesa_richiesta is not None:
            if fallito.attesa_richiesta > ATTESA_MASSIMA_RETRY_AFTER:
                return None
            attesa = max(attesa, fallito.attesa_richiesta)
        # Dopo l'attesa serve ancora il tempo di un tentativo intero.
        if trascorso + attesa + self._timeout > FATTORE_TETTO_TEMPO * self._timeout:
            return None
        return attesa

    @staticmethod
    def _definitivo(fallito: _Transitorio, tentativi: int) -> LLMError:
        """L'errore da mostrare quando non si riprova più: quello del provider, più i tentativi."""
        messaggio = str(fallito.errore)
        richiesta = fallito.attesa_richiesta
        if richiesta is not None and richiesta > ATTESA_MASSIMA_RETRY_AFTER:
            messaggio += f" Il provider chiede di attendere {round(richiesta)} secondi."
        if tentativi > 1:
            messaggio += f" (dopo {tentativi} tentativi)"
        return LLMError(messaggio)

    def _un_tentativo(
        self, url: str, corpo: dict[str, Any], intestazioni: dict[str, str] | None
    ) -> dict[str, Any]:
        """Una richiesta. `_Transitorio` se può valere la pena riprovare, `LLMError` altrimenti."""
        try:
            risposta = requests.post(
                url,
                json=corpo,
                headers=intestazioni,
                timeout=(min(SECONDI_CONNESSIONE, self._timeout), self._timeout),
            )
        except requests.exceptions.Timeout as errore:
            raise _Transitorio(
                LLMError(
                    f"Il modello non ha risposto entro {self._timeout} secondi. "
                    "Riprova, o aumenta LLM_TIMEOUT in .env."
                ),
                "timeout",
            ) from errore
        except requests.exceptions.ConnectionError as errore:
            raise _Transitorio(LLMError(self._messaggio_connessione()), "connessione") from errore
        except requests.exceptions.RequestException as errore:
            logger.error("Richiesta al modello non riuscita: %s", type(errore).__name__)
            raise LLMError(
                "La richiesta al modello non è riuscita. I dettagli sono nel file di log."
            ) from errore

        if risposta.status_code >= 400:
            logger.error(
                "Il provider %s ha risposto con lo stato HTTP %d",
                self.provider,
                risposta.status_code,
            )
            errore = LLMError(self._messaggio_http(risposta.status_code, self._dettaglio(risposta)))
            if risposta.status_code in STATI_TRANSITORI:
                raise _Transitorio(
                    errore, f"stato {risposta.status_code}", self._retry_after(risposta)
                )
            raise errore
        try:
            dati = risposta.json()
        except ValueError as errore:
            raise LLMError(
                f"La risposta di {self.provider} non è JSON: forse non è il servizio atteso."
            ) from errore
        if not isinstance(dati, dict):
            raise LLMError(f"La risposta di {self.provider} ha un formato inatteso.")
        return dati

    @staticmethod
    def _retry_after(risposta: requests.Response) -> float | None:
        """Quanto chiede di aspettare l'intestazione `Retry-After` (secondi o data HTTP), se c'è."""
        valore = risposta.headers.get("Retry-After")
        if not valore:
            return None
        try:
            return max(0.0, float(valore))
        except ValueError:
            pass
        try:
            scadenza = parsedate_to_datetime(valore)
        except (TypeError, ValueError):
            return None
        if scadenza.tzinfo is None:
            scadenza = scadenza.replace(tzinfo=UTC)
        return max(0.0, (scadenza - datetime.now(UTC)).total_seconds())

    @staticmethod
    def _dettaglio(risposta: requests.Response) -> str:
        """Il motivo che il provider dà dell'errore, se lo dà: breve e senza dati nostri."""
        try:
            corpo = risposta.json()
        except ValueError:
            return ""
        errore = corpo.get("error") if isinstance(corpo, dict) else None
        if isinstance(errore, dict):
            errore = errore.get("message")
        return str(errore)[:200] if errore else ""

    @abstractmethod
    def _messaggio_connessione(self) -> str:
        """Cosa dire quando non ci si riesce a collegare."""

    @abstractmethod
    def _messaggio_http(self, stato: int, dettaglio: str) -> str:
        """Cosa dire per uno stato HTTP di errore."""

    @staticmethod
    def _numero(valore: Any) -> int | None:
        return valore if isinstance(valore, int) and not isinstance(valore, bool) else None


class ClientOllama(LLMClient):
    """Ollama sul computer o in rete locale: gratis, e le note non escono dalla macchina."""

    provider = "ollama"

    def __init__(
        self, modello: str, timeout: int, url: str = OLLAMA_URL_PREDEFINITO, **politica: Any
    ) -> None:
        super().__init__(modello, timeout, **politica)
        self._url = url.rstrip("/")

    def _completa(
        self,
        sistema: str,
        utente: str,
        temperatura: float,
        massimo_token: int | None,
        risposta_json: bool,
    ) -> RispostaLLM:
        opzioni: dict[str, Any] = {"temperature": temperatura}
        if massimo_token is not None:
            opzioni["num_predict"] = massimo_token
        corpo: dict[str, Any] = {
            "model": self._modello,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": utente},
            ],
            "stream": False,  # una sola risposta intera
            "options": opzioni,
        }
        if risposta_json:
            corpo["format"] = "json"

        dati, tentativi = self._invia(f"{self._url}/api/chat", corpo)

        messaggio = dati.get("message")
        testo = messaggio.get("content") if isinstance(messaggio, dict) else None
        if not isinstance(testo, str) or not testo.strip():
            raise LLMError("Ollama ha risposto senza testo. Controlla che il modello sia caricato.")
        return RispostaLLM(
            testo=testo,
            provider=self.provider,
            modello=str(dati.get("model") or self._modello),
            durata_ms=0,
            token_prompt=self._numero(dati.get("prompt_eval_count")),
            token_risposta=self._numero(dati.get("eval_count")),
            tentativi=tentativi,
        )

    def _messaggio_connessione(self) -> str:
        return (
            f"Ollama non risponde su {self._url}. Avvialo (`ollama serve`) oppure cambia "
            "LLM_PROVIDER o OLLAMA_BASE_URL in .env."
        )

    def _messaggio_http(self, stato: int, dettaglio: str) -> str:
        if stato == 404:
            return (
                f"Ollama non ha il modello «{self._modello}». Scaricalo con: "
                f"ollama pull {self._modello}"
            )
        if stato >= 500:
            return "Ollama ha avuto un errore interno. Riprova fra poco."
        extra = f" ({dettaglio})" if dettaglio else ""
        return f"Ollama ha rifiutato la richiesta (stato {stato}){extra}."


class ClientOpenRouter(LLMClient):
    """OpenRouter nel cloud: serve LLM_API_KEY, e le note escono dal computer."""

    provider = "openrouter"

    def __init__(
        self,
        modello: str,
        timeout: int,
        api_key: str | None,
        url: str = URL_OPENROUTER,
        **politica: Any,
    ) -> None:
        super().__init__(modello, timeout, **politica)
        if not api_key:
            raise LLMError("Per usare OpenRouter serve LLM_API_KEY in .env.")
        self._api_key = api_key
        self._url = url.rstrip("/")

    def _completa(
        self,
        sistema: str,
        utente: str,
        temperatura: float,
        massimo_token: int | None,
        risposta_json: bool,
    ) -> RispostaLLM:
        corpo: dict[str, Any] = {
            "model": self._modello,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": utente},
            ],
            "temperature": temperatura,
            "stream": False,
        }
        if massimo_token is not None:
            corpo["max_tokens"] = massimo_token
        if risposta_json:
            corpo["response_format"] = {"type": "json_object"}

        dati, tentativi = self._invia(
            f"{self._url}/chat/completions",
            corpo,
            {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
        )

        if "choices" not in dati and isinstance(dati.get("error"), dict):
            motivo = str(dati["error"].get("message") or "")[:200]
            raise LLMError(f"OpenRouter ha segnalato un errore: {motivo or 'senza dettagli'}.")
        try:
            testo = dati["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as errore:
            raise LLMError("OpenRouter ha risposto in un formato inatteso.") from errore
        if not isinstance(testo, str) or not testo.strip():
            raise LLMError("OpenRouter ha risposto senza testo.")
        uso = dati.get("usage") if isinstance(dati.get("usage"), dict) else {}
        return RispostaLLM(
            testo=testo,
            provider=self.provider,
            modello=str(dati.get("model") or self._modello),
            durata_ms=0,
            token_prompt=self._numero(uso.get("prompt_tokens")),
            token_risposta=self._numero(uso.get("completion_tokens")),
            tentativi=tentativi,
        )

    def _messaggio_connessione(self) -> str:
        return "Non riesco a collegarmi a OpenRouter. Controlla la connessione a Internet."

    def _messaggio_http(self, stato: int, dettaglio: str) -> str:
        spiegazioni = {
            401: "OpenRouter ha rifiutato la chiave: controlla LLM_API_KEY in .env.",
            402: "Il credito OpenRouter è esaurito.",
            403: "OpenRouter ha rifiutato la richiesta (accesso negato o contenuto non ammesso).",
            404: f"OpenRouter non conosce il modello «{self._modello}»: controlla LLM_MODEL.",
            408: "OpenRouter non ha risposto in tempo.",
            429: "OpenRouter ha raggiunto il limite di richieste: riprova fra poco.",
        }
        if stato in spiegazioni:
            return spiegazioni[stato]
        if stato >= 500:
            return "OpenRouter non è disponibile in questo momento. Riprova fra poco."
        extra = f" ({dettaglio})" if dettaglio else ""
        return f"OpenRouter ha rifiutato la richiesta (stato {stato}){extra}."


def crea_client(configurazione: ConfigLLM, **politica: Any) -> LLMClient:
    """Il client del provider scelto in `.env` (`LLM_PROVIDER`), con modello e timeout.

    `politica` (attese, pausa, orologio) serve solo ai test.

    Raises:
        LLMError: provider sconosciuto, o OpenRouter senza chiave.
    """
    if configurazione.provider == "ollama":
        return ClientOllama(
            configurazione.modello, configurazione.timeout, configurazione.ollama_url, **politica
        )
    if configurazione.provider == "openrouter":
        return ClientOpenRouter(
            configurazione.modello,
            configurazione.timeout,
            configurazione.api_key,
            **politica,
        )
    raise LLMError(f"Provider «{configurazione.provider}» sconosciuto: usa ollama o openrouter.")
