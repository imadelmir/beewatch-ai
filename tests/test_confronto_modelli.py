"""Test del confronto fra modelli, M4-T3: stessi campioni, nessun leakage, criterio DA-05.

Unitari: pannelli sintetici dove si sa che cosa deve succedere, e `Confronto`
costruiti a mano per il criterio. Integration: il pannello Q8 vero dal database
di test; i numeri sono quelli della model card (`docs/model_card.md`).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.pipeline import Pipeline

from beewatch.database import Database
from beewatch.exceptions import ModelError
from beewatch.ml.train import (
    ALBERO,
    MEDIA_GLOBALE,
    MEDIA_STATO,
    MEDIA_STATO_TREND,
    PERSISTENZA,
    RANDOM_FOREST,
    REGRESSIONE_LINEARE,
    SEED,
    TARGET,
    Confronto,
    carica_dataset_training,
    confronta_modelli,
    crea_modelli,
    dividi_temporale,
    metriche,
    soddisfa_criterio,
    valuta_baseline,
)

MODELLI = (REGRESSIONE_LINEARE, ALBERO, RANDOM_FOREST)
BASELINE = (MEDIA_GLOBALE, MEDIA_STATO, MEDIA_STATO_TREND, PERSISTENZA)


def pannello_rumoroso(seme: int = 0) -> pd.DataFrame:
    """Sei stati, 1998-2012, livello diverso per stato, tendenza e rumore."""
    caso = np.random.default_rng(seme)
    righe = [
        {"codice_stato": s, "anno": a, "numero_colonie": 1000 * (i + 1) + a,
         TARGET: 30 + 5 * i - 0.5 * (a - 1998) + caso.normal(0, 3)}
        for i, s in enumerate(("AA", "BB", "CC", "DD", "EE", "FF"))
        for a in range(1998, 2013)
    ]  # fmt: skip
    return pd.DataFrame(righe)


def pannello_rette() -> pd.DataFrame:
    """Ogni stato su una retta: stato + anno bastano a prevederlo senza errore."""
    righe = [
        {"codice_stato": s, "anno": a, "numero_colonie": 5000, TARGET: base - 0.5 * (a - 2000)}
        for s, base in (("AA", 40.0), ("BB", 25.0), ("CC", 60.0))
        for a in range(2000, 2013)
    ]
    return pd.DataFrame(righe)


# --------------------------------------------------------------------------- #
# I modelli
# --------------------------------------------------------------------------- #


def test_tre_pipeline_con_lo_stesso_preprocessore_e_il_seed() -> None:
    modelli = crea_modelli()

    assert tuple(modelli) == MODELLI
    for pipeline in modelli.values():
        assert isinstance(pipeline, Pipeline) and list(pipeline.named_steps) == ["prep", "modello"]
    assert modelli[ALBERO].named_steps["modello"].random_state == SEED == 42
    assert modelli[RANDOM_FOREST].named_steps["modello"].random_state == SEED
    assert crea_modelli(7)[RANDOM_FOREST].named_steps["modello"].random_state == 7


# --------------------------------------------------------------------------- #
# Stessi campioni, stessa funzione
# --------------------------------------------------------------------------- #


def test_modelli_e_baseline_sono_misurati_sulle_stesse_righe_di_verifica() -> None:
    dati = pannello_rumoroso()
    _, verifica = dividi_temporale(dati)

    confronto = confronta_modelli(dati)

    assert list(confronto.verifica.index) == list(verifica.index)
    assert set(confronto.verifica["anno"]) == {2010, 2011, 2012}
    assert tuple(confronto.previsioni) == MODELLI + BASELINE
    assert {len(p) for p in confronto.previsioni.values()} == {len(verifica)}


def test_le_baseline_del_confronto_sono_quelle_di_m4_t1() -> None:
    dati = pannello_rumoroso()
    risultati = confronta_modelli(dati).risultati()
    assert {n: risultati[n] for n in BASELINE} == valuta_baseline(dati)


def test_le_metriche_vengono_dalla_funzione_comune() -> None:
    confronto = confronta_modelli(pannello_rumoroso())
    vero = confronto.verifica[TARGET]
    for nome, previsto in confronto.previsioni.items():
        assert confronto.risultati()[nome] == metriche(vero, previsto), nome


def test_le_metriche_per_anno_si_calcolano_sulle_righe_di_quellanno() -> None:
    confronto = confronta_modelli(pannello_rumoroso())
    per_anno = confronto.risultati_per_anno()

    for nome, previsto in confronto.previsioni.items():
        assert sorted(per_anno[nome]) == [2010, 2011, 2012]
        nel_2011 = (confronto.verifica["anno"] == 2011).to_numpy()
        attese = metriche(confronto.verifica.loc[nel_2011, TARGET], previsto[nel_2011])
        assert per_anno[nome][2011] == attese, nome


# --------------------------------------------------------------------------- #
# Nessuna informazione dal futuro, riproducibilità
# --------------------------------------------------------------------------- #


def test_i_modelli_non_vedono_la_resa_che_devono_prevedere() -> None:
    """Cambiare le rese del 2012 (ultimo anno, nessuno le usa come storia) non cambia nulla."""
    base = pannello_rumoroso()
    alterato = base.copy()
    alterato.loc[alterato["anno"] == 2012, TARGET] = 999.0

    prima, dopo = confronta_modelli(base), confronta_modelli(alterato)

    for nome in MODELLI:
        np.testing.assert_array_equal(prima.previsioni[nome], dopo.previsioni[nome], nome)


def test_la_resa_dellanno_prima_in_verifica_entra_come_nella_persistenza() -> None:
    """Le rese del 2010 sono storia per il 2011: cambiano le previsioni del 2011, non del 2010."""
    base = pannello_rumoroso()
    alterato = base.copy()
    alterato.loc[alterato["anno"] == 2010, TARGET] += 10.0

    prima, dopo = confronta_modelli(base), confronta_modelli(alterato)

    anni = prima.verifica["anno"].to_numpy()
    for nome in MODELLI:
        np.testing.assert_array_equal(prima.previsioni[nome][anni == 2010],
                                      dopo.previsioni[nome][anni == 2010])  # fmt: skip
    assert not np.array_equal(prima.previsioni[RANDOM_FOREST][anni == 2011],
                              dopo.previsioni[RANDOM_FOREST][anni == 2011])  # fmt: skip


def test_lo_stesso_seed_da_lo_stesso_confronto() -> None:
    dati = pannello_rumoroso()
    primo, secondo = confronta_modelli(dati), confronta_modelli(dati)
    for nome in MODELLI:
        np.testing.assert_array_equal(primo.previsioni[nome], secondo.previsioni[nome], nome)
    assert primo.risultati() == secondo.risultati()


def test_lingresso_non_viene_modificato() -> None:
    dati = pannello_rumoroso()
    copia = dati.copy()
    confronta_modelli(dati)
    pd.testing.assert_frame_equal(dati, copia)


def test_un_indice_ripetuto_e_un_errore() -> None:
    dati = pannello_rumoroso()
    dati.index = [0] * len(dati)
    with pytest.raises(ModelError, match="indice"):
        confronta_modelli(dati)


# --------------------------------------------------------------------------- #
# Criterio DA-05 sul confronto
# --------------------------------------------------------------------------- #


def test_sui_dati_in_retta_vince_la_regressione_lineare() -> None:
    confronto = confronta_modelli(pannello_rette())
    risultati = confronto.risultati()

    assert risultati[REGRESSIONE_LINEARE].mae_kg == pytest.approx(0.0, abs=1e-9)
    assert risultati[PERSISTENZA].mae_kg == pytest.approx(0.5)  # un anno di pendenza in ritardo
    assert confronto.vincitore() == REGRESSIONE_LINEARE


def confronto_a_mano(previsioni_modelli: dict[str, list[float]]) -> Confronto:
    verifica = pd.DataFrame({"anno": [2010, 2011], TARGET: [10.0, 20.0]})
    baseline = {
        MEDIA_GLOBALE: [15.0, 15.0],
        MEDIA_STATO: [12.0, 18.0],
        MEDIA_STATO_TREND: [11.0, 19.0],
        PERSISTENZA: [10.5, 19.5],  # MAE 0,5
    }
    previsioni = {n: np.array(p) for n, p in (previsioni_modelli | baseline).items()}
    return Confronto(verifica=verifica, previsioni=previsioni, modelli=tuple(previsioni_modelli))


def test_se_nessun_modello_batte_la_persistenza_non_ce_vincitore() -> None:
    confronto = confronto_a_mano({"a": [11.0, 21.0], "b": [10.5, 19.5]})  # MAE 1,0 e 0,5
    assert confronto.vincitore() is None  # 0,5 uguale alla persistenza: non basta


def test_vince_il_mae_piu_basso_fra_i_modelli_che_battono_la_persistenza() -> None:
    confronto = confronto_a_mano({"a": [10.4, 20.4], "b": [10.1, 20.1], "c": [13.0, 20.0]})
    assert confronto.vincitore() == "b"


# --------------------------------------------------------------------------- #
# Integration: pannello Q8 dal database di test
# --------------------------------------------------------------------------- #

# I numeri della model card (verifica 2010-2012, 120 righe, kg per colonia, seed 42):
# MAE a piena precisione (è il valore che decide DA-05), RMSE e R² a tre decimali.
ATTESI_MODELLI = {
    REGRESSIONE_LINEARE: (4.025411864980751, 5.336, 0.467),
    ALBERO: (5.579183333333333, 6.858, 0.119),
    RANDOM_FOREST: (3.655800749999997, 4.570, 0.609),
}
MAE_PERSISTENZA_Q8 = 4.063428333333333


@pytest.mark.integration
def test_integrazione_il_confronto_della_model_card(
    database_test: Database, dataset_nel_database: None
) -> None:
    dati = carica_dataset_training(database_test)
    _, verifica = dividi_temporale(dati)

    confronto = confronta_modelli(dati)
    risultati = confronto.risultati()

    # Stesso campione per tutti: le 120 righe 2010-2012 dello split di M4-T1.
    assert len(confronto.verifica) == 120
    assert list(confronto.verifica.index) == list(verifica.index)
    assert {n: risultati[n] for n in BASELINE} == valuta_baseline(dati)
    assert risultati[PERSISTENZA].mae_kg == pytest.approx(MAE_PERSISTENZA_Q8, abs=1e-9)

    for nome, (mae, rmse, r2) in ATTESI_MODELLI.items():
        assert risultati[nome].mae_kg == pytest.approx(mae, abs=1e-6), nome
        assert risultati[nome].rmse_kg == pytest.approx(rmse, abs=5e-4), nome
        assert risultati[nome].r2 == pytest.approx(r2, abs=5e-4), nome

    # DA-05, sui valori non arrotondati.
    baseline = {n: risultati[n] for n in BASELINE}
    assert soddisfa_criterio(risultati[REGRESSIONE_LINEARE], baseline)
    assert soddisfa_criterio(risultati[RANDOM_FOREST], baseline)
    assert not soddisfa_criterio(risultati[ALBERO], baseline)
    assert confronto.vincitore() == RANDOM_FOREST


def test_il_notebook_dei_modelli_richiama_train_senza_duplicarlo() -> None:
    """M4-T3: `notebooks/02_modelli.ipynb` usa `train.py`; non legge il CSV né addestra da sé."""
    notebook = Path(__file__).resolve().parents[1] / "notebooks" / "02_modelli.ipynb"
    celle = json.loads(notebook.read_text(encoding="utf-8"))["cells"]
    codice = "\n".join("".join(c["source"]) for c in celle if c["cell_type"] == "code")

    assert "from beewatch.ml.train import" in codice and "confronta_modelli(" in codice
    for vietato in ("read_csv", ".fit(", "sklearn", "honeyproduction"):
        assert vietato not in codice, vietato
