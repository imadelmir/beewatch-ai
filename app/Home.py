"""
BeeWatch AI - punto d'ingresso: il router che costruisce il menu in base all'accesso (M6-T11).

Avvio in locale (dalla radice del progetto, dove sta `.streamlit/config.toml`):

    streamlit run app/Home.py

Avvio nel contenitore:

    docker compose up -d

Streamlit esegue questo file a ogni interazione, poi la pagina scelta. Il menu dipende da chi c'è:

- **nessun accesso**: solo Accedi e Registrati. Le pagine dell'app non sono nel menu, quindi non si
  raggiungono nemmeno scrivendone l'indirizzo;
- **utente appena registrato**: i primi passi guidati (primo apiario, primo alveare);
- **accesso fatto**: la Home e le sei pagine della specifica, nell'ordine di sempre.

Lo stato dell'accesso vive in `st.session_state` e nasce in `avvio.py`, come il resto dello stato.
"""

from __future__ import annotations

import streamlit as st
from avvio import accesso_effettuato, avvia, passo_onboarding

avvia("BeeWatch AI", pubblica=True)

if not accesso_effettuato():
    pagine = [
        st.Page("schermate/accedi.py", title="Accedi", icon="🔑", default=True),
        st.Page("schermate/registrati.py", title="Registrati", icon="✍️"),
    ]
elif passo_onboarding() is not None:
    pagine = [st.Page("schermate/onboarding.py", title="Primi passi", icon="🧭", default=True)]
else:
    pagine = [
        st.Page("schermate/home.py", title="Home", icon="🐝", default=True),
        st.Page("pages/1_Alveari.py", title="Alveari", icon="🏠"),
        st.Page("pages/2_Ispezioni.py", title="Ispezioni", icon="📋"),
        st.Page("pages/3_Previsione.py", title="Previsione", icon="📈"),
        st.Page("pages/4_Assistente_AI.py", title="Assistente AI", icon="🤖"),
        st.Page("pages/5_Dashboard.py", title="Dashboard", icon="📊"),
        st.Page("pages/6_Trasparenza.py", title="Trasparenza", icon="🔍"),
        st.Page("pages/7_Report.py", title="Report", icon="📄"),
    ]

st.navigation(pagine).run()
