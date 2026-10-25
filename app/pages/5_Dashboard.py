"""
BeeWatch AI - pagina Dashboard: scheletro (M6-T1).

La pagina c'è, è nel menu al suo posto e parte con lo stato di sessione e i servizi pronti; il
contenuto (l'andamento degli alveari e la qualità del modello) arriva con M6-T7. Il prefisso
numerico del nome del file decide l'ordine nel menu.
"""

from __future__ import annotations

import streamlit as st
from avvio import avvia

avvia("Dashboard", "📊")

st.title("📊 Dashboard")
st.info("Questa pagina è in costruzione: il contenuto arriva con M6-T7.", icon="🚧")
