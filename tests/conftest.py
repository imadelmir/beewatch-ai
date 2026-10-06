"""Fixture condivise da tutti i test di BeeWatch AI.

Il problema che risolvono: la configurazione legge da `os.environ` e dal file
`.env` dello sviluppatore. Senza isolamento, gli stessi test passerebbero sul
computer di chi ha un `.env` completo e fallirebbero sulla CI, che non ce l'ha.
Qui l'ambiente viene azzerato e ricostruito caso per caso, e la radice del
progetto (da cui si leggono `.env` e `logs/`) punta a una cartella temporanea.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest import mock

import pytest

from beewatch import config, logging_config
from beewatch.config import ottieni

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
