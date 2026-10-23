"""
BeeWatch AI - punto di ingresso dell'interfaccia Streamlit.

Questa e' una pagina di diagnostica, non l'applicazione: verifica che
configurazione, ambiente e contenitore siano a posto. Verra' sostituita
dall'interfaccia vera in M6, a partire da M6-T1.

Esiste gia' adesso per una ragione precisa: senza un punto di ingresso,
il Dockerfile costruirebbe un'immagine che non si puo' avviare, e nessuno
scoprirebbe che non funziona finche' non serve davvero.

Avvio in locale:

    streamlit run app/main.py

Avvio nel contenitore:

    docker compose up -d
"""

from __future__ import annotations

import sys

import streamlit as st

from beewatch.config import ottieni
from beewatch.exceptions import BeeWatchError

st.set_page_config(page_title="BeeWatch AI", page_icon="🐝", layout="centered")

st.title("🐝 BeeWatch AI")
st.caption("Pagina di diagnostica — l'interfaccia vera arriva con M6")

try:
    configurazione = ottieni()
except BeeWatchError as errore:
    # Un errore di configurazione e' l'unico da cui non si puo' proseguire:
    # meglio dirlo qui, in chiaro, che lasciare fallire la prima query.
    st.error("La configurazione non e' valida.")
    st.code(str(errore), language="text")
    st.stop()

st.success("Configurazione caricata e validata.")

st.subheader("Ambiente")
st.table(
    {
        "Voce": ["Python", "Database", "Modello di linguaggio", "Modello ML", "Livello di log"],
        "Valore": [
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            configurazione.database.descrizione(),
            configurazione.llm.descrizione(),
            str(configurazione.percorso_modello),
            configurazione.livello_log,
        ],
    }
)

st.info(
    "La password del database non compare in questa pagina: `descrizione()` la "
    "sostituisce con `***`. È lo stesso metodo usato nel log d'avvio.",
    icon="🔒",
)

st.divider()
st.caption(
    "Prossimo passo: M6 — questa pagina viene sostituita dall'interfaccia vera "
    "(Home e le sei pagine)."
)
