"""
BeeWatch AI - Accedi (M6-T11; aspetto del mockup).

Schermo diviso come nel mockup: a sinistra il pannello di benvenuto, a destra il modulo con
l'interruttore del tema in alto. Email e password le verifica il servizio (`Servizi.accedi`): la
password si confronta con l'hash bcrypt salvato, e un errore non dice mai se l'email esiste.
«Ricordami» tiene dentro per 30 giorni su questo browser.

Del mockup non ci sono «Password dimenticata?» e «Continua con Google»: dietro non c'è un servizio,
e un bottone che non fa nulla inganna. Al posto di Google c'è l'ingresso con l'utente dimostrativo
del seed (DA-02), che chi vuole solo provare l'app può usare senza password.
"""

from __future__ import annotations

import streamlit as st
from avvio import avvia, entra
from tema import interruttore_tema
from ui import mostra_errore, pannello_benvenuto, separatore_oppure, titolo_modulo

from beewatch.exceptions import BeeWatchError

servizi = avvia("Accedi", "🔑", pubblica=True)

benvenuto, modulo = st.columns([2, 3])

with benvenuto, st.container(key="bw_lato_benvenuto"):
    pannello_benvenuto()

with modulo, st.container(key="bw_lato_modulo"):
    interruttore_tema()
    titolo_modulo("Bentornato", "Accedi al tuo account per continuare.")

    with st.form("accedi"):
        email = st.text_input(
            "Email", key="accedi_email", placeholder="nome@dominio.it", icon=":material/mail:"
        )
        password = st.text_input(
            "Password", type="password", key="accedi_password", icon=":material/lock:"
        )
        ricorda = st.checkbox(
            "Ricordami",
            key="accedi_ricorda",
            help="Resti dentro per 30 giorni su questo browser. Senza la spunta, finché lo chiudi.",
        )
        premuto = st.form_submit_button(
            "Accedi",
            type="primary",
            key="accedi_invia",
            width="stretch",
            icon=":material/arrow_forward:",
        )
    if premuto:
        try:
            utente = servizi.accedi(email, password)
        except BeeWatchError as errore:
            mostra_errore(errore)
        else:
            entra(utente, ricorda=ricorda)

    separatore_oppure()
    if st.button(
        "Entra con l'utente dimostrativo",
        key="accedi_demo",
        width="stretch",
        icon=":material/hive:",
        help="Un apiario di esempio, con alveari e ispezioni già registrati.",
    ):
        try:
            utente = servizi.accesso_dimostrativo()
        except BeeWatchError as errore:
            mostra_errore(errore)
        else:
            entra(utente)

    with st.container(key="bw_link_centrato"):
        st.page_link("schermate/registrati.py", label="Non hai un account? **Registrati**")
