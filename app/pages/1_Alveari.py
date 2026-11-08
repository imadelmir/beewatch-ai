"""
BeeWatch AI - pagina Alveari: l'anagrafica di apiari e alveari (M6-T3).

Due schede, ognuna con l'anatomia del §6 della specifica: prima i controlli (aggiungere,
modificare, eliminare), poi il contenuto (l'elenco), in fondo le note.

- **Alveari**: le arnie dell'apiario attivo (scelto nella sidebar), con lo stato come pastiglia
  (`badge_stato`) e l'ultima ispezione;
- **Apiari**: i luoghi, con località e coordinate.

La pagina non scrive nel database: raccoglie i campi, li controlla (campi obbligatori, coppie di
coordinate) e chiama i servizi. Le regole vere (lunghezze, intervalli, nomi e codici già usati)
stanno nei modelli e nei repository: se un valore passa i controlli della pagina ma non quelli,
`mostra_errore` dice quale campo correggere. Dopo ogni scrittura riuscita la pagina si riesegue
con i dati nuovi e mostra l'esito (`scrittura_riuscita`). Eliminare chiede una conferma esplicita
ed è una cancellazione logica: lo storico resta.
"""

from __future__ import annotations

from datetime import date

import streamlit as st
from avvio import (
    CHIAVE_UTENTE,
    alveari_dell_apiario,
    apiari_in_anagrafica,
    avvia,
    imposta_apiario_attivo,
    prendi_esito,
    scrittura_riuscita,
)
from ui import (
    NESSUN_APIARIO,
    badge_stato,
    blocco_vuoto,
    formatta_data,
    formatta_numero,
    intestazione,
    metrica,
    mostra_errore,
    sidebar,
    stile_stato,
)

from beewatch.exceptions import BeeWatchError, ValidationError
from beewatch.models import ANNO_REGINA_MINIMO, StatoAlveare

STATI = list(StatoAlveare)
OGGI = date.today()


def etichetta_stato(stato: StatoAlveare) -> str:
    return stile_stato(stato)[0]


def coordinata(valore: float | None) -> float | None:
    """Sei decimali, quanti ne tiene il database: il widget restituisce un float approssimato."""
    return None if valore is None else round(valore, 6)


def problemi_apiario(campi: dict) -> list[ValidationError]:
    """I controlli della pagina prima del servizio (le altre regole sono nel modello)."""
    problemi = []
    if not campi["nome"].strip():
        problemi.append(ValidationError("Il nome dell'apiario è obbligatorio.", campo="nome"))
    if (campi["latitudine"] is None) != (campi["longitudine"] is None):
        problemi.append(
            ValidationError(
                "Le coordinate vanno date in coppia: latitudine e longitudine, o nessuna.",
                campo="latitudine" if campi["latitudine"] is None else "longitudine",
            )
        )
    return problemi


def problemi_alveare(campi: dict) -> list[ValidationError]:
    if campi["codice"].strip():
        return []
    return [ValidationError("Il codice dell'alveare è obbligatorio.", campo="codice")]


def campi_apiario(chiave: str, apiario=None) -> dict:
    """I campi di un apiario dentro un form; `apiario` dà i valori di partenza (modifica)."""
    nome = st.text_input(
        "Nome *", value=apiario.nome if apiario else "", max_chars=120, key=f"{chiave}_nome"
    )
    localita = st.text_input(
        "Località",
        value=(apiario.localita or "") if apiario else "",
        max_chars=160,
        key=f"{chiave}_localita",
    )
    colonne = st.columns(2)
    latitudine = colonne[0].number_input(
        "Latitudine",
        min_value=-90.0,
        max_value=90.0,
        value=float(apiario.latitudine) if apiario and apiario.latitudine is not None else None,
        format="%.6f",
        step=0.000001,
        key=f"{chiave}_latitudine",
        help="Facoltativa, in gradi decimali (es. 45.710000).",
    )
    longitudine = colonne[1].number_input(
        "Longitudine",
        min_value=-180.0,
        max_value=180.0,
        value=float(apiario.longitudine) if apiario and apiario.longitudine is not None else None,
        format="%.6f",
        step=0.000001,
        key=f"{chiave}_longitudine",
    )
    note = st.text_area("Note", value=(apiario.note or "") if apiario else "", key=f"{chiave}_note")
    return {
        "nome": nome,
        "localita": localita,
        "latitudine": coordinata(latitudine),
        "longitudine": coordinata(longitudine),
        "note": note,
    }


def campi_alveare(chiave: str, alveare=None, apiari=()) -> dict:
    """I campi di un alveare dentro un form; con `apiari` si può anche spostarlo di apiario."""
    campi = {}
    if apiari:
        nomi = {a.id: a.nome for a in apiari}
        campi["apiario_id"] = st.selectbox(
            "Apiario",
            options=list(nomi),
            index=list(nomi).index(alveare.apiario_id),
            format_func=nomi.__getitem__,
            key=f"{chiave}_apiario",
        )
    campi["codice"] = st.text_input(
        "Codice *",
        value=alveare.codice if alveare else "",
        max_chars=20,
        key=f"{chiave}_codice",
        help="Unico dentro l'apiario, per esempio A1.",
    )
    campi["stato"] = st.selectbox(
        "Stato",
        options=STATI,
        index=STATI.index(alveare.stato) if alveare else 0,
        format_func=etichetta_stato,
        key=f"{chiave}_stato",
    )
    colonne = st.columns(2)
    campi["data_installazione"] = colonne[0].date_input(
        "Installato il",
        value=alveare.data_installazione if alveare else None,
        max_value=OGGI,
        format="DD/MM/YYYY",
        key=f"{chiave}_installazione",
    )
    campi["anno_regina"] = colonne[1].number_input(
        "Anno della regina",
        min_value=ANNO_REGINA_MINIMO,
        max_value=OGGI.year,
        value=alveare.anno_regina if alveare else None,
        step=1,
        key=f"{chiave}_regina",
    )
    campi["note"] = st.text_area(
        "Note", value=(alveare.note or "") if alveare else "", key=f"{chiave}_note"
    )
    return campi


def mostra_problemi(problemi: list[ValidationError]) -> None:
    for problema in problemi:
        mostra_errore(problema)


def conferma_eliminazione(chiave: str, domanda: str, bottone: str) -> bool:
    """Una casella da spuntare e un bottone che senza la spunta non si preme."""
    confermato = st.checkbox(domanda, key=f"{chiave}_conferma")
    premuto = st.button(bottone, disabled=not confermato, type="primary", key=f"{chiave}_elimina")
    # La spunta si ricontrolla qui: un bottone disabilitato non va preso come garanzia.
    return confermato and premuto


# --------------------------------------------------------------------------- #
# Pagina
# --------------------------------------------------------------------------- #

servizi = avvia("Alveari", "🏠")
attivo = sidebar()
utente = st.session_state[CHIAVE_UTENTE]

intestazione(
    "🏠 Alveari",
    "L'anagrafica dei tuoi apiari e delle loro arnie: codice, stato di salute, regina, "
    "ultima ispezione.",
)

esito = prendi_esito()
if esito:
    st.success(esito, icon="✅")

try:
    apiari = apiari_in_anagrafica(utente)
except BeeWatchError as errore:
    mostra_errore(errore)
    st.stop()

scheda_alveari, scheda_apiari = st.tabs(["Alveari", "Apiari"])

# --------------------------------------------------------------------------- #
# Scheda Alveari
# --------------------------------------------------------------------------- #

with scheda_alveari:
    if attivo is None:
        blocco_vuoto(NESSUN_APIARIO, "Crealo nella scheda **Apiari**, qui accanto.")
    else:
        try:
            alveari = alveari_dell_apiario(utente, attivo.id)
        except BeeWatchError as errore:
            mostra_errore(errore)
            alveari = None

        if alveari is not None:
            st.subheader(f"Alveari di {attivo.nome}")

            # Controlli
            with st.expander("➕ Aggiungi un alveare", expanded=not alveari):
                with st.form("nuovo_alveare", clear_on_submit=False):
                    campi = campi_alveare("nuovo_alveare")
                    if st.form_submit_button(
                        "Aggiungi l'alveare", type="primary", key="nuovo_alveare_invia"
                    ):
                        if problemi := problemi_alveare(campi):
                            mostra_problemi(problemi)
                        else:
                            try:
                                nuovo = servizi.crea_alveare(utente, apiario_id=attivo.id, **campi)
                            except BeeWatchError as errore:
                                mostra_errore(errore)
                            else:
                                scrittura_riuscita(
                                    f"Alveare **{nuovo.codice}** aggiunto a {attivo.nome}."
                                )

            if alveari:
                with st.expander("✏️ Modifica o elimina un alveare"):
                    alveari_per_id = {a.id: a for a in alveari}
                    scelto = alveari_per_id[
                        st.selectbox(
                            "Alveare",
                            options=list(alveari_per_id),
                            format_func={a.id: a.codice for a in alveari}.__getitem__,
                            key="alveare_da_modificare",
                        )
                    ]
                    with st.form(f"modifica_alveare_{scelto.id}"):
                        campi = campi_alveare(f"alveare_{scelto.id}", scelto, apiari)
                        if st.form_submit_button(
                            "Salva le modifiche", type="primary", key=f"alveare_{scelto.id}_invia"
                        ):
                            if problemi := problemi_alveare(campi):
                                mostra_problemi(problemi)
                            else:
                                try:
                                    servizi.aggiorna_alveare(utente, scelto.id, **campi)
                                except BeeWatchError as errore:
                                    mostra_errore(errore)
                                else:
                                    scrittura_riuscita(
                                        f"Alveare **{campi['codice'].strip()}** aggiornato."
                                    )
                    st.caption(
                        "Eliminare toglie l'alveare dagli elenchi; le sue ispezioni restano "
                        "nello storico. Il codice resta riservato in questo apiario."
                    )
                    if conferma_eliminazione(
                        f"alveare_{scelto.id}",
                        f"Confermo: elimina l'alveare {scelto.codice}",
                        "Elimina l'alveare",
                    ):
                        try:
                            servizi.elimina_alveare(utente, scelto.id)
                        except BeeWatchError as errore:
                            mostra_errore(errore)
                        else:
                            scrittura_riuscita(f"Alveare **{scelto.codice}** eliminato.")

            # Contenuto
            colonne = st.columns(4)
            with colonne[0]:
                metrica("Alveari nell'apiario", len(alveari), None)
            with colonne[1]:
                metrica(
                    "In salute",
                    sum(a.stato is StatoAlveare.IN_SALUTE for a in alveari),
                    None,
                    aiuto="Alveari con stato «In salute».",
                )
            if not alveari:
                blocco_vuoto(
                    f"Nessun alveare in {attivo.nome}.",
                    "Aggiungilo con il modulo **Aggiungi un alveare** qui sopra.",
                )
            for alveare in alveari:
                with st.container(border=True):
                    codice, stato, ispezione = st.columns([2, 2, 3])
                    with codice:
                        st.markdown(f"**{alveare.codice}**")
                        dettagli = []
                        if alveare.data_installazione:
                            dettagli.append(
                                f"installato il {formatta_data(alveare.data_installazione)}"
                            )
                        if alveare.anno_regina:
                            dettagli.append(f"regina del {alveare.anno_regina}")
                        st.caption(" · ".join(dettagli) or "Nessun dettaglio registrato")
                    with stato:
                        badge_stato(alveare.stato)
                    with ispezione:
                        if alveare.ultima_ispezione is None:
                            st.caption("Mai ispezionato")
                        else:
                            peso = (
                                ""
                                if alveare.peso_kg is None
                                else f" · {formatta_numero(alveare.peso_kg)} kg"
                            )
                            st.caption(
                                f"Ultima ispezione: {formatta_data(alveare.ultima_ispezione)}{peso}"
                            )
                    if alveare.note:
                        st.caption(alveare.note)

# --------------------------------------------------------------------------- #
# Scheda Apiari
# --------------------------------------------------------------------------- #

with scheda_apiari:
    st.subheader("I tuoi apiari")

    # Controlli
    with st.expander("➕ Aggiungi un apiario", expanded=not apiari):
        with st.form("nuovo_apiario"):
            campi = campi_apiario("nuovo_apiario")
            if st.form_submit_button(
                "Aggiungi l'apiario", type="primary", key="nuovo_apiario_invia"
            ):
                if problemi := problemi_apiario(campi):
                    mostra_problemi(problemi)
                else:
                    try:
                        nuovo = servizi.crea_apiario(utente, **campi)
                    except BeeWatchError as errore:
                        mostra_errore(errore)
                    else:
                        imposta_apiario_attivo(nuovo.id)
                        scrittura_riuscita(
                            f"Apiario **{nuovo.nome}** aggiunto: ora è l'apiario attivo."
                        )

    if apiari:
        with st.expander("✏️ Modifica o elimina un apiario"):
            apiari_per_id = {a.id: a for a in apiari}
            scelto = apiari_per_id[
                st.selectbox(
                    "Apiario",
                    options=list(apiari_per_id),
                    index=list(apiari_per_id).index(attivo.id) if attivo else 0,
                    format_func={a.id: a.nome for a in apiari}.__getitem__,
                    key="apiario_da_modificare",
                )
            ]
            with st.form(f"modifica_apiario_{scelto.id}"):
                campi = campi_apiario(f"apiario_{scelto.id}", scelto)
                if st.form_submit_button(
                    "Salva le modifiche", type="primary", key=f"apiario_{scelto.id}_invia"
                ):
                    if problemi := problemi_apiario(campi):
                        mostra_problemi(problemi)
                    else:
                        try:
                            servizi.aggiorna_apiario(utente, scelto.id, **campi)
                        except BeeWatchError as errore:
                            mostra_errore(errore)
                        else:
                            scrittura_riuscita(f"Apiario **{campi['nome'].strip()}** aggiornato.")
            st.caption(
                "Eliminare toglie l'apiario e i suoi alveari dagli elenchi; ispezioni e raccolti "
                "restano nello storico. Il nome resta riservato: non si può riusare."
            )
            if conferma_eliminazione(
                f"apiario_{scelto.id}",
                f"Confermo: elimina l'apiario {scelto.nome} e toglie dagli elenchi i suoi alveari",
                "Elimina l'apiario",
            ):
                try:
                    servizi.elimina_apiario(utente, scelto.id)
                except BeeWatchError as errore:
                    mostra_errore(errore)
                else:
                    scrittura_riuscita(f"Apiario **{scelto.nome}** eliminato.")

    # Contenuto
    if not apiari:
        blocco_vuoto(NESSUN_APIARIO, "Aggiungilo con il modulo **Aggiungi un apiario** qui sopra.")
    for apiario in apiari:
        with st.container(border=True):
            nome, luogo = st.columns([2, 3])
            with nome:
                segno = " · apiario attivo" if attivo and apiario.id == attivo.id else ""
                st.markdown(f"**{apiario.nome}**{segno}")
            with luogo:
                posizione = apiario.localita or "Località non indicata"
                if apiario.latitudine is not None:
                    posizione += f" · {apiario.latitudine}, {apiario.longitudine}"
                st.caption(posizione)
            if apiario.note:
                st.caption(apiario.note)

# Note
st.divider()
st.caption(
    "I campi con * sono obbligatori. Le coordinate restano sul tuo database e non compaiono "
    "negli elenchi delle altre pagine. Eliminare è una cancellazione logica: i dati storici "
    "(ispezioni, raccolti, previsioni) non si perdono."
)
