"""Test del predittore, M4-T7: caricamento controllato, previsioni identiche, intervallo.

Unitari, sull'artefatto sintetico di `conftest.py` (un modello vero) e su copie rovinate di
proposito: file assenti, metadati incompleti, sha256 diverso, feature diverse, scikit-learn
diverso. In fondo, il modello committato in `models/`: si carica, descrive i dati ufficiali e
prevede i valori fissati.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import joblib
import numpy as np
import pandas as pd
import pytest

from beewatch.etl import extract, transform
from beewatch.exceptions import ModelError
from beewatch.ml import predictor
from beewatch.ml.artefatto import (
    COMANDO_ADDESTRAMENTO,
    impronta_pannello,
    percorso_metadati,
    sha256_file,
)
from beewatch.ml.features import FEATURE, TARGET, costruisci_feature_storiche
from beewatch.ml.predictor import Predittore, Stima

RADICE = Path(__file__).resolve().parents[1]
LOGGER = "beewatch.ml.predictor"


def ingressi(dati: pd.DataFrame) -> pd.DataFrame:
    return costruisci_feature_storiche(dati)[list(FEATURE)]


def riscrivi_json(percorso: Path, modifica) -> None:
    metadati = json.loads(percorso_metadati(percorso).read_text(encoding="utf-8"))
    modifica(metadati)
    percorso_metadati(percorso).write_text(json.dumps(metadati), encoding="utf-8")


def sostituisci_joblib(percorso: Path, contenuto: bytes) -> None:
    """Cambia il .joblib e aggiorna lo sha256 nel .json: il file è «coerente», ma sbagliato."""
    percorso.write_bytes(contenuto)

    def aggiorna(metadati: dict) -> None:
        metadati["file"]["sha256_joblib"] = sha256_file(percorso)

    riscrivi_json(percorso, aggiorna)


# --------------------------------------------------------------------------- #
# Caricamento
# --------------------------------------------------------------------------- #


def test_il_predittore_carica_il_modello_e_i_suoi_metadati(artefatto_sintetico) -> None:
    p = Predittore(artefatto_sintetico.percorso)

    assert p.versione == "v0.0.1-prova"
    assert p.feature == tuple(FEATURE)
    assert p.metadati == artefatto_sintetico.metadati
    assert p.percorso == artefatto_sintetico.percorso


def test_senza_argomenti_il_percorso_viene_dalla_configurazione(
    artefatto_sintetico, monkeypatch: pytest.MonkeyPatch
) -> None:
    configurazione = SimpleNamespace(percorso_modello=artefatto_sintetico.percorso)
    monkeypatch.setattr(predictor, "ottieni", lambda: configurazione)
    assert Predittore().versione == "v0.0.1-prova"


def test_a_ogni_caricamento_si_scrive_una_riga_info(artefatto_sintetico, caplog) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER):
        Predittore(artefatto_sintetico.percorso)

    righe = [
        r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelno == logging.INFO
    ]
    assert len(righe) == 1 and "Modello v0.0.1-prova caricato" in righe[0]


def test_senza_il_joblib_lerrore_dice_come_addestrare(copia_artefatto: Path) -> None:
    copia_artefatto.unlink()
    with pytest.raises(ModelError, match="non è stato trovato") as errore:
        Predittore(copia_artefatto)
    assert COMANDO_ADDESTRAMENTO in str(errore.value)


def test_senza_il_json_il_modello_non_si_carica(copia_artefatto: Path) -> None:
    percorso_metadati(copia_artefatto).unlink()
    with pytest.raises(ModelError, match="Mancano i metadati"):
        Predittore(copia_artefatto)


def test_un_joblib_diverso_dai_metadati_e_rifiutato(copia_artefatto: Path) -> None:
    contenuto = bytearray(copia_artefatto.read_bytes())
    contenuto[-1] ^= 0xFF  # un solo bit cambiato: lo sha256 non torna più
    copia_artefatto.write_bytes(bytes(contenuto))

    with pytest.raises(ModelError, match="non corrisponde ai suoi metadati"):
        Predittore(copia_artefatto)


def test_un_file_che_non_si_puo_caricare_e_un_model_error(copia_artefatto: Path) -> None:
    sostituisci_joblib(copia_artefatto, b"questo non e' un pickle")
    with pytest.raises(ModelError, match="non si può caricare") as errore:
        Predittore(copia_artefatto)
    assert COMANDO_ADDESTRAMENTO in str(errore.value)


def test_un_oggetto_che_non_e_una_pipeline_e_rifiutato(
    copia_artefatto: Path, tmp_path: Path
) -> None:
    altro = tmp_path / "altro.joblib"
    joblib.dump({"non": "una pipeline"}, altro)
    sostituisci_joblib(copia_artefatto, altro.read_bytes())

    with pytest.raises(ModelError, match="non contiene una Pipeline"):
        Predittore(copia_artefatto)


def test_feature_dei_metadati_diverse_da_quelle_del_modello_sono_rifiutate(
    copia_artefatto: Path,
) -> None:
    riscrivi_json(copia_artefatto, lambda m: m.update(feature=list(reversed(m["feature"]))))
    with pytest.raises(ModelError, match="non coincidono"):
        Predittore(copia_artefatto)


def test_se_il_codice_cambia_le_feature_senza_riaddestrare_si_ferma_al_caricamento(
    artefatto_sintetico, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(predictor, "FEATURE", {**FEATURE, "nuova_feature": "aggiunta dopo"})
    with pytest.raises(ModelError, match="non coincidono") as errore:
        Predittore(artefatto_sintetico.percorso)
    assert COMANDO_ADDESTRAMENTO in str(errore.value)


def test_una_versione_diversa_di_scikit_learn_avvisa_ma_carica(
    copia_artefatto: Path, caplog
) -> None:
    riscrivi_json(copia_artefatto, lambda m: m["ambiente"].update({"scikit-learn": "0.0.1"}))

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        p = Predittore(copia_artefatto)

    avvisi = [
        r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelno == logging.WARNING
    ]
    assert len(avvisi) == 1 and "scikit-learn 0.0.1" in avvisi[0]
    assert p.versione == "v0.0.1-prova"  # non si è fermato


def test_con_la_stessa_versione_di_scikit_learn_non_ce_nessun_avviso(
    artefatto_sintetico, caplog
) -> None:
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        Predittore(artefatto_sintetico.percorso)
    assert [r for r in caplog.records if r.name == LOGGER and r.levelno >= logging.WARNING] == []


# --------------------------------------------------------------------------- #
# Previsioni
# --------------------------------------------------------------------------- #


def test_il_modello_ricaricato_produce_predizioni_identiche(artefatto_sintetico) -> None:
    x = ingressi(artefatto_sintetico.dati)

    previsto = Predittore(artefatto_sintetico.percorso).prevedi(x)

    np.testing.assert_array_equal(previsto, artefatto_sintetico.modello.predict(x))
    assert previsto.dtype == "float64" and len(previsto) == len(x)


def test_colonne_in_piu_o_in_altro_ordine_non_cambiano_la_previsione(artefatto_sintetico) -> None:
    x = ingressi(artefatto_sintetico.dati)
    p = Predittore(artefatto_sintetico.percorso)

    rimescolato = x[list(reversed(x.columns))].assign(altro="x", numero_colonie=1)

    np.testing.assert_array_equal(p.prevedi(rimescolato), p.prevedi(x))


def test_i_valori_storici_mancanti_si_completano_senza_errore(artefatto_sintetico) -> None:
    p = Predittore(artefatto_sintetico.percorso)
    riga = ingressi(artefatto_sintetico.dati).iloc[[0]].copy()
    riga[["resa_anno_prima", "resa_media_3_anni_prima", "colonie_anno_prima"]] = np.nan

    previsto = p.prevedi(riga)

    assert np.isfinite(previsto).all()


def test_colonne_mancanti_sono_un_errore_che_le_elenca(artefatto_sintetico) -> None:
    p = Predittore(artefatto_sintetico.percorso)
    x = ingressi(artefatto_sintetico.dati).drop(columns=["anno", "resa_anno_prima"])

    with pytest.raises(ModelError, match="mancano le colonne: anno, resa_anno_prima"):
        p.prevedi(x)


@pytest.mark.parametrize("colonna", ["codice_stato", "anno"])
def test_senza_stato_o_anno_non_si_prevede(artefatto_sintetico, colonna: str) -> None:
    p = Predittore(artefatto_sintetico.percorso)
    x = ingressi(artefatto_sintetico.dati).iloc[[0]].copy().astype({colonna: "object"})
    x.loc[x.index[0], colonna] = None

    with pytest.raises(ModelError, match="lo stato e l'anno"):
        p.prevedi(x)


# --------------------------------------------------------------------------- #
# Stima con intervallo
# --------------------------------------------------------------------------- #


def test_la_stima_somma_alla_previsione_i_limiti_dei_metadati(artefatto_sintetico) -> None:
    p = Predittore(artefatto_sintetico.percorso)
    riga = ingressi(artefatto_sintetico.dati).iloc[-1].to_dict()
    intervallo = artefatto_sintetico.metadati["intervallo"]

    stima = p.stima(riga)

    assert isinstance(stima, Stima)
    assert stima.valore_kg == pytest.approx(float(p.prevedi(pd.DataFrame([riga]))[0]))
    assert stima.inferiore_kg == pytest.approx(stima.valore_kg + intervallo["inferiore_kg"])
    assert stima.superiore_kg == pytest.approx(stima.valore_kg + intervallo["superiore_kg"])
    assert stima.livello == 0.8
    assert stima.inferiore_kg <= stima.valore_kg <= stima.superiore_kg


def test_lintervallo_contiene_sempre_il_valore_centrale(copia_artefatto: Path) -> None:
    """Con limiti strani nei metadati (entrambi positivi) la stima resta dentro l'intervallo."""
    riscrivi_json(
        copia_artefatto,
        lambda m: m["intervallo"].update({"inferiore_kg": 2.0, "superiore_kg": 5.0}),
    )
    p = Predittore(copia_artefatto)
    dati = pd.DataFrame(
        [{"codice_stato": "AA", "anno": 2013, "resa_anno_prima": 20.0,
          "resa_media_3_anni_prima": 21.0, "colonie_anno_prima": 5000.0}]
    )  # fmt: skip
    stima = p.stima(dati.iloc[0].to_dict())

    assert stima.inferiore_kg == stima.valore_kg  # il limite inferiore non supera il centro
    assert stima.superiore_kg == pytest.approx(stima.valore_kg + 5.0)


# --------------------------------------------------------------------------- #
# Il modello committato in models/
# --------------------------------------------------------------------------- #

PERCORSO_COMMITTATO = RADICE / "models" / "produzione_v1.joblib"
DATASET = RADICE / "data" / "honeyproduction.csv"


@pytest.fixture(scope="module")
def committato() -> Predittore:
    return Predittore(PERCORSO_COMMITTATO)


def test_il_modello_committato_si_carica_e_descrive_la_versione_v1(committato: Predittore) -> None:
    assert committato.versione == "v1.0.0"
    assert committato.feature == tuple(FEATURE)
    assert committato.metadati["algoritmo"] == "RandomForestRegressor"
    assert committato.metadati["iperparametri"] == {
        "n_estimators": 200, "max_depth": None, "min_samples_leaf": 5, "random_state": 42
    }  # fmt: skip
    assert committato.metadati["ambiente"]["scikit-learn"].startswith("1.9")  # la serie bloccata


def test_i_metadati_committati_hanno_le_metriche_della_model_card(committato: Predittore) -> None:
    metriche = committato.metadati["metriche"]
    hold_out = metriche["hold_out_2010_2012"]

    assert hold_out["righe"] == 120 and hold_out["addestramento_fino_al"] == 2009
    assert hold_out["mae_kg"] == pytest.approx(3.498627342552852, abs=1e-9)
    assert hold_out["rmse_kg"] == pytest.approx(4.4826, abs=5e-5)
    assert hold_out["r2"] == pytest.approx(0.6236, abs=5e-5)
    criterio = metriche["criterio_da05"]
    assert criterio["persistenza_mae_kg"] == pytest.approx(4.0634283333333325, abs=1e-9)
    assert (
        criterio["soddisfatto"] is True
        and criterio["modello_mae_kg"] < criterio["persistenza_mae_kg"]
    )
    assert metriche["cross_validation"]["mae_kg"]["media"] == pytest.approx(4.0883, abs=5e-5)
    intervallo = committato.metadati["intervallo"]
    assert intervallo["inferiore_kg"] == pytest.approx(-5.7137, abs=5e-5)
    assert intervallo["superiore_kg"] == pytest.approx(6.5840, abs=5e-5)
    assert intervallo["livello"] == 0.8 and intervallo["residui"] == 360
    importanza = committato.metadati["importanza_variabili"]["valori"]
    assert max(importanza, key=lambda f: importanza[f]["media_kg"]) == "resa_media_3_anni_prima"


def test_i_metadati_committati_descrivono_il_dataset_ufficiale(committato: Predittore) -> None:
    """L'impronta del pannello nei metadati è quella di Q8 ricavato dal CSV ufficiale."""
    puliti, _ = transform(extract(DATASET), anno_corrente=2026)
    puliti = puliti[["codice_stato", "anno", "numero_colonie", TARGET]]
    completi = puliti.groupby("codice_stato").filter(lambda g: len(g) == 15)

    dataset = committato.metadati["dataset"]

    assert (dataset["righe"], dataset["stati"]) == (600, 40)
    assert (dataset["anno_minimo"], dataset["anno_massimo"]) == (1998, 2012)
    assert dataset["sha256_pannello"] == impronta_pannello(completi)
    assert dataset["sha256_csv_ufficiale"] == sha256_file(DATASET)


# Ottenuti dal modello committato (v1.0.0, addestrato con scikit-learn 1.9.0) per le tre righe
# del test qui sotto: CA e ND con storia completa, AL senza media né colonie (primo anno).
PREVISIONI_FISSATE = [21.36016165723675, 27.335626400867085, 25.009461794391783]


def test_il_modello_committato_prevede_i_valori_fissati(committato: Predittore) -> None:
    """Se cambia il modello, o scikit-learn lo legge in modo diverso, questo test lo dice."""
    righe = pd.DataFrame(
        [
            {"codice_stato": "CA", "anno": 2013, "resa_anno_prima": 20.0,
             "resa_media_3_anni_prima": 22.0, "colonie_anno_prima": 300_000.0},
            {"codice_stato": "ND", "anno": 2013, "resa_anno_prima": 30.0,
             "resa_media_3_anni_prima": 28.0, "colonie_anno_prima": 470_000.0},
            {"codice_stato": "AL", "anno": 2013, "resa_anno_prima": 30.0,
             "resa_media_3_anni_prima": None, "colonie_anno_prima": None},
        ]
    )  # fmt: skip

    previsto = committato.prevedi(righe)

    np.testing.assert_allclose(previsto, PREVISIONI_FISSATE, atol=1e-6)
