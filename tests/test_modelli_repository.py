"""Test di integrazione di `ModelliRepository` (M4-T7), su MySQL vero nello stack isolato.

La tabella `modelli` ha una regola che solo il database può garantire: al massimo un modello
attivo (indice univoco su una colonna generata). Qui si verifica che `registra` la rispetti, che
una versione ripetuta si aggiorni e non si duplichi, e che le colonne JSON tornino come dati.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from beewatch.database import Database
from beewatch.exceptions import DatabaseError
from beewatch.repositories_riferimento import COLONNE_MODELLI, ModelliRepository

pytestmark = pytest.mark.integration


def riga(versione: str = "v-prova", **modifiche) -> dict:
    base = {
        "versione": versione,
        "algoritmo": "RandomForestRegressor",
        "addestrato_il": datetime(2026, 10, 23, 12, 0, 0),
        "righe_addestramento": 600,
        "variabili_usate": json.dumps(["codice_stato", "anno"]),
        "importanza_variabili": json.dumps({"codice_stato": 0.5, "anno": 0.0}),
        "mae_kg": 3.499,
        "rmse_kg": 4.483,
        "r2": 0.6236,
        "percorso_file": "models/prova.joblib",
        "attivo": True,
        "note": "prova",
    }
    return {**base, **modifiche}


@pytest.fixture
def repository(database_test: Database):
    with database_test.transazione() as cursore:
        cursore.execute("DELETE FROM modelli")
    yield ModelliRepository(database_test)
    with database_test.transazione() as cursore:
        cursore.execute("DELETE FROM modelli")


def test_senza_modelli_non_ce_un_attivo(repository: ModelliRepository) -> None:
    assert repository.attivo() is None
    assert repository.trova("v-prova") is None


def test_si_registra_un_modello_e_lo_si_rilegge(repository: ModelliRepository) -> None:
    repository.registra(riga())

    modello = repository.attivo()

    assert modello["versione"] == "v-prova" and modello["attivo"] is True
    assert modello["algoritmo"] == "RandomForestRegressor" and modello["righe_addestramento"] == 600
    assert float(modello["mae_kg"]) == 3.499 and float(modello["r2"]) == 0.6236
    assert modello["addestrato_il"] == datetime(2026, 10, 23, 12, 0, 0)
    assert modello["percorso_file"] == "models/prova.joblib" and modello["note"] == "prova"
    # Le colonne JSON tornano come dati, non come testo.
    assert modello["variabili_usate"] == ["codice_stato", "anno"]
    assert modello["importanza_variabili"] == {"codice_stato": 0.5, "anno": 0.0}
    assert repository.trova("v-prova") == modello


def test_una_nuova_versione_diventa_lunica_attiva(repository: ModelliRepository) -> None:
    repository.registra(riga("v1"))
    repository.registra(riga("v2", mae_kg=3.2))

    assert repository.attivo()["versione"] == "v2"
    assert repository.trova("v1")["attivo"] is False  # disattivata, non cancellata
    assert float(repository.trova("v2")["mae_kg"]) == 3.2


def test_registrare_di_nuovo_la_stessa_versione_la_aggiorna(repository: ModelliRepository) -> None:
    repository.registra(riga("v1", righe_addestramento=500))
    repository.registra(riga("v1", righe_addestramento=600, note="riaddestrato"))

    modello = repository.trova("v1")

    assert modello["righe_addestramento"] == 600 and modello["note"] == "riaddestrato"
    assert modello["attivo"] is True


def test_si_puo_riattivare_una_versione_precedente(repository: ModelliRepository) -> None:
    repository.registra(riga("v1"))
    repository.registra(riga("v2"))
    repository.registra(riga("v1"))

    assert repository.attivo()["versione"] == "v1"
    assert repository.trova("v2")["attivo"] is False


def test_il_database_rifiuta_due_modelli_attivi(
    repository: ModelliRepository, database_test: Database
) -> None:
    """La regola «uno solo attivo» sta nello schema: anche una scrittura diretta la rispetta."""
    repository.registra(riga("v1"))

    with pytest.raises(DatabaseError):
        with database_test.transazione() as cursore:
            cursore.execute("UPDATE modelli SET attivo = FALSE")
            cursore.execute(
                "INSERT INTO modelli (versione, algoritmo, addestrato_il, righe_addestramento, "
                "variabili_usate, mae_kg, rmse_kg, r2, percorso_file, attivo) VALUES "
                "('a', 'x', NOW(), 1, '[]', 1, 1, 0.5, 'a', TRUE), "
                "('b', 'x', NOW(), 1, '[]', 1, 1, 0.5, 'b', TRUE)"
            )
    assert repository.attivo()["versione"] == "v1"  # la transazione è stata annullata


def test_la_riga_ha_tutte_le_colonne_che_il_repository_scrive() -> None:
    assert tuple(riga()) == COLONNE_MODELLI
