"""Test di `scripts/genera_grafici.py` (M4-T6): i grafici si scrivono, la CLI gestisce l'errore.

Non si controlla il disegno pixel per pixel: si verifica che i cinque file esistano, siano PNG
veri e non vuoti, che la CLI usi la valutazione senza ricalcolare nulla da sé e che, senza dati,
esca con 1 senza scrivere niente.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from beewatch.exceptions import DatabaseError
from beewatch.ml.features import TARGET
from beewatch.ml.valutazione import ValutazioneFinale, valuta_finale

NOMI = [
    "previsto_vs_reale.png",
    "residui.png",
    "importanza_variabili.png",
    "distribuzione_target.png",
    "mae_per_periodo.png",
]
FIRMA_PNG = b"\x89PNG\r\n\x1a\n"


def carica_script() -> ModuleType:
    percorso = Path(__file__).resolve().parents[1] / "scripts" / "genera_grafici.py"
    specifica = importlib.util.spec_from_file_location("genera_grafici", percorso)
    modulo = importlib.util.module_from_spec(specifica)
    specifica.loader.exec_module(modulo)
    return modulo


def pannello(seme: int = 0) -> pd.DataFrame:
    caso = np.random.default_rng(seme)
    righe = [
        {"codice_stato": s, "anno": a, "numero_colonie": 1000 * (i + 1) + a,
         TARGET: 30 + 5 * i - 0.5 * (a - 1998) + caso.normal(0, 3)}
        for i, s in enumerate(("AA", "BB", "CC", "DD", "EE", "FF"))
        for a in range(1998, 2013)
    ]  # fmt: skip
    return pd.DataFrame(righe)


@pytest.fixture(scope="module")
def script() -> ModuleType:
    return carica_script()


@pytest.fixture(scope="module")
def valutazione() -> ValutazioneFinale:
    return valuta_finale(pannello(), ripetizioni_importanza=2)


def controlla_png(percorsi: list[Path]) -> None:
    assert [p.name for p in percorsi] == NOMI
    for percorso in percorsi:
        contenuto = percorso.read_bytes()
        assert contenuto.startswith(FIRMA_PNG), percorso.name
        assert len(contenuto) > 5_000, percorso.name  # non un'immagine vuota


def test_i_cinque_grafici_sono_png_veri(
    script: ModuleType, valutazione: ValutazioneFinale, tmp_path: Path
) -> None:
    cartella = tmp_path / "nuova" / "images"  # la cartella viene creata

    percorsi = script.disegna_tutti(valutazione, pannello(), cartella)

    controlla_png(percorsi)
    assert sorted(p.name for p in cartella.iterdir()) == sorted(NOMI)


def test_rigenerare_sovrascrive_senza_errori(
    script: ModuleType, valutazione: ValutazioneFinale, tmp_path: Path
) -> None:
    script.disegna_tutti(valutazione, pannello(), tmp_path)
    controlla_png(script.disegna_tutti(valutazione, pannello(), tmp_path))


def test_i_numeri_si_scrivono_con_la_virgola_e_il_segno_meno() -> None:
    script = carica_script()
    assert script._decimali(3.4986) == "3,50"
    assert script._decimali(-5.7137, 1) == "−5,7"


def test_main_scrive_i_grafici_con_i_dati_del_database(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setattr(script, "configura", lambda: None)
    monkeypatch.setattr(script.config, "ottieni", lambda: SimpleNamespace(database=None))
    monkeypatch.setattr(script, "Database", lambda configurazione: None)
    monkeypatch.setattr(script, "carica_dataset_training", lambda database: pannello())

    esito = script.main(["--cartella", str(tmp_path / "grafici")])

    assert esito == 0
    uscita = capsys.readouterr().out.splitlines()
    assert [Path(riga).name for riga in uscita] == NOMI
    assert all(Path(riga).is_file() for riga in uscita)


def test_main_senza_dati_esce_con_1_e_non_scrive_niente(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    def database_spento(_database):
        raise DatabaseError("Impossibile connettersi al database.")

    monkeypatch.setattr(script, "configura", lambda: None)
    monkeypatch.setattr(script.config, "ottieni", lambda: SimpleNamespace(database=None))
    monkeypatch.setattr(script, "Database", lambda configurazione: None)
    monkeypatch.setattr(script, "carica_dataset_training", database_spento)

    esito = script.main(["--cartella", str(tmp_path / "grafici")])

    assert esito == 1
    assert "Grafici non generati: Impossibile connettersi" in capsys.readouterr().err
    assert not (tmp_path / "grafici").exists()
