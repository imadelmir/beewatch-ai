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

import functools
import threading
import time
from collections.abc import Callable
from datetime import date
from typing import Any, TypeVar

import pandas as pd
import streamlit as st

from beewatch.exceptions import BeeWatchError, DatabaseError
from beewatch.logging_config import configura, ottieni_logger
from beewatch.models import Apiario
from beewatch.services import (
    AlveareInElenco,
    ApiarioScelta,
    DatiDashboard,
    IntervalloParametro,
    IspezioneInElenco,
    MetricheModello,
    Panoramica,
    RiepilogoSalvato,
    Servizi,
    StatoModello,
    StatoPrevedibile,
    UtenteAutenticato,
    crea_servizi,
)

# Sotto `beewatch.`, così eredita le impostazioni di `configura()` (file di log, livello): un logger
# chiamato «avvio» (il nome del modulo, che Streamlit carica a sé) non scriverebbe da nessuna parte.
logger = ottieni_logger("beewatch.app.avvio")


# Quanto vive una lettura in cache. Dichiarato qui, non sparso nei decoratori.
TTL_LETTURE_SECONDI = 60
# Dopo un errore del database, per quanti secondi le altre letture falliscono subito con lo
# stesso errore invece di ritentare la connessione (vedi `_interruttore`, M6-T9).
PAUSA_DOPO_ERRORE_DB_SECONDI = 10

CHIAVE_UTENTE = "utente_id"
CHIAVE_APIARIO_ATTIVO = "apiario_attivo_id"
# La chiave del selettore nella sidebar. È distinta da CHIAVE_APIARIO_ATTIVO perché Streamlit
# dimentica lo stato di un widget quando si cambia pagina: la scelta vera vive nella chiave non
# legata a widget, e il selettore la ricopia a ogni esecuzione (vedi `prepara_selettore_apiario`).
CHIAVE_SELETTORE_APIARIO = "selettore_apiario"
# L'esito dell'ultima scrittura («Alveare A3 aggiunto»): dopo una scrittura la pagina si riesegue
# da capo (`st.rerun`) per mostrare i dati nuovi, e il messaggio deve sopravvivere a quel giro.
CHIAVE_ESITO = "esito_operazione"
# M6-T11: il nome di chi ha fatto l'accesso (None = nessuno: il router mostra Accedi e Registrati)
# e il passo dell'onboarding guidato dopo la registrazione (None = finito o saltato).
CHIAVE_ACCESSO = "accesso"
CHIAVE_ONBOARDING = "onboarding"
PASSI_ONBOARDING = 3  # primo apiario, primo alveare, tutto pronto


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


# --------------------------------------------------------------------------- #
# L'interruttore del database (M6-T9)
# --------------------------------------------------------------------------- #
# Con un server che non risponde, ogni lettura ritenta la connessione (tre tentativi da qualche
# secondo, `beewatch/database.py`). La sidebar e il corpo della pagina leggono ciascuno per conto
# suo: senza interruttore l'attesa si moltiplica (circa 30 s prima dell'errore, misurati in M6-T2).
# Dopo il primo `DatabaseError` di connessione (`connessione=True`: il server non risponde, non
# una query sbagliata) le letture successive falliscono subito, con lo stesso messaggio,
# per `PAUSA_DOPO_ERRORE_DB_SECONDI`; poi si riprova davvero. Una lettura riuscita lo richiude.

_F = TypeVar("_F", bound=Callable[..., Any])
_ultimo_errore_db: dict[str, Any] = {"quando": 0.0, "errore": None}
_blocco_errore_db = threading.Lock()


def _interruttore(lettura: _F) -> _F:
    @functools.wraps(lettura)
    def protetta(*argomenti: Any, **opzioni: Any) -> Any:
        with _blocco_errore_db:
            errore = _ultimo_errore_db["errore"]
            recente = time.monotonic() - _ultimo_errore_db["quando"] < PAUSA_DOPO_ERRORE_DB_SECONDI
        if errore is not None and recente:
            raise errore
        try:
            risultato = lettura(*argomenti, **opzioni)
        except DatabaseError as nuovo:
            if nuovo.connessione:  # il server non risponde; una query sbagliata no
                with _blocco_errore_db:
                    _ultimo_errore_db.update(quando=time.monotonic(), errore=nuovo)
            raise
        with _blocco_errore_db:
            _ultimo_errore_db["errore"] = None
        return risultato

    return protetta  # type: ignore[return-value]


def azzera_interruttore() -> None:
    """Dimentica l'ultimo errore del database: lo chiama `svuota_letture` dopo una scrittura."""
    with _blocco_errore_db:
        _ultimo_errore_db.update(quando=0.0, errore=None)


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
@_interruttore
def panoramica(utente_id: int) -> Panoramica:
    """I numeri della Home e l'elenco degli apiari (sola lettura, `TTL_LETTURE_SECONDI`)."""
    return servizi().panoramica(utente_id)


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
@_interruttore
def apiari(utente_id: int) -> tuple[ApiarioScelta, ...]:
    """Gli apiari tra cui scegliere quello attivo (sola lettura, `TTL_LETTURE_SECONDI`)."""
    return tuple(servizi().elenca_apiari(utente_id))


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
@_interruttore
def apiari_in_anagrafica(utente_id: int) -> tuple[Apiario, ...]:
    """Gli apiari con tutti i campi, per la pagina Alveari (sola lettura, `TTL_LETTURE_SECONDI`)."""
    return tuple(servizi().apiari_in_anagrafica(utente_id))


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
@_interruttore
def alveari_dell_apiario(utente_id: int, apiario_id: int) -> tuple[AlveareInElenco, ...]:
    """Gli alveari attivi di un apiario, con l'ultima ispezione (sola lettura, in cache)."""
    return tuple(servizi().alveari_dell_apiario(utente_id, apiario_id))


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
@_interruttore
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
@_interruttore
def riepiloghi_ispezione(utente_id: int, ispezione_id: int) -> tuple[RiepilogoSalvato, ...]:
    """I riepiloghi AI già salvati di un'ispezione, dal più recente (sola lettura, in cache)."""
    return tuple(servizi().riepiloghi_ispezione(utente_id, ispezione_id))


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
@_interruttore
def stati_prevedibili() -> tuple[StatoPrevedibile, ...]:
    """Gli stati per cui il modello può prevedere, con i loro anni (sola lettura, in cache)."""
    return tuple(servizi().stati_prevedibili())


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
@_interruttore
def intervalli_parametri() -> tuple[IntervalloParametro, ...]:
    """Gli intervalli ammessi per i parametri scritti a mano (sola lettura, in cache)."""
    return servizi().intervalli_parametri()


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
@_interruttore
def storico_previsioni(utente_id: int, alveare_id: int | None = None) -> tuple[dict, ...]:
    """Le ultime previsioni salvate, di tutti gli alveari o di uno (sola lettura, in cache)."""
    return tuple(servizi().storico_previsioni(utente_id, alveare_id=alveare_id))


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
@_interruttore
def dashboard_apiario(utente_id: int, apiario_id: int) -> DatiDashboard:
    """KPI e tabelle aggregate della Dashboard di un apiario (sola lettura, in cache)."""
    return servizi().dashboard_apiario(utente_id, apiario_id)


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
def metriche_modello() -> MetricheModello:
    """Le metriche del modello lette dai suoi metadati (sola lettura, in cache)."""
    return servizi().metriche_modello()


@st.cache_data(ttl=TTL_LETTURE_SECONDI, show_spinner=False)
@_interruttore
def confronto_previsto_reale(codice_stato: str) -> pd.DataFrame:
    """Stima del modello e resa vera degli ultimi anni di uno stato (sola lettura, in cache)."""
    return servizi().confronto_previsto_reale(codice_stato)


def svuota_letture() -> None:
    """Dimentica tutte le letture in cache: da chiamare subito dopo una scrittura.

    Una scrittura riuscita dice anche che il database risponde: l'interruttore si richiude.
    """
    st.cache_data.clear()
    azzera_interruttore()


# --------------------------------------------------------------------------- #
# Stato della sessione: l'unico punto in cui nasce
# --------------------------------------------------------------------------- #


def inizializza_stato() -> None:
    """Crea le chiavi di `st.session_state` che mancano, senza toccare quelle che ci sono.

    - `utente_id`: l'utente che ha fatto l'accesso, None prima (M6-T11);
    - `apiario_attivo_id`: l'apiario scelto, il contesto di tutte le pagine; `None` finché non si
      sa quali apiari esistono (lo imposta `scegli_apiario_iniziale`);
    - `esito_operazione`: il messaggio dell'ultima scrittura riuscita, finché non si mostra;
    - `accesso`: il nome di chi ha fatto l'accesso, o None (M6-T11);
    - `onboarding`: il passo dei primi passi guidati dopo la registrazione, o None.
    """
    st.session_state.setdefault(CHIAVE_UTENTE, None)  # nessuno, finché non c'è l'accesso
    st.session_state.setdefault(CHIAVE_APIARIO_ATTIVO, None)
    st.session_state.setdefault(CHIAVE_ESITO, None)
    st.session_state.setdefault(CHIAVE_ACCESSO, None)
    st.session_state.setdefault(CHIAVE_ONBOARDING, None)


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
# Accesso e onboarding (M6-T11)
# --------------------------------------------------------------------------- #


def accesso_effettuato() -> bool:
    return st.session_state[CHIAVE_ACCESSO] is not None


def nome_in_accesso() -> str | None:
    return st.session_state[CHIAVE_ACCESSO]


def passo_onboarding() -> int | None:
    return st.session_state[CHIAVE_ONBOARDING]


def entra(utente: UtenteAutenticato, *, nuovo: bool = False) -> None:
    """L'accesso è riuscito: da qui le pagine sono sue. Un utente nuovo parte dall'onboarding.

    Riesegue l'app, così il router (`Home.py`) ricostruisce il menu: va chiamata per ultima.
    """
    st.session_state[CHIAVE_UTENTE] = utente.id
    st.session_state[CHIAVE_ACCESSO] = utente.nome
    st.session_state[CHIAVE_APIARIO_ATTIVO] = None  # quello dell'utente di prima non è suo
    st.session_state[CHIAVE_ONBOARDING] = 1 if nuovo else None
    st.session_state[CHIAVE_ESITO] = None
    logger.info("Accesso nella sessione dell'utente %s", utente.id)
    st.rerun()


def avanza_onboarding() -> None:
    """Il passo dopo dei primi passi; dopo l'ultimo, l'onboarding finisce."""
    passo = (st.session_state[CHIAVE_ONBOARDING] or 0) + 1
    st.session_state[CHIAVE_ONBOARDING] = passo if passo <= PASSI_ONBOARDING else None
    st.rerun()


def termina_onboarding() -> None:
    """Fine dei primi passi (anche saltati): il router mostra l'app."""
    st.session_state[CHIAVE_ONBOARDING] = None
    st.rerun()


def esci() -> None:
    """Callback del bottone «Esci»: la sessione torna a prima dell'accesso.

    È un callback (`on_click`): Streamlit riesegue l'app da sé, e il router mostra Accedi.
    """
    st.session_state[CHIAVE_UTENTE] = None
    st.session_state[CHIAVE_ACCESSO] = None
    st.session_state[CHIAVE_APIARIO_ATTIVO] = None
    st.session_state[CHIAVE_ONBOARDING] = None
    st.session_state[CHIAVE_ESITO] = None


# --------------------------------------------------------------------------- #
# Prima riga di ogni pagina
# --------------------------------------------------------------------------- #


def avvia(titolo: str, icona: str = "🐝", *, pubblica: bool = False) -> Servizi:
    """Prepara la pagina: configurazione, stato, servizi. Va chiamata per prima in ogni pagina.

    Una pagina non `pubblica` senza accesso si ferma qui (M6-T11). Il router (`Home.py`) già
    non la mette nel menu: questo è il secondo lucchetto, se un giorno ci si arrivasse lo stesso
    (la cartella `pages/` è anche registrata in automatico da Streamlit). Pubblici sono solo il
    router, Accedi e Registrati.

    `st.set_page_config` dev'essere il primo comando Streamlit di uno script, quindi sta qui e non
    nella pagina. Se la configurazione non è valida l'errore si mostra e la pagina si ferma: è
    l'unico errore da cui non si può proseguire.
    """
    st.set_page_config(page_title=f"{titolo} · BeeWatch AI", page_icon=icona, layout="wide")
    inizializza_stato()
    if not pubblica and not accesso_effettuato():
        st.info("Per vedere questa pagina accedi a BeeWatch AI.", icon="🔑")
        st.stop()
    try:
        return servizi()
    except BeeWatchError as errore:
        # Import qui e non in cima: `ui` importa `avvio`, e il contrario in cima sarebbe un ciclo.
        from ui import mostra_errore

        st.title("🐝 BeeWatch AI")
        st.write("L'applicazione non può partire.")
        mostra_errore(errore)
        st.stop()
