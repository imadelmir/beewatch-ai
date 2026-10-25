"""Fixture condivise da tutti i test di BeeWatch AI.

Il problema che risolvono: la configurazione legge da `os.environ` e dal file
`.env` dello sviluppatore. Senza isolamento, gli stessi test passerebbero sul
computer di chi ha un `.env` completo e fallirebbero sulla CI, che non ce l'ha.
Qui l'ambiente viene azzerato e ricostruito caso per caso, e la radice del
progetto (da cui si leggono `.env` e `logs/`) punta a una cartella temporanea.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest import mock

import pytest
from docker_support import (
    DB_NAME,
    DB_USER,
    Stack,
    docker_pronto,
    fotografia_risorse_reali,
    porta_libera,
)

from beewatch import config, logging_config
from beewatch.config import ConfigDatabase, ottieni
from beewatch.database import Database
from beewatch.etl import STATI_AMMESSI, extract, load, transform

# Le variabili lette da beewatch.config, più DB_ROOT_PASSWORD: la config non la
# legge, ma i test la usano come segreto e non deve venire dal computer di chi
# li lancia. Vanno tolte dall'ambiente prima di ogni test, altrimenti il .env o
# la shell dello sviluppatore falsano il risultato.
VARIABILI_BEEWATCH = (
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_ROOT_PASSWORD",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_API_KEY",
    "LLM_TIMEOUT",
    "MODEL_PATH",
    "LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def ambiente_pulito(tmp_path: Path) -> Iterator[Path]:
    """Ambiente deterministico per ogni test. Restituisce la radice finta.

    - toglie le variabili BeeWatch da `os.environ` e a fine test lo rimette
      com'era (`patch.dict`): ciò che `load_dotenv` scrive nel processo non
      passa al test successivo né resta lì. Con `monkeypatch.delenv` non
      basterebbe: registrerebbe il valore «sporco» lasciato dal test
      precedente e lo ripristinerebbe, accumulando i segreti finti dei test.
      Non usa la fixture `monkeypatch` dei test: così viene montata prima e
      smontata dopo, e il ripristino dell'ambiente avviene per ultimo (se
      avvenisse prima, l'`undo` di un `setenv` del test cancellerebbe una
      variabile vera dello sviluppatore, appena rimessa a posto);
    - sposta `RADICE` (da cui `carica()` legge `.env`) e le cartelle dei log in
      una cartella temporanea vuota: nessun test legge il `.env` vero né
      scrive in `logs/`;
    - azzera la cache di `ottieni()`, che è memorizzata con lru_cache: senza,
      il secondo test riceverebbe la configurazione letta dal primo.

    È `autouse`: vale anche per i test che non la chiedono. Un test che vuole
    un `.env` nella radice lo scrive in `<radice>/.env`.
    """
    with mock.patch.dict(os.environ), pytest.MonkeyPatch.context() as mp:
        for nome in VARIABILI_BEEWATCH:
            os.environ.pop(nome, None)

        radice = tmp_path / "radice_progetto"
        radice.mkdir()
        mp.setattr(config, "RADICE", radice)
        mp.setattr(logging_config, "CARTELLA_LOG", radice / "logs")
        mp.setattr(logging_config, "FILE_LOG", radice / "logs" / "beewatch.log")

        ottieni.cache_clear()
        yield radice
        ottieni.cache_clear()


# --------------------------------------------------------------------------- #
# Nessuna rete: la suite non può chiamare un provider vero (M5-T6)
# --------------------------------------------------------------------------- #

_NOMI_LOCALI = frozenset({"", "localhost", "0.0.0.0", "::"})


def _indirizzo_locale(host: object) -> bool:
    """True per il computer stesso (loopback): i soli indirizzi con cui i test possono parlare."""
    if host is None:
        return True
    testo = host.decode() if isinstance(host, bytes) else str(host)
    if testo in _NOMI_LOCALI or testo.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(testo).is_loopback
    except ValueError:
        return False


def _blocca(host: object) -> RuntimeError:
    return RuntimeError(
        f"Test senza rete: la connessione a «{host}» è bloccata. I test parlano solo con il "
        "computer stesso (127.0.0.1): un provider vero non si chiama mai dalla suite."
    )


@pytest.fixture(autouse=True)
def rete_bloccata(ambiente_pulito: Path) -> Iterator[None]:
    """Vieta le connessioni e le risoluzioni DNS verso qualunque macchina che non sia questa.

    Il server HTTP finto dei test (127.0.0.1) e MySQL nello stack Docker (127.0.0.1, porta mappata)
    funzionano; Ollama, OpenRouter e Internet no: provano a collegarsi e il test fallisce subito con
    un messaggio chiaro, invece di passare perché per caso la rete c'era. Così «la suite gira senza
    rete e senza chiave API» non è una speranza ma una proprietà verificata a ogni esecuzione.
    """
    # Un proxy impostato nella shell dello sviluppatore instraderebbe anche le richieste al server
    # finto (127.0.0.1) fuori dal computer: i test dipenderebbero da come è configurata la sua rete.
    for nome in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        os.environ.pop(nome, None)
        os.environ.pop(nome.lower(), None)
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost,::1"

    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex
    risolvi = socket.getaddrinfo

    def connect_guardato(self: socket.socket, indirizzo: object) -> None:
        if self.family in (socket.AF_INET, socket.AF_INET6) and isinstance(indirizzo, tuple):
            if not _indirizzo_locale(indirizzo[0]):
                raise _blocca(indirizzo[0])
        return connect(self, indirizzo)  # type: ignore[arg-type]

    def connect_ex_guardato(self: socket.socket, indirizzo: object) -> int:
        if self.family in (socket.AF_INET, socket.AF_INET6) and isinstance(indirizzo, tuple):
            if not _indirizzo_locale(indirizzo[0]):
                raise _blocca(indirizzo[0])
        return connect_ex(self, indirizzo)  # type: ignore[arg-type]

    def risolvi_guardato(host: object, *argomenti: object, **opzioni: object):
        if not _indirizzo_locale(host):
            raise _blocca(host)
        return risolvi(host, *argomenti, **opzioni)  # type: ignore[arg-type]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(socket.socket, "connect", connect_guardato)
        mp.setattr(socket.socket, "connect_ex", connect_ex_guardato)
        mp.setattr(socket, "getaddrinfo", risolvi_guardato)
        yield


@pytest.fixture
def scrivi_env(tmp_path: Path) -> Callable[..., Path]:
    """Fabbrica di file `.env` temporanei.

    Uso:
        percorso = scrivi_env(DB_NAME="x", DB_USER="y", DB_PASSWORD="z")
        config = carica(percorso)
    """

    def _scrivi(**valori: object) -> Path:
        percorso = tmp_path / ".env"
        righe = "\n".join(f"{chiave}={valore}" for chiave, valore in valori.items())
        percorso.write_text(righe + "\n", encoding="utf-8")
        return percorso

    return _scrivi


@pytest.fixture
def logging_azzerato() -> Iterator[None]:
    """Riporta il logging allo stato iniziale prima e dopo il test.

    Serve perché gli handler vivono a livello di modulo: senza azzeramento il
    secondo test troverebbe quelli installati dal primo e la verifica
    sull'idempotenza non proverebbe nulla.
    """
    logging_config.azzera()
    yield
    logging_config.azzera()


# --------------------------------------------------------------------------- #
# MySQL vero per i test di integrazione del livello dati
# --------------------------------------------------------------------------- #
# Questi test non usano mai il database dello sviluppatore: girano su uno stack
# Docker temporaneo (progetto, contenitore e volume propri, credenziali casuali:
# vedi `docker_support.Stack`), e dentro quello stack sul database separato
# `<DB_NAME>_test`, creato da `sql/00_test_db.sh`. La configurazione è costruita
# qui a mano: niente `.env`, niente `os.environ`.


@pytest.fixture(scope="session")
def stack_mysql(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    """Un MySQL isolato, avviato alla prima richiesta e smontato a fine sessione.

    Se Docker non è in esecuzione il test FALLISCE: un test di integrazione
    saltato in silenzio sembrerebbe superato. Una sentinella confronta le
    risorse reali (contenitori e volume di sviluppo) prima e dopo.
    """
    if not docker_pronto():
        pytest.fail(
            "I test di integrazione del database richiedono Docker in esecuzione: "
            'avvia Docker Desktop, oppure lancia solo `pytest -m "not integration"`.',
            pytrace=False,
        )
    prima = fotografia_risorse_reali()
    stack = Stack(tmp_path_factory.mktemp("stack_mysql"), porta_libera())
    try:
        stack.avvia(costruisci=False, servizi=("mysql",))
        yield stack
    finally:
        stack.smonta()
    dopo = fotografia_risorse_reali()
    assert dopo == prima, f"le risorse reali sono cambiate durante i test: {prima} -> {dopo}"


@pytest.fixture(scope="session")
def config_db_test(stack_mysql: Stack) -> ConfigDatabase:
    """La configurazione del database di TEST dello stack isolato, mai di quello principale."""
    nome = f"{DB_NAME}_test"
    assert nome != DB_NAME and nome.endswith("_test")
    return ConfigDatabase(
        host="127.0.0.1",
        porta=stack_mysql.porta_db,
        nome=nome,
        utente=DB_USER,
        password=stack_mysql.password_app,
    )


@pytest.fixture
def database_test(config_db_test: ConfigDatabase) -> Database:
    """Un `Database` sul database di test. È quello che useranno anche i repository."""
    return Database(config_db_test)


@pytest.fixture
def dataset_nel_database(database_test: Database) -> Iterator[None]:
    """Il dataset vero caricato con l'ETL nel database di test (M4); alla fine lo toglie."""
    dataset = Path(__file__).resolve().parents[1] / "data" / "honeyproduction.csv"
    puliti, _ = transform(extract(dataset), anno_corrente=2026)
    load(puliti, database_test)
    yield
    segnaposto = ", ".join(["%s"] * len(STATI_AMMESSI))
    with database_test.transazione() as cursore:
        cursore.execute(
            f"DELETE FROM produzione_usda WHERE codice_stato IN ({segnaposto})",
            tuple(sorted(STATI_AMMESSI)),
        )


# --------------------------------------------------------------------------- #
# Un modello vero ma piccolo, salvato come in produzione (M4-T7)
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def artefatto_sintetico(tmp_path_factory: pytest.TempPathFactory):
    """Pipeline addestrata su un pannello sintetico e salvata con i suoi metadati.

    Restituisce un oggetto con `percorso` (il .joblib), `metadati` (quelli scritti nel .json),
    `modello` (la Pipeline in memoria) e `dati` (il pannello). Non si modifica: i test che
    devono rovinarlo ne copiano i file (`copia_artefatto`).
    """
    from datetime import UTC, datetime
    from types import SimpleNamespace

    import numpy as np
    import pandas as pd

    from beewatch.ml.addestramento import addestra_modello_finale, crea_metadati
    from beewatch.ml.artefatto import scrivi_artefatto
    from beewatch.ml.features import TARGET
    from beewatch.ml.valutazione import valuta_finale

    caso = np.random.default_rng(0)
    dati = pd.DataFrame(
        [
            {"codice_stato": s, "anno": a, "numero_colonie": 1000 * (i + 1) + a,
             TARGET: 30 + 5 * i - 0.5 * (a - 1998) + caso.normal(0, 3)}
            for i, s in enumerate(("AA", "BB", "CC", "DD", "EE", "FF"))
            for a in range(1998, 2013)
        ]
    )  # fmt: skip
    valutazione = valuta_finale(dati, ripetizioni_importanza=2)
    momento = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    metadati = crea_metadati(dati, valutazione, versione="v0.0.1-prova", addestrato_il=momento)
    modello = addestra_modello_finale(dati)
    percorso = tmp_path_factory.mktemp("artefatto") / "prova.joblib"
    completi = scrivi_artefatto(modello, metadati, percorso)
    return SimpleNamespace(percorso=percorso, metadati=completi, modello=modello, dati=dati)


@pytest.fixture
def copia_artefatto(artefatto_sintetico, tmp_path: Path) -> Path:
    """Una copia dei due file dell'artefatto, che il test può rovinare."""
    import shutil

    from beewatch.ml.artefatto import percorso_metadati

    destinazione = tmp_path / "copia.joblib"
    shutil.copy(artefatto_sintetico.percorso, destinazione)
    shutil.copy(percorso_metadati(artefatto_sintetico.percorso), percorso_metadati(destinazione))
    return destinazione
