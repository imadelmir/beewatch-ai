"""Le card del mockup ad alta fedeltà, condivise dalle pagine (testata, KPI, elenchi, ciambella).

Accanto a `ui.py`, che ha il catalogo del §8 della specifica: qui ci sono i pezzi che il mockup
ripete in più schermate. Come in `ui.py`, l'HTML usa solo testi fissi o passati da
`html.escape`, e i colori vengono dal tema attivo (`tema.PALETTE`).
"""

from __future__ import annotations

import base64
import html
import io
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import tema
from streamlit.delta_generator import DeltaGenerator
from ui import etichetta_rischio, formatta_numero, stile_figura, stile_stato

from beewatch.models import LivelloRischio, StatoAlveare
from beewatch.services import MESI

# --------------------------------------------------------------------------- #
# Testata della pagina
# --------------------------------------------------------------------------- #


def testata(titolo: str, descrizione: str) -> DeltaGenerator:
    """Titolo e sottotitolo a sinistra, come nel mockup; restituisce la colonna di destra, dove la
    pagina mette le sue azioni (la data, «Nuova ispezione»…)."""
    sinistra, destra = st.columns([3, 2], vertical_alignment="center")
    with sinistra, st.container(key="bw_testata"):
        st.title(titolo)
        st.caption(descrizione)
    return destra


def data_estesa(giorno: date) -> str:
    """«14 novembre 2026»."""
    return f"{giorno.day} {MESI[giorno.month - 1]} {giorno.year}"


def pillola_data(giorno: date) -> None:
    """La data di oggi nel riquadro con il calendario, in cima alla Dashboard."""
    icona = immagine_icona("calendario", 18)
    st.html(f'<div class="bw-pillola-data"><span>{data_estesa(giorno)}</span>{icona}</div>')


def immagine_icona(nome: str, misura: int = 20, colore: str | None = None) -> str:
    """Un'icona del mockup come `<img>` (Streamlit toglie gli `<svg>` scritti nell'HTML)."""
    tinta = colore or tema.PALETTE[tema.tema_attivo()]["accento"]
    svg = tema.icona_svg(nome, tinta, misura).replace("'", '"')
    dati = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f'<img src="data:image/svg+xml;base64,{dati}" width="{misura}" height="{misura}" alt="">'


# --------------------------------------------------------------------------- #
# Card dei numeri (KPI)
# --------------------------------------------------------------------------- #


def scheda_kpi(
    icona: str,
    etichetta: str,
    valore: Any,
    unita: str | None,
    *,
    nota: str | None = None,
    variazione: str | None = None,
    aiuto: str | None = None,
    evidenzia: bool = False,
    tono: str | None = None,
) -> None:
    """Una card del mockup: etichetta, icona in alto a destra, numero grande, una riga sotto.

    È un `st.metric` vero (si legge anche senza lo stile): `variazione` è la parte verde
    («+2»), `nota` il resto («questo mese»). Con `evidenzia` il valore è nel giallo del tema
    (lo «Stato generale» del mockup); con `tono` («attenzione», «critico», «successo») nel
    colore di quel significato, come «Scarse» in rosso nel dettaglio di un alveare.
    """
    testo = valore if isinstance(valore, str) else formatta_numero(valore)
    if unita and testo != "—":
        testo = f"{testo} {unita}"
    # il valore nel giallo del tema (evidenzia) o nel colore di un tono: attenzione, critico
    suffisso = "_evidenza" if evidenzia else f"_tono_{tono}" if tono else ""
    chiave = f"bw_kpi_{icona}{suffisso}"
    with st.container(key=chiave):
        st.metric(
            etichetta,
            testo,
            delta=variazione or nota,
            delta_color="normal" if variazione else "off",
            delta_arrow="off",
            delta_description=nota if variazione else None,
            help=aiuto,
            border=True,
        )


# --------------------------------------------------------------------------- #
# Pastiglie di stato (mockup: Sano, Attenzione, Critico)
# --------------------------------------------------------------------------- #

# Il gruppo di colore di ogni stato: il testo resta quello preciso dello stato («Debole»).
GRUPPI_STATO = {
    StatoAlveare.IN_SALUTE: "sano",
    StatoAlveare.IN_OSSERVAZIONE: "attenzione",
    StatoAlveare.DEBOLE: "attenzione",
    StatoAlveare.SCIAMATO: "attenzione",
    StatoAlveare.MORTO: "critico",
}
GRUPPI_RISCHIO = {
    LivelloRischio.NESSUNO: "sano",
    LivelloRischio.BASSO: "sano",
    LivelloRischio.MEDIO: "attenzione",
    LivelloRischio.ALTO: "critico",
}


def pastiglia_stato(stato: StatoAlveare) -> str:
    """La pastiglia dello stato di un alveare, come HTML (per le righe delle tabelle)."""
    return _pastiglia(stile_stato(stato)[0], GRUPPI_STATO.get(stato, "neutro"))


def pastiglia_rischio(livello: LivelloRischio) -> str:
    """La pastiglia del rischio di un'ispezione («Rischio medio»), come HTML."""
    return _pastiglia(etichetta_rischio(livello), GRUPPI_RISCHIO.get(livello, "neutro"))


def _pastiglia(testo: str, gruppo: str) -> str:
    return f'<span class="bw-badge {gruppo}">{html.escape(testo)}</span>'


# --------------------------------------------------------------------------- #
# Elenchi dentro le card (notifiche, scadenze)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Voce:
    """Una riga di un elenco: icona (o nessuna), testo, e a destra la data o il tempo."""

    testo: str
    destra: str = ""
    icona: str | None = None
    tono: str = "accento"  # accento, attenzione, critico, successo


def elenco(voci: Sequence[Voce], vuoto: str) -> None:
    """Le righe di «Ultime notifiche» e «Prossime scadenze»; senza voci, una frase."""
    if not voci:
        st.caption(vuoto)
        return
    colori = tema.PALETTE[tema.tema_attivo()]
    righe = []
    for voce in voci:
        icona = immagine_icona(voce.icona, 20, colori[voce.tono]) if voce.icona else ""
        righe.append(
            f'<li>{icona}<span class="bw-voce-testo">{html.escape(voce.testo)}</span>'
            f'<span class="bw-voce-destra">{html.escape(voce.destra)}</span></li>'
        )
    classe = "bw-elenco con-icone" if any(v.icona for v in voci) else "bw-elenco"
    st.html(f'<ul class="{classe}">{"".join(righe)}</ul>')


def titolo_card(titolo: str, dettaglio: str | None = None) -> None:
    """Il titolo in grassetto di una card, con la nota grigia accanto («(per anno)»)."""
    extra = (
        f' <span class="bw-titolo-card-nota">{html.escape(dettaglio)}</span>' if dettaglio else ""
    )
    st.html(f'<div class="bw-titolo-card">{html.escape(titolo)}{extra}</div>')


# --------------------------------------------------------------------------- #
# Grafici del mockup
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Fetta:
    etichetta: str
    numero: int
    tono: str  # accento, attenzione, testo2…


def figura_ciambella(fette: Iterable[Fetta], totale: int) -> go.Figure:
    """La ciambella «Stato alveari»: il totale al centro, le fette nei colori del tema."""
    fette = [f for f in fette if f.numero > 0]
    colori = tema.PALETTE[tema.tema_attivo()]
    figura = go.Figure(
        go.Pie(
            labels=[f.etichetta for f in fette],
            values=[f.numero for f in fette],
            hole=0.68,
            sort=False,
            direction="clockwise",
            marker={"colors": [colori[f.tono] for f in fette]},
            textinfo="none",
            hovertemplate="%{label}: %{value}<extra></extra>",
        )
    )
    figura.update_layout(
        showlegend=False,
        height=230,
        annotations=[
            {
                "text": f"<b>{totale}</b>",
                "x": 0.5,
                "y": 0.56,
                "showarrow": False,
                "font": {"size": 36, "color": colori["testo"]},
            },
            {
                "text": "Totale",
                "x": 0.5,
                "y": 0.38,
                "showarrow": False,
                "font": {"size": 13, "color": colori["testo2"]},
            },
        ],  # fmt: skip
        **{**stile_figura(), "margin": {"l": 0, "r": 0, "t": 0, "b": 0}},
    )
    return figura


def _percento(parte: int, totale: int) -> str:
    return f"{round(100 * parte / totale) if totale else 0}%"


def legenda_ciambella(fette: Sequence[Fetta], totale: int) -> None:
    """La legenda a destra della ciambella: pallino, nome, numero e percentuale."""
    colori = tema.PALETTE[tema.tema_attivo()]
    righe = "".join(
        f'<li><span class="bw-pallino" style="background:{colori[f.tono]}"></span>'
        f"<span>{html.escape(f.etichetta)}</span>"
        f'<span class="bw-voce-destra">{f.numero} ({_percento(f.numero, totale)})</span></li>'
        for f in fette
    )
    st.html(f'<ul class="bw-legenda">{righe}</ul>')


def figura_area(x: Sequence[Any], y: Sequence[float], etichetta_y: str) -> go.Figure:
    """La linea gialla con l'area sfumata sotto (mockup, «Produzione»)."""
    colori = tema.PALETTE[tema.tema_attivo()]
    figura = go.Figure(
        go.Scatter(
            x=list(x),
            y=list(y),
            mode="lines+markers",
            line={"color": colori["accento"], "width": 3, "shape": "spline", "smoothing": 0.6},
            marker={"color": colori["accento"], "size": 8},
            fill="tozeroy",
            fillgradient={
                "type": "vertical",
                "colorscale": [[0, "rgba(245, 179, 1, 0)"], [1, "rgba(245, 179, 1, 0.35)"]],
            },
            hovertemplate="%{x}: %{y:.1f} kg<extra></extra>",
        )
    )
    figura.update_layout(
        height=260,
        xaxis={"type": "category", "showgrid": False, "title": ""},
        yaxis={"title": etichetta_y, "gridcolor": colori["bordo"], "rangemode": "tozero"},
        **{**stile_figura(), "margin": {"l": 10, "r": 10, "t": 10, "b": 10}},
    )
    return figura


def disegna(figura: go.Figure, chiave: str) -> None:
    """Una figura a tutta larghezza della card, senza la barra degli strumenti di Plotly."""
    st.plotly_chart(
        figura, width="stretch", theme=None, key=chiave, config={"displayModeBar": False}
    )


# --------------------------------------------------------------------------- #
# Esporta (il bottone in cima alle tabelle)
# --------------------------------------------------------------------------- #


def csv_per_excel(tabella: pd.DataFrame) -> bytes:
    """Una tabella in CSV come lo apre Excel in italiano: «;», virgola decimale, BOM UTF-8."""
    testo = io.StringIO()
    tabella.to_csv(testo, sep=";", decimal=",", index=False)
    return ("\ufeff" + testo.getvalue()).encode("utf-8")


# --------------------------------------------------------------------------- #
# Pezzi delle tabelle e dei dettagli (Alveari, Ispezioni)
# --------------------------------------------------------------------------- #


def intestazione_tabella(colonne: Sequence[str], larghezze: Sequence[float]) -> None:
    """La riga grigia dei nomi delle colonne, sopra le righe della tabella.

    `larghezze` sono le stesse proporzioni di `st.columns` delle righe: così i nomi stanno
    sopra i valori.
    """
    celle = "".join(f"<span>{html.escape(c)}</span>" for c in colonne)
    griglia = " ".join(f"{float(x):g}fr" for x in larghezze)
    st.html(f'<div class="bw-tabella-testa" style="grid-template-columns:{griglia}">{celle}</div>')


def mostra_pastiglia_stato(stato: StatoAlveare) -> None:
    st.html(pastiglia_stato(stato))


def mostra_pastiglia_rischio(livello: LivelloRischio) -> None:
    st.html(pastiglia_rischio(livello))


def icona_tonda_avviso() -> None:
    """Il «!» rosso nel cerchio, in cima a una finestra che chiede di confermare."""
    st.html('<div class="bw-avviso-tondo">!</div>')


def icona_vuoto() -> None:
    """L'esagono giallo dello stato vuoto (mockup «Nessun alveare registrato»)."""
    st.html('<div class="bw-vuoto-icona">⬡</div>')


def barra_rischio(nome: str, livello: int, etichetta: str) -> None:
    """Una barra di «Salute e rischi»: verde sotto 50, arancio fino a 75, rossa oltre.

    `livello` va da 0 a 100; `etichetta` dice il valore a parole (il colore non basta).
    """
    tono = "critico" if livello >= 75 else "attenzione" if livello >= 50 else "successo"
    larghezza = max(0, min(100, int(livello)))
    st.html(
        f'<div class="bw-barra"><div class="bw-barra-testa"><span>{html.escape(nome)}</span>'
        f"<span>{html.escape(etichetta)}</span></div>"
        f'<div class="bw-barra-fondo"><span class="{tono}" style="width:{larghezza}%"></span>'
        "</div></div>"
    )


# --------------------------------------------------------------------------- #
# La «chat» dell'AI Assistant
# --------------------------------------------------------------------------- #


def intestazione_chat(nome: str, descrizione: str, in_locale: bool | None) -> None:
    """La riga in cima alla chat: l'icona, il nome e la pastiglia di dove gira l'assistente.

    `descrizione` è «modello via provider (chiave: …)» (`InfoAssistente`): nella pastiglia va il
    provider, e accanto il modello. Senza provider configurato la pastiglia lo dice.
    """
    modello, _, resto = descrizione.partition(" via ")
    provider = resto.split(" ")[0].capitalize() if resto else "Non configurato"
    dove = {True: "sul PC", False: "esterno", None: ""}[in_locale]
    nota = f" · {html.escape(modello)} {dove}".rstrip() if resto else ""
    st.html(
        f'<div class="bw-chat-testa">{immagine_icona("assistente", 22)}'
        f'<span class="bw-chat-nome">{html.escape(nome)}</span>'
        f'<span class="bw-badge sano">{html.escape(provider)}</span>'
        f'<span class="bw-chat-nota">{nota}</span></div>'
    )
