"""
BeeWatch AI - pagina Dashboard: scheletro (M6-T1) con gli helper condivisi (M6-T2).

La pagina ha già la sidebar comune, l'intestazione, un numero di contesto e i suoi stati di vuoto
e di errore. Il contenuto vero arriva con M6-T7:
gli andamenti nel tempo e il confronto tra previsto e reale.

Il prefisso numerico del nome del file decide l'ordine nel menu.
"""

from __future__ import annotations

import streamlit as st
from avvio import CHIAVE_UTENTE, avvia, panoramica
from ui import (
    AZIONE_NESSUN_APIARIO,
    NESSUN_APIARIO,
    blocco_vuoto,
    intestazione,
    metrica,
    mostra_errore,
    sidebar,
)

from beewatch.exceptions import BeeWatchError

avvia("Dashboard", "📊")
attivo = sidebar()

intestazione(
    "📊 Dashboard",
    "L'andamento della produzione nel tempo e il confronto fra previsto e reale.",
)

try:
    quadro = panoramica(st.session_state[CHIAVE_UTENTE])
except BeeWatchError as errore:
    mostra_errore(errore)
    st.stop()

if attivo is None:
    blocco_vuoto(NESSUN_APIARIO, AZIONE_NESSUN_APIARIO)
colonne = st.columns(4)  # la griglia della Home
with colonne[0]:
    metrica("Produzione stagione", quadro.produzione_stagione_kg, "kg")
with colonne[1]:
    metrica(
        "Da controllare",
        quadro.alveari_da_controllare,
        None,
        aiuto="Attivi e mai ispezionati, o non ispezionati da oltre 30 giorni.",
    )

st.info("Questa pagina è in costruzione: il contenuto arriva con M6-T7.", icon="🚧")
