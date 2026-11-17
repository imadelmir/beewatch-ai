"""
BeeWatch AI - pagina Impostazioni (M6-T13; aspetto del mockup, tavole 40–46).

Quattro schede (`st.tabs`), con le card del mockup:

- **Profilo**: «Dati profilo» (avatar con le iniziali, nome ed email), «Sicurezza» (la password,
  conoscendo quella attuale) e la cancellazione dell'account con tutti i suoi dati (GDPR art. 17),
  confermata con la password e una spunta; accanto, «Aspetto» con l'interruttore Scuro/Chiaro;
- **Notifiche**: dopo quanti giorni un alveare va ricontrollato e se avvisare delle ispezioni a
  rischio: la Dashboard li usa per notifiche e scadenze;
- **AI e Modelli**: l'assistente in uso e il consenso a inviare le note a un servizio esterno, che
  il servizio stesso fa rispettare; accanto, il modello di previsione con le sue metriche;
- **Database**: la configurazione da `.env`, in sola lettura, senza password né chiavi.

Del mockup mancano foto, telefono, azienda, ruolo, lingua, unità di misura, autenticazione a due
fattori, temperatura, lunghezza e prompt dell'assistente, il riaddestramento con un clic, i backup
e «svuota database»: l'app non li ha, e un campo che non si salva inganna. Non c'è nemmeno un
unico «Salva modifiche»: ogni card salva da sé, così è chiaro che cosa si è salvato.
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
    password_cambiata,
    preferenze,
    prendi_esito,
    profilo,
    promemoria,
    scrittura_riuscita,
)
from schede import Voce, avatar_profilo, elenco, testata
from tema import interruttore_tema
from ui import formatta_numero, metrica, mostra_errore, sidebar

from beewatch.exceptions import BeeWatchError
from beewatch.services import GIORNI_PROMEMORIA, REGOLE_PASSWORD

servizi = avvia("Impostazioni", "⚙️")
sidebar()
utente = st.session_state[CHIAVE_UTENTE]

testata("Impostazioni", "Gestisci il tuo profilo, le notifiche, i modelli e il database.")

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
    sinistra, destra = st.columns([1.6, 1])
    with sinistra, st.container(key="bw_card_profilo"):
        st.subheader("Dati profilo")
        avatar_profilo(chi.nome, "Apicoltore")
        with st.form("profilo", border=False):
            colonne = st.columns(2)
            nome = colonne[0].text_input(
                "Nome e cognome", value=chi.nome, max_chars=120, key="profilo_nome"
            )
            email = colonne[1].text_input(
                "Email", value=chi.email, key="profilo_email", icon=":material/mail:"
            )
            if st.form_submit_button("Salva il profilo", type="primary", key="profilo_invia",
                                     icon=":material/check_circle:"):  # fmt: skip
                try:
                    nuovo = servizi.aggiorna_profilo(utente, nome=nome, email=email)
                except BeeWatchError as errore:
                    mostra_errore(errore)
                else:
                    aggiorna_nome_in_accesso(nuovo.nome)
                    scrittura_riuscita("Profilo aggiornato.")

        st.subheader("Sicurezza")
        with st.form("password", clear_on_submit=True, border=False):
            attuale = st.text_input("Password attuale", type="password", key="password_attuale",
                                    icon=":material/lock:")  # fmt: skip
            colonne = st.columns(2)
            nuova = colonne[0].text_input(
                "Nuova password", type="password", key="password_nuova", help=REGOLE_PASSWORD
            )
            conferma = colonne[1].text_input(
                "Conferma la nuova password", type="password", key="password_conferma"
            )
            if st.form_submit_button("Cambia la password", key="password_invia",
                                     icon=":material/lock_reset:"):  # fmt: skip
                try:
                    servizi.cambia_password(utente, attuale=attuale, nuova=nuova, conferma=conferma)
                except BeeWatchError as errore:
                    mostra_errore(errore)
                else:
                    password_cambiata()  # gli altri browser escono, questo resta dentro
                    scrittura_riuscita("Password cambiata.")

    with destra:
        with st.container(key="bw_card_aspetto"):
            st.subheader("Aspetto")
            st.caption("Tema dell'applicazione: la pagina si ricarica e resti dentro.")
            interruttore_tema()

        with st.container(key="bw_card_pericolo"):
            st.subheader("Cancella l'account")
            st.caption(
                "Cancella per sempre l'account e tutti i suoi dati: apiari, alveari, ispezioni, "
                "raccolti, stime, riepiloghi, report e preferenze. Non si torna indietro (GDPR, "
                "art. 17)."
            )
            password_cancella = st.text_input(
                "Password, per confermare", type="password", key="cancella_password"
            )
            confermato = st.checkbox(
                "Confermo: cancella il mio account e tutti i miei dati", key="cancella_conferma"
            )
            with st.container(key="bw_bottone_elimina"):
                premuto = st.button(
                    "Cancella l'account", disabled=not confermato, key="cancella_invia",
                    icon=":material/delete:", width="stretch",
                )  # fmt: skip
            if premuto and confermato:  # la spunta si ricontrolla: un bottone disabilitato no
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
    sinistra, destra = st.columns([1.6, 1])
    with sinistra, st.container(key="bw_card_notifiche"):
        st.subheader("Notifiche")
        st.caption("Compaiono nella Dashboard, ogni volta che la apri: non partono email.")
        minimo, massimo = GIORNI_PROMEMORIA
        with st.form("notifiche", border=False):
            giorni = st.slider(
                "Promemoria ispezioni: un alveare va ricontrollato dopo quanti giorni?",
                min_value=minimo, max_value=massimo, value=scelte.giorni_promemoria,
                key="notifiche_giorni",
            )  # fmt: skip
            avvisi = st.toggle(
                "Avvisi sanitari: ispezioni recenti con rischio medio o alto",
                value=scelte.avvisi_rischio, key="notifiche_avvisi",
            )  # fmt: skip
            if st.form_submit_button("Salva le notifiche", type="primary", key="notifiche_invia",
                                     icon=":material/check_circle:"):  # fmt: skip
                try:
                    salva(giorni_promemoria=giorni, avvisi_rischio=avvisi)
                except BeeWatchError as errore:
                    mostra_errore(errore)
                else:
                    scrittura_riuscita("Notifiche salvate.")
    with destra, st.container(key="bw_card_promemoria"):
        st.subheader("Adesso")
        try:
            ora = promemoria(utente)
        except BeeWatchError as errore:
            mostra_errore(errore)
        else:
            metrica(
                "Alveari da ricontrollare",
                len(ora.da_controllare),
                None,
                aiuto=f"Mai ispezionati, o non da oltre {ora.giorni} giorni.",
            )
            if ora.avvisi_rischio:
                metrica("Ispezioni a rischio (60 giorni)", len(ora.a_rischio), None)

# --------------------------------------------------------------------------- #
# AI e Modelli
# --------------------------------------------------------------------------- #

with scheda_ai:
    sinistra, destra = st.columns([1.6, 1])
    with sinistra, st.container(key="bw_card_ai_impostazioni"):
        st.subheader("Impostazioni AI")
        info = servizi.info_assistente()
        dove = {True: "su questo computer", False: "servizio esterno", None: "non configurato"}
        elenco([
            Voce("Assistente", info.descrizione),
            Voce("Dove gira", dove[info.in_locale]),
            Voce("Versione del prompt", info.versione_prompt),
        ], "")  # fmt: skip
        with st.form("assistente", border=False):
            esterno = st.toggle(
                "Consenti di inviare le note delle ispezioni a un servizio esterno",
                value=scelte.assistente_esterno,
                key="ai_esterno",
                help="Se lo togli e l'assistente è esterno (OpenRouter), le note non escono dal "
                "PC: il riepilogo non si genera.",
            )
            if st.form_submit_button("Salva", type="primary", key="ai_invia",
                                     icon=":material/check_circle:"):  # fmt: skip
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
        st.caption("Provider, modello e chiave si cambiano nel file `.env`, non da qui.")

    with destra, st.container(key="bw_card_modelli"):
        st.subheader("Modello di previsione")
        try:
            stato = modello()
        except BeeWatchError as errore:
            mostra_errore(errore)
        else:
            metrica("Errore medio", stato.mae_kg, "kg", aiuto="Sul 2010–2012, anni mai visti.")
            elenco([
                Voce("Versione", stato.versione),
                Voce("Algoritmo", stato.algoritmo),
                Voce("Righe di addestramento", formatta_numero(stato.righe_addestramento)),
            ], "")  # fmt: skip
            st.caption(
                f"Modello {stato.versione} ({stato.algoritmo}): in media sbaglia di "
                f"{formatta_numero(stato.mae_kg)} kg per colonia. Si cambia riaddestrandolo "
                "(`python scripts/train_model.py`), non da qui."
            )

# --------------------------------------------------------------------------- #
# Database (sola lettura)
# --------------------------------------------------------------------------- #

with scheda_database, st.container(key="bw_card_database"):
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
