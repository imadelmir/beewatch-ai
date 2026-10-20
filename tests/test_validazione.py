"""Test della cross-validation temporale, M4-T4: fold per anno, nessun leakage, aggregati.

Unitari: un pannello sintetico 1998-2012, e `CrossValidazione` costruite a mano
per i conteggi. Integration: il pannello Q8 vero dal database di test; i numeri
sono quelli della model card (`docs/model_card.md`).
"""

from __future__ import annotations

import statistics

import numpy as np
import pandas as pd
import pytest

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
    TARGET,
    Confronto,
    carica_dataset_training,
    valuta_baseline,
)
from beewatch.ml.validazione import (
    FOLD_TEMPORALI,
    CrossValidazione,
    Fold,
    cross_validation_temporale,
    fold_temporali,
)

MODELLI = (REGRESSIONE_LINEARE, ALBERO, RANDOM_FOREST)
BASELINE = (MEDIA_GLOBALE, MEDIA_STATO, MEDIA_STATO_TREND, PERSISTENZA)


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
def cv_base() -> CrossValidazione:
    """La cross-validation del pannello sintetico, calcolata una volta per il modulo."""
    return cross_validation_temporale(pannello())


# --------------------------------------------------------------------------- #
# I fold
# --------------------------------------------------------------------------- #


def test_i_fold_sono_quelli_del_backlog_e_non_toccano_lhold_out() -> None:
    assert FOLD_TEMPORALI == (
        Fold(2003, (2004, 2005)),
        Fold(2005, (2006, 2007)),
        Fold(2007, (2008, 2009)),
    )
    assert max(a for f in FOLD_TEMPORALI for a in f.anni_valutazione) == 2009


def test_gli_indici_dei_fold_separano_gli_anni_senza_sovrapposizioni() -> None:
    dati = pannello().sample(frac=1, random_state=1)  # l'ordine delle righe non conta
    anni = dati["anno"].to_numpy()

    fold = list(fold_temporali(dati))

    assert len(fold) == 3
    for (addestramento, valutazione), f in zip(fold, FOLD_TEMPORALI, strict=True):
        assert set(anni[addestramento]) == set(range(1998, f.fine_addestramento + 1))
        assert set(anni[valutazione]) == set(f.anni_valutazione)
        assert anni[addestramento].max() < anni[valutazione].min()
        assert not set(addestramento) & set(valutazione)
        assert len(valutazione) == 6 * 2  # sei stati, due anni


@pytest.mark.parametrize(
    "fold",
    [
        (Fold(2003, (2005, 2006)),),  # un anno di buco dopo l'addestramento
        (Fold(2003, (2004, 2006)),),  # anni non consecutivi
        (Fold(2003, ()),),  # niente da valutare
        (Fold(2008, (2009, 2010)),),  # entra nell'hold-out 2010-2012
    ],
    ids=["buco", "non_consecutivi", "vuoto", "hold_out"],
)
def test_un_fold_non_valido_e_un_errore(fold: tuple[Fold, ...]) -> None:
    with pytest.raises(ModelError):
        list(fold_temporali(pannello(), fold))
    with pytest.raises(ModelError):
        cross_validation_temporale(pannello(), fold=fold)


def test_con_un_fold_solo_non_ce_deviazione_standard() -> None:
    with pytest.raises(ModelError, match="due fold"):
        cross_validation_temporale(pannello(), fold=(Fold(2003, (2004, 2005)),))


# --------------------------------------------------------------------------- #
# Stessi campioni, stessa procedura
# --------------------------------------------------------------------------- #


def test_ogni_fold_misura_modelli_e_baseline_sulle_righe_dei_suoi_indici(
    cv_base: CrossValidazione,
) -> None:
    dati, cv = pannello(), cv_base

    for confronto, (_, valutazione), f in zip(
        cv.confronti, fold_temporali(dati), FOLD_TEMPORALI, strict=True
    ):
        assert list(confronto.verifica.index) == list(dati.index[valutazione])
        assert set(confronto.verifica["anno"]) == set(f.anni_valutazione)
        assert tuple(confronto.previsioni) == MODELLI + BASELINE
        assert {len(p) for p in confronto.previsioni.values()} == {len(valutazione)}


def test_le_baseline_di_ogni_fold_usano_solo_il_suo_addestramento(
    cv_base: CrossValidazione,
) -> None:
    dati, cv = pannello(), cv_base
    for risultati, f in zip(cv.risultati_per_fold(), FOLD_TEMPORALI, strict=True):
        fino_alla_valutazione = dati[dati["anno"] <= f.anni_valutazione[-1]]
        attese = valuta_baseline(fino_alla_valutazione, f.fine_addestramento)
        assert {n: risultati[n] for n in BASELINE} == attese


# --------------------------------------------------------------------------- #
# Nessuna informazione dal futuro, riproducibilità
# --------------------------------------------------------------------------- #


def test_gli_anni_dopo_la_valutazione_non_cambiano_il_fold(cv_base: CrossValidazione) -> None:
    """Cambiare tutto dal 2006 in poi lascia identico il primo fold (2004-2005)."""
    base = pannello()
    alterato = base.copy()
    dopo = alterato["anno"] >= 2006
    alterato.loc[dopo, TARGET] = 999.0
    alterato.loc[dopo, "numero_colonie"] = 1

    prima_cv, dopo_cv = cv_base, cross_validation_temporale(alterato)

    for nome in MODELLI + BASELINE:
        np.testing.assert_array_equal(
            prima_cv.confronti[0].previsioni[nome], dopo_cv.confronti[0].previsioni[nome], nome
        )


def test_lhold_out_2010_2012_non_entra_nella_cross_validation(
    cv_base: CrossValidazione,
) -> None:
    base = pannello()
    alterato = base.copy()
    alterato.loc[alterato["anno"] >= 2010, TARGET] = 999.0
    assert cv_base.risultati_per_fold() == cross_validation_temporale(alterato).risultati_per_fold()


def test_nel_fold_i_modelli_non_vedono_la_resa_che_devono_prevedere(
    cv_base: CrossValidazione,
) -> None:
    """La resa del 2005 (ultimo anno del primo fold) non serve a prevedere 2004 né 2005."""
    base = pannello()
    alterato = base.copy()
    alterato.loc[alterato["anno"] == 2005, TARGET] = 999.0

    prima_cv, dopo_cv = cv_base, cross_validation_temporale(alterato)

    for nome in MODELLI:
        np.testing.assert_array_equal(
            prima_cv.confronti[0].previsioni[nome], dopo_cv.confronti[0].previsioni[nome], nome
        )


def test_lo_stesso_seed_da_la_stessa_cross_validation(cv_base: CrossValidazione) -> None:
    assert cross_validation_temporale(pannello()).risultati_per_fold() == (
        cv_base.risultati_per_fold()
    )


# --------------------------------------------------------------------------- #
# Aggregati
# --------------------------------------------------------------------------- #


def test_media_e_deviazione_standard_campionaria_dei_fold(cv_base: CrossValidazione) -> None:
    cv = cv_base
    per_fold = cv.risultati_per_fold()

    riepilogo = cv.riepilogo()

    assert tuple(riepilogo) == MODELLI + BASELINE
    for nome, valori in riepilogo.items():
        mae = [r[nome].mae_kg for r in per_fold]
        r2 = [r[nome].r2 for r in per_fold]
        assert valori.media.mae_kg == pytest.approx(sum(mae) / 3)
        assert valori.dev_std.mae_kg == pytest.approx(statistics.stdev(mae))  # n - 1
        assert valori.media.r2 == pytest.approx(sum(r2) / 3)
        assert valori.dev_std.rmse_kg == pytest.approx(
            statistics.stdev([r[nome].rmse_kg for r in per_fold])
        )


def confronto_a_mano(mae_modello: float, mae_persistenza: float) -> Confronto:
    """Due righe con vero 10 e 20: errori costanti danno esattamente il MAE voluto."""
    verifica = pd.DataFrame({"anno": [2004, 2005], TARGET: [10.0, 20.0]})
    previsioni = {
        "m": np.array([10.0, 20.0]) + mae_modello,
        PERSISTENZA: np.array([10.0, 20.0]) + mae_persistenza,
    }
    return Confronto(verifica=verifica, previsioni=previsioni, modelli=("m",))


def test_conta_i_fold_in_cui_un_modello_batte_la_persistenza() -> None:
    cv = CrossValidazione(
        fold=FOLD_TEMPORALI,
        confronti=(confronto_a_mano(1.0, 2.0), confronto_a_mano(2.0, 2.0),
                   confronto_a_mano(3.0, 2.5)),
    )  # fmt: skip
    assert cv.fold_sotto_la_persistenza() == {"m": 1}  # a parità non conta


# --------------------------------------------------------------------------- #
# Integration: pannello Q8 dal database di test
# --------------------------------------------------------------------------- #

# I numeri della model card: MAE per fold a piena precisione, seed 42.
MAE_PER_FOLD = {
    REGRESSIONE_LINEARE: (3.9995760791203283, 4.453334617745753, 4.18965433404455),
    ALBERO: (6.083818750000001, 5.1085825, 5.930726249999999),
    RANDOM_FOREST: (4.138917912499997, 4.178266674999997, 4.096221512500001),
    MEDIA_STATO_TREND: (3.765715522619048, 4.396126575520833, 4.140010311931818),
    PERSISTENZA: (5.159608749999999, 4.269432500000001, 4.910136249999999),
}
# Media ± deviazione standard del MAE sui tre fold, a quattro decimali.
MAE_RIEPILOGO = {
    REGRESSIONE_LINEARE: (4.2142, 0.2279),
    ALBERO: (5.7077, 0.5245),
    RANDOM_FOREST: (4.1378, 0.0410),
    MEDIA_GLOBALE: (7.0827, 0.1288),
    MEDIA_STATO: (4.7756, 0.6258),
    MEDIA_STATO_TREND: (4.1006, 0.3170),
    PERSISTENZA: (4.7797, 0.4592),
}


@pytest.mark.integration
def test_integrazione_la_cross_validation_della_model_card(
    database_test: Database, dataset_nel_database: None
) -> None:
    dati = carica_dataset_training(database_test)

    cv = cross_validation_temporale(dati)

    assert [len(c.verifica) for c in cv.confronti] == [80, 80, 80]
    assert all(c.verifica["anno"].max() <= 2009 for c in cv.confronti)
    per_fold = cv.risultati_per_fold()
    for nome, attesi in MAE_PER_FOLD.items():
        for risultati, mae in zip(per_fold, attesi, strict=True):
            assert risultati[nome].mae_kg == pytest.approx(mae, abs=1e-6), nome
    for nome, valori in cv.riepilogo().items():
        assert valori.media.mae_kg == pytest.approx(MAE_RIEPILOGO[nome][0], abs=5e-5), nome
        assert valori.dev_std.mae_kg == pytest.approx(MAE_RIEPILOGO[nome][1], abs=5e-5), nome

    assert cv.fold_sotto_la_persistenza() == {
        REGRESSIONE_LINEARE: 2,
        ALBERO: 0,
        RANDOM_FOREST: 3,
    }
