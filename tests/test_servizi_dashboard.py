"""I servizi della Dashboard: aggregati dell'apiario, metriche del modello, previsto/reale (M6-T7).

Unitari con anagrafica, raccolti e dati USDA in memoria. Le metriche si leggono dal file vero
`models/produzione_v1.json`, per provare che nessun numero è scritto nel codice. Con MySQL e il
modello committato: in fondo a `test_services.py` (integration).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from anagrafica_finta import anagrafica_di_prova, raccolti_di_prova
from previsione_finta import RESE, PredittoreFinto, ProduzioneFinta

from beewatch.exceptions import ValidationError
from beewatch.services import INTERO_APIARIO, MetricheModello, Servizi

METADATI = Path(__file__).resolve().parents[1] / "models" / "produzione_v1.json"


class PredittoreConIMetadatiVeri(PredittoreFinto):
    def __init__(self) -> None:
        super().__init__()
        self.metadati = json.loads(METADATI.read_text(encoding="utf-8"))
        self.versione = self.metadati["versione"]


def servizi(predittore=None) -> Servizi:
    apiari, alveari = anagrafica_di_prova()
    return Servizi(
        None,
        apiari=apiari,
        alveari=alveari,
        raccolti=raccolti_di_prova(apiari),
        produzione=ProduzioneFinta(),
        crea_predittore=lambda: predittore or PredittoreFinto(),
    )


# --------------------------------------------------------------------------- #
# Aggregati dell'apiario
# --------------------------------------------------------------------------- #


def test_i_kpi_dellapiario():
    dati = servizi().dashboard_apiario(1, 10)

    assert dati.numero_alveari == 2  # A1 e A2; A9 è eliminato
    assert dati.produzione_totale_kg == pytest.approx(102.5)  # 99 kg di un altro utente esclusi
    assert dati.media_per_alveare_kg == pytest.approx(51.25)
    assert dati.ultima_ispezione == date(2026, 10, 30)


def test_la_produzione_per_anno_tiene_separato_lintero_apiario():
    dati = servizi().dashboard_apiario(1, 10)

    assert dati.raccolti_per_anno.to_dict("records") == [
        {"anno": 2025, "alveare": "A1", "kg": 12.8},
        {"anno": 2025, "alveare": INTERO_APIARIO, "kg": 55.5},
        {"anno": 2026, "alveare": "Alveare eliminato", "kg": 5.0},
        {"anno": 2026, "alveare": INTERO_APIARIO, "kg": 29.2},
    ]


def test_la_distribuzione_mostra_anche_gli_alveari_senza_raccolti():
    per_alveare = servizi().dashboard_apiario(1, 10).per_alveare

    assert dict(zip(per_alveare["alveare"], per_alveare["kg"], strict=True)) == pytest.approx(
        {"A1": 12.8, "A2": 0.0, INTERO_APIARIO: 84.7, "Alveare eliminato": 5.0}
    )
    assert list(per_alveare["alveare"])[:2] == ["A1", "A2"]  # prima gli alveari, per codice


def test_un_apiario_vuoto_ha_kpi_onesti_e_tabelle_vuote():
    dati = servizi().dashboard_apiario(1, 11)  # «Valle»: nessun alveare, nessun raccolto

    assert (dati.numero_alveari, dati.produzione_totale_kg) == (0, 0.0)
    assert dati.media_per_alveare_kg is None and dati.ultima_ispezione is None
    assert dati.raccolti_per_anno.empty and list(dati.raccolti_per_anno.columns) == [
        "anno", "alveare", "kg",
    ]  # fmt: skip
    assert dati.per_alveare.empty


def test_lapiario_di_un_altro_utente_non_mostra_nulla():
    dati = servizi().dashboard_apiario(1, 20)

    assert dati.numero_alveari == 0 and dati.produzione_totale_kg == 0.0


@pytest.mark.parametrize(
    ("utente", "apiario", "campo"), [(0, 10, "utente_id"), (1, "10", "apiario_id")]
)
def test_gli_id_non_validi_si_rifiutano(utente, apiario, campo):
    with pytest.raises(ValidationError) as errore:
        servizi().dashboard_apiario(utente, apiario)
    assert errore.value.campo == campo


# --------------------------------------------------------------------------- #
# Metriche del modello, dal file
# --------------------------------------------------------------------------- #


def test_le_metriche_sono_quelle_del_file_dei_metadati():
    file = json.loads(METADATI.read_text(encoding="utf-8"))
    metriche_file = file["metriche"]

    m = servizi(PredittoreConIMetadatiVeri()).metriche_modello()

    assert isinstance(m, MetricheModello)
    assert m.versione == file["versione"] and m.algoritmo == file["algoritmo"]
    assert m.mae_kg == metriche_file["hold_out_2010_2012"]["mae_kg"]
    assert m.rmse_kg == metriche_file["hold_out_2010_2012"]["rmse_kg"]
    assert m.r2 == metriche_file["hold_out_2010_2012"]["r2"]
    assert m.cv_mae_kg == metriche_file["cross_validation"]["mae_kg"]["media"]
    migliore = min(metriche_file["baseline_hold_out"].items(), key=lambda b: b[1]["mae_kg"])
    assert (m.migliore_baseline, m.migliore_baseline_mae_kg) == (migliore[0], migliore[1]["mae_kg"])
    assert m.righe_addestramento == file["addestramento"]["righe"]


# --------------------------------------------------------------------------- #
# Previsto contro reale
# --------------------------------------------------------------------------- #


def test_il_confronto_ha_gli_ultimi_sei_anni_con_stima_banda_e_resa_vera():
    confronto = servizi().confronto_previsto_reale("ca")

    assert list(confronto["anno"]) == [2007, 2008, 2009, 2010, 2011, 2012]
    riga = confronto.iloc[-1]
    media_tre_anni = sum(RESE["CA"][a] for a in (2009, 2010, 2011)) / 3
    assert riga["previsto_kg"] == pytest.approx(round(media_tre_anni, 1))  # solo anni prima
    assert riga["inferiore_kg"] < riga["previsto_kg"] < riga["superiore_kg"]
    assert riga["reale_kg"] == RESE["CA"][2012]


def test_il_confronto_non_salva_nulla_e_rifiuta_uno_stato_ignoto():
    s = servizi()

    with pytest.raises(ValidationError) as errore:
        s.confronto_previsto_reale("TX")
    assert errore.value.campo == "codice_stato"
    assert isinstance(s.confronto_previsto_reale("ND"), pd.DataFrame)
