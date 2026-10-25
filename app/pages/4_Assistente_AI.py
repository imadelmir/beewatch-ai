"""
BeeWatch AI - pagina Assistente AI: scheletro (M6-T1).

La pagina c'è, è nel menu al suo posto e parte con lo stato di sessione e i servizi pronti; il
contenuto (il riepilogo delle note di un'ispezione) arriva con M6-T6. Il prefisso numerico del
nome del file decide l'ordine nel menu.
"""

from __future__ import annotations

import streamlit as st
from avvio import avvia

avvia("Assistente AI", "🤖")

st.title("🤖 Assistente AI")
st.info("Questa pagina è in costruzione: il contenuto arriva con M6-T6.", icon="🚧")
