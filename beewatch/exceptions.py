"""
Gerarchia delle eccezioni di BeeWatch AI.

Tutti gli errori *previsti* dall'applicazione discendono da `BeeWatchError`.
Questo permette a chi chiama di separare in due righe i due casi che vanno
trattati in modo diverso:

    try:
        alveari = repository.elenca()
    except BeeWatchError as errore:
        # problema previsto: messaggio comprensibile all'utente
        st.error(str(errore))
    except Exception:
        # imprevisto: è un bug, va nel log con lo stack completo
        logger.exception("Errore non gestito")
        st.error("Errore imprevisto. Controlla il file di log.")

Il messaggio di ogni eccezione è scritto in italiano e senza gergo tecnico,
perché finisce sotto gli occhi dell'utente finale. I dettagli tecnici (query
SQL, traceback, risposta del provider) vanno nel log, non nel messaggio.
"""

from __future__ import annotations


class BeeWatchError(Exception):
    """Radice di tutti gli errori previsti dall'applicazione.

    Non va sollevata direttamente: si usa sempre una delle sottoclassi.
    Esiste per essere intercettata.
    """


class ConfigError(BeeWatchError):
    """Configurazione assente, incompleta o con valori non validi.

    Sollevata all'avvio da `beewatch.config.carica()` e da
    `beewatch.logging_config.configura()` (livello di log non valido, file di
    log inutilizzabile). È l'unico errore che l'applicazione non può gestire in
    alcun modo: se la configurazione non è valida, non c'è niente da avviare.
    """


class DatabaseError(BeeWatchError):
    """Errore nell'accesso a MySQL.

    Copre connessione rifiutata, credenziali sbagliate, timeout e query
    fallite. Il modulo di accesso ai dati traduce qui le eccezioni del driver,
    così il resto del progetto non conosce `mysql.connector`.
    """


class ValidationError(BeeWatchError):
    """Dato inserito dall'utente non valido.

    Porta con sé il nome del campo che ha causato il problema, così il form
    che l'ha sollevata può evidenziare la casella giusta invece di limitarsi
    a un messaggio generico in cima alla pagina.
    """

    def __init__(self, messaggio: str, campo: str | None = None) -> None:
        super().__init__(messaggio)
        self.campo = campo


class ModelError(BeeWatchError):
    """Il modello di machine learning è assente o non utilizzabile.

    Casi tipici: il file .joblib indicato da MODEL_PATH non esiste perché non
    è ancora stato addestrato, oppure è stato salvato con una versione di
    scikit-learn incompatibile.
    """


class LLMError(BeeWatchError):
    """Il modello di linguaggio non risponde o risponde male.

    Copre il server Ollama spento, la chiave OpenRouter rifiutata, il timeout
    e le risposte che non rispettano il formato richiesto dal prompt.
    """
