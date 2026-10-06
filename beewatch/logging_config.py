"""
Configurazione centralizzata del logging.

Un solo punto in cui si decide *dove* finiscono i messaggi e *con che formato*.
I moduli non configurano nulla: chiedono il proprio logger e scrivono.

    from beewatch.logging_config import ottieni_logger

    logger = ottieni_logger(__name__)
    logger.info("Alveare %s aggiornato", codice)

Due destinazioni:

    - il terminale, per lo sviluppo e per la demo davanti al docente;
    - `logs/beewatch.log`, a rotazione, per ricostruire cosa è successo dopo.

Nota su Streamlit
-----------------
A ogni interazione dell'utente Streamlit riesegue lo script dall'inizio. Se
`configura()` non fosse idempotente, a ogni click aggiungerebbe un handler in
più e le righe di log si moltiplicherebbero (due, tre, dieci copie della stessa
riga). Per questo la funzione controlla se ha già lavorato e in tal caso esce
subito.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from beewatch.config import LIVELLI_LOG, RADICE, forma_canonica, ottieni
from beewatch.exceptions import ConfigError

# --------------------------------------------------------------------------- #
# Costanti
# --------------------------------------------------------------------------- #

# Il nome del logger di pacchetto. Ogni modulo che chiama ottieni_logger(__name__)
# ottiene un figlio di questo (es. "beewatch.database.repository") e ne eredita
# livello e handler.
NOME_LOGGER = "beewatch"

FORMATO = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"

CARTELLA_LOG = RADICE / "logs"
FILE_LOG = CARTELLA_LOG / "beewatch.log"

# Un file da 1 MB tiene circa 10.000 righe: abbastanza per una sessione di
# lavoro, poco abbastanza da restare leggibile. Ne conserviamo tre storici.
DIMENSIONE_MASSIMA_BYTE = 1_000_000
COPIE_STORICHE = 3

# Librerie di terze parti troppo loquaci quando il livello globale è DEBUG:
# senza questo, i messaggi dell'applicazione si perdono nel rumore.
LIBRERIE_SILENZIATE = ("urllib3", "httpx", "httpcore", "matplotlib", "PIL")

# Marcatore applicato ai nostri handler. Serve a riconoscerli fra quelli che
# altri strumenti (pytest, Streamlit) possono aggiungere allo stesso logger:
# la guardia di idempotenza deve rispondere a «ho già configurato *io*?», non
# a «esiste un handler qualsiasi?».
_MARCATORE = "_beewatch"

# Livelli che `configura()` ha cambiato alle librerie silenziate, così `azzera()`
# può rimetterli com'erano.
_livelli_precedenti: dict[str, int] = {}


# --------------------------------------------------------------------------- #
# Configurazione
# --------------------------------------------------------------------------- #


def _marca(handler: logging.Handler) -> logging.Handler:
    """Contrassegna un handler come nostro."""
    setattr(handler, _MARCATORE, True)
    return handler


def _nostri_handler(logger: logging.Logger) -> list[logging.Handler]:
    """Gli handler installati da questo modulo, ignorando quelli altrui."""
    return [h for h in logger.handlers if getattr(h, _MARCATORE, False)]


def _livello_richiesto(livello: str | None) -> str | None:
    """Livello passato a `configura()` in forma canonica, o None se omesso.

    Valgono le stesse regole di `LOG_LEVEL` in `.env`: maiuscole e minuscole
    indifferenti, vuoto equivale a «non indicato». Un valore sconosciuto
    solleva `ConfigError` invece del `ValueError` grezzo del modulo logging.
    """
    grezzo = (livello or "").strip()
    if not grezzo:
        return None
    canonico = forma_canonica(grezzo, LIVELLI_LOG)
    if canonico is None:
        raise ConfigError(
            f"Livello di log non valido: «{grezzo}». Valori ammessi: {', '.join(LIVELLI_LOG)}."
        )
    return canonico


def _crea_handler_su_file() -> RotatingFileHandler:
    """Prepara la cartella dei log e apre il file, traducendo gli errori di I/O."""
    try:
        CARTELLA_LOG.mkdir(parents=True, exist_ok=True)
        return RotatingFileHandler(
            FILE_LOG,
            maxBytes=DIMENSIONE_MASSIMA_BYTE,
            backupCount=COPIE_STORICHE,
            encoding="utf-8",
        )
    except OSError as errore:
        raise ConfigError(
            f"Impossibile usare il file di log {FILE_LOG}: "
            f"{errore.strerror or type(errore).__name__}. "
            f"Controlla che la cartella {CARTELLA_LOG} esista, sia scrivibile e non sia un file."
        ) from errore


def configura(livello: str | None = None, *, su_file: bool = True) -> logging.Logger:
    """Prepara il logger di pacchetto e restituisce il logger radice.

    Va chiamata una volta sola, il più presto possibile all'avvio
    dell'applicazione (in `app.py`, prima di qualunque altra cosa).

    Args:
        livello: forza un livello specifico (uno fra `LIVELLI_LOG`, senza
            distinguere maiuscole e minuscole). Se omesso o vuoto si usa
            `LOG_LEVEL` dalla configurazione, cioè dal file `.env`.
        su_file: se False scrive solo a terminale. Serve ai test, che non
            devono sporcare `logs/`.

    Returns:
        Il logger di pacchetto, già configurato.

    Raises:
        ConfigError: livello non valido, oppure cartella/file di log non
            utilizzabile. In entrambi i casi il logger resta com'era.
    """
    radice = logging.getLogger(NOME_LOGGER)
    richiesto = _livello_richiesto(livello)

    # Guardia di idempotenza (vedi la nota su Streamlit in cima al modulo):
    # si controllano solo gli handler che abbiamo installato noi.
    if _nostri_handler(radice):
        return radice

    livello_effettivo = richiesto or ottieni().livello_log

    formattatore = logging.Formatter(FORMATO, FORMATO_DATA)

    # Gli handler si preparano tutti prima di toccare il logger: se il file di
    # log non è utilizzabile l'eccezione esce senza lasciare una configurazione
    # a metà (console sì, file no).
    su_disco = _crea_handler_su_file() if su_file else None
    nuovi: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if su_disco is not None:
        nuovi.append(su_disco)

    for handler in nuovi:
        handler.setFormatter(formattatore)
        radice.addHandler(_marca(handler))

    radice.setLevel(livello_effettivo)

    # Il logger di pacchetto non propaga al logger root: senza questo, in
    # presenza di una configurazione di root (Streamlit ne installa una) ogni
    # riga verrebbe stampata due volte.
    radice.propagate = False

    for nome_libreria in LIBRERIE_SILENZIATE:
        libreria = logging.getLogger(nome_libreria)
        _livelli_precedenti[nome_libreria] = libreria.level
        libreria.setLevel(logging.WARNING)

    radice.debug(
        "Logging configurato: livello=%s, file=%s",
        livello_effettivo,
        FILE_LOG if su_file else "disattivato",
    )
    return radice


def ottieni_logger(nome: str) -> logging.Logger:
    """Logger da usare dentro un modulo.

    Uso previsto, in cima a ogni modulo che deve scrivere qualcosa:

        logger = ottieni_logger(__name__)

    Passando `__name__` il logger eredita automaticamente la configurazione
    del pacchetto e il messaggio porta con sé il modulo che l'ha prodotto.
    """
    return logging.getLogger(nome)


def azzera() -> None:
    """Annulla ciò che ha fatto `configura()`.

    Serve soltanto ai test, che devono poter riconfigurare il logging da capo
    fra un caso e l'altro. Non va chiamata dall'applicazione. Toglie i nostri
    handler, riporta il logger di pacchetto ai valori predefiniti di Python
    (livello NOTSET, `propagate` True: non quelli che aveva prima, che nessuno
    registra) e rimette alle librerie silenziate il livello che avevano prima di
    `configura()`. Senza il ripristino di `propagate`, `caplog` (che ascolta il
    root) non vedrebbe più i messaggi di `beewatch.*` per il resto della
    sessione. Gli handler installati da altri strumenti non vengono toccati.
    """
    radice = logging.getLogger(NOME_LOGGER)
    for handler in _nostri_handler(radice):
        handler.close()
        radice.removeHandler(handler)

    radice.setLevel(logging.NOTSET)
    radice.propagate = True

    for nome_libreria, livello in _livelli_precedenti.items():
        logging.getLogger(nome_libreria).setLevel(livello)
    _livelli_precedenti.clear()
