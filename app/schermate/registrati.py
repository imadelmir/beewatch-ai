"""
BeeWatch AI - Registrati (M6-T11).

Nome, email, password due volte e il consenso esplicito a come l'app tratta i dati. La pagina
controlla il consenso; il resto (forma dell'email, lunghezza della password, password uguali,
email già usata) lo controlla il servizio, che salva solo l'hash della password. Dopo la
registrazione l'utente è dentro e parte dai primi passi guidati.
"""

from __future__ import annotations

import streamlit as st
from avvio import avvia, entra
from ui import intestazione, mostra_errore

from beewatch.exceptions import BeeWatchError, ValidationError
from beewatch.services import REGOLE_PASSWORD

servizi = avvia("Registrati", "✍️", pubblica=True)

intestazione(
    "🐝 BeeWatch AI",
    "Crea il tuo account: in pochi minuti registri il primo apiario e il primo alveare.",
)

presentazione, modulo = st.columns([1, 1], gap="large")

with presentazione:
    st.subheader("Come trattiamo i tuoi dati")
    st.markdown(
        "- Nome, email e i dati dell'apiario restano nel **database di questo computer**.\n"
        "- La password **non si salva**: si salva solo un'impronta cifrata (hash), da cui non "
        "si può risalire alla password.\n"
        "- Puoi chiedere di **cancellare tutto**: l'account e, con lui, apiari, ispezioni e "
        "riepiloghi.\n"
        "- I dettagli sono nella pagina **Trasparenza**, dopo l'accesso."
    )

with modulo:
    st.subheader("Crea il tuo account")
    with st.form("registrati"):
        nome = st.text_input("Nome e cognome", max_chars=120, key="registrati_nome")
        email = st.text_input("Email", key="registrati_email", placeholder="nome@dominio.it")
        colonne = st.columns(2)
        password = colonne[0].text_input(
            "Password", type="password", key="registrati_password", help=REGOLE_PASSWORD
        )
        conferma = colonne[1].text_input(
            "Conferma la password", type="password", key="registrati_conferma"
        )
        consenso = st.checkbox(
            "Ho letto come vengono trattati i miei dati", key="registrati_consenso"
        )
        premuto = st.form_submit_button(
            "Crea l'account", type="primary", key="registrati_invia", width="stretch"
        )
    if premuto:
        if not consenso:
            mostra_errore(
                ValidationError(
                    "Per creare l'account conferma di aver letto come vengono trattati i dati.",
                    campo="consenso",
                )
            )
        else:
            try:
                utente = servizi.registra_utente(
                    nome=nome, email=email, password=password, conferma=conferma
                )
            except BeeWatchError as errore:
                mostra_errore(errore)
            else:
                entra(utente, nuovo=True)

    st.page_link("schermate/accedi.py", label="Hai già un account? **Accedi**", icon="🔑")
