"""
BeeWatch AI - Registrati (M6-T11; aspetto del mockup).

Come nel mockup: nome e cognome, email, password con l'indicatore di robustezza e la conferma, il
nome dell'apiario (facoltativo) e il consenso. La pagina controlla il consenso; il resto (forma
dell'email, regole della password, password uguali, email già usata) lo controlla il servizio,
che salva solo l'hash della password. Se c'è il nome dell'apiario, l'apiario nasce subito, con lo
stesso servizio della pagina Alveari. Dopo la registrazione si parte dai primi passi.

Niente `st.form`: così l'indicatore della password si aggiorna appena si esce dal campo.
"""

from __future__ import annotations

import streamlit as st
from avvio import avvia, entra
from tema import interruttore_tema
from ui import indicatore_forza, mostra_errore, pannello_benvenuto, titolo_modulo

from beewatch.exceptions import BeeWatchError, ValidationError
from beewatch.logging_config import ottieni_logger
from beewatch.services import REGOLE_PASSWORD

logger = ottieni_logger("beewatch.app.registrati")

TRATTAMENTO_DATI = (
    "Nome, email e i dati dell'apiario restano nel database di questo computer. La password non "
    "si salva: si salva solo un'impronta cifrata (hash). Puoi cancellare tutto quando vuoi, dalle "
    "Impostazioni. I dettagli sono nella pagina Trasparenza."
)

servizi = avvia("Registrati", "✍️", pubblica=True)

benvenuto, modulo = st.columns([2, 3])

with benvenuto, st.container(key="bw_lato_benvenuto"):
    pannello_benvenuto()

with modulo, st.container(key="bw_lato_modulo"):
    interruttore_tema()
    titolo_modulo("Crea il tuo account", "Inizia a monitorare il tuo apiario in pochi minuti.")

    colonne = st.columns(2)
    nome = colonne[0].text_input("Nome", max_chars=60, key="registrati_nome")
    cognome = colonne[1].text_input("Cognome", max_chars=60, key="registrati_cognome")
    email = st.text_input(
        "Email", key="registrati_email", placeholder="nome@dominio.it", icon=":material/mail:"
    )
    colonne = st.columns(2)
    with colonne[0]:
        password = st.text_input(
            "Password",
            type="password",
            key="registrati_password",
            help=REGOLE_PASSWORD,
            icon=":material/lock:",
        )
        indicatore_forza(password)
    conferma = colonne[1].text_input(
        "Conferma password", type="password", key="registrati_conferma", icon=":material/lock:"
    )
    nome_apiario = st.text_input(
        "Nome apiario / azienda",
        max_chars=120,
        key="registrati_apiario",
        icon=":material/hive:",
        placeholder="Facoltativo: puoi aggiungerlo anche dopo",
    )
    consenso = st.checkbox(
        "Accetto il trattamento dei miei dati descritto in Trasparenza",
        key="registrati_consenso",
        help=TRATTAMENTO_DATI,
    )
    premuto = st.button(
        "Crea account",
        type="primary",
        key="registrati_invia",
        width="stretch",
        icon=":material/arrow_forward:",
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
                    nome=f"{nome.strip()} {cognome.strip()}".strip(),
                    email=email,
                    password=password,
                    conferma=conferma,
                )
            except BeeWatchError as errore:
                mostra_errore(errore)
            else:
                if nome_apiario.strip():
                    try:
                        servizi.crea_apiario(utente.id, nome=nome_apiario, localita="")
                    except BeeWatchError as errore:  # l'account c'è: l'apiario si crea dopo
                        logger.warning("Apiario della registrazione non creato: %s", errore)
                entra(utente, nuovo=True)

    with st.container(key="bw_link_centrato"):
        st.page_link("schermate/accedi.py", label="Hai già un account? **Accedi**")
