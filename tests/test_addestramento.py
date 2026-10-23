"""Test dell'addestramento e della CLI `scripts/train_model.py`, M4-T7.

Unitari: pannello sintetico, repository finto, CLI con funzioni sostituite. Integration: il
pannello Q8 vero nel database di test; si addestra, si salva, si ricarica e si controlla che
l'addestramento sia riproducibile e che i metadati descrivano il modello committato.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from beewatch.config import RADICE
from beewatch.database import Database
from beewatch.exceptions import DatabaseError, ModelError
from beewatch.ml import addestramento
from beewatch.ml.addestramento import (
    addestra_e_salva,
    addestra_modello_finale,
    crea_metadati,
)
from beewatch.ml.artefatto import (
    controlla_metadati,
    impronta_pannello,
    leggi_metadati,
    percorso_metadati,
    percorso_per_la_tabella,
)
from beewatch.ml.features import FEATURE, TARGET, costruisci_feature_storiche
from beewatch.ml.predictor import Predittore
from beewatch.ml.train import (
    PERSISTENZA,
    RANDOM_FOREST_OTTIMIZZATA,
    carica_dataset_training,
    soddisfa_criterio,
)
from beewatch.ml.valutazione import valuta_finale
from beewatch.repositories_riferimento import ModelliRepository


def pannello(seme: int = 0) -> pd.DataFrame:
    caso = np.random.default_rng(seme)
    righe = [
        {"codice_stato": s, "anno": a, "numero_colonie": 1000 * (i + 1) + a,
         TARGET: 30 + 5 * i - 0.5 * (a - 1998) + caso.normal(0, 3)}
        for i, s in enumerate(("AA", "BB", "CC", "DD", "EE", "FF"))
        for a in range(1998, 2013)
    ]  # fmt: skip
    return pd.DataFrame(righe)


class RepositoryFinto:
    """Registra le chiamate a `registra` invece di scrivere nel database."""

    chiamate: list[dict] = []

    def __init__(self, _database) -> None:
        pass

    def registra(self, riga: dict) -> None:
        RepositoryFinto.chiamate.append(riga)


@pytest.fixture
def senza_database(monkeypatch: pytest.MonkeyPatch):
    RepositoryFinto.chiamate = []
    monkeypatch.setattr(addestramento, "carica_dataset_training", lambda database: pannello())
    monkeypatch.setattr(addestramento, "ModelliRepository", RepositoryFinto)
    return RepositoryFinto


# --------------------------------------------------------------------------- #
# Addestramento e metadati
# --------------------------------------------------------------------------- #


def test_il_modello_salvato_si_addestra_su_tutte_le_righe_con_le_sole_feature() -> None:
    dati = pannello()

    modello = addestra_modello_finale(dati)

    assert tuple(modello.feature_names_in_) == tuple(FEATURE)
    assert modello.named_steps["modello"].n_estimators == 200
    # Ha visto anche il 2010–2012: prevedere un anno di verifica ora è «in campione».
    ingressi = costruisci_feature_storiche(dati)[list(FEATURE)]
    ultime = dati["anno"] >= 2010
    errore_in_campione = np.abs(modello.predict(ingressi[ultime]) - dati.loc[ultime, TARGET]).mean()
    assert errore_in_campione < 3.0


def test_i_metadati_sono_completi_serializzabili_e_coerenti_con_la_valutazione() -> None:
    dati = pannello()
    valutazione = valuta_finale(dati, ripetizioni_importanza=2)
    momento = datetime(2026, 5, 6, 7, 8, 9, 999, tzinfo=UTC)

    metadati = crea_metadati(dati, valutazione, versione="v9", seed=7, addestrato_il=momento)

    json.dumps(metadati)  # nessun tipo di numpy o pandas: si può scrivere come JSON
    controlla_metadati({**metadati, "file": {}}, "prova")
    assert metadati["versione"] == "v9" and metadati["addestrato_il"] == "2026-05-06T07:08:09+00:00"
    assert metadati["iperparametri"] == {
        "n_estimators": 200, "max_depth": None, "min_samples_leaf": 5, "random_state": 7
    }  # fmt: skip
    assert metadati["feature"] == list(FEATURE)
    assert set(metadati["feature_escluse"]) >= {TARGET, "numero_colonie", "produzione_totale_kg"}
    assert metadati["dataset"] == {
        "origine": metadati["dataset"]["origine"],
        "righe": 90, "stati": 6, "anno_minimo": 1998, "anno_massimo": 2012,
        "sha256_pannello": impronta_pannello(dati),
        "sha256_csv_ufficiale": metadati["dataset"]["sha256_csv_ufficiale"],
    }  # fmt: skip
    assert metadati["addestramento"]["righe"] == 90 and metadati["addestramento"]["seed"] == 7


def test_le_metriche_dei_metadati_sono_quelle_del_modello_valutato_fino_al_2009() -> None:
    dati = pannello()
    valutazione = valuta_finale(dati, ripetizioni_importanza=2)
    ris = valutazione.hold_out.risultati()
    finale = ris[RANDOM_FOREST_OTTIMIZZATA]

    metriche = crea_metadati(dati, valutazione)["metriche"]

    hold_out = metriche["hold_out_2010_2012"]
    assert hold_out["addestramento_fino_al"] == 2009 and hold_out["righe"] == 18
    assert (hold_out["mae_kg"], hold_out["rmse_kg"], hold_out["r2"]) == (
        finale.mae_kg, finale.rmse_kg, finale.r2
    )  # fmt: skip
    baseline = {n: m for n, m in ris.items() if n not in valutazione.hold_out.modelli}
    assert set(metriche["baseline_hold_out"]) == set(baseline)
    assert metriche["criterio_da05"] == {
        "modello_mae_kg": finale.mae_kg,
        "persistenza_mae_kg": baseline[PERSISTENZA].mae_kg,
        "soddisfatto": soddisfa_criterio(finale, baseline),
    }
    cv = valutazione.cv.riepilogo()[RANDOM_FOREST_OTTIMIZZATA]
    assert metriche["cross_validation"]["mae_kg"] == {
        "media": cv.media.mae_kg, "dev_std": cv.dev_std.mae_kg
    }  # fmt: skip


def test_lintervallo_e_limportanza_dei_metadati_vengono_dalla_valutazione() -> None:
    dati = pannello()
    valutazione = valuta_finale(dati, ripetizioni_importanza=2)

    metadati = crea_metadati(dati, valutazione)

    assert metadati["intervallo"]["inferiore_kg"] == valutazione.intervallo_finale.inferiore_kg
    assert metadati["intervallo"]["superiore_kg"] == valutazione.intervallo_finale.superiore_kg
    assert metadati["intervallo"]["residui"] == len(valutazione.previsioni)
    assert set(metadati["importanza_variabili"]["valori"]) == set(FEATURE)


# --------------------------------------------------------------------------- #
# addestra_e_salva
# --------------------------------------------------------------------------- #


def test_si_scrivono_i_due_file_e_la_riga_di_modelli(senza_database, tmp_path: Path) -> None:
    percorso = tmp_path / "m.joblib"

    metadati = addestra_e_salva(None, percorso, versione="v-test")

    assert percorso.is_file() and percorso_metadati(percorso).is_file()
    assert leggi_metadati(percorso) == metadati
    assert len(senza_database.chiamate) == 1
    riga = senza_database.chiamate[0]
    assert riga["versione"] == "v-test" and riga["attivo"] is True
    assert riga["mae_kg"] == metadati["metriche"]["hold_out_2010_2012"]["mae_kg"]
    assert riga["percorso_file"] == percorso.resolve().as_posix()  # fuori dalla radice: assoluto


def test_senza_registrazione_non_si_tocca_la_tabella(senza_database, tmp_path: Path) -> None:
    addestra_e_salva(None, tmp_path / "m.joblib", registra=False)
    assert senza_database.chiamate == []


def test_il_percorso_nella_tabella_e_relativo_se_sta_nel_progetto(senza_database) -> None:
    assert percorso_per_la_tabella(RADICE / "models" / "x.joblib") == "models/x.joblib"


def test_il_modello_salvato_si_ricarica_e_prevede_come_quello_addestrato(
    senza_database, tmp_path: Path
) -> None:
    percorso = tmp_path / "m.joblib"
    addestra_e_salva(None, percorso)
    atteso = addestra_modello_finale(pannello())
    ingressi = costruisci_feature_storiche(pannello())[list(FEATURE)]

    previsto = Predittore(percorso).prevedi(ingressi)

    np.testing.assert_array_equal(previsto, atteso.predict(ingressi))


def test_lo_stesso_addestramento_due_volte_da_le_stesse_previsioni_e_la_stessa_impronta(
    senza_database, tmp_path: Path
) -> None:
    primo = addestra_e_salva(None, tmp_path / "a.joblib", registra=False)
    secondo = addestra_e_salva(None, tmp_path / "b.joblib", registra=False)
    ingressi = costruisci_feature_storiche(pannello())[list(FEATURE)]

    np.testing.assert_array_equal(
        Predittore(tmp_path / "a.joblib").prevedi(ingressi),
        Predittore(tmp_path / "b.joblib").prevedi(ingressi),
    )
    assert primo["dataset"]["sha256_pannello"] == secondo["dataset"]["sha256_pannello"]
    assert primo["metriche"] == secondo["metriche"]


def test_un_altro_seed_cambia_il_modello(senza_database, tmp_path: Path) -> None:
    addestra_e_salva(None, tmp_path / "a.joblib", registra=False, seed=1)
    addestra_e_salva(None, tmp_path / "b.joblib", registra=False, seed=2)
    ingressi = costruisci_feature_storiche(pannello())[list(FEATURE)]

    uno = Predittore(tmp_path / "a.joblib").prevedi(ingressi)
    due = Predittore(tmp_path / "b.joblib").prevedi(ingressi)

    assert not np.array_equal(uno, due)


# --------------------------------------------------------------------------- #
# La CLI
# --------------------------------------------------------------------------- #


def carica_script() -> ModuleType:
    percorso = Path(__file__).resolve().parents[1] / "scripts" / "train_model.py"
    specifica = importlib.util.spec_from_file_location("train_model", percorso)
    modulo = importlib.util.module_from_spec(specifica)
    specifica.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    modulo = carica_script()
    configurazione = SimpleNamespace(database=None, percorso_modello=tmp_path / "da_config.joblib")
    monkeypatch.setattr(modulo, "configura", lambda: None)
    monkeypatch.setattr(modulo.config, "ottieni", lambda: configurazione)
    monkeypatch.setattr(modulo, "Database", lambda cfg: None)
    return modulo


def test_la_cli_addestra_nel_percorso_della_configurazione_e_stampa_il_riepilogo(
    script: ModuleType, senza_database, tmp_path: Path, capsys
) -> None:
    esito = script.main([])

    assert esito == 0
    uscita = capsys.readouterr().out
    assert "Modello v1.0.0 salvato in" in uscita and "da_config.joblib" in uscita
    assert "DA-05: MAE" in uscita and "impronta del pannello:" in uscita
    assert (tmp_path / "da_config.joblib").is_file()
    assert len(senza_database.chiamate) == 1  # registrato per impostazione predefinita


def test_la_cli_accetta_percorso_versione_seed_e_nessuna_registrazione(
    script: ModuleType, senza_database, tmp_path: Path
) -> None:
    percorso = tmp_path / "altro" / "m.joblib"

    esito = script.main(
        ["--modello", str(percorso), "--versione", "v2.0.0", "--seed", "3", "--senza-registrazione"]
    )

    assert esito == 0 and senza_database.chiamate == []
    metadati = leggi_metadati(percorso)
    assert metadati["versione"] == "v2.0.0" and metadati["addestramento"]["seed"] == 3


@pytest.mark.parametrize(
    "errore",
    [DatabaseError("Impossibile connettersi al database."), ModelError("Nessun dato USDA.")],
    ids=["database_spento", "senza_dati"],
)
def test_la_cli_esce_con_1_e_non_scrive_niente_se_non_puo_addestrare(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys, errore
) -> None:
    def fallisce(*argomenti, **opzioni):
        raise errore

    monkeypatch.setattr(script, "addestra_e_salva", fallisce)

    esito = script.main(["--modello", str(tmp_path / "m.joblib")])

    assert esito == 1
    assert f"Modello non addestrato: {errore}" in capsys.readouterr().err
    assert not (tmp_path / "m.joblib").exists()


# --------------------------------------------------------------------------- #
# Integration: pannello Q8 dal database di test
# --------------------------------------------------------------------------- #

PERCORSO_COMMITTATO = RADICE / "models" / "produzione_v1.joblib"


def uguali_a_meno_di_rumore(a, b, tolleranza: float = 1e-9) -> None:
    """Dizionari uguali, con i numeri uguali a meno dell'ultima cifra (piattaforme diverse)."""
    if isinstance(a, dict):
        assert a.keys() == b.keys()
        for chiave in a:
            uguali_a_meno_di_rumore(a[chiave], b[chiave], tolleranza)
    elif isinstance(a, float):
        assert a == pytest.approx(b, abs=tolleranza, rel=tolleranza)
    else:
        assert a == b


@pytest.fixture
def modelli_puliti(database_test: Database):
    """La tabella `modelli` del database di test, vuota prima e dopo."""
    with database_test.transazione() as cursore:
        cursore.execute("DELETE FROM modelli")
    yield
    with database_test.transazione() as cursore:
        cursore.execute("DELETE FROM modelli")


@pytest.mark.integration
def test_integrazione_si_addestra_dal_database_e_si_ricarica_identico(
    database_test: Database, dataset_nel_database: None, modelli_puliti: None, tmp_path: Path
) -> None:
    percorso = tmp_path / "m.joblib"

    metadati = addestra_e_salva(database_test, percorso, versione="v-integrazione")

    # Il file e la tabella dicono le stesse cose (DA-05, DA-06).
    riga = ModelliRepository(database_test).attivo()
    hold_out = metadati["metriche"]["hold_out_2010_2012"]
    assert riga["versione"] == "v-integrazione" and riga["attivo"] is True
    assert float(riga["mae_kg"]) == pytest.approx(hold_out["mae_kg"], abs=5e-4)  # DECIMAL(6,3)
    assert float(riga["r2"]) == pytest.approx(hold_out["r2"], abs=5e-5)  # DECIMAL(5,4)
    assert riga["righe_addestramento"] == 600 and riga["variabili_usate"] == list(FEATURE)
    assert riga["percorso_file"] == percorso.resolve().as_posix()

    # Il modello ricaricato produce le predizioni del modello addestrato di nuovo.
    dati = carica_dataset_training(database_test)
    ingressi = costruisci_feature_storiche(dati)[list(FEATURE)]
    np.testing.assert_array_equal(
        Predittore(percorso).prevedi(ingressi), addestra_modello_finale(dati).predict(ingressi)
    )


@pytest.mark.integration
def test_integrazione_i_metadati_committati_descrivono_questo_database(
    database_test: Database, dataset_nel_database: None
) -> None:
    """Il modello in `models/` è stato addestrato sugli stessi dati che MySQL ha adesso."""
    committati = leggi_metadati(PERCORSO_COMMITTATO)
    dati = carica_dataset_training(database_test)

    assert committati["dataset"]["sha256_pannello"] == impronta_pannello(dati)
    valutazione = valuta_finale(dati)
    ricalcolati = crea_metadati(dati, valutazione)
    # Il training si rifà con gli stessi numeri.
    for sezione in ("metriche", "intervallo", "importanza_variabili"):
        uguali_a_meno_di_rumore(ricalcolati[sezione], committati[sezione])
    ingressi = costruisci_feature_storiche(dati)[list(FEATURE)]
    np.testing.assert_allclose(
        Predittore(PERCORSO_COMMITTATO).prevedi(ingressi),
        addestra_modello_finale(dati).predict(ingressi),
        atol=1e-9,
    )
