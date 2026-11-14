"""
BeeWatch AI - pagina Impostazioni: Profilo, Notifiche, AI e Modelli, Database (M6-T13).

Quattro schede (`st.tabs`). Le prime tre scrivono su MySQL tramite i servizi:

- **Profilo**: nome ed email, la password (conoscendo quella attuale), e la cancellazione
  dell'account con tutti i suoi dati (GDPR art. 17), confermata con la password e una spunta;
- **Notifiche**: dopo quanti giorni un alveare va ricontrollato e se avvisare delle ispezioni a
  rischio: la Home li usa per i promemoria e per il numero «Da controllare»;
- **AI e Modelli**: l'assistente e il modello in uso, e il consenso a inviare le note a un servizio
  esterno, che il servizio stesso fa rispettare.

La quarta, **Database**, è in sola lettura: la configurazione che arriva da `.env`, senza password
né chiavi (si dicono solo «impostata» o «mancante»).
"""

from __future__ import annotations

import streamlit as st
from avvio import (
    CHIAVE_UTENTE,
    account_eliminato,
    aggiorna_nome_in_accesso,
    apiari,
    avvia,
    modello,
    preferenze,
    prendi_esito,
    profilo,
    promemoria,
    scrittura_riuscita,
)
from ui import formatta_numero, intestazione, metrica, mostra_errore, sidebar

from beewatch.exceptions import BeeWatchError
from beewatch.services import GIORNI_PROMEMORIA, REGOLE_PASSWORD

servizi = avvia("Impostazioni", "⚙️")
sidebar()
utente = st.session_state[CHIAVE_UTENTE]

intestazione(
    "⚙️ Impostazioni",
    "Il tuo profilo, i promemoria, l'assistente AI e la configurazione dell'applicazione.",
)

esito = prendi_esito()
if esito:
    st.success(esito, icon="✅")

try:
    apiari(utente)  # la sidebar non solleva: se il database è giù, lo dice il corpo
    chi = profilo(utente)
    scelte = preferenze(utente)
except BeeWatchError as errore:
    mostra_errore(errore)
    st.stop()


def salva(**cambiate) -> None:
    """Salva le preferenze cambiando solo quelle indicate."""
    valori = {
        "giorni_promemoria": scelte.giorni_promemoria,
        "avvisi_rischio": scelte.avvisi_rischio,
        "assistente_esterno": scelte.assistente_esterno,
        **cambiate,
    }
    servizi.salva_preferenze(utente, **valori)


scheda_profilo, scheda_notifiche, scheda_ai, scheda_database = st.tabs(
    ["Profilo", "Notifiche", "AI e Modelli", "Database"]
)

# --------------------------------------------------------------------------- #
# Profilo
# --------------------------------------------------------------------------- #

with scheda_profilo:
    st.subheader("Il tuo profilo")
    with st.form("profilo"):
        nome = st.text_input("Nome e cognome", value=chi.nome, max_chars=120, key="profilo_nome")
        email = st.text_input("Email", value=chi.email, key="profilo_email")
        if st.form_submit_button("Salva il profilo", type="primary", key="profilo_invia"):
            try:
                nuovo = servizi.aggiorna_profilo(utente, nome=nome, email=email)
            except BeeWatchError as errore:
                mostra_errore(errore)
            else:
                aggiorna_nome_in_accesso(nuovo.nome)
                scrittura_riuscita("Profilo aggiornato.")

    st.subheader("Password")
    with st.form("password", clear_on_submit=True):
        attuale = st.text_input("Password attuale", type="password", key="password_attuale")
        colonne = st.columns(2)
        nuova = colonne[0].text_input(
            "Nuova password", type="password", key="password_nuova", help=REGOLE_PASSWORD
        )
        conferma = colonne[1].text_input(
            "Conferma la nuova password", type="password", key="password_conferma"
        )
        if st.form_submit_button("Cambia la password", key="password_invia"):
            try:
                servizi.cambia_password(utente, attuale=attuale, nuova=nuova, conferma=conferma)
            except BeeWatchError as errore:
                mostra_errore(errore)
            else:
                scrittura_riuscita("Password cambiata.")

    st.subheader("Cancella l'account")
    st.caption(
        "Cancella per sempre l'account e tutti i suoi dati: apiari, alveari, ispezioni, raccolti, "
        "stime, riepiloghi, report e preferenze. Non si torna indietro (GDPR, art. 17)."
    )
    password_cancella = st.text_input(
        "Password, per confermare", type="password", key="cancella_password"
    )
    confermato = st.checkbox(
        "Confermo: cancella il mio account e tutti i miei dati", key="cancella_conferma"
    )
    premuto = st.button(
        "Cancella l'account", type="primary", disabled=not confermato, key="cancella_invia"
    )
    if premuto and confermato:  # la spunta si ricontrolla: un bottone disabilitato non basta
        try:
            servizi.elimina_account(utente, password=password_cancella)
        except BeeWatchError as errore:
            mostra_errore(errore)
        else:
            account_eliminato()

# --------------------------------------------------------------------------- #
# Notifiche
# --------------------------------------------------------------------------- #

with scheda_notifiche:
    st.subheader("Promemoria nella Home")
    minimo, massimo = GIORNI_PROMEMORIA
    with st.form("notifiche"):
        giorni = st.slider(
            "Un alveare va ricontrollato dopo quanti giorni senza ispezione?",
            min_value=minimo,
            max_value=massimo,
            value=scelte.giorni_promemoria,
            key="notifiche_giorni",
        )
        avvisi = st.checkbox(
            "Avvisami delle ispezioni recenti con rischio medio o alto",
            value=scelte.avvisi_rischio,
            key="notifiche_avvisi",
        )
        if st.form_submit_button("Salva le notifiche", type="primary", key="notifiche_invia"):
            try:
                salva(giorni_promemoria=giorni, avvisi_rischio=avvisi)
            except BeeWatchError as errore:
                mostra_errore(errore)
            else:
                scrittura_riuscita("Notifiche salvate.")
    try:
        ora = promemoria(utente)
    except BeeWatchError as errore:
        mostra_errore(errore)
    else:
        colonne = st.columns(4)
        with colonne[0]:
            metrica(
                "Alveari da ricontrollare",
                len(ora.da_controllare),
                None,
                aiuto=f"Mai ispezionati, o non da oltre {ora.giorni} giorni.",
            )
        if ora.avvisi_rischio:
            with colonne[1]:
                metrica("Ispezioni a rischio (60 giorni)", len(ora.a_rischio), None)
    st.caption("I promemoria compaiono nella Home, ogni volta che la apri: non partono email.")

# --------------------------------------------------------------------------- #
# AI e Modelli
# --------------------------------------------------------------------------- #

with scheda_ai:
    st.subheader("Assistente AI")
    info = servizi.info_assistente()
    dove = {
        True: "gira su questo computer",
        False: "è un servizio esterno",
        None: "non è configurato",
    }
    st.markdown(
        f"**{info.descrizione}** · prompt **{info.versione_prompt}** · {dove[info.in_locale]}."
    )
    with st.form("assistente"):
        esterno = st.checkbox(
            "Consenti di inviare le note delle ispezioni a un servizio esterno",
            value=scelte.assistente_esterno,
            key="ai_esterno",
            help="Se lo togli e l'assistente è esterno (OpenRouter), le note non escono dal PC: "
            "il riepilogo non si genera.",
        )
        if st.form_submit_button("Salva", type="primary", key="ai_invia"):
            try:
                salva(assistente_esterno=esterno)
            except BeeWatchError as errore:
                mostra_errore(errore)
            else:
                scrittura_riuscita("Preferenze dell'assistente salvate.")
    if info.in_locale is True:
        st.caption(
            "Ora l'assistente è locale: le note non escono comunque. La scelta conta se un "
            "giorno l'assistente diventa esterno."
        )

    st.subheader("Modello di previsione")
    try:
        stato = modello()
    except BeeWatchError as errore:
        mostra_errore(errore)
    else:
        colonne = st.columns(4)
        with colonne[0]:
            metrica("Errore medio", stato.mae_kg, "kg", aiuto="Sul 2010–2012, anni mai visti.")
        with colonne[1]:
            metrica("Righe di addestramento", stato.righe_addestramento, None)
        st.caption(
            f"Modello {stato.versione} ({stato.algoritmo}): in media sbaglia di "
            f"{formatta_numero(stato.mae_kg)} kg per colonia. Si cambia riaddestrandolo "
            "(`python scripts/train_model.py`), non da qui."
        )

# --------------------------------------------------------------------------- #
# Database (sola lettura)
# --------------------------------------------------------------------------- #

with scheda_database:
    st.subheader("Configurazione")
    voci = servizi.configurazione_visibile()
    if voci:
        st.dataframe(
            [{"Sezione": s, "Voce": v, "Valore": valore} for s, v, valore in voci],
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption("La configurazione non è disponibile in questa esecuzione.")
    st.caption(
        "In sola lettura: questi valori vengono dal file `.env`. Per cambiarli si modifica il "
        "file e si riavvia l'applicazione. Password e chiavi non si mostrano mai: si dice solo "
        "se sono impostate."
    )
