"""Test del tuning, M4-T5: griglia, fold temporali senza hold-out, confronto con i default.

Unitari: pannello sintetico e griglie piccole (per velocità), `EsitoTuning`
costruiti a mano per la regola di adozione. Integration: il pannello Q8 vero dal
database di test, con la griglia del backlog; i numeri sono quelli della model card.
"""

from __future__ import annotations

import statistics

import numpy as np
import pandas as pd
import pytest
from sklearn.exceptions import NotFittedError
from sklearn.utils.validation import check_is_fitted

from beewatch.database import Database
from beewatch.ml.train import (
    PERSISTENZA,
    RANDOM_FOREST,
    TARGET,
    Confronto,
    carica_dataset_training,
    confronta_modelli,
    crea_modelli,
)
from beewatch.ml.tuning import (
    DEFAULT,
    GRIGLIA_RANDOM_FOREST,
    OTTIMIZZATA,
    EsitoTuning,
    ottimizza_random_forest,
)
from beewatch.ml.validazione import FOLD_TEMPORALI, CrossValidazione, cross_validation_temporale

GRIGLIA_PICCOLA = {"modello__n_estimators": [20], "modello__min_samples_leaf": [1, 5]}


def pannello(seme: int = 0) -> pd.DataFrame:
    """Sei stati, 1998-2012, livello diverso per stato, tendenza e rumore."""
    caso = np.random.default_rng(seme)
    righe = [
        {"codice_stato": s, "anno": a, "numero_colonie": 1000 * (i + 1) + a,
         TARGET: 30 + 5 * i - 0.5 * (a - 1998) + caso.normal(0, 3)}
        for i, s in enumerate(("AA", "BB", "CC", "DD", "EE", "FF"))
        for a in range(1998, 2013)
    ]  # fmt: skip
    return pd.DataFrame(righe)


@pytest.fixture(scope="module")
def esito_base() -> EsitoTuning:
    return ottimizza_random_forest(pannello(), griglia=GRIGLIA_PICCOLA)


# --------------------------------------------------------------------------- #
# Griglia e ricerca
# --------------------------------------------------------------------------- #


def test_la_griglia_e_quella_del_backlog() -> None:
    assert GRIGLIA_RANDOM_FOREST == {
        "modello__n_estimators": [200, 500],
        "modello__max_depth": [None, 8, 15],
        "modello__min_samples_leaf": [1, 3, 5],
    }


def test_la_tabella_della_ricerca_ha_una_riga_per_configurazione(
    esito_base: EsitoTuning,
) -> None:
    tabella = esito_base.ricerca
    assert len(tabella) == 2
    assert list(tabella.columns) == [
        "n_estimators", "min_samples_leaf", "mae_medio", "mae_dev_std", "rango"
    ]  # fmt: skip
    prima = tabella[tabella["rango"] == 1].iloc[0]
    assert esito_base.migliori_parametri == {
        "modello__n_estimators": prima["n_estimators"],
        "modello__min_samples_leaf": prima["min_samples_leaf"],
    }
    assert prima["mae_medio"] == tabella["mae_medio"].min()


def test_la_ricerca_e_la_rivalutazione_misurano_le_stesse_righe(esito_base: EsitoTuning) -> None:
    """Il MAE medio di GridSearchCV per la scelta coincide con quello di `metriche()` sui fold."""
    migliore = esito_base.ricerca.loc[esito_base.ricerca["rango"] == 1, "mae_medio"].iloc[0]
    rivalutato = statistics.fmean(esito_base.mae_per_fold(OTTIMIZZATA))
    assert migliore == pytest.approx(rivalutato, abs=1e-9)


def test_i_default_sono_la_random_forest_di_m4_t4(esito_base: EsitoTuning) -> None:
    cv = cross_validation_temporale(pannello())
    attesi = [r[RANDOM_FOREST].mae_kg for r in cv.risultati_per_fold()]
    assert esito_base.mae_per_fold(DEFAULT) == attesi


def test_il_confronto_usa_i_fold_di_m4_t4_e_le_baseline(esito_base: EsitoTuning) -> None:
    confronto = esito_base.confronto
    assert confronto.fold == FOLD_TEMPORALI
    for c, f in zip(confronto.confronti, FOLD_TEMPORALI, strict=True):
        assert set(c.verifica["anno"]) == set(f.anni_valutazione)
        assert c.modelli == (DEFAULT, OTTIMIZZATA)
        assert PERSISTENZA in c.previsioni


# --------------------------------------------------------------------------- #
# Hold-out fuori, indici allineati, riproducibilità
# --------------------------------------------------------------------------- #


def test_lhold_out_2010_2012_non_entra_nel_tuning(esito_base: EsitoTuning) -> None:
    alterato = pannello()
    alterato.loc[alterato["anno"] >= 2010, TARGET] = 999.0

    esito = ottimizza_random_forest(alterato, griglia=GRIGLIA_PICCOLA)

    pd.testing.assert_frame_equal(esito.ricerca, esito_base.ricerca)
    assert esito.mae_per_fold(OTTIMIZZATA) == esito_base.mae_per_fold(OTTIMIZZATA)


def test_ordine_e_indice_dellingresso_non_cambiano_il_risultato(esito_base: EsitoTuning) -> None:
    """Gli indici dei fold sono posizioni del frame ristretto, non etichette dell'ingresso."""
    mescolato = pannello().sample(frac=1, random_state=7)
    mescolato.index = mescolato.index * 10 + 3

    esito = ottimizza_random_forest(mescolato, griglia=GRIGLIA_PICCOLA)

    pd.testing.assert_frame_equal(esito.ricerca, esito_base.ricerca)
    assert esito.mae_per_fold(OTTIMIZZATA) == esito_base.mae_per_fold(OTTIMIZZATA)


def test_lo_stesso_seed_da_lo_stesso_tuning(esito_base: EsitoTuning) -> None:
    esito = ottimizza_random_forest(pannello(), griglia=GRIGLIA_PICCOLA)
    pd.testing.assert_frame_equal(esito.ricerca, esito_base.ricerca)
    assert esito.mae_per_fold(OTTIMIZZATA) == esito_base.mae_per_fold(OTTIMIZZATA)


def test_se_la_griglia_contiene_solo_i_default_non_ce_guadagno() -> None:
    esito = ottimizza_random_forest(pannello(), griglia={"modello__n_estimators": [100]})

    assert esito.mae_per_fold(OTTIMIZZATA) == esito.mae_per_fold(DEFAULT)
    assert esito.guadagno_medio_kg() == 0.0
    assert esito.fold_migliorati() == 0
    assert not esito.da_adottare()


def test_i_modelli_passati_al_confronto_non_restano_addestrati() -> None:
    modello = crea_modelli()[RANDOM_FOREST]
    confronta_modelli(pannello(), modelli={"rf": modello})
    with pytest.raises(NotFittedError):
        check_is_fitted(modello)


# --------------------------------------------------------------------------- #
# Regola di adozione
# --------------------------------------------------------------------------- #


def confronto_a_mano(mae_default: float, mae_ottimizzata: float) -> Confronto:
    """Due righe con vero 10 e 20: errori costanti danno esattamente il MAE voluto."""
    verifica = pd.DataFrame({"anno": [2004, 2005], TARGET: [10.0, 20.0]})
    vero = np.array([10.0, 20.0])
    previsioni = {DEFAULT: vero + mae_default, OTTIMIZZATA: vero + mae_ottimizzata,
                  PERSISTENZA: vero + 9.0}  # fmt: skip
    return Confronto(verifica=verifica, previsioni=previsioni, modelli=(DEFAULT, OTTIMIZZATA))


def esito_a_mano(coppie: list[tuple[float, float]]) -> EsitoTuning:
    cv = CrossValidazione(
        fold=FOLD_TEMPORALI, confronti=tuple(confronto_a_mano(d, o) for d, o in coppie)
    )
    return EsitoTuning(migliori_parametri={}, ricerca=pd.DataFrame(), confronto=cv)


@pytest.mark.parametrize(
    "coppie,migliorati,adottare",
    [
        ([(4.0, 3.0), (4.0, 3.5), (4.0, 4.5)], 2, True),  # meglio in media e in 2 fold
        ([(4.0, 2.0), (4.0, 4.1), (4.0, 4.1)], 1, False),  # meglio in media, ma in 1 fold
        ([(4.0, 3.9), (4.0, 3.9), (4.0, 4.5)], 2, False),  # 2 fold, ma peggio in media
        ([(4.0, 4.0), (4.0, 4.0), (4.0, 4.0)], 0, False),  # identici
    ],
    ids=["adottata", "un_fold_solo", "peggio_in_media", "pari"],
)
def test_la_regola_di_adozione(
    coppie: list[tuple[float, float]], migliorati: int, adottare: bool
) -> None:
    esito = esito_a_mano(coppie)
    assert esito.fold_migliorati() == migliorati
    assert esito.guadagno_medio_kg() == pytest.approx(
        statistics.fmean(d for d, _ in coppie) - statistics.fmean(o for _, o in coppie)
    )
    assert esito.da_adottare() is adottare


# --------------------------------------------------------------------------- #
# Integration: pannello Q8 dal database di test, griglia del backlog
# --------------------------------------------------------------------------- #

MAE_DEFAULT = (4.138917912499997, 4.178266674999997, 4.096221512500001)
MAE_OTTIMIZZATA = (4.136515644088574, 3.956260490882703, 4.172254814975283)


@pytest.mark.integration
def test_integrazione_il_tuning_della_model_card(
    database_test: Database, dataset_nel_database: None
) -> None:
    esito = ottimizza_random_forest(carica_dataset_training(database_test))

    assert len(esito.ricerca) == 18
    assert esito.migliori_parametri == {
        "modello__max_depth": None,
        "modello__min_samples_leaf": 5,
        "modello__n_estimators": 200,
    }
    assert esito.mae_per_fold(DEFAULT) == pytest.approx(MAE_DEFAULT, abs=1e-6)
    assert esito.mae_per_fold(OTTIMIZZATA) == pytest.approx(MAE_OTTIMIZZATA, abs=1e-6)
    migliore = esito.ricerca.loc[esito.ricerca["rango"] == 1, "mae_medio"].iloc[0]
    assert migliore == pytest.approx(statistics.fmean(MAE_OTTIMIZZATA), abs=1e-6)
    assert esito.guadagno_medio_kg() == pytest.approx(0.049458, abs=1e-6)
    assert esito.fold_migliorati() == 2
    assert esito.da_adottare()
