"""
BeeWatch AI - pagina Assistente AI: scheletro (M6-T1) con gli helper condivisi (M6-T2).

La pagina ha già la sidebar comune, l'intestazione, un numero di contesto e i suoi stati di vuoto
e di errore. Il contenuto vero arriva con M6-T6:
il riepilogo AI delle note di un'ispezione.

Il prefisso numerico del nome del file decide l'ordine nel menu.
"""

from __future__ import annotations

import streamlit as st
from avvio import CHIAVE_UTENTE, avvia, panoramica
from ui import (
    AZIONE_NESSUN_APIARIO,
    NESSUN_APIARIO,
    banner_ai,
    blocco_vuoto,
    intestazione,
    metrica,
    mostra_errore,
    sidebar,
)

from beewatch.exceptions import BeeWatchError

avvia("Assistente AI", "🤖")
attivo = sidebar()

intestazione(
    "🤖 Assistente AI",
    "Un riepilogo delle note di campo di un'ispezione, scritto da un modello di linguaggio.",
)
banner_ai()

try:
    quadro = panoramica(st.session_state[CHIAVE_UTENTE])
except BeeWatchError as errore:
    mostra_errore(errore)
    st.stop()

if attivo is None:
    blocco_vuoto(NESSUN_APIARIO, AZIONE_NESSUN_APIARIO)
with st.columns(4)[0]:  # la griglia della Home: card della stessa larghezza
    metrica(
        "Ispezioni da riassumere (30 giorni)",
        quadro.ispezioni_30_giorni,
        None,
        aiuto="Le ispezioni recenti di cui l'assistente può riassumere le note.",
    )

st.info("Questa pagina è in costruzione: il contenuto arriva con M6-T6.", icon="🚧")
