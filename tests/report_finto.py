"""L'archivio dei report in memoria, con le regole di `ReportRepository` (M6-T12)."""

from __future__ import annotations

import json
from datetime import datetime

from beewatch.exceptions import ValidationError


class ReportInMemoria:
    def __init__(self) -> None:
        self.righe: dict[int, dict] = {}
        self.errore: Exception | None = None

    def _prova(self) -> None:
        if self.errore:
            raise self.errore

    def salva(self, utente_id, apiario_id, modello, titolo, contenuto) -> int:
        self._prova()
        nuovo = max(self.righe, default=0) + 1
        self.righe[nuovo] = {
            "id": nuovo, "utente_id": utente_id, "apiario_id": apiario_id, "modello": modello,
            "titolo": titolo, "contenuto_json": json.loads(json.dumps(contenuto)),
            "creato_il": datetime(2026, 11, 14, 10, nuovo),
        }  # fmt: skip
        return nuovo

    def elenco(self, utente_id: int, limite: int = 50) -> list[dict]:
        self._prova()
        dell_utente = [r for r in self.righe.values() if r["utente_id"] == utente_id]
        ordinati = sorted(dell_utente, key=lambda r: (r["creato_il"], r["id"]), reverse=True)
        return [{k: v for k, v in r.items() if k != "contenuto_json"} for r in ordinati][:limite]

    def trova(self, utente_id: int, report_id: int) -> dict | None:
        self._prova()
        riga = self.righe.get(report_id)
        return dict(riga) if riga and riga["utente_id"] == utente_id else None

    def elimina(self, utente_id: int, report_id: int) -> None:
        self._prova()
        if not self.trova(utente_id, report_id):
            raise ValidationError("Report non trovato.", campo="report_id")
        del self.righe[report_id]
