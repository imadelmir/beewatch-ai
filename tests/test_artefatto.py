"""Test del formato dell'artefatto, M4-T7: i due file, i metadati, la riga di `modelli`.

Unitari: valori calcolati a mano e l'artefatto sintetico di `conftest.py` (un modello vero).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from beewatch.exceptions import ModelError
from beewatch.ml.artefatto import (
    COMANDO_ADDESTRAMENTO,
    SCHEMA_ARTEFATTO,
    SEZIONI_OBBLIGATORIE,
    controlla_metadati,
    impronta_pannello,
    leggi_metadati,
    percorso_metadati,
    riga_tabella_modelli,
    scrivi_artefatto,
    sha256_file,
    versioni_ambiente,
)
from beewatch.ml.features import FEATURE, TARGET
from beewatch.repositories_riferimento import COLONNE_MODELLI


def test_il_json_sta_accanto_al_joblib_con_lo_stesso_nome() -> None:
    assert percorso_metadati(Path("models/produzione_v1.joblib")) == Path(
        "models/produzione_v1.json"
    )


def test_sha256_di_un_file_noto(tmp_path: Path) -> None:
    file = tmp_path / "abc.bin"
    file.write_bytes(b"abc")
    assert sha256_file(file) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def pannello_piccolo() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "codice_stato": ["BB", "AA", "AA"],
            "anno": [1998, 1999, 1998],
            "numero_colonie": [10, 20, 30],
            TARGET: [1.5, 2.25, 3.0],
        }
    )


def test_limpronta_del_pannello_non_dipende_da_ordine_ne_da_colonne_extra() -> None:
    base = pannello_piccolo()
    rimescolato = base.sample(frac=1, random_state=2).assign(altro="x")
    assert impronta_pannello(base) == impronta_pannello(rimescolato)


def test_limpronta_del_pannello_cambia_se_cambia_un_valore_ma_non_oltre_i_quattro_decimali() -> (
    None
):
    base = pannello_piccolo()
    cambiato = base.copy()
    cambiato.loc[0, TARGET] = 1.6
    rumore = base.copy()
    rumore.loc[0, TARGET] = 1.5 + 1e-7  # sotto la precisione di produzione_usda

    assert impronta_pannello(base) != impronta_pannello(cambiato)
    assert impronta_pannello(base) == impronta_pannello(rumore)
    assert len(impronta_pannello(base)) == 64


def test_le_versioni_dellambiente_comprendono_le_librerie_del_formato() -> None:
    assert set(versioni_ambiente()) == {"python", "scikit-learn", "pandas", "numpy", "joblib"}


def test_si_scrivono_due_file_con_lo_sha256_del_joblib(artefatto_sintetico) -> None:
    percorso = artefatto_sintetico.percorso
    testo = percorso_metadati(percorso).read_bytes()

    assert b"\r" not in testo and testo.endswith(b"\n")  # sempre LF
    metadati = json.loads(testo)
    assert metadati == artefatto_sintetico.metadati
    assert metadati["file"] == {"joblib": "prova.joblib", "sha256_joblib": sha256_file(percorso)}
    assert [s for s in SEZIONI_OBBLIGATORIE if s not in metadati] == []


def test_il_modello_salvato_ricaricato_prevede_come_quello_in_memoria(artefatto_sintetico) -> None:
    from beewatch.ml.features import costruisci_feature_storiche

    ingressi = costruisci_feature_storiche(artefatto_sintetico.dati)[list(FEATURE)]
    ricaricato = joblib.load(artefatto_sintetico.percorso)  # scritto dalla fixture: fidato
    np.testing.assert_array_equal(
        ricaricato.predict(ingressi), artefatto_sintetico.modello.predict(ingressi)
    )


def test_leggere_i_metadati_restituisce_quanto_scritto(artefatto_sintetico) -> None:
    assert leggi_metadati(artefatto_sintetico.percorso) == artefatto_sintetico.metadati


def test_senza_il_json_lerrore_dice_come_addestrare(tmp_path: Path) -> None:
    with pytest.raises(ModelError, match="Mancano i metadati") as errore:
        leggi_metadati(tmp_path / "assente.joblib")
    assert COMANDO_ADDESTRAMENTO in str(errore.value)


def test_un_json_non_valido_e_un_model_error(tmp_path: Path) -> None:
    percorso = tmp_path / "rotto.joblib"
    percorso_metadati(percorso).write_text("{non è json", encoding="utf-8")
    with pytest.raises(ModelError, match="non sono leggibili"):
        leggi_metadati(percorso)


@pytest.mark.parametrize("contenuto", [[1, 2], "testo", 3], ids=["lista", "testo", "numero"])
def test_i_metadati_devono_essere_un_oggetto(contenuto: object) -> None:
    with pytest.raises(ModelError, match="non sono un oggetto"):
        controlla_metadati(contenuto, "prova.json")


def test_le_sezioni_mancanti_si_elencano(artefatto_sintetico) -> None:
    metadati = {
        k: v for k, v in artefatto_sintetico.metadati.items() if k not in {"intervallo", "feature"}
    }
    with pytest.raises(ModelError, match="mancano feature, intervallo") as errore:
        controlla_metadati(metadati, "prova.json")
    assert COMANDO_ADDESTRAMENTO in str(errore.value)


def test_uno_schema_sconosciuto_e_rifiutato(artefatto_sintetico) -> None:
    metadati = {**artefatto_sintetico.metadati, "schema": SCHEMA_ARTEFATTO + 1}
    with pytest.raises(ModelError, match="schema"):
        controlla_metadati(metadati, "prova.json")


def test_la_riga_della_tabella_modelli_viene_dai_metadati(artefatto_sintetico) -> None:
    metadati = artefatto_sintetico.metadati

    riga = riga_tabella_modelli(metadati, "models/prova.joblib")

    assert tuple(riga) == COLONNE_MODELLI
    hold_out = metadati["metriche"]["hold_out_2010_2012"]
    assert (riga["mae_kg"], riga["rmse_kg"], riga["r2"]) == (
        hold_out["mae_kg"], hold_out["rmse_kg"], hold_out["r2"]
    )  # fmt: skip
    assert riga["versione"] == "v0.0.1-prova" and riga["attivo"] is True
    assert riga["righe_addestramento"] == len(artefatto_sintetico.dati)
    assert riga["percorso_file"] == "models/prova.joblib"
    assert riga["addestrato_il"] == datetime(2026, 1, 1, 12, 0)  # UTC, senza fuso
    assert json.loads(riga["variabili_usate"]) == list(FEATURE)
    importanza = json.loads(riga["importanza_variabili"])
    assert set(importanza) == set(FEATURE)
    assert all(isinstance(valore, float) for valore in importanza.values())
    assert riga["note"] == metadati["addestramento"]["strategia"]


def test_scrivere_in_una_cartella_nuova_la_crea(artefatto_sintetico, tmp_path: Path) -> None:
    percorso = tmp_path / "nuova" / "cartella" / "m.joblib"
    scrivi_artefatto(artefatto_sintetico.modello, {"versione": "x"}, percorso)
    assert percorso.is_file() and percorso_metadati(percorso).is_file()
