"""
BeeWatch AI - pagina Alveari (M6-T3; aspetto del mockup, tavole 16–24).

Due viste, come nel mockup:

- **l'elenco**: la tabella degli alveari di tutti gli apiari, con ricerca, filtri per stato e
  per apiario («Posizione»), Esporta in CSV, pastiglie di stato, Forza e Scorte di miele, ultima
  ispezione e le tre azioni (vedi, modifica, elimina), dieci righe per pagina;
- **il dettaglio** di un alveare («Alveare A12»): stato, forza, scorte e peso all'ultima
  ispezione, l'andamento del peso, lo storico delle ispezioni, i dettagli e i rischi.

Nuovo alveare, modifica, eliminazione e gestione degli apiari si aprono in una finestra
(`st.dialog`). Eliminare è una cancellazione logica: lo storico resta.

Forza e Scorte vengono dai telaini contati all'ultima ispezione (soglie in `services`); tipo
d'arnia, numero di telaini dell'arnia, operatore e origine della regina del mockup non ci sono:
l'app non li registra. La pagina non scrive nel database: chiama i servizi.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st
from avvio import (
    CHIAVE_UTENTE,
    alveare_in_vista,
    apiari_in_anagrafica,
    apri_finestra,
    avvia,
    chiudi_finestra,
    elenco_alveari,
    finestra_aperta,
    imposta_apiario_attivo,
    ispezioni_dell_apiario,
    mostra_alveare,
    prendi_esito,
    scrittura_riuscita,
)
from schede import (
    Voce,
    barra_rischio,
    csv_per_excel,
    disegna,
    elenco,
    figura_area,
    icona_tonda_avviso,
    icona_vuoto,
    intestazione_tabella,
    mostra_pastiglia_rischio,
    mostra_pastiglia_stato,
    scheda_kpi,
    testata,
    titolo_card,
)
from ui import (
    NESSUN_APIARIO,
    blocco_vuoto,
    etichetta_rischio,
    formatta_data,
    mostra_errore,
    sidebar,
    stile_stato,
)

from beewatch.exceptions import BeeWatchError, ValidationError
from beewatch.models import ANNO_REGINA_MINIMO, LivelloRischio, StatoAlveare
from beewatch.services import SOGLIE_FORZA, SOGLIE_SCORTE

STATI = list(StatoAlveare)
OGGI = date.today()
RIGHE_PER_PAGINA = 10
TUTTI, TUTTE = "Tutti", "Tutte"
COLONNE = [1.1, 1.7, 1.7, 1.1, 1.3, 1.5, 1.4]
INTESTAZIONI = ("ID alveare", "Posizione", "Stato", "Forza", "Scorte di miele", "Ultima ispezione",
                "Azioni")  # fmt: skip
TONI = {"Bassa": "critico", "Media": "attenzione", "Scarse": "critico", "Medie": "attenzione"}
LIVELLI = {LivelloRischio.NESSUNO: 10, LivelloRischio.BASSO: 35, LivelloRischio.MEDIO: 65,
           LivelloRischio.ALTO: 90}  # fmt: skip


def etichetta_stato(stato: StatoAlveare) -> str:
    return stile_stato(stato)[0]


def soglie(elenco_soglie: tuple[tuple[int, str], ...]) -> str:
    """«Alta da 6 telaini, Media da 3, Bassa sotto»: le soglie dette a parole."""
    (alto, parola_alta), (medio, parola_media), (_, parola_bassa) = elenco_soglie
    return f"{parola_alta} da {alto} telaini, {parola_media} da {medio}, {parola_bassa} sotto"


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


def mostra_problemi(problemi: list[ValidationError]) -> None:
    for problema in problemi:
        mostra_errore(problema)


def campi_alveare(chiave: str, apiari, alveare=None, apiario_predefinito=None) -> dict:
    """I campi di un alveare, su due colonne come nel mockup; `alveare` dà i valori di partenza."""
    nomi = {a.id: a.nome for a in apiari}
    di_partenza = alveare.apiario_id if alveare else apiario_predefinito
    sinistra, destra = st.columns(2)
    codice = sinistra.text_input(
        "ID alveare *", value=alveare.codice if alveare else "", max_chars=20,
        key=f"{chiave}_codice", placeholder="A25", help="Unico dentro l'apiario.",
    )  # fmt: skip
    apiario_id = destra.selectbox(
        "Posizione (apiario)", options=list(nomi), format_func=nomi.__getitem__,
        index=list(nomi).index(di_partenza) if di_partenza in nomi else 0,
        key=f"{chiave}_apiario",
    )  # fmt: skip
    sinistra, destra = st.columns(2)
    stato = sinistra.selectbox(
        "Stato", options=STATI, index=STATI.index(alveare.stato) if alveare else 0,
        format_func=etichetta_stato, key=f"{chiave}_stato",
    )  # fmt: skip
    installazione = destra.date_input(
        "Data installazione", value=alveare.data_installazione if alveare else None,
        max_value=OGGI, format="DD/MM/YYYY", key=f"{chiave}_installazione",
    )  # fmt: skip
    sinistra, _ = st.columns(2)
    regina = sinistra.number_input(
        "Anno della regina", min_value=ANNO_REGINA_MINIMO, max_value=OGGI.year,
        value=alveare.anno_regina if alveare else None, step=1, key=f"{chiave}_regina",
    )  # fmt: skip
    note = st.text_area(
        "Note (opzionale)", value=(alveare.note or "") if alveare else "", key=f"{chiave}_note"
    )
    return {"apiario_id": apiario_id, "codice": codice, "stato": stato,
            "data_installazione": installazione, "anno_regina": regina, "note": note}  # fmt: skip


def campi_apiario(chiave: str, apiario=None) -> dict:
    """I campi di un apiario; `apiario` dà i valori di partenza (modifica)."""
    sinistra, destra = st.columns(2)
    nome = sinistra.text_input(
        "Nome *", value=apiario.nome if apiario else "", max_chars=120, key=f"{chiave}_nome"
    )
    localita = destra.text_input(
        "Località", value=(apiario.localita or "") if apiario else "", max_chars=160,
        key=f"{chiave}_localita",
    )  # fmt: skip
    sinistra, destra = st.columns(2)
    latitudine = sinistra.number_input(
        "Latitudine", min_value=-90.0, max_value=90.0, format="%.6f", step=0.000001,
        value=float(apiario.latitudine) if apiario and apiario.latitudine is not None else None,
        key=f"{chiave}_latitudine", help="Facoltativa, in gradi decimali (es. 45.710000).",
    )  # fmt: skip
    longitudine = destra.number_input(
        "Longitudine", min_value=-180.0, max_value=180.0, format="%.6f", step=0.000001,
        value=float(apiario.longitudine) if apiario and apiario.longitudine is not None else None,
        key=f"{chiave}_longitudine",
    )  # fmt: skip
    note = st.text_area("Note", value=(apiario.note or "") if apiario else "", key=f"{chiave}_note")
    return {"nome": nome, "localita": localita, "latitudine": coordinata(latitudine),
            "longitudine": coordinata(longitudine), "note": note}  # fmt: skip


def bottoni_finestra(chiave: str, conferma: str, icona: str) -> bool:
    """Annulla e il bottone che conferma, in fondo a destra della finestra (mockup)."""
    _, annulla, salva = st.columns([2, 1, 1.3])
    if annulla.form_submit_button("Annulla", key=f"{chiave}_annulla", width="stretch"):
        chiudi_e_ricarica()
    return salva.form_submit_button(conferma, type="primary", key=f"{chiave}_invia",
                                    icon=icona, width="stretch")  # fmt: skip


def chiudi_e_ricarica() -> None:
    """Chiude la finestra e riesegue tutta la pagina.

    Un clic dentro una finestra riesegue solo la finestra: senza `st.rerun()` resterebbe aperta.
    """
    chiudi_finestra()
    st.rerun()


# --------------------------------------------------------------------------- #
# Finestre
# --------------------------------------------------------------------------- #


@st.dialog("Nuovo alveare", width="large", on_dismiss=chiudi_finestra)
def finestra_nuovo_alveare() -> None:
    st.caption("Registra un nuovo alveare nel tuo apiario.")
    with st.form("nuovo_alveare", border=False):
        campi = campi_alveare("nuovo_alveare", apiari, apiario_predefinito=attivo and attivo.id)
        premuto = bottoni_finestra("nuovo_alveare", "Salva alveare", ":material/check_circle:")
    if premuto:
        if problemi := problemi_alveare(campi):
            mostra_problemi(problemi)
            return
        try:
            nuovo = servizi.crea_alveare(utente, **campi)
        except BeeWatchError as errore:
            mostra_errore(errore)
        else:
            chiudi_finestra()
            scrittura_riuscita(f"Alveare **{nuovo.codice}** aggiunto.")


@st.dialog("Modifica alveare", width="large", on_dismiss=chiudi_finestra)
def finestra_modifica_alveare(riga) -> None:
    st.caption(f"Cambia i dati dell'alveare {riga.codice}.")
    with st.form(f"modifica_alveare_{riga.id}", border=False):
        campi = campi_alveare(f"alveare_{riga.id}", apiari, riga)
        premuto = bottoni_finestra(f"alveare_{riga.id}", "Salva modifiche", ":material/check:")
    if premuto:
        if problemi := problemi_alveare(campi):
            mostra_problemi(problemi)
            return
        try:
            servizi.aggiorna_alveare(utente, riga.id, **campi)
        except BeeWatchError as errore:
            mostra_errore(errore)
        else:
            chiudi_finestra()
            scrittura_riuscita(f"Alveare **{campi['codice'].strip()}** aggiornato.")


@st.dialog("Elimina alveare", on_dismiss=chiudi_finestra)
def finestra_elimina_alveare(riga) -> None:
    with st.container(key="bw_conferma_elimina"):
        icona_tonda_avviso()
        st.markdown(f"**Eliminare l'alveare {riga.codice}?**")
        st.caption(
            "L'alveare sparisce dagli elenchi; le sue ispezioni restano nello storico e il codice "
            f"resta riservato in {riga.apiario}."
        )
        annulla, elimina = st.columns(2)
        if annulla.button("Annulla", key=f"alveare_{riga.id}_annulla_elimina", width="stretch"):
            chiudi_e_ricarica()
        with elimina, st.container(key="bw_bottone_elimina"):
            premuto = st.button("Elimina", key=f"alveare_{riga.id}_elimina", width="stretch",
                                icon=":material/delete:")  # fmt: skip
    if premuto:
        try:
            servizi.elimina_alveare(utente, riga.id)
        except BeeWatchError as errore:
            mostra_errore(errore)
        else:
            chiudi_finestra()
            if alveare_in_vista() == riga.id:
                mostra_alveare(None)
            scrittura_riuscita(f"Alveare **{riga.codice}** eliminato.")


@st.dialog("I tuoi apiari", width="large", on_dismiss=chiudi_finestra)
def finestra_apiari() -> None:
    st.caption("Gli apiari sono i luoghi dove stanno le arnie: la «Posizione» della tabella.")
    for apiario in apiari:
        segno = " · apiario attivo" if attivo and apiario.id == attivo.id else ""
        posizione = apiario.localita or "Località non indicata"
        if apiario.latitudine is not None:
            posizione += f" · {apiario.latitudine}, {apiario.longitudine}"
        st.markdown(f"**{apiario.nome}**{segno}  \n{posizione}")
        if apiario.note:
            st.caption(apiario.note)
    with st.expander("➕ Aggiungi un apiario", expanded=not apiari):
        with st.form("nuovo_apiario", border=False):
            campi = campi_apiario("nuovo_apiario")
            if st.form_submit_button("Aggiungi l'apiario", type="primary",
                                     key="nuovo_apiario_invia"):  # fmt: skip
                if problemi := problemi_apiario(campi):
                    mostra_problemi(problemi)
                else:
                    try:
                        nuovo = servizi.crea_apiario(utente, **campi)
                    except BeeWatchError as errore:
                        mostra_errore(errore)
                    else:
                        imposta_apiario_attivo(nuovo.id)
                        chiudi_finestra()
                        scrittura_riuscita(
                            f"Apiario **{nuovo.nome}** aggiunto: ora è l'apiario attivo."
                        )
    if not apiari:
        return
    with st.expander("✏️ Modifica o elimina un apiario"):
        per_id = {a.id: a for a in apiari}
        scelto = per_id[
            st.selectbox(
                "Apiario", options=list(per_id), format_func=lambda i: per_id[i].nome,
                index=list(per_id).index(attivo.id) if attivo and attivo.id in per_id else 0,
                key="apiario_da_modificare",
            )
        ]  # fmt: skip
        with st.form(f"modifica_apiario_{scelto.id}", border=False):
            campi = campi_apiario(f"apiario_{scelto.id}", scelto)
            if st.form_submit_button("Salva le modifiche", type="primary",
                                     key=f"apiario_{scelto.id}_invia"):  # fmt: skip
                if problemi := problemi_apiario(campi):
                    mostra_problemi(problemi)
                else:
                    try:
                        servizi.aggiorna_apiario(utente, scelto.id, **campi)
                    except BeeWatchError as errore:
                        mostra_errore(errore)
                    else:
                        chiudi_finestra()
                        scrittura_riuscita(f"Apiario **{campi['nome'].strip()}** aggiornato.")
        st.caption(
            "Eliminare toglie l'apiario e i suoi alveari dagli elenchi; ispezioni e raccolti "
            "restano nello storico. Il nome resta riservato: non si può riusare."
        )
        confermato = st.checkbox(
            f"Confermo: elimina l'apiario {scelto.nome} e toglie dagli elenchi i suoi alveari",
            key=f"apiario_{scelto.id}_conferma",
        )
        premuto = st.button("Elimina l'apiario", disabled=not confermato, type="primary",
                            key=f"apiario_{scelto.id}_elimina")  # fmt: skip
        if confermato and premuto:  # la spunta si ricontrolla: un bottone disabilitato non basta
            try:
                servizi.elimina_apiario(utente, scelto.id)
            except BeeWatchError as errore:
                mostra_errore(errore)
            else:
                chiudi_finestra()
                scrittura_riuscita(f"Apiario **{scelto.nome}** eliminato.")


# --------------------------------------------------------------------------- #
# Vista: la tabella
# --------------------------------------------------------------------------- #


def vista_elenco(righe) -> None:
    azioni = testata("Alveari", "Gestisci i tuoi alveari e visualizza le informazioni principali.")
    with azioni:
        _, apiari_bottone, nuovo = st.columns([1, 1.1, 1.5])
        apiari_bottone.button(
            "Apiari", key="apri_apiari", icon=":material/location_on:", width="stretch",
            on_click=apri_finestra, args=("apiari",),
        )  # fmt: skip
        nuovo.button(
            "Nuovo alveare", type="primary", key="apri_nuovo_alveare", icon=":material/add:",
            width="stretch", on_click=apri_finestra, args=("nuovo_alveare",), disabled=not apiari,
            help=None if apiari else "Prima serve un apiario: aggiungilo con «Apiari».",
        )  # fmt: skip
    if esito:
        st.success(esito, icon="✅")
    if not apiari:
        blocco_vuoto(NESSUN_APIARIO, "Aggiungilo con il bottone **Apiari**, qui sopra.")
        return
    if not righe:
        with st.container(key="bw_vuoto"):
            icona_vuoto()
            st.markdown("**Nessun alveare registrato**")
            st.caption("Aggiungi il tuo primo alveare per iniziare a monitorare produzione, "
                       "ispezioni e salute.")  # fmt: skip
            st.button("Nuovo alveare", type="primary", key="vuoto_nuovo_alveare",
                      icon=":material/add:", on_click=apri_finestra,
                      args=("nuovo_alveare",))  # fmt: skip
        return

    with st.container(key="bw_card_alveari"):
        cerca, stato, posizione, _, esporta = st.columns([3, 1.6, 1.8, 0.6, 1.2])
        testo = cerca.text_input(
            "Cerca", key="alveari_cerca", placeholder="Cerca alveare...",
            label_visibility="collapsed", icon=":material/search:",
        )  # fmt: skip
        filtro_stato = stato.selectbox(
            "Stato", [TUTTI, *STATI], key="alveari_filtro_stato", label_visibility="collapsed",
            format_func=lambda s: f"Stato: {s if s == TUTTI else etichetta_stato(s)}",
        )  # fmt: skip
        nomi_apiari = [a.nome for a in apiari]
        filtro_apiario = posizione.selectbox(
            "Posizione", [TUTTE, *nomi_apiari], key="alveari_filtro_apiario",
            label_visibility="collapsed", format_func=lambda p: f"Posizione: {p}",
        )  # fmt: skip
        scelte = [
            r for r in righe
            if (not testo.strip() or testo.strip().lower() in r.codice.lower())
            and (filtro_stato == TUTTI or r.stato == filtro_stato)
            and (filtro_apiario == TUTTE or r.apiario == filtro_apiario)
        ]  # fmt: skip
        esporta.download_button(
            "Esporta", data=csv_alveari(scelte), file_name="alveari.csv", mime="text/csv",
            key="alveari_esporta", icon=":material/download:", width="stretch",
        )  # fmt: skip

        pagine = max(1, -(-len(scelte) // RIGHE_PER_PAGINA))
        pagina = st.session_state.get("alveari_pagina") or 1
        pagina = min(pagina, pagine)
        mostrate = scelte[(pagina - 1) * RIGHE_PER_PAGINA : pagina * RIGHE_PER_PAGINA]

        intestazione_tabella(INTESTAZIONI, COLONNE)
        if not mostrate:
            st.caption("Nessun alveare corrisponde alla ricerca o ai filtri.")
        for riga in mostrate:
            with st.container(key=f"bw_riga_{riga.id}"):
                celle = st.columns(COLONNE, vertical_alignment="center")
                celle[0].markdown(f"**{riga.codice}**")
                celle[1].write(riga.apiario)
                with celle[2]:
                    mostra_pastiglia_stato(riga.stato)
                celle[3].write(riga.forza or "—")
                celle[4].write(riga.scorte or "—")
                celle[5].write(formatta_data(riga.ultima_ispezione)
                               if riga.ultima_ispezione else "Mai")  # fmt: skip
                with celle[6]:
                    vedi, modifica, elimina = st.columns(3)
                    vedi.button("", key=f"vedi_{riga.id}", icon=":material/visibility:",
                                type="tertiary", help=f"Apri {riga.codice}",
                                on_click=mostra_alveare, args=(riga.id,))  # fmt: skip
                    modifica.button("", key=f"modifica_{riga.id}", icon=":material/edit:",
                                    type="tertiary", help=f"Modifica {riga.codice}",
                                    on_click=apri_finestra,
                                    args=("modifica_alveare", riga.id))  # fmt: skip
                    with elimina, st.container(key=f"bw_cestino_{riga.id}"):
                        st.button("", key=f"elimina_{riga.id}", icon=":material/delete:",
                                  type="tertiary", help=f"Elimina {riga.codice}",
                                  on_click=apri_finestra,
                                  args=("elimina_alveare", riga.id))  # fmt: skip

        piede, numeri = st.columns([2, 1], vertical_alignment="center")
        piede.caption(f"Mostrando {len(mostrate)} di {len(scelte)} alveari")
        if pagine > 1:
            with numeri, st.container(key="bw_pagine"):
                st.segmented_control(
                    "Pagina", list(range(1, pagine + 1)), default=pagina, key="alveari_pagina",
                    label_visibility="collapsed",
                )  # fmt: skip

    st.caption(
        f"Forza e scorte vengono dai telaini contati all'ultima ispezione che li ha registrati "
        f"(arnia da 10): forza "
        f"{soglie(SOGLIE_FORZA)}; scorte {soglie(SOGLIE_SCORTE)}. «—» se non sono stati contati."
    )


def csv_alveari(righe) -> bytes:
    """La tabella filtrata, in CSV per Excel in italiano."""
    return csv_per_excel(
        pd.DataFrame(
            [
                {
                    "ID alveare": r.codice,
                    "Posizione": r.apiario,
                    "Stato": etichetta_stato(r.stato),
                    "Forza": r.forza or "",
                    "Scorte di miele": r.scorte or "",
                    "Ultima ispezione": formatta_data(r.ultima_ispezione)
                    if r.ultima_ispezione
                    else "",
                    "Peso (kg)": r.peso_kg,
                }
                for r in righe
            ]  # fmt: skip
        )
    )


# --------------------------------------------------------------------------- #
# Vista: il dettaglio di un alveare
# --------------------------------------------------------------------------- #


def vista_dettaglio(riga) -> None:
    st.button("Alveari", key="torna_elenco", icon=":material/arrow_back:", type="tertiary",
              on_click=mostra_alveare, args=(None,))  # fmt: skip
    ultima = formatta_data(riga.ultima_ispezione) if riga.ultima_ispezione else "mai"
    azioni = testata(f"Alveare {riga.codice}", f"{riga.apiario} · Ultima ispezione {ultima}")
    with azioni:
        _, modifica, nuova = st.columns([0.6, 1.2, 1.6])
        modifica.button("Modifica", key="dettaglio_modifica", icon=":material/edit:",
                        width="stretch", on_click=apri_finestra,
                        args=("modifica_alveare", riga.id))  # fmt: skip
        if nuova.button("Nuova ispezione", type="primary", key="dettaglio_nuova_ispezione",
                        icon=":material/add:", width="stretch"):  # fmt: skip
            apri_finestra("nuova_ispezione", riga.id)  # il modulo, con questo alveare già scelto
            st.switch_page("pages/2_Ispezioni.py")
    if esito:
        st.success(esito, icon="✅")

    try:
        storico = ispezioni_dell_apiario(utente, riga.apiario_id, riga.id)
    except BeeWatchError as errore:
        mostra_errore(errore)
        storico = ()

    sinistra, destra = st.columns([2.3, 1])
    with sinistra:
        colonne = st.container(key="bw_dettaglio_kpi").columns(4)
        gruppo = {StatoAlveare.IN_SALUTE: None, StatoAlveare.MORTO: "critico"}
        with colonne[0]:
            scheda_kpi("salute", "Stato", etichetta_stato(riga.stato), None,
                       tono=gruppo.get(riga.stato, "attenzione"))  # fmt: skip
        with colonne[1]:
            scheda_kpi("forza", "Forza", riga.forza or "—", None, tono=TONI.get(riga.forza),
                       aiuto=f"Telaini di covata: {soglie(SOGLIE_FORZA)}.")  # fmt: skip
        with colonne[2]:
            scheda_kpi("miele", "Scorte", riga.scorte or "—", None, tono=TONI.get(riga.scorte),
                       aiuto=f"Telaini di scorte: {soglie(SOGLIE_SCORTE)}.")  # fmt: skip
        with colonne[3]:
            scheda_kpi("peso", "Peso", riga.peso_kg, "kg", aiuto="All'ultima ispezione.")

        with st.container(key="bw_card_peso"):
            titolo_card("Andamento del peso", "(kg, alle ispezioni)")
            pesate = [(i.data_ispezione, i.peso_kg) for i in reversed(storico) if i.peso_kg]
            if len(pesate) < 2:
                st.caption("Servono almeno due ispezioni con il peso per disegnare l'andamento.")
            else:
                disegna(
                    figura_area([formatta_data(d) for d, _ in pesate], [p for _, p in pesate],
                                "kg"),
                    f"peso_{riga.id}",
                )  # fmt: skip

        with st.container(key="bw_card_storico"):
            titolo, tutte = st.columns([3, 1], vertical_alignment="center")
            with titolo:
                titolo_card("Storico ispezioni")
            if tutte.button("Vedi tutte", key="dettaglio_vedi_tutte", width="stretch"):
                st.switch_page("pages/2_Ispezioni.py")
            if not storico:
                st.caption("Nessuna ispezione registrata per questo alveare.")
            for ispezione in storico[:4]:
                data, rischio, nota = st.columns([1.2, 1.6, 4], vertical_alignment="center")
                data.markdown(f"**{formatta_data(ispezione.data_ispezione)}**")
                with rischio:
                    mostra_pastiglia_rischio(ispezione.livello_rischio)
                nota.write(ispezione.note or "Nessuna nota")

    with destra:
        with st.container(key="bw_card_dettagli"):
            titolo_card("Dettagli alveare")
            regina = str(riga.anno_regina) if riga.anno_regina else "—"
            installato = formatta_data(riga.data_installazione)
            elenco([
                Voce("Posizione", riga.apiario), Voce("Installato il", installato),
                Voce("Regina", regina), Voce("Note", riga.note or "—"),
            ], "")  # fmt: skip

        with st.container(key="bw_card_rischi"):
            titolo_card("Salute e rischi", "(all'ultima ispezione)")
            if not storico:
                st.caption("Dopo la prima ispezione qui compaiono rischio, sciamatura e scorte.")
            else:
                recente = storico[0]
                barre = [
                    ("Rischio rilevato", LIVELLI[recente.livello_rischio],
                     etichetta_rischio(recente.livello_rischio)),
                    ("Sciamatura", 85 if recente.sciamatura else 15,
                     "Osservata" if recente.sciamatura else "Non osservata"),
                ]  # fmt: skip
                if riga.scorte:
                    carenza = {"Buone": 15, "Medie": 55, "Scarse": 85}[riga.scorte]
                    barre.append(("Carenza di scorte", carenza, riga.scorte))
                for nome, livello, etichetta in barre:
                    barra_rischio(nome, livello, etichetta)

        with st.container(key="bw_card_ai"):
            titolo_card("Assistente AI")
            st.caption("Chiedi all'assistente un riepilogo delle note dell'ultima ispezione, con "
                       "i punti da controllare.")  # fmt: skip
            if st.button("Apri l'assistente", key="dettaglio_assistente", width="stretch"):
                st.switch_page("pages/4_Assistente_AI.py")


# --------------------------------------------------------------------------- #
# Pagina
# --------------------------------------------------------------------------- #

servizi = avvia("Alveari", "🏠")
attivo = sidebar()
utente = st.session_state[CHIAVE_UTENTE]
esito = prendi_esito()

try:
    apiari = apiari_in_anagrafica(utente)
    righe = elenco_alveari(utente)
except BeeWatchError as errore:
    testata("Alveari", "Gestisci i tuoi alveari e visualizza le informazioni principali.")
    mostra_errore(errore)
    st.stop()

per_id = {r.id: r for r in righe}
in_vista = per_id.get(alveare_in_vista())
if in_vista is not None:
    vista_dettaglio(in_vista)
else:
    vista_elenco(righe)

if finestra_aperta("nuovo_alveare") and apiari:
    finestra_nuovo_alveare()
elif finestra_aperta("apiari"):
    finestra_apiari()
elif (scelto := finestra_aperta("modifica_alveare")) in per_id:
    finestra_modifica_alveare(per_id[scelto])
elif (scelto := finestra_aperta("elimina_alveare")) in per_id:
    finestra_elimina_alveare(per_id[scelto])
