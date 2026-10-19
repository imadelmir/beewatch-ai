"""Il dataset USDA del repository (`data/honeyproduction.csv`, DA-04).

Il file è versionato perché la licenza (CC0) lo permette; questi test
garantiscono che sia **proprio** la versione documentata in `data/README.md` e
che l'ETL lo tratti come prevedono M2 e M3: niente database, girano ovunque.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from beewatch.etl import (
    SHA256_DATASET_UFFICIALE,
    STATI_AMMESSI,
    conteggio_scarti,
    extract,
    impronta,
    transform,
)

RADICE = Path(__file__).resolve().parents[1]
DATASET = RADICE / "data" / "honeyproduction.csv"


def test_il_dataset_e_nel_repository_con_il_checksum_documentato() -> None:
    assert DATASET.is_file()
    assert hashlib.sha256(DATASET.read_bytes()).hexdigest() == SHA256_DATASET_UFFICIALE
    assert impronta(DATASET) == SHA256_DATASET_UFFICIALE
    assert SHA256_DATASET_UFFICIALE in (RADICE / "data" / "README.md").read_text(encoding="utf-8")


def test_il_file_e_utf8_senza_bom_con_fine_riga_lf() -> None:
    contenuto = DATASET.read_bytes()
    assert not contenuto.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in contenuto  # .gitattributes lo tiene LF: il checksum non cambia col sistema
    contenuto.decode("utf-8")


def test_forma_626_righe_8_colonne_44_stati_15_anni() -> None:
    grezzo = extract(DATASET)
    assert grezzo.shape == (626, 8)
    assert set(grezzo["state"]) == STATI_AMMESSI
    assert sorted(grezzo["year"].unique()) == list(range(1998, 2013))
    assert not grezzo.isna().any().any()  # dati.md: nessun valore mancante
    assert not grezzo.duplicated(["state", "year"]).any()  # né chiavi duplicate


def test_letl_non_scarta_nulla_e_segnala_solo_nebraska_2006(caplog) -> None:
    """dati.md: «il lavoro di pulizia sarà di conversione e normalizzazione, non di scarto»."""
    caplog.set_level("WARNING", logger="beewatch.etl")
    puliti, scartati = transform(extract(DATASET), anno_corrente=2026)
    assert len(puliti) == 626 and conteggio_scarti(scartati) == {}
    assert [r.getMessage() for r in caplog.records] == [
        "Scorte superiori alla produzione: NE 2006. La riga resta (regola R11)."
    ]


@pytest.mark.parametrize(
    "stato,anno,resa,produzione,scorte,prezzo",
    [
        ("AL", 1998, 32.2051, 515_280.93, 72_121.19, 1.5873),
        ("IA", 2005, 39.9161, 1_117_651.60, 558_825.80, 2.6676),
        ("WY", 2012, 23.1332, 1_156_660.54, 208_198.90, 4.1226),
    ],
)
def test_le_tre_righe_di_dati_md_sul_file_vero(
    stato: str, anno: int, resa: float, produzione: float, scorte: float, prezzo: float
) -> None:
    puliti, _ = transform(extract(DATASET), anno_corrente=2026)
    riga = puliti[(puliti["codice_stato"] == stato) & (puliti["anno"] == anno)].iloc[0]
    assert riga["resa_per_colonia_kg"] == pytest.approx(resa, abs=5e-5)
    assert riga["produzione_totale_kg"] == pytest.approx(produzione, abs=5e-3)
    assert riga["scorte_kg"] == pytest.approx(scorte, abs=5e-3)
    assert riga["prezzo_per_kg_usd"] == pytest.approx(prezzo, abs=5e-5)


def test_quaranta_stati_con_la_serie_completa_e_quattro_parziali() -> None:
    """R10 (anomalia A1): SC, MD, OK, NV hanno meno di 15 anni e restano nel dataset."""
    anni = extract(DATASET).groupby("state").size()
    assert (anni == 15).sum() == 40
    assert anni[anni < 15].to_dict() == {"MD": 6, "NV": 11, "OK": 6, "SC": 3}


def test_il_fixture_dei_test_non_e_il_dataset() -> None:
    mini = RADICE / "tests" / "fixtures" / "honey_mini.csv"
    assert impronta(mini) != SHA256_DATASET_UFFICIALE
