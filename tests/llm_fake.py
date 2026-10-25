"""Un client LLM finto per i test: risponde con testi (o errori) decisi dal test, senza rete.

Non è un mock di `requests`: sostituisce direttamente `LLMClient`, così i test del parser,
dell'assistente e del servizio non toccano né la rete né la chiave API
(e non leggono il `.env` dell'utente).
"""

from __future__ import annotations

from dataclasses import dataclass

from beewatch.ai.llm import LLMClient, RispostaLLM
from beewatch.exceptions import LLMError


@dataclass
class Chiamata:
    sistema: str
    utente: str
    temperatura: float
    massimo_token: int | None
    risposta_json: bool


class LLMFinto(LLMClient):
    """Restituisce in ordine le risposte date: una stringa è il testo, un'eccezione viene sollevata.

    Esaurite le risposte, l'ultima si ripete: un test che chiama più del previsto lo vede da
    `chiamate`, non da un errore oscuro.
    """

    provider = "finto"

    def __init__(
        self,
        risposte: list[str | Exception],
        *,
        modello: str = "modello-finto",
        token: tuple[int, int] | None = (100, 50),
    ) -> None:
        super().__init__(modello, timeout=1)
        if not risposte:
            raise ValueError("serve almeno una risposta")
        self._risposte = list(risposte)
        self._token = token
        self.chiamate: list[Chiamata] = []

    def _completa(
        self,
        sistema: str,
        utente: str,
        temperatura: float,
        massimo_token: int | None,
        risposta_json: bool,
    ) -> RispostaLLM:
        self.chiamate.append(Chiamata(sistema, utente, temperatura, massimo_token, risposta_json))
        indice = min(len(self.chiamate), len(self._risposte)) - 1
        voce = self._risposte[indice]
        if isinstance(voce, Exception):
            raise voce
        prompt, risposta = self._token if self._token else (None, None)
        return RispostaLLM(
            testo=voce,
            provider=self.provider,
            modello=self._modello,
            durata_ms=0,
            token_prompt=prompt,
            token_risposta=risposta,
        )

    def _messaggio_connessione(self) -> str:
        return "client finto: nessuna connessione"

    def _messaggio_http(self, stato: int, dettaglio: str) -> str:
        return f"client finto: HTTP {stato}"


__all__ = ["Chiamata", "LLMError", "LLMFinto"]
