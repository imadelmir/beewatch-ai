"""
BeeWatch AI - pagina Trasparenza: scheletro (M6-T1) con gli helper condivisi (M6-T2).

La pagina ha già la sidebar comune, l'intestazione, un numero di contesto e i suoi stati di vuoto
e di errore. Il contenuto vero arriva con M6-T8:
come funzionano il modello e l'assistente, e i loro limiti.

Il prefisso numerico del nome del file decide l'ordine nel menu.
"""

from __future__ import annotations

import streamlit as st
from avvio import avvia, modello
from ui import intestazione, metrica, mostra_errore, sidebar

from beewatch.exceptions import BeeWatchError

avvia("Trasparenza", "🔍")
sidebar()

intestazione(
    "🔍 Trasparenza",
    "Come lavorano il modello di previsione e l'assistente AI, e dove possono sbagliare.",
)

try:
    stato = modello()
except BeeWatchError as errore:
    mostra_errore(errore)
else:
    colonne = st.columns(4)  # la griglia della Home
    with colonne[0]:
        metrica(
            "Errore medio del modello",
            stato.mae_kg,
            "kg",
            aiuto="Scarto medio delle stime sul 2010–2012, anni mai visti in addestramento.",
        )
    with colonne[1]:
        metrica("Righe di addestramento", stato.righe_addestramento, None)

st.info("Questa pagina è in costruzione: il contenuto arriva con M6-T8.", icon="🚧")
