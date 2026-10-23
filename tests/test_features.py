"""Test delle feature, M4-T2: storia per stato senza informazione dal futuro, preprocessore.

Unitari: piccoli pannelli costruiti a mano, dove ogni ritardo si conosce in
anticipo; il preprocessore addestrato su un pannello e applicato a un altro.

Integration: il pannello Q8 vero dal database di test. La resa dell'anno prima
delle righe di verifica è esattamente la baseline di persistenza di M4-T1.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline

from beewatch.database import Database
from beewatch.exceptions import ModelError
from beewatch.ml.features import (
    COLONIE_ANNO_PRIMA,
    FEATURE,
    FEATURE_ESCLUSE,
    RESA_ANNO_PRIMA,
    RESA_MEDIA_3_ANNI_PRIMA,
    TARGET,
    costruisci_feature_storiche,
    crea_preprocessore,
)
from beewatch.ml.train import (
    PERSISTENZA,
    carica_dataset_training,
    dividi_temporale,
    metriche,
    previsioni_baseline,
    valuta_baseline,
)

STORICHE = [RESA_ANNO_PRIMA, RESA_MEDIA_3_ANNI_PRIMA, COLONIE_ANNO_PRIMA]


def pannello(valori: dict[str, dict[int, float]], colonie: int = 1000) -> pd.DataFrame:
    righe = [
        {"codice_stato": s, "anno": a, "numero_colonie": colonie + a, TARGET: float(r)}
        for s, anni in valori.items()
        for a, r in anni.items()
    ]
    return pd.DataFrame(righe)


def colonna(dati: pd.DataFrame, nome: str) -> list[float | None]:
    return [None if np.isnan(v) else v for v in dati[nome]]


# --------------------------------------------------------------------------- #
# Feature storiche
# --------------------------------------------------------------------------- #


def test_le_feature_storiche_calcolate_a_mano() -> None:
    dati = pannello({"AA": {2000: 10, 2001: 20, 2002: 30, 2003: 40, 2004: 50}})

    feature = costruisci_feature_storiche(dati)

    assert colonna(feature, RESA_ANNO_PRIMA) == [None, 10, 20, 30, 40]
    # Media degli anni t-1, t-2, t-3 che esistono: basta uno.
    assert colonna(feature, RESA_MEDIA_3_ANNI_PRIMA) == [None, 10, 15, 20, 30]
    assert colonna(feature, COLONIE_ANNO_PRIMA) == [None, 3000, 3001, 3002, 3003]


def test_ogni_stato_ha_la_sua_storia() -> None:
    dati = pannello({"AA": {2000: 10, 2001: 20}, "BB": {2000: 50, 2001: 60}})
    assert colonna(costruisci_feature_storiche(dati), RESA_ANNO_PRIMA) == [None, 10, None, 50]


def test_la_riga_non_vede_mai_il_proprio_anno() -> None:
    """Cambiare resa e colonie dell'anno t non cambia le feature della riga t."""
    base = pannello({"AA": {a: 10.0 + a % 7 for a in range(2000, 2010)}})
    alterato = base.copy()
    anno = alterato["anno"] == 2005
    alterato.loc[anno, TARGET] = 999.0
    alterato.loc[anno, "numero_colonie"] = 999_999

    prima, dopo = (costruisci_feature_storiche(d) for d in (base, alterato))

    cambiate = prima[STORICHE].fillna(-1).ne(dopo[STORICHE].fillna(-1)).any(axis=1)
    # Cambiano solo le righe che hanno il 2005 fra gli anni precedenti: 2006, 2007, 2008.
    assert list(prima.loc[cambiate, "anno"]) == [2006, 2007, 2008]


def test_un_anno_mancante_non_viene_sostituito_da_quello_prima() -> None:
    dati = pannello({"AA": {2006: 10, 2007: 20, 2008: 30, 2010: 50}})  # manca il 2009

    feature = costruisci_feature_storiche(dati).set_index("anno")

    assert np.isnan(feature.loc[2010, RESA_ANNO_PRIMA])  # non il 2008
    assert np.isnan(feature.loc[2010, COLONIE_ANNO_PRIMA])
    assert feature.loc[2010, RESA_MEDIA_3_ANNI_PRIMA] == pytest.approx(25.0)  # 2008 e 2007


def test_ordine_e_indice_dellingresso_restano_e_lingresso_non_cambia() -> None:
    dati = pannello({"AA": {2000: 10, 2001: 20, 2002: 30}, "BB": {2000: 5, 2001: 6}})
    mescolato = dati.sample(frac=1, random_state=3)
    copia = mescolato.copy()

    feature = costruisci_feature_storiche(mescolato)

    pd.testing.assert_frame_equal(mescolato, copia)  # ingresso intatto
    assert list(feature.index) == list(mescolato.index)
    ordinato = costruisci_feature_storiche(dati)
    pd.testing.assert_frame_equal(feature.sort_index(), ordinato)


def test_in_previsione_la_riga_futura_senza_resa_ha_le_sue_feature() -> None:
    storia = pannello({"AA": {2010: 30, 2011: 33, 2012: 36}})
    futura = pd.DataFrame([{"codice_stato": "AA", "anno": 2013, "numero_colonie": 0, TARGET: None}])

    feature = costruisci_feature_storiche(pd.concat([storia, futura], ignore_index=True))

    ultima = feature.iloc[-1]
    assert ultima[RESA_ANNO_PRIMA] == 36.0
    assert ultima[RESA_MEDIA_3_ANNI_PRIMA] == pytest.approx(33.0)
    assert ultima[COLONIE_ANNO_PRIMA] == 3012


def test_mancano_colonne_errore_che_le_elenca() -> None:
    with pytest.raises(ModelError, match="numero_colonie"):
        costruisci_feature_storiche(pd.DataFrame({"codice_stato": ["AA"], "anno": [2000],
                                                  TARGET: [1.0]}))  # fmt: skip


def test_una_coppia_stato_anno_ripetuta_e_un_errore() -> None:
    dati = pd.concat([pannello({"AA": {2000: 10}})] * 2, ignore_index=True)
    with pytest.raises(ModelError, match="più di una volta"):
        costruisci_feature_storiche(dati)


def test_la_resa_dellanno_prima_e_la_baseline_di_persistenza() -> None:
    dati = pannello({"AA": {a: 20.0 + (a * 7) % 5 for a in range(2005, 2013)},
                     "BB": {a: 35.0 - (a * 3) % 4 for a in range(2005, 2013)}})  # fmt: skip
    addestramento, verifica = dividi_temporale(dati)

    feature = costruisci_feature_storiche(dati).loc[verifica.index]

    persistenza = previsioni_baseline(addestramento, verifica, dati)[PERSISTENZA]
    assert list(feature[RESA_ANNO_PRIMA]) == list(persistenza)


# --------------------------------------------------------------------------- #
# Preprocessore
# --------------------------------------------------------------------------- #


def addestrato_su(dati: pd.DataFrame):
    return crea_preprocessore().fit(costruisci_feature_storiche(dati))


def test_feature_e_feature_escluse_non_si_sovrappongono() -> None:
    assert not set(FEATURE) & set(FEATURE_ESCLUSE)
    assert {"produzione_totale_kg", "valore_produzione_usd", "numero_colonie", TARGET} <= set(
        FEATURE_ESCLUSE
    )


def test_il_preprocessore_produce_le_colonne_attese_senza_mancanti() -> None:
    dati = pannello({"AA": {2000: 10, 2001: 20, 2002: 30}, "BB": {2000: 50, 2001: 60, 2002: 70}})

    preprocessore = addestrato_su(dati)
    matrice = preprocessore.transform(costruisci_feature_storiche(dati))

    assert list(preprocessore.get_feature_names_out()) == [
        "numeriche__anno",
        f"numeriche__{RESA_ANNO_PRIMA}",
        f"numeriche__{RESA_MEDIA_3_ANNI_PRIMA}",
        f"colonie__{COLONIE_ANNO_PRIMA}",
        f"senza_storia__missingindicator_{RESA_ANNO_PRIMA}",
        "stato__codice_stato_AA",
        "stato__codice_stato_BB",
    ]
    assert matrice.shape == (6, 7) and not np.isnan(matrice.astype(float)).any()
    assert list(matrice[:, 4]) == [1, 0, 0, 1, 0, 0]  # il primo anno di ogni stato


def test_mediane_e_scale_si_imparano_solo_dalle_righe_di_addestramento() -> None:
    addestramento = pannello({"AA": {2000: 10, 2001: 20, 2002: 40}})
    preprocessore = addestrato_su(addestramento)
    numeriche = preprocessore.named_transformers_["numeriche"]

    # Rese dell'anno prima nell'addestramento: (mancante), 10, 20 -> mediana 15.
    assert numeriche.named_steps["imputa"].statistics_[1] == pytest.approx(15.0)
    assert numeriche.named_steps["scala"].mean_[0] == pytest.approx(2001.0)

    # Applicato a righe nuove, non cambia: le statistiche restano quelle imparate.
    nuove = costruisci_feature_storiche(pannello({"AA": {2003: 99, 2004: 1}}))
    preprocessore.transform(nuove)
    assert numeriche.named_steps["imputa"].statistics_[1] == pytest.approx(15.0)


def test_le_colonne_escluse_non_entrano_nel_modello() -> None:
    dati = costruisci_feature_storiche(pannello({"AA": {2000: 10, 2001: 20, 2002: 30}}))
    dati["produzione_totale_kg"] = 1.0
    alterato = dati.copy()
    alterato[TARGET] = 999.0
    alterato["numero_colonie"] = 1
    alterato["produzione_totale_kg"] = 1e9

    preprocessore = crea_preprocessore().fit(dati)

    np.testing.assert_array_equal(preprocessore.transform(dati), preprocessore.transform(alterato))


def test_le_colonie_sono_in_logaritmo_con_la_mediana_dei_log_al_posto_dei_mancanti() -> None:
    """Il valore della trasformazione, calcolato a mano con numpy: log1p, mediana, scala."""
    dati = pd.DataFrame(
        {
            "codice_stato": "AA",
            "anno": [2000, 2001, 2002, 2003],
            "numero_colonie": [2_000, 20_000, 200_000, 2_000_000],  # lontane: il logaritmo conta
            TARGET: [10.0, 20.0, 30.0, 40.0],
        }
    )
    preprocessore = addestrato_su(dati)

    matrice = preprocessore.transform(costruisci_feature_storiche(dati))

    colonie_anno_prima = np.log1p(np.array([np.nan, 2_000, 20_000, 200_000]))
    log = np.where(
        np.isnan(colonie_anno_prima), np.nanmedian(colonie_anno_prima), colonie_anno_prima
    )
    attese = (log - log.mean()) / log.std()  # StandardScaler: deviazione standard di popolazione
    posizione = list(preprocessore.get_feature_names_out()).index(f"colonie__{COLONIE_ANNO_PRIMA}")
    np.testing.assert_allclose(matrice[:, posizione], attese)


def test_senza_storia_resta_una_colonna_anche_se_laddestramento_ha_sempre_la_storia() -> None:
    """Il numero di colonne non dipende dai mancanti visti in addestramento."""
    feature = costruisci_feature_storiche(
        pannello({"AA": {2000: 10, 2001: 20, 2002: 30, 2003: 40}})
    )
    preprocessore = crea_preprocessore().fit(feature[feature["anno"] > 2000])  # nessun mancante

    matrice = preprocessore.transform(feature)  # ma qui il 2000 non ha storia

    nome = f"senza_storia__missingindicator_{RESA_ANNO_PRIMA}"
    assert list(matrice[:, list(preprocessore.get_feature_names_out()).index(nome)]) == [1, 0, 0, 0]


def test_uno_stato_mai_visto_non_e_un_errore() -> None:
    preprocessore = addestrato_su(pannello({"AA": {2000: 10, 2001: 20}}))
    nuovo = costruisci_feature_storiche(pannello({"ZZ": {2000: 30, 2001: 31}}))

    matrice = preprocessore.transform(nuovo)

    assert list(matrice[:, -1]) == [0, 0]  # nessuna colonna di stato accesa


def test_il_preprocessore_apre_una_pipeline_di_scikit_learn() -> None:
    dati = pannello({s: {a: base - 0.5 * (a - 2000) for a in range(2000, 2013)}
                     for s, base in (("AA", 40), ("BB", 25), ("CC", 60))})  # fmt: skip
    feature = costruisci_feature_storiche(dati)
    addestramento, verifica = dividi_temporale(feature)

    modello = Pipeline([("prep", crea_preprocessore()), ("modello", LinearRegression())])
    modello.fit(addestramento, addestramento[TARGET])

    # Dati su una retta per stato: stato + anno bastano a prevederli esattamente.
    assert metriche(verifica[TARGET], modello.predict(verifica)).mae_kg == pytest.approx(
        0.0, abs=1e-9
    )


# --------------------------------------------------------------------------- #
# Integration: pannello Q8 dal database di test
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_integrazione_le_feature_sul_pannello_q8(
    database_test: Database, dataset_nel_database: None
) -> None:
    dati = carica_dataset_training(database_test)
    addestramento, verifica = dividi_temporale(dati)

    feature = costruisci_feature_storiche(dati)

    # Mancanti solo nel primo anno di ogni stato; la verifica ha sempre tre anni di storia.
    mancanti = feature[feature[STORICHE].isna().any(axis=1)]
    assert set(mancanti["anno"]) == {1998} and len(mancanti) == 40
    assert not feature.loc[verifica.index, STORICHE].isna().any().any()

    # La resa dell'anno prima, presa come previsione, è la persistenza di M4-T1.
    persistenza = valuta_baseline(dati)[PERSISTENZA]
    come_previsione = metriche(verifica[TARGET], feature.loc[verifica.index, RESA_ANNO_PRIMA])
    assert come_previsione == persistenza

    preprocessore = crea_preprocessore().fit(feature.loc[addestramento.index])
    matrice = preprocessore.transform(feature.loc[verifica.index])
    assert matrice.shape == (120, 5 + 40) and not np.isnan(matrice.astype(float)).any()
