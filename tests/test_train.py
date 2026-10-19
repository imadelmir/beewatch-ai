"""Test del training, parte M4-T1: dataset dal database, split temporale, metriche, baseline.

Unitari: metriche e baseline su piccoli pannelli costruiti a mano, dove il
risultato giusto si sa in anticipo. Il caricamento dal database con un
repository finto.

Integration: il dataset vero caricato con l'ETL nel database di test dello stack
Docker; le baseline calcolate da lì sono i numeri della model card
(`docs/model_card.md`), che così si possono rifare.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from beewatch.database import Database
from beewatch.etl import STATI_AMMESSI, extract, load, transform
from beewatch.exceptions import ModelError
from beewatch.ml import train
from beewatch.ml.train import (
    MEDIA_GLOBALE,
    MEDIA_STATO,
    MEDIA_STATO_TREND,
    PERSISTENZA,
    TARGET,
    Metriche,
    carica_dataset_training,
    dividi_temporale,
    metriche,
    migliore_baseline,
    previsioni_baseline,
    valuta_baseline,
)

RADICE = Path(__file__).resolve().parents[1]


def pannello(valori: dict[str, dict[int, float]]) -> pd.DataFrame:
    righe = [
        {"codice_stato": s, "anno": a, "numero_colonie": 1000, TARGET: float(r)}
        for s, anni in valori.items()
        for a, r in anni.items()
    ]
    return pd.DataFrame(righe)


# --------------------------------------------------------------------------- #
# Metriche
# --------------------------------------------------------------------------- #


def test_metriche_su_valori_calcolati_a_mano() -> None:
    risultato = metriche([10, 20, 30], [12, 18, 33])  # errori +2, -2, +3
    assert risultato.mae_kg == pytest.approx(7 / 3)
    assert risultato.rmse_kg == pytest.approx(math.sqrt(17 / 3))
    assert risultato.r2 == pytest.approx(1 - 17 / 200)  # SSres 17, SStot 200


def test_previsione_perfetta() -> None:
    assert metriche([1.5, 2.5, 4.0], [1.5, 2.5, 4.0]) == Metriche(0.0, 0.0, 1.0)


def test_r2_negativo_se_peggio_della_media() -> None:
    assert metriche([1, 2, 3], [3, 2, 1]).r2 == pytest.approx(-3.0)


def test_r2_non_definito_se_il_vero_e_costante() -> None:
    assert math.isnan(metriche([5, 5], [4, 6]).r2)


@pytest.mark.parametrize(
    "vero,previsto",
    [([1, 2], [1]), ([], []), ([1, 2], [1, float("nan")])],
    ids=["lunghezze_diverse", "vuoto", "previsione_mancante"],
)
def test_metriche_rifiutano_ingressi_non_validi(vero: list, previsto: list) -> None:
    with pytest.raises(ModelError):
        metriche(vero, previsto)


# --------------------------------------------------------------------------- #
# Split temporale
# --------------------------------------------------------------------------- #


def test_lo_split_e_temporale_2009_in_addestramento_2010_in_verifica() -> None:
    dati = pannello({"AA": {a: 30 for a in range(2007, 2013)}})
    addestramento, verifica = dividi_temporale(dati)
    assert list(addestramento["anno"]) == [2007, 2008, 2009]
    assert list(verifica["anno"]) == [2010, 2011, 2012]
    assert addestramento["anno"].max() < verifica["anno"].min()  # nessun anno in comune


@pytest.mark.parametrize("ultimo", [2005, 2012], ids=["addestramento_vuoto", "verifica_vuota"])
def test_uno_split_che_lascia_una_parte_vuota_e_un_errore(ultimo: int) -> None:
    with pytest.raises(ModelError, match="vuot"):
        dividi_temporale(pannello({"AA": {2008: 1, 2012: 2}}).query("anno > 2005"), ultimo)


# --------------------------------------------------------------------------- #
# Baseline, su pannelli dove la risposta si conosce
# --------------------------------------------------------------------------- #


def test_le_quattro_baseline_su_un_pannello_calcolato_a_mano() -> None:
    # AA: 10, 12, 14 nell'addestramento (2007-2009), 16 nel 2010; BB: 30, 30, 30, poi 27.
    dati = pannello({"AA": {2007: 10, 2008: 12, 2009: 14, 2010: 16},
                     "BB": {2007: 30, 2008: 30, 2009: 30, 2010: 27}})  # fmt: skip
    addestramento, verifica = dividi_temporale(dati)

    previsioni = previsioni_baseline(addestramento, verifica, dati)

    assert list(previsioni[MEDIA_GLOBALE]) == [21.0, 21.0]  # (36 + 90) / 6
    assert list(previsioni[MEDIA_STATO]) == [12.0, 30.0]
    # Pendenza comune: scarti di AA (-2, 0, +2) e di BB (0, 0, 0) contro gli anni
    # (-1, 0, +1): (2 + 2) / (1 + 1 + 1 + 1) = 1 kg l'anno; dal 2008 al 2010, +2.
    assert list(previsioni[MEDIA_STATO_TREND]) == pytest.approx([14.0, 32.0])
    assert list(previsioni[PERSISTENZA]) == [14.0, 30.0]  # il 2009 dello stesso stato


def test_la_tendenza_e_perfetta_se_i_dati_sono_una_retta() -> None:
    dati = pannello({s: {a: base - 0.5 * (a - 2000) for a in range(2000, 2013)}
                     for s, base in (("AA", 40), ("BB", 25), ("CC", 60))})  # fmt: skip
    risultati = valuta_baseline(dati)
    assert risultati[MEDIA_STATO_TREND].mae_kg == pytest.approx(0.0, abs=1e-9)
    assert risultati[PERSISTENZA].mae_kg == pytest.approx(0.5)  # un anno di pendenza in ritardo


def test_la_persistenza_usa_la_resa_vera_dellanno_prima_anche_nella_verifica() -> None:
    """Per il 2011 la persistenza usa il 2010 vero: si prevede un anno alla volta."""
    dati = pannello({"AA": {2008: 10, 2009: 20, 2010: 30, 2011: 40}})
    addestramento, verifica = dividi_temporale(dati)
    assert list(previsioni_baseline(addestramento, verifica, dati)[PERSISTENZA]) == [20.0, 30.0]


def test_medie_e_tendenza_non_guardano_la_verifica() -> None:
    """Cambiare i valori della verifica non deve cambiare le previsioni (nessun leakage)."""
    base = pannello({"AA": {2007: 10, 2008: 12, 2009: 14, 2010: 16, 2011: 18}})
    alterato = base.copy()
    alterato.loc[alterato["anno"] >= 2010, TARGET] = 999.0
    previsioni = [previsioni_baseline(*dividi_temporale(d), d) for d in (base, alterato)]
    for nome in (MEDIA_GLOBALE, MEDIA_STATO, MEDIA_STATO_TREND):
        assert list(previsioni[0][nome]) == list(previsioni[1][nome]), nome


@pytest.mark.parametrize(
    "valori",
    [
        {"AA": {2008: 10, 2009: 12}, "BB": {2010: 20}},  # stato mai visto in addestramento
        {"AA": {2008: 10, 2009: 12, 2011: 14}},  # manca l'anno prima (2010)
    ],
    ids=["stato_nuovo", "anno_precedente_mancante"],
)
def test_una_baseline_che_non_si_puo_calcolare_e_un_errore(valori: dict) -> None:
    with pytest.raises(ModelError, match="anno precedente|addestramento"):
        valuta_baseline(pannello(valori))


def test_la_migliore_baseline_e_quella_con_il_mae_minore() -> None:
    risultati = {"a": Metriche(5, 6, 0.1), "b": Metriche(4, 7, 0.0), "c": Metriche(4.5, 5, 0.3)}
    assert migliore_baseline(risultati) == ("b", Metriche(4, 7, 0.0))


# --------------------------------------------------------------------------- #
# Dataset dal database (repository finto)
# --------------------------------------------------------------------------- #


class RepositoryFinto:
    righe: list[dict] = []

    def __init__(self, _database) -> None:
        pass

    def dati_addestramento(self) -> list[dict]:
        return self.righe


def test_il_dataset_viene_dal_repository_con_tipi_numerici(monkeypatch) -> None:
    RepositoryFinto.righe = [
        {"codice_stato": "AL", "anno": 1998, "numero_colonie": 16000,
         "resa_per_colonia_kg": Decimal("32.2051")},
    ]  # fmt: skip
    monkeypatch.setattr(train, "ProduzioneUsdaRepository", RepositoryFinto)

    dati = carica_dataset_training(Database.__new__(Database))

    assert list(dati.columns) == ["codice_stato", "anno", "numero_colonie", TARGET]
    assert dati.loc[0, TARGET] == pytest.approx(32.2051)
    assert dati[TARGET].dtype == "float64" and dati["anno"].dtype == "int64"


def test_database_senza_dati_usda_errore_che_dice_cosa_fare(monkeypatch) -> None:
    RepositoryFinto.righe = []
    monkeypatch.setattr(train, "ProduzioneUsdaRepository", RepositoryFinto)
    with pytest.raises(ModelError, match="run_etl.py"):
        carica_dataset_training(Database.__new__(Database))


def test_in_beewatch_ml_non_si_legge_mai_il_csv() -> None:
    """Requisito: il training legge dal database (MySQL è lo storage primario)."""
    for file in (RADICE / "beewatch" / "ml").rglob("*.py"):
        testo = file.read_text(encoding="utf-8")
        assert "read_csv" not in testo and "honeyproduction" not in testo, file.name


# --------------------------------------------------------------------------- #
# Integration: dataset vero, nel database di test
# --------------------------------------------------------------------------- #

DATASET = RADICE / "data" / "honeyproduction.csv"

# I numeri della model card (docs/model_card.md), sul pannello Q8 dal database.
ATTESI_Q8 = {
    MEDIA_GLOBALE: (6.655, 8.371, -0.313),
    MEDIA_STATO: (5.727, 6.798, 0.134),
    MEDIA_STATO_TREND: (4.168, 5.435, 0.447),
    PERSISTENZA: (4.063, 5.296, 0.474),
}


@pytest.fixture
def dataset_nel_database(database_test: Database) -> Iterator[None]:
    """Carica il dataset vero con l'ETL; alla fine toglie le righe caricate (tutte)."""
    puliti, _ = transform(extract(DATASET), anno_corrente=2026)
    load(puliti, database_test)
    yield
    segnaposto = ", ".join(["%s"] * len(STATI_AMMESSI))
    with database_test.transazione() as cursore:
        cursore.execute(
            f"DELETE FROM produzione_usda WHERE codice_stato IN ({segnaposto})",
            tuple(sorted(STATI_AMMESSI)),
        )


@pytest.mark.integration
def test_integrazione_il_dataset_di_training_e_il_pannello_q8(
    database_test: Database, dataset_nel_database: None
) -> None:
    dati = carica_dataset_training(database_test)

    assert len(dati) == 600 and dati["codice_stato"].nunique() == 40
    assert set(dati.groupby("codice_stato").size()) == {15}
    assert not {"MD", "NV", "OK", "SC"} & set(dati["codice_stato"])  # R10: serie parziali fuori
    addestramento, verifica = dividi_temporale(dati)
    assert (len(addestramento), len(verifica)) == (480, 120)


@pytest.mark.integration
def test_integrazione_le_baseline_della_model_card(
    database_test: Database, dataset_nel_database: None
) -> None:
    risultati = valuta_baseline(carica_dataset_training(database_test))

    for nome, (mae, rmse, r2) in ATTESI_Q8.items():
        assert risultati[nome].mae_kg == pytest.approx(mae, abs=5e-4), nome
        assert risultati[nome].rmse_kg == pytest.approx(rmse, abs=5e-4), nome
        assert risultati[nome].r2 == pytest.approx(r2, abs=5e-4), nome
    assert migliore_baseline(risultati)[0] == PERSISTENZA


@pytest.mark.integration
def test_integrazione_sulle_626_righe_si_ritrovano_i_numeri_di_m2_t3(
    database_test: Database, dataset_nel_database: None
) -> None:
    """Controllo incrociato: con tutti gli stati (come in M2-T3) e lo stesso codice."""
    with database_test.transazione() as cursore:
        cursore.execute(
            "SELECT codice_stato, anno, numero_colonie, resa_per_colonia_kg FROM produzione_usda"
        )
        tutti = pd.DataFrame(cursore.fetchall()).astype({TARGET: "float64"})
    assert len(tutti) == 626

    risultati = valuta_baseline(tutti)

    assert round(risultati[MEDIA_GLOBALE].mae_kg, 2) == 6.46  # M2-T3: 6,46
    assert round(risultati[MEDIA_STATO].mae_kg, 2) == 5.73  # M2-T3: 5,73
    assert round(risultati[PERSISTENZA].mae_kg, 2) == 4.06  # verifica del 6/10: 4,06
    # M2-T3 dichiara 4,25 senza definire come stimava la pendenza; con quella di
    # questo codice (comune, sugli scarti dalla media dello stato) il valore è 4,17.
    assert round(risultati[MEDIA_STATO_TREND].mae_kg, 2) == 4.17
    assert np.isclose(risultati[MEDIA_GLOBALE].r2, -0.257, atol=5e-4)
