"""Accesso a MySQL: connessioni, transazioni, traduzione degli errori.

È il punto del progetto che sa come si parla con MySQL. Il resto del codice
riceve un `Database`, apre una `transazione()` e lavora con il cursore: non
importa `mysql.connector` e non ne vede le eccezioni. (L'unica altra eccezione
è `beewatch.healthcheck`, che di proposito fa da sé: è un controllo di salute
e non deve né ritentare né scrivere nei log dell'app.)

Uso tipico:

    from beewatch.config import ottieni
    from beewatch.database import Database

    db = Database(ottieni().database)
    with db.transazione() as cursore:
        cursore.execute(
            "SELECT id, codice FROM alveari WHERE apiario_id = %s AND attivo = TRUE",
            (apiario_id,),
        )
        righe = cursore.fetchall()  # list[dict]: una riga è un dizionario per colonna

Le scelte che contano:

- **La configurazione si passa, non si va a prendere.** `Database` riceve una
  `ConfigDatabase` e non chiama `ottieni()`: così i test usano un database
  diverso semplicemente costruendo un'altra configurazione, e nessun codice può
  finire sul database vero «per dimenticanza».
- **Una connessione per transazione, nessun pool.** Si apre all'ingresso del
  `with` e si chiude all'uscita. Non c'è stato condiviso fra le chiamate (né in
  questo modulo né nell'oggetto), quindi non c'è niente da proteggere fra i
  thread di Streamlit e niente da rilasciare allo spegnimento.
- **Si ritenta solo l'apertura della connessione**, e solo per gli errori che
  possono passare da soli (server non ancora pronto, rete). Una query non si
  ripete mai: rieseguire una scrittura può duplicarla. Credenziali sbagliate o
  database inesistente non si ritentano: non cambierebbe niente.
- **Gli errori del driver diventano `DatabaseError`**, con un messaggio in
  italiano per chi usa l'app. I dettagli tecnici vanno nel log, mai la password.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import mysql.connector

from beewatch.config import ConfigDatabase
from beewatch.exceptions import DatabaseError
from beewatch.logging_config import ottieni_logger

if TYPE_CHECKING:
    from mysql.connector.abstracts import MySQLConnectionAbstract, MySQLCursorAbstract

logger = ottieni_logger(__name__)

# Secondi concessi all'apertura di una connessione, per ogni tentativo.
TIMEOUT_CONNESSIONE = 5
# `verifica_connessione()` serve all'interfaccia, che non può restare ferma:
# un solo tentativo, più breve.
TIMEOUT_VERIFICA = 2

# Attese fra un tentativo di connessione e il successivo: i tentativi sono uno
# in più delle attese. Con questi valori, tre tentativi e al massimo 1,5 secondi
# di attesa in tutto.
ATTESE_RETRY = (0.5, 1.0)

# Errori che possono risolversi da soli nel giro di un secondo. Sono gli unici
# per cui ha senso riprovare.
#   1040  troppe connessioni aperte sul server
#   2002  server non raggiungibile (socket locale)
#   2003  server non raggiungibile (rete): spento, in avvio, porta sbagliata
#   2006  il server ha chiuso la connessione
#   2013  connessione persa durante la stretta di mano (MySQL sta ancora partendo)
#   2055  connessione persa (stesso caso, segnalato dal driver)
ERRORI_TRANSITORI = frozenset({1040, 2002, 2003, 2006, 2013, 2055})

# Messaggi per l'utente finale, per numero d'errore di MySQL. Tutto ciò che non
# è qui riceve un messaggio generico (vedi `_messaggio`).
_SERVER_IRRAGGIUNGIBILE = (
    "Impossibile connettersi al database. Verifica che MySQL sia avviato "
    "(docker compose up -d mysql) e che DB_HOST e DB_PORT in .env siano corretti."
)
_MESSAGGI = {
    1040: "Il database ha troppe connessioni aperte. Riprova fra qualche secondo.",
    1044: (
        "L'utente del database non ha accesso al database «{nome}». "
        "Controlla DB_NAME e DB_USER in .env."
    ),
    1045: "Il database ha rifiutato le credenziali. Controlla DB_USER e DB_PASSWORD in .env.",
    1049: (
        "Il database «{nome}» non esiste. Controlla DB_NAME in .env, oppure ricrea "
        "il database (docker compose down -v, poi docker compose up -d)."
    ),
    1142: "L'utente del database non ha il permesso di eseguire questa operazione.",
    2002: _SERVER_IRRAGGIUNGIBILE,
    2003: _SERVER_IRRAGGIUNGIBILE,
    2005: _SERVER_IRRAGGIUNGIBILE,
}
_CONNESSIONE_PERSA = frozenset({2006, 2013, 2055})


class Database:
    """Porta d'accesso a un database MySQL.

    Costruirlo non apre connessioni: la prima si apre alla prima `transazione()`
    (o `verifica_connessione()`). L'oggetto non conserva connessioni né altro
    stato, quindi si può condividere fra thread e non va chiuso.
    """

    def __init__(self, config: ConfigDatabase) -> None:
        self._config = config

    # ----------------------------------------------------------------------- #
    # Interfaccia
    # ----------------------------------------------------------------------- #

    @contextmanager
    def transazione(self) -> Iterator[MySQLCursorAbstract]:
        """Una transazione: tutto ciò che si esegue nel blocco vale o non vale insieme.

        Restituisce un cursore le cui righe sono dizionari (`riga["codice"]`).

        - Il blocco termina senza errori: `commit`.
        - Il blocco solleva una qualunque eccezione: `rollback`, poi l'eccezione
          riemerge. Se viene dal driver riemerge come `DatabaseError`; le altre
          (una `ValidationError`, un bug) riemergono così come sono.
        - In ogni caso cursore e connessione vengono chiusi.

        Raises:
            DatabaseError: connessione impossibile, query o commit falliti.
        """
        connessione = self._apri(TIMEOUT_CONNESSIONE, ATTESE_RETRY)
        cursore = None
        logger.debug("Transazione aperta su %s", self._config.descrizione())
        try:
            # buffered: le righe si leggono tutte subito. Senza, un risultato non
            # letto fino in fondo farebbe fallire il commit («Unread result found»).
            cursore = connessione.cursor(dictionary=True, buffered=True)
            yield cursore
            connessione.commit()
            logger.debug("Transazione confermata (commit)")
        except mysql.connector.Error as errore:
            self._annulla(connessione)
            self._registra(errore, "Transazione annullata per un errore di MySQL")
            raise DatabaseError(self._messaggio(errore, in_connessione=False)) from errore
        except BaseException:
            # Qualunque altra cosa, comprese l'interruzione da tastiera e la
            # chiusura del generatore: i dati non devono restare a metà.
            self._annulla(connessione)
            logger.debug("Transazione annullata (rollback): il blocco ha sollevato un'eccezione")
            raise
        finally:
            self._chiudi(cursore, connessione)

    def verifica_connessione(self) -> bool:
        """True se il database risponde, False altrimenti. Non solleva.

        Serve all'interfaccia per mostrare lo stato del database. È pensata per
        essere rapida: un solo tentativo con un timeout breve, niente retry.
        """
        try:
            connessione = self._apri(TIMEOUT_VERIFICA, attese=())
        except DatabaseError:
            return False

        cursore = None
        try:
            cursore = connessione.cursor()
            cursore.execute("SELECT 1")
            cursore.fetchall()
        except mysql.connector.Error as errore:
            self._registra(errore, "Verifica della connessione fallita")
            return False
        finally:
            self._chiudi(cursore, connessione)
        return True

    # ----------------------------------------------------------------------- #
    # Connessione
    # ----------------------------------------------------------------------- #

    def _apri(self, timeout: int, attese: tuple[float, ...]) -> MySQLConnectionAbstract:
        """Apre una connessione, ritentando gli errori transitori dopo ogni attesa."""
        fatti = 0
        while True:
            try:
                return mysql.connector.connect(
                    host=self._config.host,
                    port=self._config.porta,
                    user=self._config.utente,
                    password=self._config.password,
                    database=self._config.nome,
                    charset="utf8mb4",
                    collation="utf8mb4_unicode_ci",
                    autocommit=False,
                    connection_timeout=timeout,
                )
            except mysql.connector.Error as errore:
                if errore.errno not in ERRORI_TRANSITORI or fatti == len(attese):
                    self._registra(errore, "Connessione al database non riuscita")
                    raise DatabaseError(self._messaggio(errore, in_connessione=True)) from errore
                attesa = attese[fatti]
                fatti += 1
                logger.warning(
                    "Connessione a %s non riuscita (errore MySQL %s): tentativo %d di %d, "
                    "riprovo fra %.1f s",
                    self._config.descrizione(),
                    errore.errno,
                    fatti,
                    len(attese) + 1,
                    attesa,
                )
                time.sleep(attesa)

    @staticmethod
    def _annulla(connessione: MySQLConnectionAbstract) -> None:
        """Rollback che non solleva: l'errore che conta è quello che l'ha causato."""
        try:
            connessione.rollback()
        except Exception as errore:  # qualunque cosa: non deve coprire l'originale
            # Tipico: la connessione è caduta. Il server annulla comunque la
            # transazione quando la connessione si chiude.
            logger.warning("Rollback non riuscito (%s)", type(errore).__name__)

    @staticmethod
    def _chiudi(cursore: Any, connessione: MySQLConnectionAbstract) -> None:
        """Chiude cursore e connessione. Un errore in chiusura non deve mascherare altro."""
        for risorsa in (cursore, connessione):
            if risorsa is None:
                continue
            try:
                risorsa.close()
            except Exception as errore:  # vedi sopra
                logger.warning(
                    "Chiusura di %s non riuscita (%s)",
                    "cursore" if risorsa is cursore else "connessione",
                    type(errore).__name__,
                )

    # ----------------------------------------------------------------------- #
    # Errori
    # ----------------------------------------------------------------------- #

    def _registra(self, errore: mysql.connector.Error, cosa: str) -> None:
        """Scrive nel log i dettagli tecnici di un errore del driver.

        A livello ERROR vanno solo numero d'errore e SQLSTATE, con la descrizione
        del database (senza password). Il testo del driver va a DEBUG: può citare
        un pezzo della query o un valore («Duplicate entry '...'»), cioè dati che
        in un log normale non devono finire.
        """
        logger.error(
            "%s: errore MySQL %s (SQLSTATE %s) su %s",
            cosa,
            errore.errno,
            errore.sqlstate,
            self._config.descrizione(),
        )
        logger.debug("Dettaglio del driver: %s", errore.msg)

    def _messaggio(self, errore: mysql.connector.Error, *, in_connessione: bool) -> str:
        """Il messaggio per l'utente finale: cosa è successo e cosa fare."""
        if errore.errno in _CONNESSIONE_PERSA:
            if in_connessione:
                return _SERVER_IRRAGGIUNGIBILE
            return (
                "La connessione al database si è interrotta e l'operazione non è stata "
                "completata. Riprova."
            )
        modello = _MESSAGGI.get(errore.errno)
        if modello is not None:
            return modello.format(nome=self._config.nome)
        if in_connessione:
            return "Impossibile connettersi al database. I dettagli sono nel file di log."
        return (
            "L'operazione sul database non è riuscita e non è stata salvata. "
            "I dettagli sono nel file di log."
        )
