"""Dati e repository finti per i test dell'AI: nessun database, nessuna rete.

Usati da `test_assistente.py` e da `test_ai_offline.py`. Sono dati di prova scritti a mano, non
estratti da nessun database reale.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from beewatch.ai.assistant import ContestoIspezione
from beewatch.models import (
    Alveare,
    Apiario,
    Ispezione,
    LivelloRischio,
    Raccolto,
    StatoAlveare,
    TipoMiele,
)

RISPOSTA = json.dumps(
    {
        "stato_salute": "attenzione",
        "elementi_rilevati": ["covata a macchie"],
        "criticita": [{"descrizione": "covata a macchie", "gravita": "media"}],
        "azioni_suggerite": [
            {"azione": "ricontrollare tra una settimana", "priorita": "media", "entro_giorni": 7}
        ],
        "confidenza": "media",
        "campi_non_deducibili": ["causa della covata a macchie"],
    },
    ensure_ascii=False,
)
NOTA = "Covata a macchie su due telaini, regina vista. NOTA-SEGRETA-777"


def ispezione(id_: int, giorno: date, note: str | None = "una nota", **extra) -> Ispezione:
    base = {
        "alveare_id": 5,
        "data_ispezione": giorno,
        "livello_rischio": LivelloRischio.MEDIO,
        "peso_kg": Decimal("23.70"),
        "telaini_covata": 4,
        "telaini_scorte": 3,
        "regina_vista": True,
        "sciamatura": False,
    }
    return Ispezione(id=id_, note=note, **{**base, **extra})


ALVEARE = Alveare(
    apiario_id=2,
    codice="A3",
    stato=StatoAlveare.IN_OSSERVAZIONE,
    data_installazione=date(2024, 3, 1),
    anno_regina=2024,
    id=5,
)
APIARIO = Apiario(
    utente_id=1,
    nome="Collina",
    localita="Frazione Segreta",
    latitudine=Decimal("45.123456"),
    longitudine=Decimal("9.654321"),
    id=2,
)


def raccolto(id_: int, giorno: date, kg: str = "10.0", alveare_id=None) -> Raccolto:
    return Raccolto(
        apiario_id=2,
        tipo_miele=TipoMiele.ACACIA,
        data_raccolto=giorno,
        quantita_kg=Decimal(kg),
        alveare_id=alveare_id,
        id=id_,
    )


def contesto(**extra) -> ContestoIspezione:
    base = {
        "apiario": "Collina",
        "alveare": ALVEARE,
        "ispezione": ispezione(12, date(2026, 5, 16), NOTA),
        "precedenti": (),
        "raccolti": (),
    }
    return ContestoIspezione(**{**base, **extra})


class IspezioniFinte:
    def __init__(self, elenco: list[Ispezione]):
        self.elenco = elenco
        self.richieste: list[tuple] = []

    def trova(self, utente_id, ispezione_id):
        self.richieste.append(("trova", utente_id, ispezione_id))
        return next((i for i in self.elenco if i.id == ispezione_id), None)

    def ispezioni_per_alveare(self, utente_id, alveare_id):
        self.richieste.append(("per_alveare", utente_id, alveare_id))
        return sorted(
            (i for i in self.elenco if i.alveare_id == alveare_id),
            key=lambda i: (i.data_ispezione, i.id),
            reverse=True,
        )


class AlveariFinti:
    def __init__(self, alveare=ALVEARE):
        self.alveare = alveare

    def trova(self, utente_id, alveare_id):
        return self.alveare if self.alveare and self.alveare.id == alveare_id else None


class ApiariFinti:
    def __init__(self, apiario=APIARIO):
        self.apiario = apiario

    def trova(self, utente_id, apiario_id):
        return self.apiario


class RaccoltiFinti:
    def __init__(self, elenco: list[Raccolto]):
        self.elenco = elenco

    def per_apiario(self, utente_id, apiario_id):
        return sorted(self.elenco, key=lambda r: (r.data_raccolto, r.id), reverse=True)


class RiepiloghiFinti:
    def __init__(self, errore: Exception | None = None):
        self.salvati: list[dict] = []
        self.errore = errore

    def salva(self, utente_id, ispezione_id, **campi):
        if self.errore:
            raise self.errore
        self.salvati.append({"utente_id": utente_id, "ispezione_id": ispezione_id, **campi})
        return 100 + len(self.salvati)

    def ultimo(self, utente_id, ispezione_id):
        return {"id": 101, "chiesto": (utente_id, ispezione_id)}


STORIA = [
    ispezione(10, date(2026, 3, 28), "Invernamento riuscito"),
    ispezione(11, date(2026, 4, 20), "Ripresa regolare"),
    ispezione(12, date(2026, 5, 16), NOTA),
    ispezione(13, date(2026, 6, 20), "Dopo: non deve comparire"),  # successiva
]
