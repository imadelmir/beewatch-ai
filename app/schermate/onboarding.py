"""
BeeWatch AI - Primi passi dopo la registrazione (M6-T11; aspetto del mockup).

Come nel mockup: una card al centro, con i tre passi numerati. Il primo, **Profilo**, è la
registrazione appena fatta; poi:

1. **Primo alveare**: codice, apiario, stato e anno della regina. Se l'apiario non c'è ancora
   (non è stato scritto alla registrazione), qui se ne dà il nome;
2. **Preferenze**: promemoria, avvisi e consenso all'assistente esterno, le stesse delle
   Impostazioni.

Del mockup mancano tipo d'arnia, numero di telaini e «Bilancia IoT / Sensori meteo»: l'app non li
registra, e un campo che non si salva inganna. Ogni passo si può saltare: l'app funziona anche
vuota. La pagina non scrive nel database: chiama i servizi, gli stessi di Alveari e Impostazioni.
"""

from __future__ import annotations

import streamlit as st
from avvio import (
    CHIAVE_UTENTE,
    PASSI_ONBOARDING,
    apiari,
    avanza_onboarding,
    avvia,
    imposta_apiario_attivo,
    indietro_onboarding,
    passo_onboarding,
    svuota_letture,
    termina_onboarding,
)
from ui import logo_centrato, mostra_errore, passi_numerati, stile_stato, titolo_modulo

from beewatch.exceptions import BeeWatchError, ValidationError
from beewatch.models import StatoAlveare
from beewatch.services import GIORNI_PROMEMORIA, Preferenze

servizi = avvia("Primi passi", "🧭")
utente = st.session_state[CHIAVE_UTENTE]
passo = passo_onboarding() or PASSI_ONBOARDING
TOTALE = PASSI_ONBOARDING + 1  # più il profilo, già fatto

logo_centrato()

with st.container(key="bw_onboarding"):
    passi_numerati(passo + 1)

    if passo == 1:
        titolo_modulo(
            "Aggiungi il tuo primo alveare",
            "Potrai aggiungerne altri in qualsiasi momento dalla sezione Alveari.",
        )
        try:
            elenco = apiari(utente)
        except BeeWatchError as errore:
            mostra_errore(errore)
            elenco = ()
        nomi = {a.id: a.nome for a in elenco}
        stati = list(StatoAlveare)
        with st.form("onboarding_alveare"):
            colonne = st.columns(2)
            codice = colonne[0].text_input(
                "Codice dell'alveare *", max_chars=20, key="onboarding_codice", placeholder="A01"
            )
            if nomi:
                apiario_id = colonne[1].selectbox(
                    "Apiario", options=list(nomi), format_func=nomi.__getitem__,
                    key="onboarding_apiario",
                )  # fmt: skip
                nome_apiario = localita = ""
            else:
                apiario_id = None
                nome_apiario = colonne[1].text_input(
                    "Nome dell'apiario *", max_chars=120, key="onboarding_nome",
                    placeholder="Es. Colline Sud",
                )  # fmt: skip
            colonne = st.columns(2)
            stato = colonne[0].selectbox(
                "Stato", options=stati, format_func=lambda s: stile_stato(s)[0],
                key="onboarding_stato",
            )  # fmt: skip
            regina = colonne[1].number_input(
                "Anno della regina", min_value=1990, max_value=2100, value=None, step=1,
                key="onboarding_regina", placeholder="Facoltativo",
            )  # fmt: skip
            if not nomi:
                localita = st.text_input(
                    "Località dell'apiario", max_chars=160, key="onboarding_localita"
                )
            piede, _, indietro, avanti = st.columns([3, 2, 2, 2], vertical_alignment="center")
            piede.caption(f"Passo {passo + 1} di {TOTALE}")
            indietro.form_submit_button(
                "Indietro", key="onboarding_indietro_1", disabled=True, width="stretch"
            )
            premuto = avanti.form_submit_button(
                "Continua", type="primary", key="onboarding_alveare_invia",
                icon=":material/arrow_forward:", width="stretch",
            )  # fmt: skip
        if premuto:
            if not codice.strip():
                mostra_errore(
                    ValidationError("Il codice dell'alveare è obbligatorio.", campo="codice")
                )
            elif not nomi and not nome_apiario.strip():
                mostra_errore(ValidationError("Il nome dell'apiario è obbligatorio.", campo="nome"))
            else:
                try:
                    if apiario_id is None:
                        apiario_id = servizi.crea_apiario(
                            utente, nome=nome_apiario, localita=localita
                        ).id
                        imposta_apiario_attivo(apiario_id)
                        svuota_letture()  # se l'alveare fallisce, l'apiario c'è già
                    servizi.crea_alveare(
                        utente, apiario_id=apiario_id, codice=codice, stato=stato,
                        anno_regina=regina,
                    )  # fmt: skip
                except BeeWatchError as errore:
                    mostra_errore(errore)
                else:
                    imposta_apiario_attivo(apiario_id)
                    svuota_letture()
                    avanza_onboarding()

    else:
        titolo_modulo(
            "Le tue preferenze",
            "Si cambiano quando vuoi dalle Impostazioni.",
        )
        attuali = Preferenze()
        minimo, massimo = GIORNI_PROMEMORIA
        with st.form("onboarding_preferenze"):
            giorni = st.slider(
                "Un alveare va ricontrollato dopo quanti giorni senza ispezione?",
                min_value=minimo, max_value=massimo, value=attuali.giorni_promemoria,
                key="onboarding_giorni",
            )  # fmt: skip
            avvisi = st.toggle(
                "Avvisami delle ispezioni recenti con rischio medio o alto",
                value=attuali.avvisi_rischio, key="onboarding_avvisi",
            )  # fmt: skip
            esterno = st.toggle(
                "Consenti di inviare le note delle ispezioni a un assistente AI esterno",
                value=attuali.assistente_esterno, key="onboarding_esterno",
                help="Conta solo se l'assistente è un servizio esterno (OpenRouter): con Ollama "
                "le note restano comunque su questo computer.",
            )  # fmt: skip
            piede, _, indietro, avanti = st.columns([3, 2, 2, 2], vertical_alignment="center")
            piede.caption(f"Passo {passo + 1} di {TOTALE}")
            torna = indietro.form_submit_button(
                "Indietro", key="onboarding_indietro", width="stretch"
            )
            premuto = avanti.form_submit_button(
                "Inizia", type="primary", key="onboarding_fine",
                icon=":material/arrow_forward:", width="stretch",
            )  # fmt: skip
        if torna:
            indietro_onboarding()
        if premuto:
            try:
                servizi.salva_preferenze(
                    utente, giorni_promemoria=giorni, avvisi_rischio=avvisi,
                    assistente_esterno=esterno,
                )  # fmt: skip
            except BeeWatchError as errore:
                mostra_errore(errore)
            else:
                svuota_letture()
                termina_onboarding()

with st.container(key="bw_salta"):
    if st.button("Salta configurazione", key="onboarding_salta", type="tertiary"):
        termina_onboarding()
