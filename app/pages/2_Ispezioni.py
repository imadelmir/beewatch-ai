"""
BeeWatch AI - pagina Ispezioni: il registro delle visite all'arnia (M6-T4).

L'anatomia del §6 della specifica:

- **controlli**: il modulo «Registra un'ispezione» (campi strutturati e note libere) e i filtri
  dello storico (alveare, intervallo di date);
- **contenuto**: tre metriche, la tabella dello storico dalla più recente e la scheda di una
  ispezione, con le note complete e il collegamento all'alveare;
- **note** in fondo.

Le note sono la materia prima dell'assistente AI (M6-T6): si salvano come sono state scritte, senza
tagli, e si rileggono in un campo di sola lettura, che non interpreta asterischi o trattini come
formattazione. La pagina non scrive nel database: controlla i campi che vede (alveare e data
obbligatori) e chiama i servizi; le altre regole (data non futura, intervalli, lunghezza delle
note) stanno nel modello `Ispezione` e arrivano con `mostra_errore` e il nome del campo.
"""

from __future__ import annotations

from datetime import date

import streamlit as st
from avvio import (
    CHIAVE_UTENTE,
    alveari_dell_apiario,
    apiari,
    avvia,
    ispezioni_dell_apiario,
    prendi_esito,
    scrittura_riuscita,
)
from ui import (
    AZIONE_NESSUN_APIARIO,
    DATO_MANCANTE,
    NESSUN_APIARIO,
    badge_stato,
    blocco_vuoto,
    etichetta_rischio,
    formatta_data,
    formatta_numero,
    intestazione,
    metrica,
    mostra_errore,
    sidebar,
)

from beewatch.exceptions import BeeWatchError, ValidationError
from beewatch.models import CHILI_MASSIMI, TELAINI_MASSIMI, LivelloRischio

LIVELLI = list(LivelloRischio)
RISCHIO_DA_SEGNALARE = {LivelloRischio.MEDIO, LivelloRischio.ALTO}
TUTTI = 0  # nel filtro: nessun alveare scelto
ANTEPRIMA_NOTE = 80  # caratteri delle note mostrati nella tabella
OGGI = date.today()


def problemi_ispezione(campi: dict) -> list[ValidationError]:
    """I controlli della pagina prima del servizio (le altre regole sono nel modello)."""
    if campi["data_ispezione"] is None:
        return [ValidationError("La data dell'ispezione è obbligatoria.", campo="data_ispezione")]
    return []


def campi_ispezione(codici: dict[int, str], preferito: int | None) -> dict:
    """I campi di una nuova ispezione dentro il form; `preferito` è l'alveare proposto."""
    alveari = list(codici)
    campi = {}
    colonne = st.columns(3)
    campi["alveare_id"] = colonne[0].selectbox(
        "Alveare *",
        options=alveari,
        index=alveari.index(preferito) if preferito in codici else 0,
        format_func=codici.__getitem__,
        # Streamlit ricorda il valore per chiave e ignorerebbe il nuovo `index`: con la chiave
        # legata al filtro, cambiare il filtro cambia anche l'alveare proposto.
        key=f"ispezione_alveare_{preferito or 'tutti'}",
    )
    campi["data_ispezione"] = colonne[1].date_input(
        "Data *", value=OGGI, max_value=OGGI, format="DD/MM/YYYY", key="ispezione_data"
    )
    campi["livello_rischio"] = colonne[2].selectbox(
        "Rischio rilevato",
        options=LIVELLI,
        format_func=etichetta_rischio,
        key="ispezione_rischio",
        help="Malattie, parassiti, saccheggio: quanto ti preoccupa quello che hai visto.",
    )
    colonne = st.columns(3)
    peso = colonne[0].number_input(
        "Peso dell'arnia (kg)",
        min_value=0.0,
        max_value=float(CHILI_MASSIMI),
        value=None,
        step=0.1,
        format="%.2f",
        key="ispezione_peso",
    )
    campi["peso_kg"] = None if peso is None else round(peso, 2)
    campi["telaini_covata"] = colonne[1].number_input(
        "Telaini di covata",
        min_value=0,
        max_value=TELAINI_MASSIMI,
        value=None,
        step=1,
        key="ispezione_covata",
    )
    campi["telaini_scorte"] = colonne[2].number_input(
        "Telaini di scorte",
        min_value=0,
        max_value=TELAINI_MASSIMI,
        value=None,
        step=1,
        key="ispezione_scorte",
    )
    colonne = st.columns(3)
    campi["regina_vista"] = colonne[0].checkbox("Regina vista", key="ispezione_regina")
    campi["sciamatura"] = colonne[1].checkbox("Sciamatura in corso", key="ispezione_sciamatura")
    campi["note"] = st.text_area(
        "Note di campo",
        height=200,
        key="ispezione_note",
        placeholder="Cosa hai visto: covata, scorte, comportamento, segni di malattie o "
        "parassiti, interventi fatti. Scrivi pure a lungo: le note non vengono tagliate.",
        help="L'assistente AI ne ricava un riepilogo strutturato (pagina Assistente AI).",
    )
    return campi


def si_no(valore: bool) -> str:
    return "sì" if valore else "no"


def anteprima(note: str | None) -> str:
    if not note:
        return ""
    riga = " ".join(note.split())
    return riga if len(riga) <= ANTEPRIMA_NOTE else riga[: ANTEPRIMA_NOTE - 1] + "…"


def riga_tabella(ispezione) -> dict:
    return {
        "Data": formatta_data(ispezione.data_ispezione),
        "Alveare": ispezione.codice_alveare,
        "Rischio": etichetta_rischio(ispezione.livello_rischio),
        "Peso (kg)": formatta_numero(ispezione.peso_kg),
        "Covata": formatta_numero(ispezione.telaini_covata),
        "Scorte": formatta_numero(ispezione.telaini_scorte),
        "Regina vista": si_no(ispezione.regina_vista),
        "Sciamatura": si_no(ispezione.sciamatura),
        "Note": anteprima(ispezione.note),
    }


def titolo_ispezione(ispezione) -> str:
    return (
        f"{formatta_data(ispezione.data_ispezione)} · {ispezione.codice_alveare} · "
        f"{etichetta_rischio(ispezione.livello_rischio)}"
    )


def scheda_ispezione(ispezione, alveare) -> None:
    """Tutta l'ispezione: l'alveare a cui si riferisce, i campi e le note complete."""
    with st.container(border=True):
        sinistra, destra = st.columns([2, 3])
        with sinistra:
            st.markdown(f"**Alveare {ispezione.codice_alveare}**")
            badge_stato(alveare.stato if alveare else None)
            st.page_link(
                "pages/1_Alveari.py", label="Vai all'alveare nella pagina Alveari", icon="🏠"
            )
        with destra:
            st.markdown(f"**Ispezione del {formatta_data(ispezione.data_ispezione)}**")
            peso = formatta_numero(ispezione.peso_kg)
            st.caption(
                f"{etichetta_rischio(ispezione.livello_rischio)} · "
                f"peso: {peso if peso == DATO_MANCANTE else peso + ' kg'} · "
                f"telaini di covata: {formatta_numero(ispezione.telaini_covata)} · "
                f"telaini di scorte: {formatta_numero(ispezione.telaini_scorte)} · "
                f"regina vista: {si_no(ispezione.regina_vista)} · "
                f"sciamatura: {si_no(ispezione.sciamatura)}"
            )
        if ispezione.note:
            # Sola lettura e testo semplice: le note si leggono come sono state scritte.
            st.text_area(
                "Note di campo",
                value=ispezione.note,
                height=220,
                disabled=True,
                key=f"note_ispezione_{ispezione.id}",
            )
        else:
            st.caption("Nessuna nota per questa ispezione.")


# --------------------------------------------------------------------------- #
# Pagina
# --------------------------------------------------------------------------- #

servizi = avvia("Ispezioni", "📋")
attivo = sidebar()
utente = st.session_state[CHIAVE_UTENTE]

intestazione(
    "📋 Ispezioni",
    "Il registro delle visite all'arnia: covata, scorte, regina, rischio e note di campo.",
)

esito = prendi_esito()
if esito:
    st.success(esito, icon="✅")

try:
    # La sidebar non solleva: se il database non risponde, è il corpo della pagina a dirlo
    # (altrimenti l'utente leggerebbe «nessun apiario» invece di «database non raggiungibile»).
    apiari(utente)
    alveari = alveari_dell_apiario(utente, attivo.id) if attivo else ()
except BeeWatchError as errore:
    mostra_errore(errore)
    st.stop()

if attivo is None:
    blocco_vuoto(NESSUN_APIARIO, AZIONE_NESSUN_APIARIO)
    st.stop()

if not alveari:
    blocco_vuoto(
        f"Nessun alveare in {attivo.nome}.",
        "Vai su **Alveari** per aggiungerne uno: le ispezioni si registrano alveare per alveare.",
    )
    st.stop()

codici = {a.id: a.codice for a in alveari}
alveari_per_id = {a.id: a for a in alveari}

# --------------------------------------------------------------------------- #
# Controlli: filtri dello storico e nuova ispezione
# --------------------------------------------------------------------------- #

st.subheader(f"Ispezioni di {attivo.nome}")

filtri = st.columns(3)
scelto = filtri[0].selectbox(
    "Alveare",
    options=[TUTTI, *codici],
    format_func={TUTTI: "Tutti gli alveari", **codici}.__getitem__,
    key="filtro_alveare",
)
dal = filtri[1].date_input("Dal", value=None, max_value=OGGI, format="DD/MM/YYYY", key="filtro_dal")
al = filtri[2].date_input("Al", value=None, max_value=OGGI, format="DD/MM/YYYY", key="filtro_al")
alveare_filtro = None if scelto == TUTTI else scelto

with st.expander("➕ Registra un'ispezione"):
    with st.form("nuova_ispezione"):
        campi = campi_ispezione(codici, alveare_filtro)
        if st.form_submit_button(
            "Registra l'ispezione", type="primary", key="nuova_ispezione_invia"
        ):
            if problemi := problemi_ispezione(campi):
                for problema in problemi:
                    mostra_errore(problema)
            else:
                try:
                    nuova = servizi.registra_ispezione(utente, **campi)
                except BeeWatchError as errore:
                    mostra_errore(errore)
                else:
                    scrittura_riuscita(
                        f"Ispezione di **{codici[nuova.alveare_id]}** del "
                        f"{formatta_data(nuova.data_ispezione)} registrata."
                    )

# --------------------------------------------------------------------------- #
# Contenuto: metriche, storico, scheda di un'ispezione
# --------------------------------------------------------------------------- #

try:
    storico = ispezioni_dell_apiario(utente, attivo.id, alveare_filtro, dal, al)
except BeeWatchError as errore:
    mostra_errore(errore)
    storico = None

if storico is not None:
    colonne = st.columns(4)
    with colonne[0]:
        metrica("Ispezioni mostrate", len(storico), None, aiuto="Quelle che passano i filtri.")
    with colonne[1]:
        metrica(
            "Con rischio medio o alto",
            sum(i.livello_rischio in RISCHIO_DA_SEGNALARE for i in storico),
            None,
            aiuto="Le visite in cui hai segnalato un rischio medio o alto.",
        )
    with colonne[2]:
        metrica(
            "Ultima ispezione",
            storico[0].data_ispezione if storico else None,
            None,
        )

    filtrato = alveare_filtro is not None or dal is not None or al is not None
    if not storico and filtrato:
        blocco_vuoto(
            "Nessuna ispezione con questi filtri.",
            "Allarga l'intervallo di date o scegli **Tutti gli alveari**.",
        )
    elif not storico:
        blocco_vuoto(
            f"Nessuna ispezione registrata in {attivo.nome}.",
            "Registra la prima con il modulo **Registra un'ispezione** qui sopra.",
        )
    else:
        st.dataframe([riga_tabella(i) for i in storico], hide_index=True, width="stretch")

        per_id = {i.id: i for i in storico}
        letta = per_id[
            st.selectbox(
                "Leggi un'ispezione",
                options=list(per_id),
                format_func={i.id: titolo_ispezione(i) for i in storico}.__getitem__,
                # La chiave cambia con l'elenco: dopo un salvataggio o un filtro il selettore
                # riparte dalla più recente. Con una chiave fissa il browser mostrava ancora
                # l'etichetta vecchia mentre la scheda era già quella nuova.
                key=f"ispezione_da_leggere_{hash(tuple(per_id)) & 0xFFFFFFFF:x}",
            )
        ]
        scheda_ispezione(letta, alveari_per_id.get(letta.alveare_id))

# --------------------------------------------------------------------------- #
# Note
# --------------------------------------------------------------------------- #

st.caption(
    "Lo storico comprende gli alveari attivi dell'apiario scelto nella sidebar, dalla visita più "
    "recente. Le date si fermano a oggi: un'ispezione nel futuro non si registra. Le note si "
    "salvano per intero, accenti compresi; la tabella ne mostra solo l'inizio, la scheda tutto."
)
