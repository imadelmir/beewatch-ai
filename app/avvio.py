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
stanno in `app/ui.py` e arrivano con M6-T2.
"""

from __future__ import annotations

import streamlit as st

from beewatch.exceptions import BeeWatchError
from beewatch.logging_config import configura, ottieni_logger
from beewatch.services import ApiarioScelta, Panoramica, Servizi, StatoModello, crea_servizi

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
      sa quali apiari esistono (lo imposta `scegli_apiario_iniziale`).
    """
    st.session_state.setdefault(CHIAVE_UTENTE, UTENTE_DEMO_ID)
    st.session_state.setdefault(CHIAVE_APIARIO_ATTIVO, None)


def scegli_apiario_iniziale(apiari: tuple[ApiarioScelta, ...]) -> None:
    """Se l'apiario attivo manca (o non esiste più), diventa il primo dell'elenco."""
    ammessi = {a.id for a in apiari}
    if st.session_state[CHIAVE_APIARIO_ATTIVO] not in ammessi:
        st.session_state[CHIAVE_APIARIO_ATTIVO] = apiari[0].id if apiari else None


def apiario_attivo(apiari: tuple[ApiarioScelta, ...]) -> ApiarioScelta | None:
    """L'apiario attivo, tra quelli dell'utente, o None se non ce n'è nessuno."""
    attivo = st.session_state[CHIAVE_APIARIO_ATTIVO]
    return next((a for a in apiari if a.id == attivo), None)


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
        st.error("L'applicazione non può partire.")
        st.code(str(errore), language="text")
        st.stop()
