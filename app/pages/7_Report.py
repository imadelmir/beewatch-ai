"""
BeeWatch AI - pagina Report: tre modelli, l'archivio, CSV/XLSX/PDF (M6-T12).

L'anatomia del §6 della specifica:

- **controlli**: il modulo «Nuovo report» (modello, e mese e anno per il report mensile);
- **contenuto**: l'archivio dei report generati e quello scelto, con sintesi, tabelle e i tre
  bottoni per scaricarlo (`st.download_button`); eliminare chiede una conferma;
- **note** in fondo.

Ogni report generato si salva nell'archivio (`crea_report`), com'è in quel momento: riaprirlo dopo
dà gli stessi numeri. La pagina non scrive file né query: i servizi compongono il report con pandas
e lo esportano (`beewatch/report.py`).
"""

from __future__ import annotations

from datetime import date

import streamlit as st
from avvio import (
    CHIAVE_UTENTE,
    apiari,
    archivio_report,
    avvia,
    prendi_esito,
    report_salvato,
    scrittura_riuscita,
)
from ui import (
    AZIONE_NESSUN_APIARIO,
    NESSUN_APIARIO,
    blocco_vuoto,
    formatta_numero,
    intestazione,
    metrica,
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


def cella(valore) -> str:
    """Un valore del report come lo legge un italiano: i testi restano, i numeri si formattano."""
    return valore if isinstance(valore, str) else formatta_numero(valore)


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
# Pagina
# --------------------------------------------------------------------------- #

servizi = avvia("Report", "📄")
attivo = sidebar()
utente = st.session_state[CHIAVE_UTENTE]

intestazione(
    "📄 Report",
    "Tre report sull'apiario attivo, da tenere nell'archivio e scaricare in CSV, Excel o PDF.",
)

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
# Controlli: un report nuovo
# --------------------------------------------------------------------------- #

st.subheader("Nuovo report")
if attivo is None:
    blocco_vuoto(NESSUN_APIARIO, AZIONE_NESSUN_APIARIO)
else:
    with st.form("nuovo_report"):
        modello = st.radio(
            "Modello",
            options=list(MODELLI),
            format_func=MODELLI.__getitem__,
            captions=[DESCRIZIONI[m] for m in MODELLI],
            key="report_modello",
        )
        colonne = st.columns(2)
        mese = colonne[0].selectbox(
            "Mese (report mensile)",
            options=list(range(1, 13)),
            index=OGGI.month - 1,
            format_func=lambda m: MESI[m - 1].capitalize(),
            key="report_mese",
        )
        anno = colonne[1].selectbox(
            "Anno (report mensile)",
            options=list(range(OGGI.year, 1999, -1)),
            key="report_anno",
        )
        premuto = st.form_submit_button(
            f"Genera il report su {attivo.nome}", type="primary", key="report_genera"
        )
    if premuto:
        try:
            with st.spinner("Preparo il report..."):
                nuovo = servizi.crea_report(utente, attivo.id, modello, anno=anno, mese=mese)
        except BeeWatchError as errore:
            mostra_errore(errore)
        else:
            scrittura_riuscita(f"Report «{nuovo.titolo}» salvato nell'archivio.")

# --------------------------------------------------------------------------- #
# Contenuto: l'archivio e il report scelto
# --------------------------------------------------------------------------- #

st.subheader("Archivio")
with st.columns(4)[0]:
    metrica("Report salvati", len(archivio), None, aiuto="I tuoi report, dal più recente.")

if not archivio:
    blocco_vuoto(
        "Nessun report nell'archivio.",
        "Generane uno qui sopra: resta qui, da riaprire e scaricare quando vuoi.",
    )
else:
    per_id = {v.id: v for v in archivio}
    scelto = st.selectbox(
        "Report da aprire",
        options=list(per_id),
        format_func={v.id: f"{v.creato_il} · {v.titolo}" for v in archivio}.__getitem__,
        # La chiave segue l'archivio: dopo un report nuovo si apre quello (vedi M6-T4).
        key=f"report_scelto_{hash(tuple(per_id)) & 0xFFFFFFFF:x}",
    )
    try:
        report = report_salvato(utente, scelto)
    except BeeWatchError as errore:
        mostra_errore(errore)
    else:
        with st.container(border=True):
            mostra_report(report)
            bottoni = st.columns(len(FORMATI))
            for colonna, (formato, (tipo, nome)) in zip(bottoni, FORMATI.items(), strict=True):
                colonna.download_button(
                    f"Scarica in {nome}",
                    data=servizi.esporta_report(report, formato),
                    file_name=report.nome_file(formato),
                    mime=tipo,
                    key=f"scarica_{formato}_{report.id}",
                    icon="⬇️",
                    width="stretch",
                )

        st.caption("Eliminare toglie il report dall'archivio; i dati dell'apiario non cambiano.")
        confermato = st.checkbox(
            f"Confermo: elimina «{report.titolo}»", key=f"report_{report.id}_conferma"
        )
        if (
            st.button(
                "Elimina il report",
                disabled=not confermato,
                key=f"report_{report.id}_elimina",
            )
            and confermato  # la spunta si ricontrolla: un bottone disabilitato non è una garanzia
        ):
            try:
                servizi.elimina_report(utente, report.id)
            except BeeWatchError as errore:
                mostra_errore(errore)
            else:
                scrittura_riuscita("Report eliminato dall'archivio.")

# --------------------------------------------------------------------------- #
# Note
# --------------------------------------------------------------------------- #

st.caption(
    "Un report è una fotografia: si salva com'era quando l'hai generato, anche se poi arrivano "
    "ispezioni nuove. Il CSV usa il punto e virgola e la virgola decimale, come lo apre Excel in "
    "italiano. I report riassumono i dati registrati: non sono una diagnosi."
)
