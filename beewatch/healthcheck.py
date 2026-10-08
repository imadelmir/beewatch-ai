"""Controllo di salute del contenitore dell'applicazione.

È il comando del `HEALTHCHECK` del Dockerfile:

    python -m beewatch.healthcheck

Un contenitore dell'app è «sano» solo se sono veri tutti e tre i punti, nell'ordine:

    1. la configurazione è valida (le variabili DB_* arrivano e sono corrette);
    2. Streamlit risponde;
    3. MySQL è raggiungibile con le credenziali dell'applicazione.

I primi due dicono se l'app è viva, il terzo se può lavorare: senza, un contenitore
con la password sbagliata o il database spento risulterebbe `healthy` e nessuno se
ne accorgerebbe finché qualcuno non apre una pagina.

Il controllo non scrive nulla: apre una connessione e fa `SELECT 1`. Stampa una riga
sola, con il motivo in poche parole (è ciò che si legge in `docker inspect`), e non
include mai host, utente, password o il testo degli errori del driver: quel testo può
contenere le credenziali. Per i dettagli ci sono i log dell'app.

Esce con 0 se sano, con 1 altrimenti.
"""

from __future__ import annotations

import sys
import urllib.request

import mysql.connector

from beewatch.config import Config, ottieni
from beewatch.exceptions import BeeWatchError

# Lo stesso indirizzo e la stessa porta di `streamlit run` nel Dockerfile. 127.0.0.1 e
# non `localhost`: quest'ultimo può risolversi in ::1, dove Streamlit non ascolta.
URL_STREAMLIT = "http://127.0.0.1:8501/_stcore/health"

# Ogni controllo ha un tempo massimo: la somma resta sotto il `--timeout` del
# HEALTHCHECK, così un database che non risponde dà «unhealthy» e non un blocco.
TIMEOUT_SECONDI = 3


def _controlla_streamlit() -> str | None:
    """None se Streamlit risponde 200, altrimenti il motivo."""
    try:
        with urllib.request.urlopen(URL_STREAMLIT, timeout=TIMEOUT_SECONDI) as risposta:
            if risposta.status == 200:
                return None
            return f"Streamlit risponde con stato {risposta.status}"
    except OSError:  # URLError, rifiuto della connessione e timeout sono tutti OSError
        return "Streamlit non risponde"


def _controlla_database(config: Config) -> str | None:
    """None se MySQL accetta le credenziali dell'app ed esegue `SELECT 1`."""
    try:
        connessione = mysql.connector.connect(
            host=config.database.host,
            port=config.database.porta,
            user=config.database.utente,
            password=config.database.password,
            database=config.database.nome,
            connection_timeout=TIMEOUT_SECONDI,
        )
    except mysql.connector.Error as errore:
        # Solo il numero: il messaggio può citare utente e host.
        return f"database non raggiungibile (errore MySQL {errore.errno})"

    try:
        cursore = connessione.cursor()
        cursore.execute("SELECT 1")
        cursore.fetchall()
    except mysql.connector.Error as errore:
        return f"il database non esegue query (errore MySQL {errore.errno})"
    finally:
        connessione.close()
    return None


def controlla() -> str | None:
    """None se il contenitore è sano, altrimenti il motivo in una riga."""
    try:
        config = ottieni()
    except BeeWatchError:
        # Il messaggio di ConfigError elenca anche i valori sbagliati: qui no.
        return "configurazione non valida (vedi i log dell'app)"
    return _controlla_streamlit() or _controlla_database(config)


def main() -> int:
    problema = controlla()
    if problema:
        print(f"KO: {problema}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
