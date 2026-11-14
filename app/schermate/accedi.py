"""
BeeWatch AI - Accedi (M6-T11).

Email e password, verificate dal servizio (`Servizi.accedi`): la password si confronta con l'hash
bcrypt salvato, e un errore non dice mai se l'email esiste. Chi vuole solo provare l'app può
entrare con l'utente dimostrativo del seed (DA-02), con un bottone esplicito.
"""

from __future__ import annotations

import streamlit as st
from avvio import avvia, entra
from ui import intestazione, mostra_errore

from beewatch.exceptions import BeeWatchError

servizi = avvia("Accedi", "🔑", pubblica=True)

intestazione(
    "🐝 BeeWatch AI",
    "Il quaderno di campo dell'apicoltore, con una stima della produzione e un assistente AI.",
)

presentazione, modulo = st.columns([1, 1], gap="large")

with presentazione:
    st.subheader("Monitora il tuo apiario con l'AI")
    st.markdown(
        "- **Ispezioni e raccolti** in un quaderno digitale\n"
        "- **Previsioni della produzione**, sempre con il loro margine d'errore\n"
        "- **Un assistente AI** che riassume le note di campo"
    )
    st.caption("I tuoi dati restano nel database di questo computer.")

with modulo:
    st.subheader("Bentornato")
    with st.form("accedi"):
        email = st.text_input("Email", key="accedi_email", placeholder="nome@dominio.it")
        password = st.text_input("Password", type="password", key="accedi_password")
        premuto = st.form_submit_button(
            "Accedi", type="primary", key="accedi_invia", width="stretch"
        )
    if premuto:
        try:
            utente = servizi.accedi(email, password)
        except BeeWatchError as errore:
            mostra_errore(errore)
        else:
            entra(utente)

    st.page_link("schermate/registrati.py", label="Non hai un account? **Registrati**", icon="✍️")

    st.divider()
    st.caption("Vuoi solo provare l'app? C'è un apiario dimostrativo con i dati di esempio.")
    if st.button("Entra con l'utente dimostrativo", key="accedi_demo", width="stretch"):
        try:
            utente = servizi.accesso_dimostrativo()
        except BeeWatchError as errore:
            mostra_errore(errore)
        else:
            entra(utente)
