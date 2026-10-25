"""Test di integrazione dei riepiloghi AI (M5-T5), su MySQL vero nello stack isolato.

Il database fa tre cose che solo lui può garantire: le cascate (un riepilogo contiene il testo
delle note e sparisce con l'ispezione o con l'utente), i valori ammessi di `stato_salute` e
`confidenza`, e il JSON che torna identico. Qui si verifica anche il servizio intero, con il
seed vero e un modello di linguaggio finto: il flusso ispezione → contesto → riepilogo → riga.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from datetime import date, timedelta

import pytest
from llm_fake import LLMFinto

from beewatch.database import Database
from beewatch.exceptions import DatabaseError, ValidationError
from beewatch.models import Alveare, Apiario, Ispezione, LivelloRischio, StatoAlveare
from beewatch.repositories import AlveariRepository, ApiariRepository, IspezioniRepository
from beewatch.repositories_riferimento import RiepiloghiRepository, UtentiRepository
from beewatch.services import Servizi

pytestmark = pytest.mark.integration

RIEPILOGO = {
    "stato_salute": "attenzione",
    "elementi_rilevati": ["covata a macchie", "è più forte di un anno fa 🐝"],
    "criticita": [{"descrizione": "covata a macchie", "gravita": "media"}],
    "azioni_suggerite": [{"azione": "ricontrollare", "priorita": "media", "entro_giorni": 7}],
    "confidenza": "media",
    "campi_non_deducibili": ["causa della covata a macchie"],
}


def salva(repository: RiepiloghiRepository, utente: int, ispezione: int, **extra) -> int:
    campi = {
        "riepilogo": RIEPILOGO,
        "stato_salute": "attenzione",
        "confidenza": "media",
        "provider": "ollama",
        "modello": "llama3.1:8b",
        "versione_prompt": "v1",
        "durata_ms": 1234,
        "token_prompt": 800,
        "token_risposta": 200,
        "tentativi": 1,
    }
    return repository.salva(utente, ispezione, **{**campi, **extra})


def righe(db: Database, sql: str, parametri: tuple = ()) -> list[dict]:
    with db.transazione() as cursore:
        cursore.execute(sql, parametri)
        return cursore.fetchall()


@pytest.fixture
def nuovo_utente(database_test: Database) -> Iterator[Callable[[], int]]:
    creati: list[int] = []

    def _crea() -> int:
        with database_test.transazione() as cursore:
            cursore.execute(
                "INSERT INTO utenti (email, nome_completo, hash_password) VALUES (%s, %s, %s)",
                (f"test-{uuid.uuid4().hex}@beewatch.test", "Utente di prova", "x" * 60),
            )
            creati.append(cursore.lastrowid)
        return creati[-1]

    yield _crea
    for utente_id in creati:
        try:
            UtentiRepository(database_test).elimina(utente_id)
        except ValidationError:
            pass


@pytest.fixture
def ispezione_di(
    database_test: Database, nuovo_utente: Callable[[], int]
) -> Callable[[], tuple[int, int]]:
    """Fabbrica di (utente, ispezione): un utente nuovo con apiario, alveare e un'ispezione."""

    def _crea() -> tuple[int, int]:
        utente = nuovo_utente()
        apiario = ApiariRepository(database_test).crea(Apiario(utente_id=utente, nome="Collina"))
        alveare = AlveariRepository(database_test).crea(
            utente, Alveare(apiario_id=apiario.id, codice="A1", stato=StatoAlveare.IN_SALUTE)
        )
        ispezione = IspezioniRepository(database_test).crea(
            utente,
            Ispezione(
                alveare_id=alveare.id,
                data_ispezione=date.today() - timedelta(days=1),
                livello_rischio=LivelloRischio.BASSO,
                note="Covata a macchie.",
            ),
        )
        return utente, ispezione.id

    return _crea


@pytest.fixture
def repository(database_test: Database) -> RiepiloghiRepository:
    return RiepiloghiRepository(database_test)


# --------------------------------------------------------------------------- #
# IspezioniRepository.trova
# --------------------------------------------------------------------------- #


def test_trova_restituisce_lispezione_dellutente_con_i_suoi_valori(
    database_test: Database, ispezione_di
) -> None:
    utente, ispezione_id = ispezione_di()

    trovata = IspezioniRepository(database_test).trova(utente, ispezione_id)

    assert trovata.id == ispezione_id and trovata.note == "Covata a macchie."
    assert trovata.livello_rischio is LivelloRischio.BASSO
    assert trovata.regina_vista is False and trovata.sciamatura is False


def test_trova_non_distingue_un_id_altrui_da_uno_inesistente(
    database_test: Database, ispezione_di, nuovo_utente
) -> None:
    _, ispezione_id = ispezione_di()
    intruso = nuovo_utente()
    repo = IspezioniRepository(database_test)
    assert repo.trova(intruso, ispezione_id) is None
    assert repo.trova(intruso, 999_999_999) is None


# --------------------------------------------------------------------------- #
# RiepiloghiRepository
# --------------------------------------------------------------------------- #


def test_un_riepilogo_si_salva_e_si_rilegge_identico(
    repository: RiepiloghiRepository, ispezione_di
) -> None:
    utente, ispezione_id = ispezione_di()

    nuovo_id = salva(repository, utente, ispezione_id)

    letto = repository.ultimo(utente, ispezione_id)
    assert letto["id"] == nuovo_id and letto["ispezione_id"] == ispezione_id
    assert letto["riepilogo_json"] == RIEPILOGO  # accenti ed emoji compresi
    assert (letto["stato_salute"], letto["confidenza"]) == ("attenzione", "media")
    assert (letto["provider"], letto["modello"], letto["versione_prompt"]) == (
        "ollama",
        "llama3.1:8b",
        "v1",
    )
    assert (letto["durata_ms"], letto["token_prompt"], letto["token_risposta"]) == (1234, 800, 200)
    assert letto["tentativi"] == 1 and letto["creato_il"] is not None


def test_i_token_sconosciuti_restano_null(repository: RiepiloghiRepository, ispezione_di) -> None:
    utente, ispezione_id = ispezione_di()
    salva(repository, utente, ispezione_id, token_prompt=None, token_risposta=None)
    letto = repository.ultimo(utente, ispezione_id)
    assert letto["token_prompt"] is None and letto["token_risposta"] is None


def test_ultimo_e_il_piu_recente_e_i_vecchi_restano(
    repository: RiepiloghiRepository, database_test: Database, ispezione_di
) -> None:
    utente, ispezione_id = ispezione_di()
    primo = salva(repository, utente, ispezione_id, modello="vecchio")
    secondo = salva(repository, utente, ispezione_id, modello="nuovo", tentativi=2)

    assert repository.ultimo(utente, ispezione_id)["id"] == secondo
    assert repository.ultimo(utente, ispezione_id)["modello"] == "nuovo"
    ids = {
        r["id"]
        for r in righe(
            database_test, "SELECT id FROM riepiloghi_ispezione WHERE utente_id = %s", (utente,)
        )
    }
    assert ids == {primo, secondo}


def test_senza_riepiloghi_ultimo_e_none(repository: RiepiloghiRepository, ispezione_di) -> None:
    utente, ispezione_id = ispezione_di()
    assert repository.ultimo(utente, ispezione_id) is None


def test_un_utente_non_salva_ne_legge_i_riepiloghi_altrui(
    repository: RiepiloghiRepository, database_test: Database, ispezione_di, nuovo_utente
) -> None:
    utente, ispezione_id = ispezione_di()
    intruso = nuovo_utente()

    with pytest.raises(ValidationError, match="Ispezione non trovata") as errore:
        salva(repository, intruso, ispezione_id)
    assert errore.value.campo == "ispezione_id"
    assert (
        righe(database_test, "SELECT 1 FROM riepiloghi_ispezione WHERE utente_id = %s", (intruso,))
        == []
    )

    salva(repository, utente, ispezione_id)
    assert repository.ultimo(intruso, ispezione_id) is None


def test_un_ispezione_inesistente_e_un_errore_chiaro(
    repository: RiepiloghiRepository, ispezione_di
) -> None:
    utente, _ = ispezione_di()
    with pytest.raises(ValidationError, match="Ispezione non trovata"):
        salva(repository, utente, 999_999_999)


@pytest.mark.parametrize(
    "extra",
    [
        {"stato_salute": "ottimo"},
        {"confidenza": "certa"},
        {"tentativi": 3},
        {"tentativi": 0},
        {"provider": "x" * 21},
    ],
)
def test_il_database_rifiuta_i_valori_fuori_schema(
    repository: RiepiloghiRepository, ispezione_di, extra
) -> None:
    utente, ispezione_id = ispezione_di()
    with pytest.raises(DatabaseError):
        salva(repository, utente, ispezione_id, **extra)
    assert repository.ultimo(utente, ispezione_id) is None


def test_cancellando_lispezione_spariscono_i_suoi_riepiloghi(
    repository: RiepiloghiRepository, database_test: Database, ispezione_di
) -> None:
    utente, ispezione_id = ispezione_di()
    salva(repository, utente, ispezione_id)
    salva(repository, utente, ispezione_id)

    IspezioniRepository(database_test).elimina(utente, ispezione_id)

    assert (
        righe(database_test, "SELECT 1 FROM riepiloghi_ispezione WHERE utente_id = %s", (utente,))
        == []
    )


def test_cancellando_lutente_spariscono_i_suoi_riepiloghi(
    repository: RiepiloghiRepository, database_test: Database, ispezione_di
) -> None:
    utente, ispezione_id = ispezione_di()
    salva(repository, utente, ispezione_id)

    UtentiRepository(database_test).elimina(utente)

    assert (
        righe(database_test, "SELECT 1 FROM riepiloghi_ispezione WHERE utente_id = %s", (utente,))
        == []
    )


# --------------------------------------------------------------------------- #
# Il servizio intero, con il seed
# --------------------------------------------------------------------------- #


@pytest.fixture
def riepiloghi_puliti(database_test: Database) -> Iterator[None]:
    """Dopo il test toglie i riepiloghi fatti sulle ispezioni del seed (utente 1)."""
    yield
    with database_test.transazione() as cursore:
        cursore.execute("DELETE FROM riepiloghi_ispezione WHERE utente_id = 1")


def test_servizio_intero_sulla_nota_lunga_di_a3_del_seed(
    database_test: Database, riepiloghi_puliti: None, caplog
) -> None:
    client = LLMFinto([json.dumps(RIEPILOGO)], modello="m-prova")
    servizi = Servizi(database_test, crea_llm=lambda: client)

    with caplog.at_level("INFO"):
        r = servizi.genera_riepilogo_ispezione(1, 12)  # A3, 2026-05-16: la nota lunga

    assert r.valido and r.salvato and r.id is not None
    riga = servizi.riepilogo_salvato(1, 12)
    assert riga["id"] == r.id and riga["riepilogo_json"] == RIEPILOGO
    assert (riga["provider"], riga["modello"]) == ("finto", "m-prova")
    assert riga["versione_prompt"] == "v1" and riga["tentativi"] == 1

    # Il contesto passato al modello viene dal database, ed è quello giusto.
    richiesta = client.chiamate[0].utente
    assert "Codice: A3" in richiesta and "Apiario: " in richiesta
    assert "2025-06-14" in richiesta  # l'unica ispezione precedente di A3 (id 11)
    assert "Nucleo in crescita regolare" in richiesta
    assert "34,50 kg" in richiesta and "21,00 kg" in richiesta  # raccolti 1 e 2 dell'apiario
    assert "12,80" not in richiesta  # il raccolto 3 è di A1
    assert "29,20" not in richiesta  # il raccolto 4 è dopo l'ispezione
    assert "trovato la regina sul terzo telaino" in richiesta  # la nota intera
    assert "[ispezione]" in caplog.text and "[storico]" in caplog.text  # e il contesto è nel log


def test_servizio_su_unispezione_altrui_o_inesistente(
    database_test: Database, riepiloghi_puliti: None, nuovo_utente
) -> None:
    client = LLMFinto([json.dumps(RIEPILOGO)])
    servizi = Servizi(database_test, crea_llm=lambda: client)

    with pytest.raises(ValidationError, match="non trovata"):
        servizi.genera_riepilogo_ispezione(nuovo_utente(), 12)  # l'ispezione 12 è dell'utente 1
    with pytest.raises(ValidationError, match="non trovata"):
        servizi.genera_riepilogo_ispezione(1, 999_999)
    assert client.chiamate == []


def test_servizio_su_ispezione_senza_note_non_chiama_il_modello(
    database_test: Database, riepiloghi_puliti: None, ispezione_di
) -> None:
    utente, ispezione_id = ispezione_di()
    with database_test.transazione() as cursore:
        cursore.execute("UPDATE ispezioni SET note = NULL WHERE id = %s", (ispezione_id,))
    client = LLMFinto([json.dumps(RIEPILOGO)])

    with pytest.raises(ValidationError, match="non ha note"):
        Servizi(database_test, crea_llm=lambda: client).genera_riepilogo_ispezione(
            utente, ispezione_id
        )
    assert client.chiamate == []
