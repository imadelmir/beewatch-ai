"""Le preferenze dell'utente in memoria, come `PreferenzeRepository` (M6-T13)."""

from __future__ import annotations


class PreferenzeInMemoria:
    def __init__(self) -> None:
        self.righe: dict[int, dict] = {}
        self.errore: Exception | None = None

    def leggi(self, utente_id: int) -> dict | None:
        if self.errore:
            raise self.errore
        return dict(self.righe[utente_id]) if utente_id in self.righe else None

    def salva(self, utente_id: int, giorni: int, avvisi: bool, esterno: bool) -> None:
        if self.errore:
            raise self.errore
        self.righe[utente_id] = {
            "giorni_promemoria": giorni,
            "avvisi_rischio": avvisi,
            "assistente_esterno": esterno,
        }
