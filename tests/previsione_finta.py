"""Dati USDA, predittore e previsioni finti per la pagina Previsione (M6-T5).

Servono ai test dell'interfaccia, senza database e senza il file del modello. Le regole vere del
servizio (feature costruite dalla storia, arrotondamenti, regola dell'intervallo, salvataggio) le
applica `Servizi`, che qui è quello vero; i test con MySQL e il modello committato sono in
`test_services.py` e `test_app_database.py`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from beewatch.exceptions import ModelError
from beewatch.ml.features import FEATURE
from beewatch.ml.predictor import Stima
from beewatch.models import Previsione

ANNI = range(1998, 2013)
# California sulla trentina di chili per colonia, North Dakota sulla cinquantina.
RESE = {
    "CA": {anno: 30.0 + (anno % 3) for anno in ANNI},
    "ND": {anno: 50.0 + (anno % 4) for anno in ANNI},
}
COLONIE = {"CA": 400_000, "ND": 450_000}
NOMI = {"CA": "California", "ND": "North Dakota"}


class ProduzioneFinta:
    """Due stati con la serie completa 1998–2012 (il pannello di addestramento)."""

    def __init__(
        self, vuota: bool = False, errore: Exception | None = None, senza_pannello: bool = False
    ) -> None:
        self.vuota = vuota  # nessun dato USDA
        self.errore = errore
        self.senza_pannello = senza_pannello  # gli stati ci sono, il pannello di addestramento no

    def _prova(self) -> None:
        if self.errore:
            raise self.errore

    def stati_del_pannello(self) -> list[dict]:
        self._prova()
        if self.vuota:
            return []
        return [
            {"codice": c, "nome": NOMI[c], "primo_anno": 1998, "ultimo_anno": 2012}
            for c in sorted(NOMI, key=NOMI.get)
        ]

    def serie_storica_stato(self, codice_stato: str) -> list[dict]:
        self._prova()
        return [
            {"anno": a, "resa_per_colonia_kg": Decimal(str(r)),
             "numero_colonie": COLONIE[codice_stato]}
            for a, r in sorted(RESE[codice_stato].items())
        ]  # fmt: skip

    def dati_addestramento(self) -> list[dict]:
        self._prova()
        if self.vuota or self.senza_pannello:
            return []
        return [
            {"codice_stato": c, "anno": a, "numero_colonie": COLONIE[c] + a,
             "resa_per_colonia_kg": Decimal(str(r))}
            for c in NOMI
            for a, r in RESE[c].items()
        ]  # fmt: skip


class PredittoreFinto:
    """Prevede la resa media dei 3 anni prima; la banda viene dal costruttore."""

    versione = "v-finto"
    percorso = Path("models/finto.joblib")

    def __init__(
        self, inferiore: float = -3.0, superiore: float = 4.0, errore: Exception | None = None
    ) -> None:
        self.inferiore, self.superiore, self.errore = inferiore, superiore, errore
        self.ricevute: list[dict] = []
        self.metadati: dict[str, Any] = {
            "metriche": {
                "hold_out_2010_2012": {"mae_kg": 3.5, "rmse_kg": 4.5, "r2": 0.62},
                "cross_validation": {"mae_kg": {"media": 4.1, "dev_std": 0.1}},
                "baseline_hold_out": {
                    "media globale": {"mae_kg": 6.7},
                    "persistenza (resa dell'anno prima)": {"mae_kg": 4.1},
                },
            },
            "versione": "v-finto",
            "algoritmo": "RandomForestRegressor",
            "addestrato_il": "2026-10-23T12:00:00+00:00",
            "addestramento": {"righe": 600, "strategia": "prova"},
            "feature": list(FEATURE),
            "importanza_variabili": {"valori": {n: {"media_kg": 0.1} for n in FEATURE}},
        }

    def stima(self, riga: dict) -> Stima:
        if self.errore:
            raise self.errore
        self.ricevute.append(dict(riga))
        valore = float(riga["resa_media_3_anni_prima"])
        return Stima(valore, valore + self.inferiore, valore + self.superiore, 0.8)


FEATURE_INCOMPATIBILI = ModelError(
    "Per prevedere mancano le colonne: temperatura_media. Il modello v-finto usa: codice_stato, "
    "anno, temperatura_media."
)


class PrevisioniInMemoria:
    """Le previsioni salvate, come `PrevisioniRepository` (righe di Q9, dalla più recente)."""

    def __init__(self, codici_alveari: dict[int, str] | None = None) -> None:
        self.codici_alveari = codici_alveari or {}
        self.salvate: list[Previsione] = []
        self.errore: Exception | None = None

    def salva_previsione(self, previsione: Previsione) -> Previsione:
        salvata = Previsione(**{**previsione.__dict__, "id": len(self.salvate) + 1})
        self.salvate.append(salvata)
        return salvata

    def ultime_previsioni(
        self, utente_id: int, limite: int = 20, alveare_id: int | None = None
    ) -> list[dict]:
        if self.errore:
            raise self.errore
        scelte = [
            p for p in self.salvate
            if p.utente_id == utente_id and alveare_id in (None, p.alveare_id)
        ]  # fmt: skip
        return [
            {
                "id": p.id,
                "creato_il": datetime(2026, 11, 8, 10, p.id),
                "alveare_id": p.alveare_id,
                "alveare": self.codici_alveari.get(p.alveare_id),
                "codice_stato_riferimento": p.codice_stato_riferimento,
                "anno_riferimento": p.anno_riferimento,
                # come MySQL: DECIMAL(6, 2), quindi Decimal con due cifre
                "stima_kg": Decimal(p.stima_kg).quantize(Decimal("0.01")),
                "limite_inferiore_kg": Decimal(p.limite_inferiore_kg).quantize(Decimal("0.01")),
                "limite_superiore_kg": Decimal(p.limite_superiore_kg).quantize(Decimal("0.01")),
                "feature_json": p.feature,
                "versione": p.versione_modello,
                "algoritmo": "RandomForestRegressor",
                "mae_kg": Decimal("3.5"),
            }
            for p in reversed(scelte)
        ][:limite]


class ModelliFinti:
    def __init__(self) -> None:
        self.registrati: list[dict] = []

    def trova(self, versione: str):
        return {"versione": versione} if self.registrati else None

    def registra(self, riga: dict) -> None:
        self.registrati.append(riga)
