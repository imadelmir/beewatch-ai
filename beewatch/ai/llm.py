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
- **Ogni errore diventa un `LLMError`** con un messaggio in italiano che dice cosa fare. La chiave
  API non compare mai in un messaggio né nel log; del testo inviato si registra solo la lunghezza
  (le note di ispezione sono dati dell'utente).
- Formati verificati sulla documentazione ufficiale (ottobre 2026): Ollama `POST /api/chat`
  (<https://docs.ollama.com/api/chat>) e OpenRouter `POST /api/v1/chat/completions`
  (<https://openrouter.ai/docs/api-reference/chat-completion>).

Robustezza (timeout, nuovi tentativi, limite di richieste) è di M5-T2: qui una richiesta, un
tentativo.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Any

import requests

from beewatch.config import OLLAMA_URL_PREDEFINITO, ConfigLLM
from beewatch.exceptions import LLMError
from beewatch.logging_config import ottieni_logger

logger = ottieni_logger(__name__)

URL_OPENROUTER = "https://openrouter.ai/api/v1"
SECONDI_CONNESSIONE = 10  # massimo per aprire la connessione; per rispondere vale LLM_TIMEOUT


@dataclass(frozen=True)
class RispostaLLM:
    """Ciò che il modello ha risposto e come: i campi coincidono con le colonne di `messaggi`."""

    testo: str
    provider: str
    modello: str
    durata_ms: int
    token_prompt: int | None  # None se il provider non li dichiara
    token_risposta: int | None


class LLMClient(ABC):
    """Un provider di modelli di linguaggio dietro `completa`."""

    provider: str

    def __init__(self, modello: str, timeout: int) -> None:
        self._modello = modello
        self._timeout = timeout

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
            LLMError: il provider non risponde, rifiuta la richiesta o risponde in un formato
                inatteso.
        """
        inizio = time.perf_counter()
        risposta = self._completa(sistema, utente, temperatura, massimo_token, risposta_json)
        durata_ms = round((time.perf_counter() - inizio) * 1000)
        risposta = replace(risposta, durata_ms=durata_ms)
        logger.info(
            "LLM %s/%s: %d ms, token %s→%s, richiesta di %d caratteri",
            risposta.provider,
            risposta.modello,
            risposta.durata_ms,
            risposta.token_prompt,
            risposta.token_risposta,
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
    # HTTP, in comune
    # ----------------------------------------------------------------------- #

    def _invia(
        self, url: str, corpo: dict[str, Any], intestazioni: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Un POST con corpo JSON; restituisce il JSON della risposta.

        Raises:
            LLMError: timeout, rete, stato HTTP di errore, risposta che non è un oggetto JSON.
        """
        try:
            risposta = requests.post(
                url,
                json=corpo,
                headers=intestazioni,
                timeout=(min(SECONDI_CONNESSIONE, self._timeout), self._timeout),
            )
        except requests.exceptions.Timeout as errore:
            raise LLMError(
                f"Il modello non ha risposto entro {self._timeout} secondi. "
                "Riprova, o aumenta LLM_TIMEOUT in .env."
            ) from errore
        except requests.exceptions.ConnectionError as errore:
            raise LLMError(self._messaggio_connessione()) from errore
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
            raise LLMError(self._messaggio_http(risposta.status_code, self._dettaglio(risposta)))
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

    def __init__(self, modello: str, timeout: int, url: str = OLLAMA_URL_PREDEFINITO) -> None:
        super().__init__(modello, timeout)
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

        dati = self._invia(f"{self._url}/api/chat", corpo)

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
        self, modello: str, timeout: int, api_key: str | None, url: str = URL_OPENROUTER
    ) -> None:
        super().__init__(modello, timeout)
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

        dati = self._invia(
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


def crea_client(configurazione: ConfigLLM) -> LLMClient:
    """Il client del provider scelto in `.env` (`LLM_PROVIDER`), con modello e timeout.

    Raises:
        LLMError: provider sconosciuto, o OpenRouter senza chiave.
    """
    if configurazione.provider == "ollama":
        return ClientOllama(
            configurazione.modello, configurazione.timeout, configurazione.ollama_url
        )
    if configurazione.provider == "openrouter":
        return ClientOpenRouter(
            configurazione.modello, configurazione.timeout, configurazione.api_key
        )
    raise LLMError(f"Provider «{configurazione.provider}» sconosciuto: usa ollama o openrouter.")
