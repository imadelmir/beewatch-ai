"""Test della valutazione finale, M4-T6: residui, intervallo, importanza, distribuzione del target.

Unitari: valori calcolati a mano e pannello sintetico (griglia di seed fissi, 3 ripetizioni
per l'importanza, per restare veloci). Integration: il pannello Q8 vero dal database di test;
i numeri sono quelli della model card (`docs/model_card.md`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from beewatch.database import Database
from beewatch.exceptions import ModelError
from beewatch.ml.features import FEATURE, TARGET, costruisci_feature_storiche
from beewatch.ml.train import (
    PARAMETRI_RF_OTTIMIZZATI,
    PERSISTENZA,
    RANDOM_FOREST,
    RANDOM_FOREST_OTTIMIZZATA,
    carica_dataset_training,
    crea_modello_finale,
    dividi_temporale,
    metriche,
)
from beewatch.ml.tuning import ottimizza_random_forest
from beewatch.ml.valutazione import (
    PERIODO_CV,
    PERIODO_HOLD_OUT,
    Intervallo,
    ValutazioneFinale,
    calcola_intervallo,
    copertura,
    copertura_per_fascia,
    distribuzione_target,
    errori_per,
    errori_per_fascia,
    importanza_variabili,
    valuta_finale,
)


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
def valutazione() -> ValutazioneFinale:
    return valuta_finale(pannello(), ripetizioni_importanza=3)


# --------------------------------------------------------------------------- #
# Il modello finale
# --------------------------------------------------------------------------- #


def test_il_modello_finale_ha_i_parametri_adottati_in_m4_t5() -> None:
    modello = crea_modello_finale(7)
    regressore = modello.named_steps["modello"]
    assert list(modello.named_steps) == ["prep", "modello"]
    assert (regressore.n_estimators, regressore.max_depth, regressore.min_samples_leaf) == (
        200,
        None,
        5,
    )
    assert regressore.random_state == 7
    assert PARAMETRI_RF_OTTIMIZZATI == {
        "n_estimators": 200,
        "max_depth": None,
        "min_samples_leaf": 5,
    }


def test_il_modello_con_le_sole_colonne_delle_feature_prevede_come_con_tutte() -> None:
    """Il contratto del modello salvato (M4-T7) sono le colonne di FEATURE: non cambia nulla."""
    dati = pannello()
    addestramento, verifica = dividi_temporale(dati)
    ingressi = costruisci_feature_storiche(dati).drop(columns=[TARGET])

    tutte = crea_modello_finale().fit(ingressi.loc[addestramento.index], addestramento[TARGET])
    sole = crea_modello_finale().fit(
        ingressi.loc[addestramento.index, list(FEATURE)], addestramento[TARGET]
    )

    np.testing.assert_array_equal(
        tutte.predict(ingressi.loc[verifica.index]),
        sole.predict(ingressi.loc[verifica.index, list(FEATURE)]),
    )


# --------------------------------------------------------------------------- #
# Intervallo e copertura
# --------------------------------------------------------------------------- #


def test_lintervallo_sono_i_quantili_centrali_dei_residui() -> None:
    intervallo = calcola_intervallo(np.arange(1, 11))  # 1..10, interpolazione lineare

    assert intervallo == Intervallo(livello=0.8, inferiore_kg=pytest.approx(1.9),
                                    superiore_kg=pytest.approx(9.1))  # fmt: skip
    assert intervallo.larghezza_kg() == pytest.approx(7.2)


def test_un_livello_diverso_cambia_i_quantili() -> None:
    intervallo = calcola_intervallo(np.arange(0, 101), livello=0.5)
    assert (intervallo.inferiore_kg, intervallo.superiore_kg) == (25.0, 75.0)


@pytest.mark.parametrize(
    "residui,livello",
    [([], 0.8), ([1.0, float("nan")], 0.8), ([1.0, 2.0], 0.0), ([1.0, 2.0], 1.0)],
    ids=["vuoti", "mancanti", "livello_zero", "livello_uno"],
)
def test_lintervallo_rifiuta_ingressi_non_validi(residui: list, livello: float) -> None:
    with pytest.raises(ModelError):
        calcola_intervallo(residui, livello)


def test_la_copertura_conta_i_residui_dentro_estremi_compresi() -> None:
    intervallo = Intervallo(livello=0.8, inferiore_kg=-2.0, superiore_kg=2.0)
    assert copertura([-10, -2, 0, 2, 10], intervallo) == pytest.approx(3 / 5)
    with pytest.raises(ModelError):
        copertura([], intervallo)


def test_su_dati_di_calibrazione_la_copertura_e_circa_il_livello() -> None:
    residui = np.random.default_rng(1).normal(0, 4, 5000)
    assert copertura(residui, calcola_intervallo(residui)) == pytest.approx(0.8, abs=0.01)


# --------------------------------------------------------------------------- #
# Previsioni fuori campione
# --------------------------------------------------------------------------- #


def test_una_riga_per_previsione_e_il_residuo_e_vero_meno_previsto(
    valutazione: ValutazioneFinale,
) -> None:
    previsioni = valutazione.previsioni

    assert list(previsioni.columns) == [
        "periodo", "fold", "codice_stato", "anno", "vero", "previsto", "residuo"
    ]  # fmt: skip
    assert len(previsioni) == 6 * (3 * 2 + 3)  # sei stati, tre fold da due anni, tre anni
    assert not previsioni.duplicated(["codice_stato", "anno"]).any()  # nessuna previsione ripetuta
    np.testing.assert_allclose(previsioni["residuo"], previsioni["vero"] - previsioni["previsto"])
    assert set(previsioni["periodo"]) == {PERIODO_CV, PERIODO_HOLD_OUT}
    assert set(previsioni.loc[previsioni["periodo"] == PERIODO_CV, "anno"]) == set(
        range(2004, 2010)
    )
    assert set(previsioni.loc[previsioni["periodo"] == PERIODO_HOLD_OUT, "anno"]) == {
        2010, 2011, 2012
    }  # fmt: skip


def test_le_previsioni_vengono_dal_modello_finale_e_dalle_stesse_metriche(
    valutazione: ValutazioneFinale,
) -> None:
    hold_out = valutazione.previsioni[valutazione.previsioni["periodo"] == PERIODO_HOLD_OUT]
    atteso = valutazione.hold_out.risultati()[RANDOM_FOREST_OTTIMIZZATA]

    assert metriche(hold_out["vero"], hold_out["previsto"]) == atteso
    assert set(valutazione.hold_out.modelli) == {RANDOM_FOREST, RANDOM_FOREST_OTTIMIZZATA}
    assert PERSISTENZA in valutazione.hold_out.previsioni
    assert valutazione.cv.confronti[0].modelli == (RANDOM_FOREST_OTTIMIZZATA,)


def test_lhold_out_non_entra_nella_calibrazione_dellintervallo_cv() -> None:
    base = pannello()
    alterato = base.copy()
    alterato.loc[alterato["anno"] >= 2010, TARGET] = 999.0

    a = valuta_finale(base, ripetizioni_importanza=2)
    b = valuta_finale(alterato, ripetizioni_importanza=2)

    assert a.intervallo_cv == b.intervallo_cv  # calibrato sulla sola cross-validation
    assert a.copertura_hold_out != b.copertura_hold_out  # ma la copertura sul 2010-2012 cambia
    assert a.intervallo_finale != b.intervallo_finale  # quello finale usa anche i residui 2010-2012


def test_lintervallo_finale_usa_tutti_i_residui(valutazione: ValutazioneFinale) -> None:
    assert valutazione.intervallo_finale == calcola_intervallo(valutazione.previsioni["residuo"])
    residui_cv = valutazione.previsioni.loc[
        valutazione.previsioni["periodo"] == PERIODO_CV, "residuo"
    ]
    assert valutazione.intervallo_cv == calcola_intervallo(residui_cv)
    assert 0.0 <= valutazione.copertura_hold_out <= 1.0


def test_la_valutazione_e_riproducibile() -> None:
    a = valuta_finale(pannello(), ripetizioni_importanza=2)
    b = valuta_finale(pannello(), ripetizioni_importanza=2)
    pd.testing.assert_frame_equal(a.previsioni, b.previsioni)
    pd.testing.assert_frame_equal(a.importanza, b.importanza)
    assert a.intervallo_finale == b.intervallo_finale


# --------------------------------------------------------------------------- #
# Importanza delle variabili
# --------------------------------------------------------------------------- #


def test_limportanza_ha_una_riga_per_feature_dalla_piu_alla_meno_importante(
    valutazione: ValutazioneFinale,
) -> None:
    importanza = valutazione.importanza

    assert sorted(importanza.index) == sorted(FEATURE)
    assert list(importanza.columns) == ["media_kg", "dev_std_kg"]
    assert importanza["media_kg"].is_monotonic_decreasing
    assert importanza.index[0] in {
        "resa_anno_prima",
        "resa_media_3_anni_prima",
    }  # il livello recente


def test_l_anno_ha_importanza_nulla_perche_gli_anni_di_verifica_escono_dal_range() -> None:
    """Tutti gli anni 2010-2012 superano ogni soglia imparata: mischiarli non cambia il percorso."""
    importanza = importanza_variabili(pannello(), ripetizioni=3)
    assert importanza.loc["anno", "media_kg"] == 0.0
    assert importanza.loc["anno", "dev_std_kg"] == 0.0


def test_limportanza_e_riproducibile_con_lo_stesso_seed() -> None:
    a = importanza_variabili(pannello(), seed=3, ripetizioni=3)
    b = importanza_variabili(pannello(), seed=3, ripetizioni=3)
    pd.testing.assert_frame_equal(a, b)


# --------------------------------------------------------------------------- #
# Distribuzione del target
# --------------------------------------------------------------------------- #


def test_la_distribuzione_del_target_calcolata_a_mano() -> None:
    dati = pd.DataFrame({TARGET: [10.0, 20.0, 30.0, 40.0, 100.0]})

    d = distribuzione_target(dati)

    assert (d.righe, d.media, d.mediana, d.minimo, d.massimo) == (5, 40.0, 30.0, 10.0, 100.0)
    assert d.dev_std == pytest.approx(np.std([10, 20, 30, 40, 100], ddof=1))
    assert (d.p10, d.p90) == pytest.approx((14.0, 76.0))
    assert d.asimmetria > 0  # coda a destra
    simmetrica = distribuzione_target(pd.DataFrame({TARGET: [1.0, 2.0, 3.0, 4.0, 5.0]}))
    assert simmetrica.asimmetria == pytest.approx(0.0)


def test_senza_righe_non_ce_distribuzione() -> None:
    with pytest.raises(ModelError, match="vuoto"):
        distribuzione_target(pd.DataFrame({TARGET: []}))


# --------------------------------------------------------------------------- #
# Errori per gruppo
# --------------------------------------------------------------------------- #


def previsioni_a_mano() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "periodo": [PERIODO_CV] * 3 + [PERIODO_HOLD_OUT] * 3,
            "anno": [2004, 2004, 2005, 2010, 2010, 2011],
            "codice_stato": ["AA", "BB", "AA", "AA", "BB", "AA"],
            "previsto": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
            "residuo": [1.0, -2.0, 3.0, -4.0, 5.0, -6.0],
        }
    )


def test_gli_errori_per_gruppo_calcolati_a_mano() -> None:
    per_stato = errori_per(previsioni_a_mano(), "codice_stato")

    assert per_stato.loc["AA"].tolist() == [
        4,
        pytest.approx((1 + 3 + 4 + 6) / 4),
        pytest.approx(-6 / 4),
    ]
    assert per_stato.loc["BB"].tolist() == [2, pytest.approx(3.5), pytest.approx(1.5)]


def test_errori_e_copertura_per_fascia_di_previsione() -> None:
    previsioni = previsioni_a_mano()

    fasce = errori_per_fascia(previsioni, fasce=3)
    dentro = copertura_per_fascia(
        previsioni, Intervallo(livello=0.8, inferiore_kg=-3.0, superiore_kg=3.0), fasce=3
    )

    assert fasce["righe"].tolist() == [2, 2, 2]
    assert fasce["previsto_medio_kg"].tolist() == [15.0, 35.0, 55.0]
    assert fasce["mae_kg"].tolist() == [1.5, 3.5, 5.5]  # (1,2) (3,4) (5,6)
    assert fasce["errore_medio_kg"].tolist() == [-0.5, -0.5, -0.5]
    assert dentro.tolist() == [1.0, 0.5, 0.0]  # |res| <= 3: (1,-2) sì, (3,-4) metà, (5,-6) no


# --------------------------------------------------------------------------- #
# Integration: pannello Q8 dal database di test
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_integrazione_la_valutazione_finale_della_model_card(
    database_test: Database, dataset_nel_database: None
) -> None:
    dati = carica_dataset_training(database_test)

    v = valuta_finale(dati)

    # I parametri adottati sono ancora quelli che il tuning sceglie (M4-T5).
    esito = ottimizza_random_forest(dati)
    assert esito.migliori_parametri == {
        f"modello__{k}": x for k, x in PARAMETRI_RF_OTTIMIZZATI.items()
    }

    # Hold-out 2010-2012, 120 righe: il modello adottato, il default (M4-T3) e la persistenza.
    risultati = v.hold_out.risultati()
    assert len(v.hold_out.verifica) == 120
    assert risultati[RANDOM_FOREST].mae_kg == pytest.approx(3.6558007499999965, abs=1e-9)
    assert risultati[PERSISTENZA].mae_kg == pytest.approx(4.0634283333333325, abs=1e-9)
    finale = risultati[RANDOM_FOREST_OTTIMIZZATA]
    assert finale.mae_kg == pytest.approx(3.498627342552852, abs=1e-6)
    assert finale.rmse_kg == pytest.approx(4.4826, abs=5e-5)
    assert finale.r2 == pytest.approx(0.6236, abs=5e-5)

    # Cross-validation: stessi numeri di M4-T5 (tuning) per il modello adottato.
    riepilogo = v.cv.riepilogo()[RANDOM_FOREST_OTTIMIZZATA]
    assert riepilogo.media.mae_kg == pytest.approx(4.0883, abs=5e-5)
    assert riepilogo.dev_std.mae_kg == pytest.approx(0.1158, abs=5e-5)

    # Intervallo: calibrato sulla CV, controllato sul 2010-2012.
    assert len(v.previsioni) == 360
    assert v.intervallo_cv.inferiore_kg == pytest.approx(-6.5184, abs=5e-5)
    assert v.intervallo_cv.superiore_kg == pytest.approx(6.1543, abs=5e-5)
    assert v.copertura_hold_out == pytest.approx(0.85, abs=1e-9)
    assert v.intervallo_finale.inferiore_kg == pytest.approx(-5.7137, abs=5e-5)
    assert v.intervallo_finale.superiore_kg == pytest.approx(6.5840, abs=5e-5)

    # Importanza per permutazione: domina il livello recente; `anno` è zero per costruzione.
    assert v.importanza.index[0] == "resa_media_3_anni_prima"
    assert v.importanza.loc["resa_media_3_anni_prima", "media_kg"] == pytest.approx(
        2.7565, abs=5e-3
    )
    assert v.importanza.loc["anno", "media_kg"] == 0.0

    # Distribuzione del target nel pannello Q8.
    assert v.distribuzione.righe == 600
    assert v.distribuzione.asimmetria == pytest.approx(0.6678, abs=5e-5)
    assert v.distribuzione.media == pytest.approx(28.4017, abs=5e-5)
