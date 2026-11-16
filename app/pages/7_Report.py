"""
BeeWatch AI - pagina Report (M6-T12; aspetto del mockup, tavole 35–39).

Come nel mockup:

- in cima «Genera report» e le **tre card dei modelli** (Report mensile, Analisi produzione, Stato
  sanitario), ognuna con «Genera»: aprono la finestra «Genera report» con il modello già scelto
  (per il mensile si scelgono anche mese e anno);
- **Report generati**: l'archivio, con la ricerca, il nome, il tipo, quando è stato creato, i
  formati in cui si scarica e le azioni: aprire il report (sintesi, tabelle e i tre bottoni CSV,
  Excel, PDF) ed eliminarlo, con una conferma.

Ogni report generato si salva nell'archivio (`crea_report`), com'è in quel momento: riaprirlo dopo
dà gli stessi numeri. Del mockup mancano il periodo libero (dal… al…), la scelta degli alveari e
delle sezioni: i tre modelli hanno contenuti fissi. Il formato non si sceglie prima: ogni report
si scarica in tutti e tre. La pagina non scrive file né query: i servizi compongono ed esportano.
"""

from __future__ import annotations

from datetime import date

import streamlit as st
from avvio import (
    CHIAVE_UTENTE,
    apiari,
    apri_finestra,
    archivio_report,
    avvia,
    chiudi_finestra,
    finestra_aperta,
    prendi_esito,
    report_salvato,
    scrittura_riuscita,
)
from schede import icona_tonda_avviso, intestazione_tabella, scheda_modello_report, testata
from ui import (
    AZIONE_NESSUN_APIARIO,
    NESSUN_APIARIO,
    blocco_vuoto,
    formatta_numero,
    mostra_errore,
    sidebar,
)

from beewatch.exceptions import BeeWatchError
from beewatch.services import FORMATI, MESI, MODELLI

OGGI = date.today()
DESCRIZIONI = {
    "mensile": "Le ispezioni e i raccolti di un mese, con una sintesi.",
    "produzione": "Tutti i raccolti: per anno e tipo di miele, e per alveare.",
    "sanitario": "Ogni alveare: stato, ultima ispezione, rischio e chi va rivisto.",
}
ICONE = {"mensile": "ispezioni", "produzione": "forza", "sanitario": "salute"}
TIPI = {"mensile": "Mensile", "produzione": "Analisi", "sanitario": "Sanitario"}
COLONNE = [3.2, 1.3, 1.8, 2.2, 1.1]
INTESTAZIONI = ("Nome report", "Tipo", "Creato il", "Formato", "Azioni")
RIGHE_PER_PAGINA = 10


def cella(valore) -> str:
    """Un valore del report come lo legge un italiano: i testi restano, i numeri si formattano."""
    return valore if isinstance(valore, str) else formatta_numero(valore)


def chiudi_e_ricarica() -> None:
    """Chiude la finestra e riesegue tutta la pagina (un clic in una finestra riesegue solo lei)."""
    chiudi_finestra()
    st.rerun()


def mostra_report(report) -> None:
    st.markdown(f"#### {report.titolo}")
    st.caption(f"{report.sottotitolo} Salvato il {report.creato_il}.")
    st.dataframe(
        [{"Voce": etichetta, "Valore": cella(valore)} for etichetta, valore in report.sintesi],
        hide_index=True,
        width="stretch",
    )
    for sezione in report.sezioni:
        st.markdown(f"**{sezione.titolo}**")
        if sezione.righe:
            st.dataframe(
                [
                    dict(zip(sezione.colonne, map(cella, riga), strict=True))
                    for riga in sezione.righe
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption("Nessun dato in questa sezione.")
        if sezione.nota:
            st.caption(sezione.nota)


# --------------------------------------------------------------------------- #
# Finestre
# --------------------------------------------------------------------------- #


@st.dialog("Genera report", width="large", on_dismiss=chiudi_finestra)
def finestra_genera(modello_proposto: str | None) -> None:
    st.caption(f"Il report riguarda l'apiario attivo, {attivo.nome}, e si salva nell'archivio.")
    modelli = list(MODELLI)
    with st.form("nuovo_report", border=False):
        modello = st.selectbox(
            "Tipo di report", options=modelli, format_func=MODELLI.__getitem__,
            index=modelli.index(modello_proposto) if modello_proposto in modelli else 0,
            key="report_modello",
        )  # fmt: skip
        colonne = st.columns(2)
        mese = colonne[0].selectbox(
            "Mese (report mensile)", options=list(range(1, 13)), index=OGGI.month - 1,
            format_func=lambda m: MESI[m - 1].capitalize(), key="report_mese",
        )  # fmt: skip
        anno = colonne[1].selectbox(
            "Anno (report mensile)", options=list(range(OGGI.year, 1999, -1)), key="report_anno"
        )
        st.caption("Si scarica in PDF, Excel e CSV, dall'archivio, quando vuoi.")
        _, annulla, genera = st.columns([2, 1, 1.4])
        annullato = annulla.form_submit_button("Annulla", key="report_annulla", width="stretch")
        premuto = genera.form_submit_button(
            "Genera report", type="primary", key="report_genera",
            icon=":material/play_arrow:", width="stretch",
        )  # fmt: skip
    if annullato:
        chiudi_e_ricarica()
    if premuto:
        try:
            with st.spinner("Preparo il report..."):
                nuovo = servizi.crea_report(utente, attivo.id, modello, anno=anno, mese=mese)
        except BeeWatchError as errore:
            mostra_errore(errore)
        else:
            chiudi_finestra()
            scrittura_riuscita(f"Report «{nuovo.titolo}» salvato nell'archivio.")


@st.dialog("Report", width="large", on_dismiss=chiudi_finestra)
def finestra_report(voce) -> None:
    try:
        report = report_salvato(utente, voce.id)
    except BeeWatchError as errore:
        mostra_errore(errore)
        return
    bottoni = st.columns(len(FORMATI))
    for colonna, (formato, (tipo, nome)) in zip(bottoni, FORMATI.items(), strict=True):
        colonna.download_button(
            f"Scarica in {nome}", data=servizi.esporta_report(report, formato),
            file_name=report.nome_file(formato), mime=tipo, key=f"scarica_{formato}_{report.id}",
            icon=":material/download:", width="stretch",
        )  # fmt: skip
    mostra_report(report)


@st.dialog("Elimina report", on_dismiss=chiudi_finestra)
def finestra_elimina(voce) -> None:
    with st.container(key="bw_conferma_elimina"):
        icona_tonda_avviso()
        st.markdown(f"**Eliminare «{voce.titolo}»?**")
        st.caption("Il report sparisce dall'archivio; i dati dell'apiario non cambiano.")
        annulla, elimina = st.columns(2)
        if annulla.button("Annulla", key=f"report_{voce.id}_annulla", width="stretch"):
            chiudi_e_ricarica()
        with elimina, st.container(key="bw_bottone_elimina"):
            premuto = st.button("Elimina", key=f"report_{voce.id}_elimina", width="stretch",
                                icon=":material/delete:")  # fmt: skip
    if premuto:
        try:
            servizi.elimina_report(utente, voce.id)
        except BeeWatchError as errore:
            mostra_errore(errore)
        else:
            chiudi_finestra()
            scrittura_riuscita("Report eliminato dall'archivio.")


# --------------------------------------------------------------------------- #
# Pagina
# --------------------------------------------------------------------------- #

servizi = avvia("Report", "📄")
attivo = sidebar()
utente = st.session_state[CHIAVE_UTENTE]

azioni = testata("Report", "Genera, consulta ed esporta i report del tuo apiario.")
with azioni:
    _, genera = st.columns([1.3, 1])
    genera.button(
        "Genera report", type="primary", key="apri_genera_report", icon=":material/add:",
        width="stretch", on_click=apri_finestra, args=("genera_report", None),
        disabled=attivo is None,
    )  # fmt: skip

esito = prendi_esito()
if esito:
    st.success(esito, icon="✅")

try:
    apiari(utente)  # la sidebar non solleva: se il database è giù, lo dice il corpo
    archivio = archivio_report(utente)
except BeeWatchError as errore:
    mostra_errore(errore)
    st.stop()

# --------------------------------------------------------------------------- #
# Le tre card dei modelli
# --------------------------------------------------------------------------- #

if attivo is None:
    blocco_vuoto(NESSUN_APIARIO, AZIONE_NESSUN_APIARIO)
else:
    for colonna, modello in zip(st.columns(len(MODELLI)), MODELLI, strict=True):
        with colonna, st.container(key=f"bw_card_modello_{modello}"):
            scheda_modello_report(ICONE[modello], MODELLI[modello], DESCRIZIONI[modello])
            st.button(
                "Genera", key=f"genera_{modello}", icon=":material/play_arrow:",
                on_click=apri_finestra, args=("genera_report", modello),
            )  # fmt: skip

# --------------------------------------------------------------------------- #
# Report generati
# --------------------------------------------------------------------------- #

with st.container(key="bw_card_archivio"):
    titolo, cerca = st.columns([2, 1], vertical_alignment="center")
    titolo.subheader("Report generati")
    testo = cerca.text_input(
        "Cerca", key="report_cerca", placeholder="Cerca report...",
        label_visibility="collapsed", icon=":material/search:",
    )  # fmt: skip
    if not archivio:
        blocco_vuoto(
            "Nessun report nell'archivio.",
            "Generane uno qui sopra: resta qui, da riaprire e scaricare quando vuoi.",
        )
    else:
        cercato = testo.strip().lower()
        scelti = [v for v in archivio if not cercato or cercato in v.titolo.lower()]
        pagine = max(1, -(-len(scelti) // RIGHE_PER_PAGINA))
        pagina = min(st.session_state.get("report_pagina") or 1, pagine)
        mostrati = scelti[(pagina - 1) * RIGHE_PER_PAGINA : pagina * RIGHE_PER_PAGINA]
        intestazione_tabella(INTESTAZIONI, COLONNE)
        if not mostrati:
            st.caption("Nessun report corrisponde alla ricerca.")
        for voce in mostrati:
            with st.container(key=f"bw_riga_{voce.id}"):
                celle = st.columns(COLONNE, vertical_alignment="center")
                celle[0].markdown(f"**{voce.titolo}**")
                celle[1].write(TIPI.get(voce.modello, voce.modello))
                celle[2].write(voce.creato_il)
                celle[3].write(" · ".join(nome for _, nome in FORMATI.values()))
                with celle[4]:
                    apri, elimina = st.columns(2)
                    apri.button("", key=f"apri_report_{voce.id}", icon=":material/visibility:",
                                type="tertiary", help="Apri e scarica", on_click=apri_finestra,
                                args=("report", voce.id))  # fmt: skip
                    with elimina, st.container(key=f"bw_cestino_{voce.id}"):
                        st.button("", key=f"elimina_report_{voce.id}", icon=":material/delete:",
                                  type="tertiary", help="Elimina", on_click=apri_finestra,
                                  args=("elimina_report", voce.id))  # fmt: skip
        piede, numeri = st.columns([2, 1], vertical_alignment="center")
        piede.caption(f"Mostrando {len(mostrati)} di {len(scelti)} report")
        if pagine > 1:
            with numeri, st.container(key="bw_pagine"):
                st.segmented_control("Pagina", list(range(1, pagine + 1)), default=pagina,
                                     key="report_pagina",
                                     label_visibility="collapsed")  # fmt: skip

st.caption(
    "Un report è una fotografia: si salva com'era quando l'hai generato, anche se poi arrivano "
    "ispezioni nuove. Il CSV usa il punto e virgola e la virgola decimale, come lo apre Excel in "
    "italiano. I report riassumono i dati registrati: non sono una diagnosi."
)

per_id = {v.id: v for v in archivio}
if (proposto := finestra_aperta("genera_report")) is not False and attivo is not None:
    finestra_genera(None if proposto is True else proposto)
elif (scelto := finestra_aperta("report")) in per_id:
    finestra_report(per_id[scelto])
elif (scelto := finestra_aperta("elimina_report")) in per_id:
    finestra_elimina(per_id[scelto])
