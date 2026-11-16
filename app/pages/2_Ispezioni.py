"""
BeeWatch AI - pagina Ispezioni (M6-T4; aspetto del mockup, tavole 25–29).

Due viste, come nel mockup:

- **lo storico**: la tabella delle ispezioni di tutti gli alveari, dalla più recente, con ricerca,
  filtri per alveare, rischio e periodo, Esporta in CSV, pastiglia del rischio, Forza e Scorte
  (dai telaini contati), regina vista, peso e le azioni: leggere l'ispezione intera, eliminarla;
- **la nuova ispezione** a tutta pagina: alveare, data, rischio rilevato, telaini di covata e di
  scorte, regina, sciamatura, peso e le note di campo.

Le note sono la materia prima dell'assistente AI: si salvano come sono state scritte e si leggono
intere, in un campo di sola lettura che non interpreta asterischi o trattini. Del mockup mancano
operatore, temperatura, «Salva bozza» e «Compila con AI»: l'app non li ha. Modificare
un'ispezione non è previsto (si elimina e si registra di nuovo). La pagina non scrive nel database:
chiama i servizi; le regole (data non futura, intervalli, lunghezza delle note) sono nel modello.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st
from avvio import (
    CHIAVE_UTENTE,
    apiari,
    apri_finestra,
    avvia,
    chiudi_finestra,
    elenco_alveari,
    elenco_ispezioni,
    finestra_aperta,
    mostra_alveare,
    prendi_esito,
    scrittura_riuscita,
)
from schede import (
    csv_per_excel,
    icona_tonda_avviso,
    intestazione_tabella,
    mostra_pastiglia_rischio,
    pillola_data,
    testata,
)
from ui import (
    AZIONE_NESSUN_APIARIO,
    DATO_MANCANTE,
    NESSUN_APIARIO,
    blocco_vuoto,
    etichetta_rischio,
    formatta_data,
    formatta_numero,
    mostra_errore,
    sidebar,
)

from beewatch.exceptions import BeeWatchError, ValidationError
from beewatch.models import CHILI_MASSIMI, TELAINI_MASSIMI, LivelloRischio
from beewatch.services import SOGLIE_FORZA, SOGLIE_SCORTE, classifica_telaini

LIVELLI = list(LivelloRischio)
OGGI = date.today()
RIGHE_PER_PAGINA = 10
TUTTI = "Tutti"
PERIODI = {"Tutto": None, "Ultimi 30 giorni": 30, "Ultimi 90 giorni": 90, "Ultimo anno": 365}
COLONNE = [1.3, 1.2, 1.8, 1.0, 1.0, 0.9, 1.1, 1.1]
INTESTAZIONI = ("Data", "Alveare", "Stato", "Forza", "Scorte", "Regina", "Peso", "Azioni")


def problemi_ispezione(campi: dict) -> list[ValidationError]:
    """I controlli della pagina prima del servizio (le altre regole sono nel modello)."""
    if campi["data_ispezione"] is None:
        return [ValidationError("La data dell'ispezione è obbligatoria.", campo="data_ispezione")]
    return []


def si_no(valore: bool) -> str:
    return "Sì" if valore else "No"


def con_kg(valore) -> str:
    testo = formatta_numero(valore)
    return testo if testo == DATO_MANCANTE else f"{testo} kg"


def chiudi_e_ricarica() -> None:
    """Chiude la finestra o la vista e riesegue tutta la pagina (un clic in una finestra riesegue
    solo la finestra)."""
    chiudi_finestra()
    st.rerun()


# --------------------------------------------------------------------------- #
# Finestre: leggere ed eliminare un'ispezione
# --------------------------------------------------------------------------- #


@st.dialog("Ispezione", width="large", on_dismiss=chiudi_finestra)
def finestra_ispezione(ispezione) -> None:
    st.markdown(
        f"**Alveare {ispezione.codice_alveare} · {formatta_data(ispezione.data_ispezione)}**"
    )
    mostra_pastiglia_rischio(ispezione.livello_rischio)
    colonne = st.columns(3)
    colonne[0].caption(f"Peso: {con_kg(ispezione.peso_kg)}")
    colonne[1].caption(f"Telaini di covata: {formatta_numero(ispezione.telaini_covata)}")
    colonne[2].caption(f"Telaini di scorte: {formatta_numero(ispezione.telaini_scorte)}")
    colonne = st.columns(3)
    colonne[0].caption(f"Regina vista: {si_no(ispezione.regina_vista).lower()}")
    colonne[1].caption(f"Sciamatura: {si_no(ispezione.sciamatura).lower()}")
    if ispezione.note:
        # Sola lettura e testo semplice: le note si leggono come sono state scritte.
        st.text_area("Note di campo", value=ispezione.note, height=220, disabled=True,
                     key=f"note_ispezione_{ispezione.id}")  # fmt: skip
    else:
        st.caption("Nessuna nota per questa ispezione.")
    alveare, assistente = st.columns(2)
    if alveare.button("Vai all'alveare", key=f"vai_alveare_{ispezione.id}", width="stretch",
                      icon=":material/hive:"):  # fmt: skip
        chiudi_finestra()
        mostra_alveare(ispezione.alveare_id)
        st.switch_page("pages/1_Alveari.py")
    if assistente.button("Riepilogo con l'assistente", key=f"vai_ai_{ispezione.id}",
                         width="stretch", icon=":material/smart_toy:"):  # fmt: skip
        chiudi_finestra()
        st.switch_page("pages/4_Assistente_AI.py")


@st.dialog("Elimina ispezione", on_dismiss=chiudi_finestra)
def finestra_elimina_ispezione(ispezione) -> None:
    with st.container(key="bw_conferma_elimina"):
        icona_tonda_avviso()
        st.markdown(
            f"**Eliminare l'ispezione del {formatta_data(ispezione.data_ispezione)} "
            f"di {ispezione.codice_alveare}?**"
        )
        st.caption("Si cancella per sempre, con il suo eventuale riepilogo dell'assistente AI.")
        annulla, elimina = st.columns(2)
        if annulla.button("Annulla", key=f"ispezione_{ispezione.id}_annulla", width="stretch"):
            chiudi_e_ricarica()
        with elimina, st.container(key="bw_bottone_elimina"):
            premuto = st.button("Elimina", key=f"ispezione_{ispezione.id}_elimina",
                                width="stretch", icon=":material/delete:")  # fmt: skip
    if premuto:
        try:
            servizi.elimina_ispezione(utente, ispezione.id)
        except BeeWatchError as errore:
            mostra_errore(errore)
        else:
            chiudi_finestra()
            scrittura_riuscita(
                f"Ispezione del {formatta_data(ispezione.data_ispezione)} di "
                f"{ispezione.codice_alveare} eliminata."
            )


# --------------------------------------------------------------------------- #
# Vista: nuova ispezione
# --------------------------------------------------------------------------- #


def vista_nuova(alveari, preferito: int | None) -> None:
    azioni = testata("Nuova ispezione", "Inserisci i dati dell'ispezione.")
    with azioni:
        _, torna = st.columns([1.2, 1])
        if torna.button("Torna allo storico", key="ispezione_torna", icon=":material/arrow_back:",
                        width="stretch"):  # fmt: skip
            chiudi_e_ricarica()
    if not alveari:
        blocco_vuoto("Nessun alveare a cui registrare un'ispezione.",
                     "Aggiungilo nella pagina **Alveari**.")  # fmt: skip
        return
    piu_apiari = len({a.apiario for a in alveari}) > 1
    nomi = {a.id: f"{a.codice} · {a.apiario}" if piu_apiari else a.codice for a in alveari}
    with st.container(key="bw_card_nuova_ispezione"):
        st.markdown("**Dati ispezione**")
        st.caption("I campi con * sono obbligatori. Le note sono quelle che l'assistente AI "
                   "riassume: scrivi pure a lungo, non vengono tagliate.")  # fmt: skip
        with st.form("nuova_ispezione", border=False):
            sinistra, destra = st.columns(2)
            with sinistra:
                alveare_id = st.selectbox(
                    "Alveare *", options=list(nomi), format_func=nomi.__getitem__,
                    index=list(nomi).index(preferito) if preferito in nomi else 0,
                    key="ispezione_alveare",
                )  # fmt: skip
                giorno = st.date_input("Data ispezione *", value=OGGI, max_value=OGGI,
                                       format="DD/MM/YYYY", key="ispezione_data")  # fmt: skip
                rischio = st.selectbox(
                    "Stato alveare (rischio rilevato)", options=LIVELLI,
                    format_func=etichetta_rischio, key="ispezione_rischio",
                    help="Malattie, parassiti, saccheggio: quanto ti preoccupa quello che hai "
                    "visto.",
                )  # fmt: skip
                covata = st.number_input(
                    "Forza: telaini di covata", min_value=0, max_value=TELAINI_MASSIMI,
                    value=None, step=1, key="ispezione_covata",
                    help="Diventa «Forza» nelle tabelle: Alta da 6, Media da 3, Bassa sotto.",
                )  # fmt: skip
            with destra:
                scorte = st.number_input(
                    "Scorte di miele: telaini di scorte", min_value=0,
                    max_value=TELAINI_MASSIMI, value=None, step=1, key="ispezione_scorte",
                    help="Diventa «Scorte» nelle tabelle: Buone da 4, Medie da 2, Scarse sotto.",
                )  # fmt: skip
                regina = st.selectbox("Presenza regina", ["No", "Sì"], key="ispezione_regina",
                                      help="Hai visto la regina?")  # fmt: skip
                sciamatura = st.selectbox("Sciamatura in corso", ["No", "Sì"],
                                          key="ispezione_sciamatura")  # fmt: skip
                peso = st.number_input(
                    "Peso dell'arnia (kg)", min_value=0.0, max_value=float(CHILI_MASSIMI),
                    value=None, step=0.1, format="%.2f", key="ispezione_peso",
                )  # fmt: skip
            note = st.text_area(
                "Note", height=160, key="ispezione_note",
                placeholder="Cosa hai visto: covata, scorte, comportamento, segni di malattie o "
                "parassiti, interventi fatti.",
            )  # fmt: skip
            _, annulla, salva = st.columns([3, 1, 1.4])
            annullato = annulla.form_submit_button("Annulla", key="ispezione_annulla",
                                                   width="stretch")  # fmt: skip
            premuto = salva.form_submit_button(
                "Salva ispezione", type="primary", key="nuova_ispezione_invia",
                icon=":material/check_circle:", width="stretch",
            )  # fmt: skip
    if annullato:
        chiudi_e_ricarica()
    if premuto:
        campi = {"alveare_id": alveare_id, "data_ispezione": giorno, "livello_rischio": rischio,
                 "peso_kg": None if peso is None else round(peso, 2),
                 "telaini_covata": covata, "telaini_scorte": scorte,
                 "regina_vista": regina == "Sì", "sciamatura": sciamatura == "Sì",
                 "note": note}  # fmt: skip
        if problemi := problemi_ispezione(campi):
            for problema in problemi:
                mostra_errore(problema)
            return
        try:
            servizi.registra_ispezione(utente, **campi)
        except BeeWatchError as errore:
            mostra_errore(errore)
        else:
            chiudi_finestra()
            scrittura_riuscita(
                f"Ispezione di **{nomi[alveare_id]}** del {formatta_data(giorno)} registrata."
            )


# --------------------------------------------------------------------------- #
# Vista: lo storico
# --------------------------------------------------------------------------- #


def vista_storico(ispezioni, alveari) -> None:
    azioni = testata("Ispezioni", "Storico completo delle ispezioni effettuate sui tuoi alveari.")
    with azioni:
        data, nuova = st.columns([3, 2], vertical_alignment="center")
        with data:
            pillola_data(OGGI)
        nuova.button(
            "Nuova ispezione", type="primary", key="apri_nuova_ispezione", icon=":material/add:",
            on_click=apri_finestra, args=("nuova_ispezione",), disabled=not alveari,
            help=None if alveari else "Prima serve un alveare: aggiungilo nella pagina Alveari.",
        )  # fmt: skip
    if esito:
        st.success(esito, icon="✅")
    if not alveari:
        if not apiari_utente:
            blocco_vuoto(NESSUN_APIARIO, AZIONE_NESSUN_APIARIO)
        else:
            blocco_vuoto("Nessun alveare registrato.", "Aggiungilo nella pagina **Alveari**.")
        return
    if not ispezioni:
        blocco_vuoto("Ancora nessuna ispezione registrata.",
                     "Registra la prima con **Nuova ispezione**, qui sopra.")  # fmt: skip
        return

    with st.container(key="bw_card_ispezioni"):
        cerca, alveare, rischio, periodo, _, esporta = st.columns([2.6, 1.6, 1.6, 1.8, 0.2, 1.1])
        testo = cerca.text_input(
            "Cerca", key="ispezioni_cerca", placeholder="Cerca ispezione...",
            label_visibility="collapsed", icon=":material/search:",
        )  # fmt: skip
        codici = sorted({i.codice_alveare for i in ispezioni})
        filtro_alveare = alveare.selectbox(
            "Alveare", [TUTTI, *codici], key="ispezioni_filtro_alveare",
            label_visibility="collapsed", format_func=lambda c: f"Alveare: {c}",
        )  # fmt: skip
        filtro_rischio = rischio.selectbox(
            "Stato", [TUTTI, *LIVELLI], key="ispezioni_filtro_rischio",
            label_visibility="collapsed",
            format_func=lambda r: "Stato: Tutti" if r == TUTTI else etichetta_rischio(r),
        )  # fmt: skip
        with periodo, st.container(key="bw_periodo"):
            scelto = st.selectbox("Periodo", list(PERIODI), key="ispezioni_periodo",
                                  label_visibility="collapsed")  # fmt: skip
        giorni = PERIODI[scelto]
        cercato = testo.strip().lower()
        scelte = [
            i for i in ispezioni
            if (not cercato or cercato in (i.note or "").lower()
                or cercato in i.codice_alveare.lower())
            and (filtro_alveare == TUTTI or i.codice_alveare == filtro_alveare)
            and (filtro_rischio == TUTTI or i.livello_rischio == filtro_rischio)
            and (giorni is None or i.data_ispezione >= OGGI - timedelta(days=giorni))
        ]  # fmt: skip
        esporta.download_button(
            "Esporta", data=csv_ispezioni(scelte), file_name="ispezioni.csv", mime="text/csv",
            key="ispezioni_esporta", icon=":material/download:", width="stretch",
        )  # fmt: skip

        pagine = max(1, -(-len(scelte) // RIGHE_PER_PAGINA))
        pagina = min(st.session_state.get("ispezioni_pagina") or 1, pagine)
        mostrate = scelte[(pagina - 1) * RIGHE_PER_PAGINA : pagina * RIGHE_PER_PAGINA]

        intestazione_tabella(INTESTAZIONI, COLONNE)
        if not mostrate:
            st.caption("Nessuna ispezione corrisponde alla ricerca o ai filtri.")
        for ispezione in mostrate:
            with st.container(key=f"bw_riga_{ispezione.id}"):
                celle = st.columns(COLONNE, vertical_alignment="center")
                celle[0].markdown(f"**{formatta_data(ispezione.data_ispezione)}**")
                celle[1].write(ispezione.codice_alveare)
                with celle[2]:
                    mostra_pastiglia_rischio(ispezione.livello_rischio)
                celle[3].write(classifica_telaini(ispezione.telaini_covata, SOGLIE_FORZA) or "—")
                celle[4].write(classifica_telaini(ispezione.telaini_scorte, SOGLIE_SCORTE)
                               or "—")  # fmt: skip
                celle[5].write(si_no(ispezione.regina_vista))
                celle[6].write(con_kg(ispezione.peso_kg))
                with celle[7]:
                    vedi, elimina = st.columns(2)
                    vedi.button("", key=f"vedi_ispezione_{ispezione.id}",
                                icon=":material/visibility:", type="tertiary",
                                help="Leggi l'ispezione intera", on_click=apri_finestra,
                                args=("ispezione", ispezione.id))  # fmt: skip
                    with elimina, st.container(key=f"bw_cestino_{ispezione.id}"):
                        st.button("", key=f"elimina_ispezione_{ispezione.id}",
                                  icon=":material/delete:", type="tertiary",
                                  help="Elimina l'ispezione", on_click=apri_finestra,
                                  args=("elimina_ispezione", ispezione.id))  # fmt: skip

        piede, numeri = st.columns([2, 1], vertical_alignment="center")
        piede.caption(f"Mostrando {len(mostrate)} di {len(scelte)} ispezioni")
        if pagine > 1:
            with numeri, st.container(key="bw_pagine"):
                st.segmented_control("Pagina", list(range(1, pagine + 1)), default=pagina,
                                     key="ispezioni_pagina",
                                     label_visibility="collapsed")  # fmt: skip

    st.caption(
        "Forza e scorte dai telaini contati in quell'ispezione (arnia da 10): forza Alta da 6 "
        "telaini di covata, Media da 3; scorte Buone da 4 telaini, Medie da 2. «—» se non sono "
        "stati contati. La ricerca guarda il codice dell'alveare e le note."
    )


def csv_ispezioni(ispezioni) -> bytes:
    """Le ispezioni filtrate, in CSV per Excel in italiano, con le note intere."""
    return csv_per_excel(
        pd.DataFrame(
            [
                {
                    "Data": formatta_data(i.data_ispezione),
                    "Alveare": i.codice_alveare,
                    "Rischio": etichetta_rischio(i.livello_rischio),
                    "Peso (kg)": i.peso_kg,
                    "Telaini di covata": i.telaini_covata,
                    "Telaini di scorte": i.telaini_scorte,
                    "Regina vista": si_no(i.regina_vista),
                    "Sciamatura": si_no(i.sciamatura),
                    "Note": i.note or "",
                }
                for i in ispezioni
            ]  # fmt: skip
        )
    )


# --------------------------------------------------------------------------- #
# Pagina
# --------------------------------------------------------------------------- #

servizi = avvia("Ispezioni", "📋")
sidebar()
utente = st.session_state[CHIAVE_UTENTE]
esito = prendi_esito()

try:
    apiari_utente = apiari(utente)
    alveari = elenco_alveari(utente)
    ispezioni = elenco_ispezioni(utente)
except BeeWatchError as errore:
    testata("Ispezioni", "Storico completo delle ispezioni effettuate sui tuoi alveari.")
    mostra_errore(errore)
    st.stop()

per_id = {i.id: i for i in ispezioni}
nuova = finestra_aperta("nuova_ispezione")
if nuova is not False:
    vista_nuova(alveari, None if nuova is True else nuova)
else:
    vista_storico(ispezioni, alveari)
    if (scelta := finestra_aperta("ispezione")) in per_id:
        finestra_ispezione(per_id[scelta])
    elif (scelta := finestra_aperta("elimina_ispezione")) in per_id:
        finestra_elimina_ispezione(per_id[scelta])
