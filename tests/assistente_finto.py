"""Riepiloghi e raccolti in memoria per la pagina Assistente AI (M6-T6).

Con l'anagrafica e le ispezioni di `anagrafica_finta.py` e il client di `llm_fake.py` la pagina
usa il servizio vero (`genera_riepilogo_ispezione`: contesto, validazione, tentativo correttivo,
salvataggio) senza database e senza rete. Le stesse regole sul database vero sono provate in
`test_riepiloghi_repository.py` e `test_servizi_assistente_storico.py` (integration).
"""

from __future__ import annotations

import json
from datetime import datetime

RISPOSTA_CON_MARKDOWN = json.dumps(
    {
        "stato_salute": "critico",
        "elementi_rilevati": ["covata **a mosaico**", "regina non vista"],
        "criticita": [
            {"descrizione": "varroa alta sul vassoio", "gravita": "alta"},
            {"descrizione": "scorte scarse", "gravita": "media"},
        ],
        "azioni_suggerite": [
            {"azione": "nutrire con sciroppo", "priorita": "bassa", "entro_giorni": None},
            {"azione": "trattare contro la varroa", "priorita": "alta", "entro_giorni": 3},
            {"azione": "ricontrollare la regina", "priorita": "media", "entro_giorni": 7},
        ],
        "confidenza": "bassa",
        "campi_non_deducibili": ["peso dell'arnia", "[link](http://esempio.test)"],
    },
    ensure_ascii=False,
)


RISPOSTA_SENZA_ELENCHI = json.dumps(
    {
        "stato_salute": "buono",
        "elementi_rilevati": [],
        "criticita": [],
        "azioni_suggerite": [],
        "confidenza": "alta",
        "campi_non_deducibili": [],
    }
)


class RiepiloghiInMemoria:
    """Come `RiepiloghiRepository`: salva, elenco dal più recente, ultimo."""

    def __init__(self) -> None:
        self.righe: list[dict] = []
        self.errore_salvataggio: Exception | None = None
        self.errore_lettura: Exception | None = None

    def salva(self, utente_id: int, ispezione_id: int, **campi) -> int:
        if self.errore_salvataggio:
            raise self.errore_salvataggio
        nuovo = len(self.righe) + 1
        riepilogo = campi.pop("riepilogo")
        self.righe.append(
            {
                "id": nuovo,
                "utente_id": utente_id,
                "ispezione_id": ispezione_id,
                "riepilogo_json": json.loads(json.dumps(riepilogo)),
                "creato_il": datetime(2026, 11, 8, 9, nuovo),
                **campi,
            }
        )
        return nuovo

    def elenco(self, utente_id: int, ispezione_id: int, limite: int = 20) -> list[dict]:
        if self.errore_lettura:
            raise self.errore_lettura
        scelte = [
            r
            for r in self.righe
            if r["utente_id"] == utente_id and r["ispezione_id"] == ispezione_id
        ]
        return list(reversed(scelte))[:limite]

    def ultimo(self, utente_id: int, ispezione_id: int) -> dict | None:
        righe = self.elenco(utente_id, ispezione_id, limite=1)
        return righe[0] if righe else None


class RaccoltiVuoti:
    def per_apiario(self, utente_id: int, apiario_id: int) -> list:
        return []
