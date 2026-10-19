"""Test dell'accesso a MySQL (`beewatch.database`, M3-T1).

Due gruppi, nello stesso file perché proteggono lo stesso modulo.

**Unitari** (girano sempre, anche in CI): `mysql.connector.connect` è sostituito da
un finto che registra ciò che gli viene chiesto. Si verifica il comportamento che
conta per chi usa `Database`: quando si fa commit e quando rollback, che le risorse
si chiudano in ogni percorso, quali errori si ritentano e quali no, che cosa arriva
all'utente come `DatabaseError` e che la password non finisca mai in un messaggio o
in un log.

**Di integrazione** (`pytest -m integration`): MySQL vero, in uno stack Docker
temporaneo e isolato (fixture `stack_mysql` in `conftest.py`), sul database separato
`<DB_NAME>_test` creato da `sql/00_test_db.sh`. Il database e il volume dello
sviluppatore non vengono toccati. L'utente applicativo ha solo SELECT, INSERT, UPDATE
e DELETE: i test scrivono in `stati_usa` con codici riservati (`Z1`, `Z2`: non sono
fra i 44 del seed) e tolgono soltanto le righe che hanno creato, con DELETE.
"""

from __future__ import annotations

import dataclasses
import logging
import re
import time
from collections.abc import Iterator
from typing import Any

import mysql.connector
import pytest
from docker_support import DB_NAME, DB_USER, RADICE_PROGETTO, Stack, porta_libera

from beewatch import database
from beewatch.config import ConfigDatabase
from beewatch.database import ATTESE_RETRY, ERRORI_TRANSITORI, Database
from beewatch.exceptions import BeeWatchError, DatabaseError, ValidationError

PASSWORD = "PW-FINTA-db-9Z"
UTENTE = "utente_finto_db"
HOST = "host-finto-db"
CONFIG = ConfigDatabase(
    host=HOST, porta=3307, nome="beewatch_finto", utente=UTENTE, password=PASSWORD
)

# Il testo che il driver vero produce per una password sbagliata: cita utente e host.
TESTO_ACCESSO_NEGATO = f"Access denied for user '{UTENTE}'@'{HOST}' (using password: YES)"


def errore_driver(errno: int, testo: str = "errore del driver") -> mysql.connector.Error:
    return mysql.connector.Error(msg=testo, errno=errno, sqlstate="HY000")


# --------------------------------------------------------------------------- #
# Il driver finto
# --------------------------------------------------------------------------- #


class CursoreFinto:
    def __init__(self, connessione: ConnessioneFinta) -> None:
        self.connessione = connessione
        self.query: list[tuple[str, Any]] = []

    def execute(self, sql: str, parametri: Any = None) -> None:
        self.query.append((sql, parametri))
        if self.connessione.errore_query:
            raise self.connessione.errore_query

    def fetchall(self) -> list[dict[str, int]]:
        return [{"uno": 1}]

    def close(self) -> None:
        self.connessione.eventi.append("cursore chiuso")
        if self.connessione.errore_chiusura_cursore:
            raise self.connessione.errore_chiusura_cursore


class ConnessioneFinta:
    """Registra in `eventi` ciò che le viene chiesto, nell'ordine."""

    def __init__(self, **errori: Exception) -> None:
        self.eventi: list[str] = []
        self.opzioni_cursore: dict[str, Any] = {}
        self.cursore: CursoreFinto | None = None
        self.errore_cursore = errori.get("cursore")
        self.errore_query = errori.get("query")
        self.errore_commit = errori.get("commit")
        self.errore_rollback = errori.get("rollback")
        self.errore_chiusura_cursore = errori.get("chiusura_cursore")
        self.errore_chiusura = errori.get("chiusura")

    def cursor(self, **opzioni: Any) -> CursoreFinto:
        self.opzioni_cursore = opzioni
        if self.errore_cursore:
            raise self.errore_cursore
        self.cursore = CursoreFinto(self)
        return self.cursore

    def commit(self) -> None:
        self.eventi.append("commit")
        if self.errore_commit:
            raise self.errore_commit

    def rollback(self) -> None:
        self.eventi.append("rollback")
        if self.errore_rollback:
            raise self.errore_rollback

    def close(self) -> None:
        self.eventi.append("connessione chiusa")
        if self.errore_chiusura:
            raise self.errore_chiusura


class DriverFinto:
    """Sostituisce `mysql.connector.connect`.

    `esiti` è la coda di ciò che succede a ogni tentativo di connessione: un'eccezione
    viene sollevata, una `ConnessioneFinta` viene restituita. A coda vuota restituisce
    connessioni nuove e funzionanti.
    """

    def __init__(self) -> None:
        self.esiti: list[Exception | ConnessioneFinta] = []
        self.chiamate: list[dict[str, Any]] = []
        self.connessioni: list[ConnessioneFinta] = []
        self.attese: list[float] = []  # le `time.sleep` richieste dal modulo

    def __call__(self, **parametri: Any) -> ConnessioneFinta:
        self.chiamate.append(parametri)
        esito = self.esiti.pop(0) if self.esiti else ConnessioneFinta()
        if isinstance(esito, Exception):
            raise esito
        self.connessioni.append(esito)
        return esito


@pytest.fixture
def driver(monkeypatch: pytest.MonkeyPatch) -> DriverFinto:
    finto = DriverFinto()
    monkeypatch.setattr(database.mysql.connector, "connect", finto)
    monkeypatch.setattr(database.time, "sleep", finto.attese.append)  # nessuna attesa vera
    return finto


@pytest.fixture
def log(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    """Tutto ciò che il modulo scrive nel log, DEBUG compreso."""
    caplog.set_level(logging.DEBUG, logger="beewatch.database")
    return caplog


# --------------------------------------------------------------------------- #
# Connessione: quando si apre, con quali parametri, quando si chiude
# --------------------------------------------------------------------------- #


def test_costruire_un_database_non_apre_connessioni(driver: DriverFinto) -> None:
    Database(CONFIG)
    assert driver.chiamate == []


def test_la_connessione_usa_la_configurazione_ricevuta(driver: DriverFinto) -> None:
    with Database(CONFIG).transazione():
        pass

    assert driver.chiamate == [
        {
            "host": HOST,
            "port": 3307,
            "user": UTENTE,
            "password": PASSWORD,
            "database": "beewatch_finto",
            "charset": "utf8mb4",
            "collation": "utf8mb4_unicode_ci",
            "autocommit": False,
            "connection_timeout": database.TIMEOUT_CONNESSIONE,
        }
    ]


def test_database_non_legge_la_configurazione_globale(driver: DriverFinto) -> None:
    """`ambiente_pulito` ha tolto le variabili DB_*: se `Database` chiamasse `ottieni()`
    qui fallirebbe con ConfigError. Deve bastargli la configurazione ricevuta."""
    with pytest.raises(TypeError):
        Database()  # type: ignore[call-arg]  # la configurazione è obbligatoria
    assert Database(CONFIG).verifica_connessione() is True


def test_il_cursore_restituisce_dizionari_e_legge_subito_tutte_le_righe(
    driver: DriverFinto,
) -> None:
    with Database(CONFIG).transazione() as cursore:
        cursore.execute("SELECT 1 AS uno")
        assert cursore.fetchall() == [{"uno": 1}]

    # buffered: un risultato non letto non deve far fallire il commit.
    assert driver.connessioni[0].opzioni_cursore == {"dictionary": True, "buffered": True}


def test_ogni_transazione_ha_la_sua_connessione_e_la_chiude(driver: DriverFinto) -> None:
    db = Database(CONFIG)
    for _ in range(2):
        with db.transazione():
            pass

    assert len(driver.connessioni) == 2  # nessuna connessione riusata o tenuta da parte
    for connessione in driver.connessioni:
        assert connessione.eventi[-1] == "connessione chiusa"


# --------------------------------------------------------------------------- #
# Transazione: commit, rollback, chiusura in ogni percorso
# --------------------------------------------------------------------------- #


def test_uscita_normale_commit_e_poi_chiusura(driver: DriverFinto) -> None:
    with Database(CONFIG).transazione() as cursore:
        cursore.execute("INSERT INTO t VALUES (%s)", (1,))

    assert driver.connessioni[0].eventi == ["commit", "cursore chiuso", "connessione chiusa"]


def test_i_parametri_arrivano_al_driver_separati_dalla_query(driver: DriverFinto) -> None:
    with Database(CONFIG).transazione() as cursore:
        cursore.execute("SELECT * FROM t WHERE id = %s", (7,))

    assert driver.connessioni[0].cursore.query == [("SELECT * FROM t WHERE id = %s", (7,))]


@pytest.mark.parametrize(
    "eccezione",
    [ValueError("bug"), ValidationError("peso negativo", campo="peso_kg"), KeyboardInterrupt()],
    ids=["bug", "validazione", "interruzione"],
)
def test_se_il_blocco_solleva_rollback_e_la_stessa_eccezione_riemerge(
    driver: DriverFinto, eccezione: BaseException
) -> None:
    with pytest.raises(type(eccezione)) as info:
        with Database(CONFIG).transazione():
            raise eccezione

    assert info.value is eccezione  # non tradotta, non avvolta
    assert driver.connessioni[0].eventi == ["rollback", "cursore chiuso", "connessione chiusa"]


def test_errore_del_driver_nel_blocco_rollback_e_database_error(driver: DriverFinto) -> None:
    originale = errore_driver(1064, "You have an error in your SQL syntax")
    driver.esiti = [ConnessioneFinta(query=originale)]

    with pytest.raises(DatabaseError) as info:
        with Database(CONFIG).transazione() as cursore:
            cursore.execute("SELEC 1")

    assert info.value.__cause__ is originale  # la causa resta per chi fa il debug
    assert driver.connessioni[0].eventi == ["rollback", "cursore chiuso", "connessione chiusa"]


def test_errore_durante_il_commit_rollback_e_database_error(driver: DriverFinto) -> None:
    originale = errore_driver(1213, "Deadlock found")
    driver.esiti = [ConnessioneFinta(commit=originale)]

    with pytest.raises(DatabaseError) as info:
        with Database(CONFIG).transazione():
            pass

    assert info.value.__cause__ is originale
    assert driver.connessioni[0].eventi == [
        "commit",
        "rollback",
        "cursore chiuso",
        "connessione chiusa",
    ]


def test_se_il_rollback_fallisce_riemerge_leccezione_originale(
    driver: DriverFinto, log: pytest.LogCaptureFixture
) -> None:
    driver.esiti = [ConnessioneFinta(rollback=errore_driver(2013, "Lost connection"))]
    originale = ValueError("il vero problema")

    with pytest.raises(ValueError) as info:
        with Database(CONFIG).transazione():
            raise originale

    assert info.value is originale
    assert driver.connessioni[0].eventi == ["rollback", "cursore chiuso", "connessione chiusa"]
    assert "Rollback non riuscito" in log.text  # il secondo errore non sparisce: va nel log


def test_se_il_rollback_fallisce_dopo_un_errore_del_driver_la_causa_e_il_primo(
    driver: DriverFinto,
) -> None:
    primo = errore_driver(1062, "Duplicate entry")
    driver.esiti = [ConnessioneFinta(query=primo, rollback=errore_driver(2013, "Lost connection"))]

    with pytest.raises(DatabaseError) as info:
        with Database(CONFIG).transazione() as cursore:
            cursore.execute("INSERT ...")

    assert info.value.__cause__ is primo


def test_se_non_si_riesce_a_creare_il_cursore_la_connessione_si_chiude(
    driver: DriverFinto,
) -> None:
    driver.esiti = [ConnessioneFinta(cursore=errore_driver(2013, "Lost connection"))]

    with pytest.raises(DatabaseError):
        with Database(CONFIG).transazione():
            pytest.fail("il blocco non deve essere eseguito")  # pragma: no cover

    assert driver.connessioni[0].eventi == ["rollback", "connessione chiusa"]


def test_un_errore_chiudendo_il_cursore_non_impedisce_di_chiudere_la_connessione(
    driver: DriverFinto, log: pytest.LogCaptureFixture
) -> None:
    driver.esiti = [ConnessioneFinta(chiusura_cursore=errore_driver(2013, "Lost connection"))]

    with Database(CONFIG).transazione():
        pass  # il commit è riuscito: un problema in chiusura non è un errore per chi chiama

    assert driver.connessioni[0].eventi == ["commit", "cursore chiuso", "connessione chiusa"]
    assert "Chiusura di cursore non riuscita" in log.text


def test_un_errore_chiudendo_la_connessione_non_nasconde_leccezione_del_blocco(
    driver: DriverFinto, log: pytest.LogCaptureFixture
) -> None:
    driver.esiti = [ConnessioneFinta(chiusura=OSError("socket già chiuso"))]

    with pytest.raises(ValueError, match="il vero problema"):
        with Database(CONFIG).transazione():
            raise ValueError("il vero problema")

    assert "Chiusura di connessione non riuscita" in log.text


# --------------------------------------------------------------------------- #
# Retry: solo l'apertura della connessione, solo gli errori transitori
# --------------------------------------------------------------------------- #


def test_due_fallimenti_transitori_poi_la_connessione_riesce(
    driver: DriverFinto, log: pytest.LogCaptureFixture
) -> None:
    driver.esiti = [errore_driver(2003), errore_driver(2003)]

    with Database(CONFIG).transazione() as cursore:
        cursore.execute("SELECT 1")

    assert len(driver.chiamate) == 3
    assert driver.attese == [0.5, 1.0]  # attese crescenti, e nessuna dopo il successo
    avvisi = [r for r in log.records if r.levelno == logging.WARNING]
    assert len(avvisi) == 2
    assert "tentativo 1 di 3" in avvisi[0].getMessage()
    assert "tentativo 2 di 3" in avvisi[1].getMessage()
    assert not [r for r in log.records if r.levelno >= logging.ERROR]  # alla fine è andata bene


def test_esauriti_i_tentativi_database_error_senza_altre_attese(driver: DriverFinto) -> None:
    ultimo = errore_driver(2003)
    driver.esiti = [errore_driver(2003), errore_driver(2003), ultimo]

    with pytest.raises(DatabaseError, match="Impossibile connettersi al database") as info:
        with Database(CONFIG).transazione():
            pytest.fail("il blocco non deve essere eseguito")  # pragma: no cover

    assert info.value.__cause__ is ultimo
    assert len(driver.chiamate) == len(ATTESE_RETRY) + 1 == 3
    assert driver.attese == list(ATTESE_RETRY)  # mai più di 1,5 secondi in tutto
    assert sum(ATTESE_RETRY) <= 2


# Elenco scritto a mano, non letto dal modulo: togliere o aggiungere un errore ai
# transitori è una decisione, e deve far fallire un test.
@pytest.mark.parametrize("errno", [1040, 2002, 2003, 2006, 2013, 2055])
def test_ogni_errore_transitorio_viene_ritentato(driver: DriverFinto, errno: int) -> None:
    driver.esiti = [errore_driver(errno)]

    with Database(CONFIG).transazione():
        pass

    assert len(driver.chiamate) == 2
    assert errno in ERRORI_TRANSITORI


@pytest.mark.parametrize(
    "errno",
    [1045, 1044, 1049, 2005, 1064, -1],
    ids=["credenziali", "accesso_negato", "db_inesistente", "host_sconosciuto", "sql", "ignoto"],
)
def test_gli_errori_permanenti_non_si_ritentano(driver: DriverFinto, errno: int) -> None:
    driver.esiti = [errore_driver(errno)]

    with pytest.raises(DatabaseError):
        with Database(CONFIG).transazione():
            pytest.fail("il blocco non deve essere eseguito")  # pragma: no cover

    assert len(driver.chiamate) == 1
    assert driver.attese == []


def test_una_query_fallita_non_si_ripete_mai_nemmeno_per_un_errore_transitorio(
    driver: DriverFinto,
) -> None:
    """Rieseguire una scrittura può duplicarla: il retry riguarda solo la connessione."""
    driver.esiti = [ConnessioneFinta(query=errore_driver(2013, "Lost connection during query"))]

    with pytest.raises(DatabaseError, match="si è interrotta"):
        with Database(CONFIG).transazione() as cursore:
            cursore.execute("INSERT INTO t VALUES (1)")

    assert len(driver.chiamate) == 1
    assert driver.attese == []
    assert len(driver.connessioni[0].cursore.query) == 1


# --------------------------------------------------------------------------- #
# Traduzione degli errori: cosa legge l'utente
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "errno,atteso",
    [
        (1045, "rifiutato le credenziali"),
        (1049, "«beewatch_finto» non esiste"),
        (1044, "non ha accesso al database «beewatch_finto»"),
        (2003, "Verifica che MySQL sia avviato"),
        (2005, "Verifica che MySQL sia avviato"),
        (2013, "Verifica che MySQL sia avviato"),  # connessione persa mentre ci si collega
        (1040, "troppe connessioni"),
        (9999, "Impossibile connettersi al database. I dettagli sono nel file di log."),
    ],
)
def test_messaggio_per_un_errore_di_connessione(
    driver: DriverFinto, errno: int, atteso: str
) -> None:
    driver.esiti = [errore_driver(errno)] * 3

    with pytest.raises(DatabaseError) as info:
        with Database(CONFIG).transazione():
            pytest.fail("il blocco non deve essere eseguito")  # pragma: no cover

    assert atteso in str(info.value)


@pytest.mark.parametrize(
    "errno,atteso",
    [
        (1142, "non ha il permesso"),
        (2006, "si è interrotta"),
        (1064, "non è riuscita e non è stata salvata"),
    ],
)
def test_messaggio_per_un_errore_durante_la_transazione(
    driver: DriverFinto, errno: int, atteso: str
) -> None:
    driver.esiti = [ConnessioneFinta(query=errore_driver(errno))]

    with pytest.raises(DatabaseError) as info:
        with Database(CONFIG).transazione() as cursore:
            cursore.execute("...")

    assert atteso in str(info.value)


def test_un_database_error_e_un_errore_previsto_dellapplicazione(driver: DriverFinto) -> None:
    driver.esiti = [errore_driver(1045)]
    with pytest.raises(BeeWatchError):  # l'interfaccia intercetta questa, non il driver
        with Database(CONFIG).transazione():
            pytest.fail("il blocco non deve essere eseguito")  # pragma: no cover


# --------------------------------------------------------------------------- #
# verifica_connessione: rapida, e non solleva
# --------------------------------------------------------------------------- #


def test_verifica_connessione_vera_se_il_database_risponde(driver: DriverFinto) -> None:
    assert Database(CONFIG).verifica_connessione() is True

    connessione = driver.connessioni[0]
    assert connessione.cursore.query == [("SELECT 1", None)]
    assert connessione.eventi == ["cursore chiuso", "connessione chiusa"]  # niente da confermare


def test_verifica_connessione_fa_un_solo_tentativo_con_timeout_breve(
    driver: DriverFinto,
) -> None:
    driver.esiti = [errore_driver(2003), ConnessioneFinta()]  # al secondo tentativo riuscirebbe

    assert Database(CONFIG).verifica_connessione() is False

    assert len(driver.chiamate) == 1  # ma un secondo tentativo non c'è
    assert driver.attese == []
    assert driver.chiamate[0]["connection_timeout"] == database.TIMEOUT_VERIFICA
    assert database.TIMEOUT_VERIFICA < database.TIMEOUT_CONNESSIONE


@pytest.mark.parametrize("errno", [1045, 1049, 2003, -1])
def test_verifica_connessione_falsa_e_senza_eccezioni_se_non_ci_si_collega(
    driver: DriverFinto, errno: int
) -> None:
    driver.esiti = [errore_driver(errno)]
    assert Database(CONFIG).verifica_connessione() is False


def test_verifica_connessione_falsa_se_la_query_fallisce_e_chiude_comunque(
    driver: DriverFinto, log: pytest.LogCaptureFixture
) -> None:
    driver.esiti = [ConnessioneFinta(query=errore_driver(2013, "Lost connection"))]

    assert Database(CONFIG).verifica_connessione() is False

    assert driver.connessioni[0].eventi == ["cursore chiuso", "connessione chiusa"]
    assert "Verifica della connessione fallita" in log.text


def test_verifica_connessione_chiude_la_connessione_anche_senza_cursore(
    driver: DriverFinto,
) -> None:
    driver.esiti = [ConnessioneFinta(cursore=errore_driver(2013, "Lost connection"))]

    assert Database(CONFIG).verifica_connessione() is False
    assert driver.connessioni[0].eventi == ["connessione chiusa"]


# --------------------------------------------------------------------------- #
# Segreti: mai nei messaggi, mai nel log
# --------------------------------------------------------------------------- #


def _scenari_di_errore() -> list[tuple[str, list[Exception | ConnessioneFinta]]]:
    return [
        ("credenziali", [errore_driver(1045, TESTO_ACCESSO_NEGATO)]),
        ("irraggiungibile", [errore_driver(2003, f"Can't connect to server on '{HOST}'")] * 3),
        ("query", [ConnessioneFinta(query=errore_driver(1064, "syntax error near 'SELEC'"))]),
        ("commit", [ConnessioneFinta(commit=errore_driver(1213, "Deadlock found"))]),
    ]


@pytest.mark.parametrize("esiti", [s[1] for s in _scenari_di_errore()], ids=lambda e: "")
def test_la_password_non_compare_ne_nel_messaggio_ne_nel_log(
    driver: DriverFinto, log: pytest.LogCaptureFixture, esiti: list
) -> None:
    driver.esiti = list(esiti)
    db = Database(CONFIG)

    with pytest.raises(DatabaseError) as info:
        with db.transazione() as cursore:
            cursore.execute("SELECT 1")
    db.verifica_connessione()

    assert log.records, "il log deve essere stato scritto, altrimenti il test non prova nulla"
    assert PASSWORD not in log.text
    assert PASSWORD not in str(info.value)
    assert PASSWORD not in repr(info.value)
    assert PASSWORD not in repr(db.__dict__)


def test_il_messaggio_per_lutente_non_cita_utente_host_ne_il_testo_del_driver(
    driver: DriverFinto,
) -> None:
    driver.esiti = [errore_driver(1045, TESTO_ACCESSO_NEGATO)]

    with pytest.raises(DatabaseError) as info:
        with Database(CONFIG).transazione():
            pytest.fail("il blocco non deve essere eseguito")  # pragma: no cover

    messaggio = str(info.value)
    assert UTENTE not in messaggio
    assert HOST not in messaggio
    assert "Access denied" not in messaggio  # niente gergo del driver


def test_il_log_degli_errori_ha_numero_e_database_ma_il_testo_del_driver_solo_a_debug(
    driver: DriverFinto, log: pytest.LogCaptureFixture
) -> None:
    testo = "Duplicate entry 'mario.rossi@example.com' for key 'utenti.email'"
    driver.esiti = [ConnessioneFinta(query=errore_driver(1062, testo))]

    with pytest.raises(DatabaseError):
        with Database(CONFIG).transazione() as cursore:
            cursore.execute("INSERT ...")

    errori = [r.getMessage() for r in log.records if r.levelno >= logging.INFO]
    assert any("errore MySQL 1062" in riga and CONFIG.descrizione() in riga for riga in errori)
    # Il testo del driver può contenere dati: a livello normale non deve esserci.
    assert not any("mario.rossi" in riga for riga in errori)
    assert any("mario.rossi" in r.getMessage() for r in log.records if r.levelno == logging.DEBUG)


# --------------------------------------------------------------------------- #
# sql/00_test_db.sh: controlli sul testo (la prova vera è fra i test integration)
# --------------------------------------------------------------------------- #

SCRIPT_DB_TEST = RADICE_PROGETTO / "sql" / "00_test_db.sh"


def _codice_dello_script() -> str:
    righe = SCRIPT_DB_TEST.read_text(encoding="utf-8").splitlines()
    return "\n".join(r for r in righe if not r.lstrip().startswith("#"))


def test_lo_script_del_db_di_test_ha_solo_fine_riga_lf() -> None:
    """Con CRLF bash nel contenitore Linux non lo esegue (`.gitattributes` lo impone)."""
    assert b"\r" not in SCRIPT_DB_TEST.read_bytes()
    assert SCRIPT_DB_TEST.read_bytes().startswith(b"#!/bin/bash\n")


def test_lo_script_del_db_di_test_concede_solo_dml() -> None:
    codice = _codice_dello_script()

    assert re.findall(r"GRANT\s+([A-Z, ]+?)\s+ON", codice) == ["SELECT, INSERT, UPDATE, DELETE"]
    assert "WITH GRANT OPTION" not in codice
    assert "CREATE USER" not in codice
    # Lo schema si riusa, non si copia: nello script non ci sono tabelle.
    assert "CREATE TABLE" not in codice
    assert "schema.sql" in codice and "seed.sql" in codice


def test_lo_script_del_db_di_test_funziona_anche_incluso_con_source() -> None:
    """L'immagine MySQL include con `source` gli .sh non eseguibili: `exit` chiuderebbe
    l'avvio del server, `set` cambierebbe le opzioni del suo script."""
    codice = _codice_dello_script()

    assert not re.search(r"^\s*exit\b", codice, flags=re.MULTILINE)
    assert not re.search(r"^\s*set\s+[-+]", codice, flags=re.MULTILINE)


def test_lo_script_del_db_di_test_non_stampa_ne_passa_in_chiaro_la_password() -> None:
    codice = _codice_dello_script()

    for riga in codice.splitlines():
        if "echo" in riga:
            assert "PASSWORD" not in riga and "MYSQL_PWD" not in riga
    assert not re.search(r"-p\S*PASSWORD", codice)  # niente `-p"$MYSQL_ROOT_PASSWORD"`
    assert "MYSQL_USER" in codice and "MYSQL_DATABASE" in codice  # nessun nome scritto a mano


# =========================================================================== #
# INTEGRAZIONE: MySQL vero, stack Docker isolato, database `<DB_NAME>_test`
# =========================================================================== #

NOME_DB_TEST = f"{DB_NAME}_test"
CODICI_DI_PROVA = ("Z1", "Z2")  # righe che questi test creano in `stati_usa`, e solo queste
SCRIPT_NEL_CONTENITORE = "/docker-entrypoint-initdb.d/00_test_db.sh"


def _connessione_diretta(config: ConfigDatabase):
    """Una connessione che NON passa da `Database`: serve a guardare da fuori."""
    return mysql.connector.connect(
        host=config.host,
        port=config.porta,
        user=config.utente,
        password=config.password,
        database=config.nome,
        charset="utf8mb4",
        collation="utf8mb4_unicode_ci",
        connection_timeout=5,
    )


def _visto_da_fuori(config: ConfigDatabase, sql: str, parametri: tuple = ()) -> list[tuple]:
    connessione = _connessione_diretta(config)
    try:
        cursore = connessione.cursor()
        cursore.execute(sql, parametri)
        return cursore.fetchall()
    finally:
        connessione.close()


def _togli_righe_di_prova(config: ConfigDatabase) -> None:
    connessione = _connessione_diretta(config)
    try:
        cursore = connessione.cursor()
        cursore.execute("DELETE FROM stati_usa WHERE codice IN (%s, %s)", CODICI_DI_PROVA)
        connessione.commit()
    finally:
        connessione.close()


@pytest.fixture
def righe_di_prova(config_db_test: ConfigDatabase) -> Iterator[None]:
    """Toglie prima e dopo le sole righe che questi test creano. DELETE, non TRUNCATE:
    l'utente applicativo non ha (e non deve avere) il privilegio DROP."""
    _togli_righe_di_prova(config_db_test)
    yield
    _togli_righe_di_prova(config_db_test)


def _nome_di(config: ConfigDatabase, codice: str) -> list[tuple]:
    return _visto_da_fuori(config, "SELECT nome FROM stati_usa WHERE codice = %s", (codice,))


def _come_root(stack: Stack, sql: str) -> str:
    """Esegue `sql` come root DENTRO il contenitore MySQL dello stack (root non esce da lì)."""
    comando = f'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B --raw -e "{sql}"'
    esito = stack.nel_container("mysql", "sh", "-c", comando)
    assert esito.returncode == 0, stack.redigi(esito.stderr)
    return esito.stdout


@pytest.mark.integration
def test_integrazione_ci_si_collega_al_database_di_test_non_a_quello_principale(
    database_test: Database, config_db_test: ConfigDatabase
) -> None:
    assert database_test.verifica_connessione() is True

    with database_test.transazione() as cursore:
        cursore.execute("SELECT 1 AS uno, DATABASE() AS db")
        assert cursore.fetchall() == [{"uno": 1, "db": NOME_DB_TEST}]

    assert config_db_test.nome == NOME_DB_TEST != DB_NAME


@pytest.mark.integration
def test_integrazione_insert_select_update_delete(
    database_test: Database, config_db_test: ConfigDatabase, righe_di_prova: None
) -> None:
    with database_test.transazione() as cursore:
        cursore.execute("INSERT INTO stati_usa (codice, nome) VALUES (%s, %s)", ("Z1", "Prova"))
        assert cursore.rowcount == 1
    assert _nome_di(config_db_test, "Z1") == [("Prova",)]

    with database_test.transazione() as cursore:
        cursore.execute("SELECT codice, nome FROM stati_usa WHERE codice = %s", ("Z1",))
        assert cursore.fetchall() == [{"codice": "Z1", "nome": "Prova"}]

    with database_test.transazione() as cursore:
        cursore.execute("UPDATE stati_usa SET nome = %s WHERE codice = %s", ("Cambiata", "Z1"))
        assert cursore.rowcount == 1
    assert _nome_di(config_db_test, "Z1") == [("Cambiata",)]

    with database_test.transazione() as cursore:
        cursore.execute("DELETE FROM stati_usa WHERE codice = %s", ("Z1",))
        assert cursore.rowcount == 1
    assert _nome_di(config_db_test, "Z1") == []


@pytest.mark.integration
def test_integrazione_il_commit_e_visibile_da_una_seconda_connessione(
    database_test: Database, config_db_test: ConfigDatabase, righe_di_prova: None
) -> None:
    with database_test.transazione() as cursore:
        cursore.execute("INSERT INTO stati_usa (codice, nome) VALUES ('Z1', 'Confermata')")
        # Dentro la transazione, da fuori non si vede ancora niente.
        assert _nome_di(config_db_test, "Z1") == []

    assert _nome_di(config_db_test, "Z1") == [("Confermata",)]


@pytest.mark.integration
def test_integrazione_uneccezione_nel_blocco_annulla_tutte_le_scritture(
    database_test: Database, config_db_test: ConfigDatabase, righe_di_prova: None
) -> None:
    with pytest.raises(ValidationError):
        with database_test.transazione() as cursore:
            cursore.execute("INSERT INTO stati_usa (codice, nome) VALUES ('Z1', 'Annullata')")
            cursore.execute("INSERT INTO stati_usa (codice, nome) VALUES ('Z2', 'Annullata')")
            raise ValidationError("dato non valido", campo="nome")

    assert _nome_di(config_db_test, "Z1") == []
    assert _nome_di(config_db_test, "Z2") == []


@pytest.mark.integration
def test_integrazione_un_errore_sql_a_meta_annulla_cio_che_era_gia_stato_scritto(
    database_test: Database, config_db_test: ConfigDatabase, righe_di_prova: None
) -> None:
    with pytest.raises(DatabaseError) as info:
        with database_test.transazione() as cursore:
            cursore.execute("INSERT INTO stati_usa (codice, nome) VALUES ('Z1', 'Prima')")
            cursore.execute("INSERT INTO stati_usa (codice, nome) VALUES ('Z1', 'Doppione')")

    assert info.value.__cause__.errno == 1062  # chiave duplicata
    assert _nome_di(config_db_test, "Z1") == []


@pytest.mark.integration
def test_integrazione_un_risultato_non_letto_non_fa_fallire_il_commit(
    database_test: Database, config_db_test: ConfigDatabase, righe_di_prova: None
) -> None:
    with database_test.transazione() as cursore:
        cursore.execute("INSERT INTO stati_usa (codice, nome) VALUES ('Z1', 'Uno'), ('Z2', 'Due')")
        cursore.execute("SELECT codice FROM stati_usa")  # righe mai lette

    assert _nome_di(config_db_test, "Z2") == [("Due",)]


@pytest.mark.integration
def test_integrazione_utf8_accenti_ed_emoji_tornano_identici(
    database_test: Database, config_db_test: ConfigDatabase, righe_di_prova: None
) -> None:
    testo = "Città è già così – ñ ß 日本 🐝🍯"

    with database_test.transazione() as cursore:
        cursore.execute("INSERT INTO stati_usa (codice, nome) VALUES (%s, %s)", ("Z1", testo))

    with database_test.transazione() as cursore:
        cursore.execute(
            "SELECT nome, CHAR_LENGTH(nome) AS lunghezza FROM stati_usa WHERE codice = 'Z1'"
        )
        assert cursore.fetchall() == [{"nome": testo, "lunghezza": len(testo)}]
    assert _nome_di(config_db_test, "Z1") == [(testo,)]


@pytest.mark.integration
@pytest.mark.parametrize(
    "ddl",
    [
        "CREATE TABLE bw_prova_ddl (id INT)",
        "DROP TABLE stati_usa",
        "ALTER TABLE stati_usa ADD COLUMN extra INT",
        "TRUNCATE TABLE stati_usa",
        "CREATE USER 'bw_intruso'@'%' IDENTIFIED BY 'x'",
        "GRANT SELECT ON *.* TO CURRENT_USER()",
    ],
    ids=["create", "drop", "alter", "truncate", "create_user", "grant"],
)
def test_integrazione_lutente_applicativo_non_puo_cambiare_lo_schema(
    database_test: Database, config_db_test: ConfigDatabase, ddl: str
) -> None:
    with pytest.raises(DatabaseError) as info:
        with database_test.transazione() as cursore:
            cursore.execute(ddl)

    assert info.value.__cause__.errno in (1044, 1045, 1142, 1227)  # negato, non un altro errore
    tabelle = _visto_da_fuori(config_db_test, "SHOW TABLES")
    assert ("stati_usa",) in tabelle and ("bw_prova_ddl",) not in tabelle


@pytest.mark.integration
def test_integrazione_password_sbagliata_errore_chiaro_subito_e_senza_segreti(
    config_db_test: ConfigDatabase, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="beewatch.database")
    sbagliata = "PW-SBAGLIATA-4f1c"
    db = Database(dataclasses.replace(config_db_test, password=sbagliata))

    inizio = time.monotonic()
    with pytest.raises(DatabaseError, match="rifiutato le credenziali") as info:
        with db.transazione():
            pytest.fail("il blocco non deve essere eseguito")  # pragma: no cover
    durata = time.monotonic() - inizio

    assert durata < sum(ATTESE_RETRY), "un errore permanente non va ritentato"
    assert db.verifica_connessione() is False
    for segreto in (sbagliata, config_db_test.password):
        assert segreto not in str(info.value)
        assert segreto not in caplog.text
    assert "errore MySQL 1045" in caplog.text


@pytest.mark.integration
def test_integrazione_database_non_accessibile_errore_chiaro(
    config_db_test: ConfigDatabase,
) -> None:
    db = Database(dataclasses.replace(config_db_test, nome="bw_stack_che_non_esiste"))

    with pytest.raises(DatabaseError, match="bw_stack_che_non_esiste"):
        with db.transazione():
            pytest.fail("il blocco non deve essere eseguito")  # pragma: no cover


@pytest.mark.integration
def test_integrazione_server_spento_si_ritenta_poi_errore_e_verifica_rapida(
    config_db_test: ConfigDatabase, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="beewatch.database")
    db = Database(dataclasses.replace(config_db_test, porta=porta_libera()))  # non ascolta nessuno

    inizio = time.monotonic()
    assert db.verifica_connessione() is False
    assert time.monotonic() - inizio < database.TIMEOUT_VERIFICA + 3  # un tentativo solo

    caplog.clear()
    inizio = time.monotonic()
    with pytest.raises(DatabaseError, match="Impossibile connettersi al database"):
        with db.transazione():
            pytest.fail("il blocco non deve essere eseguito")  # pragma: no cover

    assert time.monotonic() - inizio >= sum(ATTESE_RETRY)  # le attese ci sono state davvero
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == len(ATTESE_RETRY)


# -- sql/00_test_db.sh sul contenitore vero -------------------------------------- #


@pytest.mark.integration
def test_integrazione_il_db_di_test_ha_schema_e_seed_del_principale_in_utf8mb4(
    stack_mysql: Stack,
) -> None:
    def tabelle(schema: str) -> str:
        return _come_root(
            stack_mysql,
            "SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{schema}' ORDER BY table_name",
        )

    assert tabelle(NOME_DB_TEST) == tabelle(DB_NAME)
    assert len(tabelle(NOME_DB_TEST).split()) == 14

    codifica = _come_root(
        stack_mysql,
        "SELECT default_character_set_name, default_collation_name "
        f"FROM information_schema.schemata WHERE schema_name = '{NOME_DB_TEST}'",
    )
    assert codifica.split() == ["utf8mb4", "utf8mb4_unicode_ci"]
    # Anche il seed è lo stesso: le tabelle di riferimento sono quelle del principale.
    for tabella in ("stati_usa", "stati_alveare", "livelli_rischio", "tipi_miele"):
        conteggio = f"SELECT COUNT(*) FROM {{}}.{tabella}"
        assert _come_root(stack_mysql, conteggio.format(NOME_DB_TEST)) == _come_root(
            stack_mysql, conteggio.format(DB_NAME)
        ), tabella


@pytest.mark.integration
def test_integrazione_i_privilegi_sono_solo_i_quattro_dml_anche_sul_db_di_test(
    stack_mysql: Stack,
) -> None:
    grants = _come_root(stack_mysql, f"SHOW GRANTS FOR '{DB_USER}'@'%'").splitlines()

    assert sorted(grants) == sorted(
        [
            f"GRANT USAGE ON *.* TO `{DB_USER}`@`%`",
            # `_` preceduto da barra rovesciata: il privilegio vale per questo nome esatto.
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON `bw\\_stack`.* TO `{DB_USER}`@`%`",
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON `bw\\_stack\\_test`.* TO `{DB_USER}`@`%`",
        ]
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "comando",
    [
        ("bash", SCRIPT_NEL_CONTENITORE),
        ("bash", "-c", f"set -eo pipefail; . {SCRIPT_NEL_CONTENITORE}; echo dopo-source"),
    ],
    ids=["eseguito", "incluso_con_source"],
)
def test_integrazione_lo_script_si_puo_rilanciare_senza_danni_ne_segreti(
    stack_mysql: Stack,
    database_test: Database,
    config_db_test: ConfigDatabase,
    righe_di_prova: None,
    comando: tuple[str, ...],
) -> None:
    """È il caso di chi ha già un volume: lo script si lancia a mano, e deve lasciare
    dati e privilegi come sono."""
    with database_test.transazione() as cursore:
        cursore.execute("INSERT INTO stati_usa (codice, nome) VALUES ('Z1', 'Resta')")
    prima = _come_root(stack_mysql, f"SHOW GRANTS FOR '{DB_USER}'@'%'")

    esito = stack_mysql.nel_container("mysql", *comando)

    uscita = esito.stdout + esito.stderr
    assert esito.returncode == 0, stack_mysql.redigi(uscita)
    assert f"database di test `{NOME_DB_TEST}` pronto" in esito.stdout
    if "source" in comando[-1]:
        assert "dopo-source" in esito.stdout  # lo script non ha chiuso la shell che lo include
    assert stack_mysql.password_root not in uscita
    assert stack_mysql.password_app not in uscita
    assert _come_root(stack_mysql, f"SHOW GRANTS FOR '{DB_USER}'@'%'") == prima
    assert _nome_di(config_db_test, "Z1") == [("Resta",)]


@pytest.mark.integration
def test_integrazione_senza_le_variabili_lo_script_fallisce_e_lo_dice(
    stack_mysql: Stack,
) -> None:
    esito = stack_mysql.nel_container(
        "mysql", "bash", SCRIPT_NEL_CONTENITORE, ambiente={"MYSQL_USER": ""}
    )

    assert esito.returncode != 0
    assert "manca la variabile MYSQL_USER" in esito.stderr
