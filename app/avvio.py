"""Avvio comune a ogni pagina: stato della sessione, servizi e letture in cache (M6-T1).

Streamlit esegue ogni pagina come uno script a sé, da cima a fondo, a ogni interazione. Tre cose
non devono ripetersi a ogni esecuzione, e stanno qui, in un posto solo:

- **le risorse** (i servizi, il modello caricato) si creano una volta per processo con
  `@st.cache_resource`: il modello non va ricaricato a ogni clic. Un log (`Modello vN caricato…`,
  scritto da `Predittore`) dimostra che accade una volta sola;
- **le letture dal database** si ricordano per `TTL_LETTURE_SECONDI` con `@st.cache_data`:
  abbastanza a lungo per non rifare le stesse query a ogni clic, abbastanza poco perché un dato
  nuovo compaia presto. Dopo una scrittura la pagina chiama `svuota_letture()` e il dato nuovo
  si vede subito;
- **lo stato della sessione** (`st.session_state`) si inizializza in `inizializza_stato()` e da
  nessun'altra parte: chi cerca una chiave sa dove nasce.

Qui non c'è logica applicativa né SQL: si chiamano i servizi di `beewatch/services.py`. Non si
importano il livello dati, `joblib` né il client del modello di linguaggio (regola della
specifica, §2).

Gli helper visivi condivisi (intestazione, sidebar, banner AI, metriche…) sono un'altra cosa:
stanno in `app/ui.py` (M6-T2), che legge da qui risorse, letture e stato.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from beewatch.exceptions import BeeWatchError
from beewatch.logging_config import configura, ottieni_logger
from beewatch.models import Apiario
from beewatch.services import (
    AlveareInElenco,
    ApiarioScelta,
    IntervalloParametro,
    IspezioneInElenco,
    Panoramica,
    Servizi,
    StatoModello,
    StatoPrevedibile,
    crea_servizi,
)

# Sotto `beewatch.`, così eredita le impostazioni di `configura()` (file di log, livello): un logger
# chiamato «avvio» (il nome del modulo, che Streamlit carica a sé) non scriverebbe da nessuna parte.
logger = ottieni_logger("beewatch.app.avvio")

# DA-02: nessun login, un solo utente dimostrativo (quello del seed). Quando ci sarà
# l'autenticazione (M6-T11) l'id verrà da lì; le pagine lo leggono già dallo stato della sessione.
UTENTE_DEMO_ID = 1

# Quanto vive una lettura in cache. Dichiarato qui, non sparso nei decoratori.
TTL_LETTURE_SECONDI = 60

CHIAVE_UTENTE = "utente_id"
CHIAVE_APIARIO_ATTIVO = "apiario_attivo_id"
# La chiave del selettore nella sidebar. È distinta da CHIAVE_APIARIO_ATTIVO perché Streamlit
# dimentica lo stato di un widget quando si cambia pagina: la scelta vera vive nella chiave non
# legata a widget, e il selettore la ricopia a ogni esecuzione (vedi `prepara_selettore_apiario`).
CHIAVE_SELETTORE_APIARIO = "selettore_apiario"
# L'esito dell'ultima scrittura («Alveare A3 aggiunto»): dopo una scrittura la pagina si riesegue
# da capo (`st.rerun`) per mostrare i dati nuovi, e il messaggio deve sopravvivere a quel giro.
CHIAVE_ESITO = "esito_operazione"


# --------------------------------------------------------------------------- #
# Risorse: una volta per processo
# --------------------------------------------------------------------------- #


@st.cache_resource(show_spinner=False)
def servizi() -> Servizi:
    """I servizi dell'applicazione (database, modello, assistente), creati una volta sola.

    Non apre connessioni e non carica il modello: lo fanno alla prima richiesta.
    """
    configura()
    logger.info("Servizi creati: da ora restano in memoria finché l'app non si riavvia")
    return crea_servizi()


@st.cache_resource(show_spinner="Carico il modello di previsione…")
def modello() -> StatoModello:
    """Il modello di previsione, caricato una volta per processo. `ModelError` se non c'è.

    Un errore non viene ricordato: ricaricando la pagina dopo aver messo il file al suo posto si
    riprova.
    """
    return servizi().stato_modello()


# --------------------------------------------------------------------------- #
# Letture: in cache per un tempo dichiarato
# --------------------------------------------------------------------------- #


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
def panoramica(utente_id: int) -> Panoramica:
    """I numeri della Home e l'elenco degli apiari (sola lettura, `TTL_LETTURE_SECONDI`)."""
    return servizi().panoramica(utente_id)


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
def apiari(utente_id: int) -> tuple[ApiarioScelta, ...]:
    """Gli apiari tra cui scegliere quello attivo (sola lettura, `TTL_LETTURE_SECONDI`)."""
    return tuple(servizi().elenca_apiari(utente_id))


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
def apiari_in_anagrafica(utente_id: int) -> tuple[Apiario, ...]:
    """Gli apiari con tutti i campi, per la pagina Alveari (sola lettura, `TTL_LETTURE_SECONDI`)."""
    return tuple(servizi().apiari_in_anagrafica(utente_id))


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
def alveari_dell_apiario(utente_id: int, apiario_id: int) -> tuple[AlveareInElenco, ...]:
    """Gli alveari attivi di un apiario, con l'ultima ispezione (sola lettura, in cache)."""
    return tuple(servizi().alveari_dell_apiario(utente_id, apiario_id))


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
def ispezioni_dell_apiario(
    utente_id: int,
    apiario_id: int,
    alveare_id: int | None = None,
    dal: date | None = None,
    al: date | None = None,
) -> tuple[IspezioneInElenco, ...]:
    """Lo storico delle ispezioni di un apiario, filtrato (sola lettura, in cache)."""
    return tuple(
        servizi().ispezioni_dell_apiario(
            utente_id, apiario_id, alveare_id=alveare_id, dal=dal, al=al
        )
    )


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
def stati_prevedibili() -> tuple[StatoPrevedibile, ...]:
    """Gli stati per cui il modello può prevedere, con i loro anni (sola lettura, in cache)."""
    return tuple(servizi().stati_prevedibili())


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
def intervalli_parametri() -> tuple[IntervalloParametro, ...]:
    """Gli intervalli ammessi per i parametri scritti a mano (sola lettura, in cache)."""
    return servizi().intervalli_parametri()


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
def storico_previsioni(utente_id: int, alveare_id: int | None = None) -> tuple[dict, ...]:
    """Le ultime previsioni salvate, di tutti gli alveari o di uno (sola lettura, in cache)."""
    return tuple(servizi().storico_previsioni(utente_id, alveare_id=alveare_id))


def svuota_letture() -> None:
    """Dimentica tutte le letture in cache: da chiamare subito dopo una scrittura."""
    st.cache_data.clear()


# --------------------------------------------------------------------------- #
# Stato della sessione: l'unico punto in cui nasce
# --------------------------------------------------------------------------- #


def inizializza_stato() -> None:
    """Crea le chiavi di `st.session_state` che mancano, senza toccare quelle che ci sono.

    - `utente_id`: l'utente corrente (DA-02: quello dimostrativo);
    - `apiario_attivo_id`: l'apiario scelto, il contesto di tutte le pagine; `None` finché non si
      sa quali apiari esistono (lo imposta `scegli_apiario_iniziale`);
    - `esito_operazione`: il messaggio dell'ultima scrittura riuscita, finché non si mostra.
    """
    st.session_state.setdefault(CHIAVE_UTENTE, UTENTE_DEMO_ID)
    st.session_state.setdefault(CHIAVE_APIARIO_ATTIVO, None)
    st.session_state.setdefault(CHIAVE_ESITO, None)


def scegli_apiario_iniziale(apiari: tuple[ApiarioScelta, ...]) -> None:
    """Se l'apiario attivo manca (o non esiste più), diventa il primo dell'elenco."""
    ammessi = {a.id for a in apiari}
    if st.session_state[CHIAVE_APIARIO_ATTIVO] not in ammessi:
        st.session_state[CHIAVE_APIARIO_ATTIVO] = apiari[0].id if apiari else None


def apiario_attivo(apiari: tuple[ApiarioScelta, ...]) -> ApiarioScelta | None:
    """L'apiario attivo, tra quelli dell'utente, o None se non ce n'è nessuno."""
    attivo = st.session_state[CHIAVE_APIARIO_ATTIVO]
    return next((a for a in apiari if a.id == attivo), None)


def prepara_selettore_apiario() -> None:
    """Porta nel selettore della sidebar l'apiario attivo, prima di disegnarlo.

    Va chiamata a ogni esecuzione, prima di `st.selectbox(key=CHIAVE_SELETTORE_APIARIO)`: così il
    selettore mostra la scelta fatta su un'altra pagina anche se Streamlit ha dimenticato il
    widget nel cambio di pagina.
    """
    st.session_state[CHIAVE_SELETTORE_APIARIO] = st.session_state[CHIAVE_APIARIO_ATTIVO]


def al_cambio_apiario() -> None:
    """Callback del selettore: la scelta dell'utente diventa l'apiario attivo di tutte le pagine."""
    st.session_state[CHIAVE_APIARIO_ATTIVO] = st.session_state[CHIAVE_SELETTORE_APIARIO]


def imposta_apiario_attivo(apiario_id: int) -> None:
    """Rende attivo un apiario (per esempio quello appena creato) su tutte le pagine."""
    st.session_state[CHIAVE_APIARIO_ATTIVO] = apiario_id


# --------------------------------------------------------------------------- #
# Dopo una scrittura
# --------------------------------------------------------------------------- #


def scrittura_riuscita(messaggio: str) -> None:
    """Chiude una scrittura riuscita: letture da rifare, esito da mostrare, pagina da rieseguire.

    `st.rerun()` interrompe l'esecuzione: va chiamata per ultima, fuori da un `try` che intercetti
    tutto. Al giro dopo la pagina mostra l'esito con `prendi_esito()` e i dati già aggiornati.
    """
    svuota_letture()
    st.session_state[CHIAVE_ESITO] = messaggio
    st.rerun()


def prendi_esito() -> str | None:
    """L'esito dell'ultima scrittura, una volta sola: dopo averlo letto non c'è più."""
    messaggio = st.session_state[CHIAVE_ESITO]
    st.session_state[CHIAVE_ESITO] = None
    return messaggio


# --------------------------------------------------------------------------- #
# Prima riga di ogni pagina
# --------------------------------------------------------------------------- #


def avvia(titolo: str, icona: str = "🐝") -> Servizi:
    """Prepara la pagina: configurazione, stato, servizi. Va chiamata per prima in ogni pagina.

    `st.set_page_config` dev'essere il primo comando Streamlit di uno script, quindi sta qui e non
    nella pagina. Se la configurazione non è valida l'errore si mostra e la pagina si ferma: è
    l'unico errore da cui non si può proseguire.
    """
    st.set_page_config(page_title=f"{titolo} · BeeWatch AI", page_icon=icona, layout="wide")
    inizializza_stato()
    try:
        return servizi()
    except BeeWatchError as errore:
        # Import qui e non in cima: `ui` importa `avvio`, e il contrario in cima sarebbe un ciclo.
        from ui import mostra_errore

        st.title("🐝 BeeWatch AI")
        st.write("L'applicazione non può partire.")
        mostra_errore(errore)
        st.stop()
