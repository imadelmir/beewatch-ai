"""Gli helper visivi condivisi dalle pagine (M6-T2).

Le nove funzioni del catalogo della specifica (§8 di `docs/markdown/M6-interfaccia/ui_spec.md`).
Se un elemento visivo compare in più di una pagina, sta qui e non viene copiato: così le sette
pagine hanno lo stesso aspetto e si rifiniscono in un punto solo.

| Funzione | Cosa fa |
|---|---|
| `intestazione(titolo, descrizione)` | titolo e una riga di contesto, in cima al corpo |
| `sidebar()` | la sidebar del §7; restituisce l'apiario attivo |
| `banner_ai()` | l'avviso permanente di contenuto generato da un'AI (§9) |
| `metrica(etichetta, valore, unita, delta, aiuto)` | `st.metric` con numeri all'italiana e unità |
| `badge_stato(stato)` | pastiglia colorata con icona e testo per `StatoAlveare` |
| `blocco_vuoto(messaggio, azione)` | lo stato «nessun dato», con l'azione suggerita |
| `mostra_errore(eccezione)` | un errore previsto in italiano comprensibile, senza traceback |
| `grafico_serie(df, x, y, titolo, …)` | grafico temporale Plotly con assi, palette e fonte |
| `stima_con_incertezza(valore, minimo, massimo, unita)` | stima sempre con banda e avvertenza |

Regole che valgono per tutte:

- **niente HTML né CSS iniettato**, con un'unica eccezione dichiarata dalla specifica (§11):
  `badge_stato`, perché Streamlit non ha un badge nativo. Un test lo verifica sul codice;
- **il colore non è mai l'unico veicolo**: ogni stato colorato ha anche testo e icona (§3);
- **nessun numero senza contesto**: le metriche hanno l'unità, le stime la loro banda (§2).

Come `avvio.py`, il modulo non tocca database, modello né provider AI: legge i servizi già in
cache attraverso `avvio`.
"""

from __future__ import annotations

import html
import math
from datetime import date
from decimal import Decimal
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import avvio
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from beewatch.exceptions import (
    BeeWatchError,
    ConfigError,
    DatabaseError,
    ETLError,
    LLMError,
    ModelError,
    ValidationError,
)
from beewatch.logging_config import ottieni_logger
from beewatch.models import StatoAlveare
from beewatch.services import ApiarioScelta

logger = ottieni_logger("beewatch.app.ui")

# --------------------------------------------------------------------------- #
# Palette (specifica §3): i colori stanno qui, con un nome, e da nessun'altra parte
# --------------------------------------------------------------------------- #

PRIMARIO = "#C77D02"
TESTO = "#1A1A1A"
TESTO_ATTENUATO = "#6B6B6B"
BORDO = "#E5DED4"
SFONDO_SECONDARIO = "#FAF6F0"

POSITIVO = "#2E7D32"
ATTENZIONE = "#ED9C00"
CRITICO = "#C62828"
INFORMAZIONE = "#1565C0"
NEUTRO = "#6B6B6B"

# Più serie nello stesso grafico: prima l'ambra, poi i colori di base. I semantici restano ai loro
# significati (§3); oltre tre serie i colori si ripetono, ma ogni serie ha anche un simbolo suo.
COLORI_SERIE = (PRIMARIO, TESTO, TESTO_ATTENUATO)

# Lo stile comune dei grafici: sfondo bianco, testo della palette.
_STILE_FIGURA: dict[str, Any] = {
    "template": "plotly_white",
    "font": {"color": TESTO},
    "title_font": {"color": TESTO},
    "margin": {"l": 10, "r": 10, "t": 50, "b": 10},
}

DATO_MANCANTE = "—"

try:
    VERSIONE = version("beewatch")
except PackageNotFoundError:  # pragma: no cover - solo se il pacchetto non è installato
    VERSIONE = "sviluppo"

# --------------------------------------------------------------------------- #
# Testi fissi
# --------------------------------------------------------------------------- #

# Specifica §9, parola per parola: non si accorcia e non si nasconde.
TESTO_BANNER_AI = (
    "Il riepilogo qui sotto è generato da un'intelligenza artificiale. Può contenere errori: "
    "verifica sempre con la tua osservazione diretta. Non sostituisce il parere di un "
    "veterinario o di un tecnico apistico."
)

AVVERTENZA_STIMA = (
    "È una stima statistica costruita sui dati storici USDA (chili di miele per colonia), non "
    "una promessa: la produzione reale dipende da meteo, fioriture e gestione dell'alveare."
)

# Lo stato vuoto più comune, uguale su tutte le pagine (specifica §11).
NESSUN_APIARIO = "Nessun apiario registrato."
AZIONE_NESSUN_APIARIO = "Vai su **Alveari** per aggiungerne uno: da lì comincia tutto."

# --------------------------------------------------------------------------- #
# Stati dell'alveare: colore, icona e testo (il colore non basta mai da solo)
# --------------------------------------------------------------------------- #

# (etichetta, icona, sfondo, colore del testo). Il testo è scelto per il contrasto: bianco sui
# colori scuri, quasi-nero sull'arancio dell'attenzione (il bianco lì non si legge).
STILI_STATO: dict[StatoAlveare, tuple[str, str, str, str]] = {
    StatoAlveare.IN_SALUTE: ("In salute", "✔", POSITIVO, "#FFFFFF"),
    StatoAlveare.IN_OSSERVAZIONE: ("In osservazione", "👁", ATTENZIONE, TESTO),
    StatoAlveare.DEBOLE: ("Debole", "▼", ATTENZIONE, TESTO),
    StatoAlveare.SCIAMATO: ("Sciamato", "↗", ATTENZIONE, TESTO),
    StatoAlveare.MORTO: ("Morto", "✖", CRITICO, "#FFFFFF"),
}
STILE_SCONOSCIUTO = ("Stato sconosciuto", "?", NEUTRO, "#FFFFFF")

# --------------------------------------------------------------------------- #
# Errori: che cosa è andato storto e che cosa può fare l'utente (specifica §11)
# --------------------------------------------------------------------------- #

# Dal più specifico al più generico: vince la prima classe che corrisponde. Il comando preciso
# (quale script lanciare, quale variabile correggere) sta già nel messaggio dell'eccezione, scritto
# per l'utente: il rimedio qui è il passo dopo, e non lo ripete.
SPIEGAZIONI_ERRORE: tuple[tuple[type[BaseException], str, str], ...] = (
    (
        ConfigError,
        "La configurazione non è valida.",
        "Correggi il file `.env` come indicato (il modello è `.env.example`) e riavvia l'app.",
    ),
    (
        DatabaseError,
        "Non riesco a raggiungere il database.",
        "Quando il database risponde di nuovo, ricarica la pagina.",
    ),
    (
        ValidationError,
        "Un dato inserito non è valido.",
        "Correggi il campo indicato e riprova.",
    ),
    (
        ModelError,
        "Il modello di previsione non è disponibile.",
        "Quando il modello è al suo posto, ricarica la pagina: il resto dell'app funziona.",
    ),
    (
        LLMError,
        "L'assistente AI non ha risposto come doveva.",
        "Riprova tra poco: il resto dell'applicazione funziona anche senza l'assistente.",
    ),
    (
        ETLError,
        "I dati storici USDA non sono stati caricati.",
        "Dopo averli caricati, ricarica la pagina.",
    ),
    (
        BeeWatchError,
        "Qualcosa non è andato come previsto.",
        "Riprova; se il problema resta, il dettaglio è nel file di log.",
    ),
)
ERRORE_IMPREVISTO = (
    "Errore imprevisto.",
    "Non è colpa tua: il dettaglio tecnico è nel file di log. Ricarica la pagina e riprova.",
)


# --------------------------------------------------------------------------- #
# Numeri all'italiana
# --------------------------------------------------------------------------- #


def formatta_numero(valore: Any, decimali: int | None = None) -> str:
    """Un numero come lo scrive un italiano: `1 234,5`. Mancante o NaN → «—».

    Gli interi restano senza decimali; gli altri ne hanno uno, salvo `decimali` esplicito.
    """
    if valore is None or isinstance(valore, bool):
        return DATO_MANCANTE
    if isinstance(valore, Decimal):
        valore = float(valore)
    if isinstance(valore, float) and math.isnan(valore):
        return DATO_MANCANTE
    if decimali is None:
        decimali = 0 if isinstance(valore, int) else 1
    testo = f"{valore:,.{decimali}f}"
    return testo.replace(",", " ").replace(".", ",")


def formatta_data(giorno: date | None) -> str:
    """Una data come la scrive un italiano: `30/10/2026`. Mancante → «—»."""
    return DATO_MANCANTE if giorno is None else giorno.strftime("%d/%m/%Y")


def _con_unita(testo: str, unita: str | None) -> str:
    return f"{testo} {unita}" if unita and testo != DATO_MANCANTE else testo


# --------------------------------------------------------------------------- #
# 1. Intestazione
# --------------------------------------------------------------------------- #


def intestazione(titolo: str, descrizione: str) -> None:
    """Il titolo della pagina (l'unico `st.title`) e una riga che spiega a cosa serve."""
    st.title(titolo)
    st.write(descrizione)


# --------------------------------------------------------------------------- #
# 2. Sidebar
# --------------------------------------------------------------------------- #


def sidebar() -> ApiarioScelta | None:
    """Disegna la sidebar del §7 e restituisce l'apiario attivo (None se non ce n'è).

    Dall'alto: identità, selettore dell'apiario attivo, stato del sistema. Il menu delle pagine
    lo genera Streamlit dalla cartella `pages/` e lo mette sempre in cima alla sidebar.

    Non solleva: se il database o il modello non rispondono, lo dice nello stato del sistema e
    lascia alla pagina il compito di mostrare l'errore nel corpo.
    """
    with st.sidebar:
        # `st.header` e non `st.title`: il titolo di livello 1 è uno per pagina (§4).
        st.header("🐝 BeeWatch AI")
        st.caption(f"Versione {VERSIONE}")

        attivo, database_raggiunto = _selettore_apiario()

        st.divider()
        st.caption(f"**Modello:** {_stato_modello()}")
        st.caption(f"**Assistente AI:** {avvio.servizi().descrizione_llm}")
        st.caption(
            "**Database:** connesso" if database_raggiunto else "**Database:** non raggiungibile"
        )
    return attivo


def _selettore_apiario() -> tuple[ApiarioScelta | None, bool]:
    """Il selettore dell'apiario attivo. Restituisce l'apiario e se il database ha risposto."""
    try:
        elenco = avvio.apiari(st.session_state[avvio.CHIAVE_UTENTE])
    except BeeWatchError as errore:
        logger.warning("Sidebar: apiari non leggibili (%s)", errore)
        st.caption("Apiario attivo: non disponibile finché il database non risponde.")
        return None, False

    avvio.scegli_apiario_iniziale(elenco)
    if not elenco:
        st.caption(f"Apiario attivo: nessuno. {NESSUN_APIARIO}")
        return None, True

    nomi = {a.id: a.nome for a in elenco}
    avvio.prepara_selettore_apiario()
    st.selectbox(
        "Apiario attivo",
        options=list(nomi),
        format_func=nomi.__getitem__,
        key=avvio.CHIAVE_SELETTORE_APIARIO,
        on_change=avvio.al_cambio_apiario,
        help="Il contesto di tutte le pagine: cambiandolo, cambia ciò che vedi ovunque.",
    )
    return avvio.apiario_attivo(elenco), True


def _stato_modello() -> str:
    try:
        stato = avvio.modello()
    except BeeWatchError:
        return "non disponibile"
    return f"{stato.versione} ({stato.algoritmo})"


# --------------------------------------------------------------------------- #
# 3. Banner AI
# --------------------------------------------------------------------------- #


def banner_ai() -> None:
    """L'avviso di contenuto generato da un'AI (§9): in cima, in blu, non richiudibile."""
    st.info(TESTO_BANNER_AI, icon="🤖")


# --------------------------------------------------------------------------- #
# 4. Metrica
# --------------------------------------------------------------------------- #


def metrica(
    etichetta: str,
    valore: Any,
    unita: str | None,
    delta: float | int | Decimal | None = None,
    aiuto: str | None = None,
) -> None:
    """`st.metric` uniforme: numero all'italiana, unità accanto, delta con la stessa unità.

    `unita` è obbligatoria anche quando non c'è (`None` per un conteggio): così non si dimentica.
    Un valore mancante si mostra come «—», mai come zero.
    """
    st.metric(
        etichetta,
        _con_unita(formatta_numero(valore), unita),
        delta=_delta(delta, unita),
        help=aiuto,
        border=True,
    )


def _delta(delta: Any, unita: str | None) -> str | None:
    if delta is None:
        return None
    testo = formatta_numero(delta)
    if testo == DATO_MANCANTE:
        return None
    segno = "+" if float(delta) > 0 else ""  # il «-» c'è già; Streamlit colora dal segno
    return _con_unita(segno + testo, unita)


# --------------------------------------------------------------------------- #
# 5. Badge di stato (l'unica eccezione al divieto di HTML)
# --------------------------------------------------------------------------- #


def stile_stato(stato: StatoAlveare | str | None) -> tuple[str, str, str, str]:
    """Etichetta, icona, sfondo e colore del testo di uno stato; i valori ignoti sono neutri."""
    try:
        return STILI_STATO[StatoAlveare(stato)]
    except ValueError:
        return STILE_SCONOSCIUTO


def badge_stato(stato: StatoAlveare | str | None) -> None:
    """Pastiglia colorata con icona e testo. Unico `unsafe_allow_html` dell'app (specifica §11).

    Il testo è fisso (viene da `STILI_STATO`), quindi nell'HTML non entra mai un dato
    dell'utente; l'escape resta comunque, per prudenza.
    """
    etichetta, icona, sfondo, colore = stile_stato(stato)
    stile = f"background:{sfondo};color:{colore};padding:2px 10px;border-radius:999px"
    pastiglia = f'<span style="{stile}">{icona} {html.escape(etichetta)}</span>'
    st.markdown(pastiglia, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# 6. Blocco vuoto
# --------------------------------------------------------------------------- #


def blocco_vuoto(messaggio: str, azione: str | None = None) -> None:
    """Lo stato «nessun dato»: mai una tabella vuota senza spiegazione (specifica §11)."""
    testo = messaggio if azione is None else f"{messaggio}\n\n**Cosa puoi fare:** {azione}"
    st.info(testo, icon="🐝")


# --------------------------------------------------------------------------- #
# 7. Errori
# --------------------------------------------------------------------------- #


def spiega_errore(eccezione: BaseException) -> tuple[str, str]:
    """Il titolo comprensibile e il rimedio per un'eccezione (vince la classe più specifica)."""
    for classe, titolo, rimedio in SPIEGAZIONI_ERRORE:
        if isinstance(eccezione, classe):
            return titolo, rimedio
    return ERRORE_IMPREVISTO


def mostra_errore(eccezione: BaseException) -> None:
    """Un `st.error` con cosa è andato storto e cosa fare. Il dettaglio tecnico va nel log.

    Il messaggio di una `BeeWatchError` è scritto per l'utente (vedi `beewatch.exceptions`) e si
    mostra; quello di un'eccezione imprevista no, perché può contenere dettagli tecnici: si scrive
    nel log con lo stack completo e a schermo resta un testo generico.
    """
    titolo, rimedio = spiega_errore(eccezione)
    if isinstance(eccezione, BeeWatchError):
        logger.warning("%s: %s", type(eccezione).__name__, eccezione)
        dettaglio = str(eccezione).strip()
        campo = getattr(eccezione, "campo", None)
        if campo:
            dettaglio = f"{dettaglio} (campo «{campo}»)"
        testo = f"**{titolo}** {dettaglio}\n\n{rimedio}" if dettaglio else f"**{titolo}** {rimedio}"
    else:
        logger.error("Errore non gestito", exc_info=eccezione)
        testo = f"**{titolo}** {rimedio}"
    st.error(testo, icon="⚠️")


# --------------------------------------------------------------------------- #
# 8. Grafico di una serie temporale
# --------------------------------------------------------------------------- #


def figura_serie(
    df: pd.DataFrame,
    x: str,
    y: str,
    titolo: str,
    *,
    etichetta_x: str,
    etichetta_y: str,
    gruppo: str | None = None,
) -> go.Figure:
    """La figura di `grafico_serie`, senza disegnarla (serve anche ai test)."""
    figura = px.line(
        df.sort_values(x),
        x=x,
        y=y,
        color=gruppo,
        symbol=gruppo,  # il colore non basta: ogni serie ha anche il suo simbolo
        markers=True,
        title=titolo,
        color_discrete_sequence=COLORI_SERIE,
    )
    figura.update_layout(
        xaxis_title=etichetta_x,
        yaxis_title=etichetta_y,
        legend_title_text="",
        **_STILE_FIGURA,
    )
    return figura


def grafico_serie(
    df: pd.DataFrame,
    x: str,
    y: str,
    titolo: str,
    *,
    etichetta_x: str,
    etichetta_y: str,
    fonte: str,
    gruppo: str | None = None,
) -> go.Figure | None:
    """Grafico temporale con lo stile comune: assi con unità, palette, didascalia con la fonte.

    Etichette degli assi e fonte sono obbligatorie (specifica §10): `etichetta_y="Produzione
    (kg)"`, `fonte="Raccolti registrati nel quaderno"`. Senza dati mostra lo stato vuoto e
    restituisce None.
    """
    if df.empty:
        blocco_vuoto("Non ci sono ancora dati da mettere nel grafico.")
        return None
    figura = figura_serie(
        df, x, y, titolo, etichetta_x=etichetta_x, etichetta_y=etichetta_y, gruppo=gruppo
    )
    _disegna(figura)
    st.caption(f"Fonte: {fonte}")
    return figura


# --------------------------------------------------------------------------- #
# 9. Stima con incertezza
# --------------------------------------------------------------------------- #


def controlla_banda(valore: Any, minimo: Any, massimo: Any) -> None:
    """Rifiuta una stima senza banda o con la banda che non la contiene.

    È un errore di programmazione, non dell'utente: `ValueError`, non `ValidationError`.
    """
    if minimo is None or massimo is None:
        raise ValueError("Una stima si mostra solo con la sua banda: minimo e massimo servono.")
    if not float(minimo) <= float(massimo):
        raise ValueError(f"Banda rovesciata: minimo {minimo} oltre il massimo {massimo}.")
    if valore is not None and not float(minimo) <= float(valore) <= float(massimo):
        raise ValueError(f"La stima {valore} è fuori dalla sua banda [{minimo}, {massimo}].")


def figura_stima(valore: Any, minimo: Any, massimo: Any, unita: str, etichetta: str) -> go.Figure:
    """La barra orizzontale con la banda d'errore (specifica §10); senza stima, la sola banda."""
    controlla_banda(valore, minimo, massimo)
    basso, alto = float(minimo), float(massimo)
    if valore is None:
        # Solo la banda: una barra crema bordata d'ambra che va dal minimo al massimo.
        traccia = go.Bar(
            x=[alto - basso],
            y=[etichetta],
            base=[basso],
            orientation="h",
            marker={"color": BORDO, "line": {"color": PRIMARIO, "width": 2}},
            hovertemplate=f"da {basso:g} a {alto:g} {unita}<extra></extra>",
        )
    else:
        centro = float(valore)
        traccia = go.Bar(
            x=[centro],
            y=[etichetta],
            orientation="h",
            marker={"color": PRIMARIO},
            error_x={
                "type": "data",
                "symmetric": False,
                "array": [alto - centro],
                "arrayminus": [centro - basso],
                "color": TESTO,
                "thickness": 2,
                "width": 12,
            },
            hovertemplate=f"stima {centro:g} {unita} (da {basso:g} a {alto:g})<extra></extra>",
        )
    figura = go.Figure(traccia)
    figura.update_layout(
        xaxis_title=f"Produzione ({unita})",
        xaxis_rangemode="tozero",
        height=180,
        showlegend=False,
        **_STILE_FIGURA,
    )
    return figura


def stima_con_incertezza(
    valore: Any,
    minimo: Any,
    massimo: Any,
    unita: str,
    *,
    etichetta: str = "Produzione stimata",
    livello: float | None = None,
) -> go.Figure:
    """Una stima con la sua banda e l'avvertenza: mai un numero secco (specifica §2 e §10).

    Senza `minimo` e `massimo` (o con una banda che non contiene la stima) solleva `ValueError`
    prima di disegnare qualsiasi cosa. `valore=None` mostra la sola banda: è il caso in cui il
    servizio dice di non mostrare il valore centrale (`RisultatoPrevisione.mostra_stima` falso).
    `livello` (0–1) è la quota di errori osservati che stanno dentro la banda.
    """
    controlla_banda(valore, minimo, massimo)
    banda = f"da {formatta_numero(minimo)} a {formatta_numero(massimo)} {unita}"
    quota = f" (intervallo al {round(livello * 100)}%)" if livello is not None else ""
    if valore is None:
        mostrato, aiuto = banda, "Il valore centrale non si mostra: la banda è troppo larga."
    else:
        mostrato, aiuto = _con_unita(formatta_numero(valore), unita), f"Banda: {banda}{quota}."
    st.metric(etichetta, mostrato, help=aiuto, border=True)
    st.caption(f"Banda di incertezza: {banda}{quota}.")
    figura = figura_stima(valore, minimo, massimo, unita, etichetta)
    _disegna(figura)
    st.caption(AVVERTENZA_STIMA)
    return figura


def _disegna(figura: go.Figure) -> None:
    """Disegna una figura a tutta larghezza (§10) con i colori della figura, non del tema.

    `width="stretch"` è l'equivalente, in Streamlit 1.60, di `use_container_width=True` citato
    dalla specifica (in questa versione deprecato). `theme=None` lascia i colori della palette.
    """
    st.plotly_chart(figura, width="stretch", theme=None)
