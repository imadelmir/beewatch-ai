"""
BeeWatch AI - Primi passi guidati dopo la registrazione (M6-T11).

Tre passi, come nel mockup: il primo apiario, il primo alveare, «tutto pronto». Ogni passo si può
saltare: l'app funziona anche vuota, e la pagina Alveari fa le stesse cose. La pagina non scrive
nel database: chiama `crea_apiario` e `crea_alveare` dei servizi, gli stessi della pagina Alveari.
"""

from __future__ import annotations

import streamlit as st
from avvio import (
    CHIAVE_APIARIO_ATTIVO,
    CHIAVE_UTENTE,
    PASSI_ONBOARDING,
    avanza_onboarding,
    avvia,
    imposta_apiario_attivo,
    nome_in_accesso,
    passo_onboarding,
    svuota_letture,
    termina_onboarding,
)
from ui import intestazione, mostra_errore, stile_stato

from beewatch.exceptions import BeeWatchError, ValidationError
from beewatch.models import StatoAlveare

TITOLI = {1: "Il tuo primo apiario", 2: "Il tuo primo alveare", 3: "Tutto pronto"}

servizi = avvia("Primi passi", "🧭")
utente = st.session_state[CHIAVE_UTENTE]
passo = passo_onboarding() or PASSI_ONBOARDING

intestazione(
    f"🧭 Benvenuto, {nome_in_accesso()}",
    "Tre passi per partire. Puoi saltarli: tutto si può fare anche dopo, dalla pagina Alveari.",
)
st.progress(passo / PASSI_ONBOARDING, text=f"Passo {passo} di {PASSI_ONBOARDING}: {TITOLI[passo]}")

if passo == 1:
    st.subheader(TITOLI[1])
    st.caption("Un apiario è il luogo dove stanno le tue arnie.")
    with st.form("onboarding_apiario"):
        nome = st.text_input("Nome dell'apiario *", max_chars=120, key="onboarding_nome")
        localita = st.text_input("Località", max_chars=160, key="onboarding_localita")
        premuto = st.form_submit_button("Continua", type="primary", key="onboarding_apiario_invia")
    if premuto:
        if not nome.strip():
            mostra_errore(ValidationError("Il nome dell'apiario è obbligatorio.", campo="nome"))
        else:
            try:
                apiario = servizi.crea_apiario(utente, nome=nome, localita=localita)
            except BeeWatchError as errore:
                mostra_errore(errore)
            else:
                imposta_apiario_attivo(apiario.id)
                svuota_letture()
                avanza_onboarding()

elif passo == 2:
    st.subheader(TITOLI[2])
    st.caption("Un alveare è un'arnia; il codice lo distingue dalle altre dell'apiario (es. A1).")
    stati = list(StatoAlveare)
    with st.form("onboarding_alveare"):
        codice = st.text_input("Codice *", max_chars=20, key="onboarding_codice")
        stato = st.selectbox(
            "Stato", options=stati, format_func=lambda s: stile_stato(s)[0], key="onboarding_stato"
        )
        premuto = st.form_submit_button("Continua", type="primary", key="onboarding_alveare_invia")
    if premuto:
        if not codice.strip():
            mostra_errore(ValidationError("Il codice dell'alveare è obbligatorio.", campo="codice"))
        else:
            try:
                servizi.crea_alveare(
                    utente,
                    apiario_id=st.session_state[CHIAVE_APIARIO_ATTIVO],
                    codice=codice,
                    stato=stato,
                )
            except BeeWatchError as errore:
                mostra_errore(errore)
            else:
                svuota_letture()
                avanza_onboarding()

else:
    st.subheader(TITOLI[3])
    st.markdown(
        "- registra le visite in **Ispezioni**, con le note di campo;\n"
        "- chiedi all'**Assistente AI** di riassumerle;\n"
        "- guarda la **Previsione** e la **Dashboard**;\n"
        "- leggi in **Trasparenza** come l'app tratta i tuoi dati."
    )
    if st.button("Vai alla Home", type="primary", key="onboarding_fine"):
        termina_onboarding()

if passo < PASSI_ONBOARDING:
    st.divider()
    if st.button("Salta i primi passi", key="onboarding_salta"):
        termina_onboarding()
