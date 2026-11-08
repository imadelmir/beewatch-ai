"""
BeeWatch AI - pagina Previsione: scheletro (M6-T1) con gli helper condivisi (M6-T2).

La pagina ha già la sidebar comune, l'intestazione, un numero di contesto e i suoi stati di vuoto
e di errore. Il contenuto vero arriva con M6-T5:
la previsione della produzione con la sua banda d'incertezza.

Il prefisso numerico del nome del file decide l'ordine nel menu.
"""

from __future__ import annotations

import streamlit as st
from avvio import avvia, modello
from ui import intestazione, metrica, mostra_errore, sidebar

from beewatch.exceptions import BeeWatchError

avvia("Previsione", "📈")
sidebar()

intestazione(
    "📈 Previsione",
    "Una stima della produzione di miele per colonia, sempre con il suo margine d'errore.",
)

try:
    stato = modello()
except BeeWatchError as errore:
    mostra_errore(errore)
else:
    with st.columns(4)[0]:  # la griglia della Home: card della stessa larghezza
        metrica(
            "Errore medio del modello",
            stato.mae_kg,
            "kg",
            aiuto=f"Scarto medio delle stime sul 2010–2012 (modello {stato.versione}).",
        )

st.info("Questa pagina è in costruzione: il contenuto arriva con M6-T5.", icon="🚧")
