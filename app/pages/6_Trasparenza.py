"""
BeeWatch AI - pagina Trasparenza: scheletro (M6-T1).

La pagina c'è, è nel menu al suo posto e parte con lo stato di sessione e i servizi pronti; il
contenuto (come funziona il modello, i suoi limiti e i dati usati) arriva con M6-T8. Il prefisso
numerico del nome del file decide l'ordine nel menu.
"""

from __future__ import annotations

import streamlit as st
from avvio import avvia

avvia("Trasparenza", "🔍")

st.title("🔍 Trasparenza")
st.info("Questa pagina è in costruzione: il contenuto arriva con M6-T8.", icon="🚧")
