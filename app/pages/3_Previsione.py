"""
BeeWatch AI - pagina Previsione: scheletro (M6-T1).

La pagina c'è, è nel menu al suo posto e parte con lo stato di sessione e i servizi pronti; il
contenuto (la stima della produzione, sempre con il suo intervallo) arriva con M6-T5. Il prefisso
numerico del nome del file decide l'ordine nel menu.
"""

from __future__ import annotations

import streamlit as st
from avvio import avvia

avvia("Previsione", "📈")

st.title("📈 Previsione")
st.info("Questa pagina è in costruzione: il contenuto arriva con M6-T5.", icon="🚧")
