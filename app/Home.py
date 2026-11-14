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
from avvio import accesso_completo, accesso_effettuato, avvia, passo_onboarding

avvia("BeeWatch AI", pubblica=True, router=True)

if not accesso_effettuato():
    pagine = [
        st.Page("schermate/accedi.py", title="Accedi", icon=":material/login:", default=True),
        st.Page("schermate/registrati.py", title="Registrati", icon=":material/person_add:"),
    ]
elif passo_onboarding() is not None:
    pagine = [
        st.Page(
            "schermate/onboarding.py", title="Primi passi", icon=":material/flag:", default=True
        )
    ]
else:
    pagine = [
        st.Page("schermate/home.py", title="Home", icon=":material/home:", default=True),
        st.Page("pages/1_Alveari.py", title="Alveari", icon=":material/hive:"),
        st.Page("pages/2_Ispezioni.py", title="Ispezioni", icon=":material/assignment_turned_in:"),
        st.Page("pages/3_Previsione.py", title="Previsioni", icon=":material/show_chart:"),
        st.Page("pages/4_Assistente_AI.py", title="AI Assistant", icon=":material/smart_toy:"),
        st.Page("pages/5_Dashboard.py", title="Dashboard", icon=":material/dashboard:"),
        st.Page("pages/6_Trasparenza.py", title="Trasparenza", icon=":material/visibility:"),
        st.Page("pages/7_Report.py", title="Report", icon=":material/description:"),
        st.Page("pages/8_Impostazioni.py", title="Impostazioni", icon=":material/settings:"),
    ]

# Prima dell'accesso e nei primi passi niente sidebar, come nel mockup: si passa da Accedi a
# Registrati con i link della pagina.
st.navigation(pagine, position="sidebar" if accesso_completo() else "hidden").run()
