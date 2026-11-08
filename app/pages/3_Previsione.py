"""
BeeWatch AI - pagina Previsione: la resa per colonia con la sua banda d'incertezza (M6-T5).

L'anatomia del §6 della specifica:

- **controlli**: l'avviso sui limiti del modello (sempre visibile), il modo di prevedere (dai dati
  storici di uno stato, con un alveare collegato se si vuole, oppure con i parametri scritti a
  mano) e il modulo;
- **contenuto**: la stima con `stima_con_incertezza` (mai un numero secco: barra orizzontale con la
  banda d'errore), il modello che l'ha prodotta, i valori usati; poi lo storico delle previsioni,
  di tutti gli alveari o di uno;
- **note** in fondo.

La pagina non carica il modello e non scrive query: chiama `prevedi_produzione` e
`prevedi_con_parametri` dei servizi, che caricano il modello una volta sola e salvano le previsioni
sui dati veri. Le simulazioni con i parametri a mano non si salvano.
"""

from __future__ import annotations

import streamlit as st
from avvio import (
    CHIAVE_UTENTE,
    alveari_dell_apiario,
    avvia,
    intervalli_parametri,
    modello,
    stati_prevedibili,
    storico_previsioni,
    svuota_letture,
)
from ui import (
    DATO_MANCANTE,
    blocco_vuoto,
    formatta_numero,
    intestazione,
    metrica,
    mostra_errore,
    sidebar,
    stima_con_incertezza,
)

from beewatch.exceptions import BeeWatchError, ValidationError

DAI_DATI = "Dai dati storici di uno stato"
A_MANO = "Con parametri scritti a mano"
NESSUNO = 0  # nel selettore: nessun alveare collegato / tutti gli alveari

LIMITI = (
    "**Limiti di trasferibilità.** Il modello ha imparato dalle rese medie per colonia degli "
    "stati USA (dati USDA, 1998–2012): stima quanto miele produce in media una colonia in uno "
    "stato e in un anno. Non conosce il tuo alveare né il clima e le fioriture italiane: collegare "
    "una previsione a un alveare serve a ritrovarla nello storico, non la rende una previsione "
    "per quell'alveare. Usala come ordine di grandezza, non come promessa."
)

ETICHETTE_FEATURE = {
    "codice_stato": "Stato",
    "anno": "Anno da prevedere",
    "resa_anno_prima": "Resa dell'anno prima (kg per colonia)",
    "resa_media_3_anni_prima": "Resa media dei 3 anni prima (kg per colonia)",
    "colonie_anno_prima": "Colonie dell'anno prima",
}


def problemi_parametri(valori: dict, intervalli) -> list[ValidationError]:
    """I controlli della pagina prima del servizio: i tre parametri vanno scritti tutti."""
    return [
        ValidationError(f"Scrivi «{intervallo.etichetta}».", campo=intervallo.campo)
        for intervallo in intervalli
        if valori[intervallo.campo] is None
    ]


def numero_breve(valore) -> str:
    """Un numero senza decimali inutili: «30», ma «8,6»."""
    return formatta_numero(valore, 0 if float(valore).is_integer() else 1)


def campo_parametro(intervallo) -> float | int | None:
    """Un parametro a mano, con l'intervallo visto in addestramento come limiti del widget."""
    intero = intervallo.unita == "colonie"
    return st.number_input(
        f"{intervallo.etichetta} ({intervallo.unita})",
        min_value=int(intervallo.minimo) if intero else float(intervallo.minimo),
        max_value=int(intervallo.massimo) if intero else float(intervallo.massimo),
        value=None,
        step=1000 if intero else 0.5,
        key=f"parametro_{intervallo.campo}",
        help=(
            f"Il modello ha visto valori da {numero_breve(intervallo.minimo)} a "
            f"{numero_breve(intervallo.massimo)} {intervallo.unita}: fuori da lì non sa stimare."
        ),
    )


def mostra_risultato(risultato) -> None:
    """La stima con la sua banda, il modello che l'ha prodotta e i valori usati."""
    titolo = f"{risultato.nome_stato}, {risultato.anno}"
    if risultato.parametri_manuali:
        titolo += " · simulazione con parametri a mano"
    st.subheader(titolo)
    if not risultato.mostra_stima:
        st.warning(risultato.messaggio, icon="⚠️")
    stima_con_incertezza(
        risultato.stima_kg if risultato.mostra_stima else None,
        risultato.limite_inferiore_kg,
        risultato.limite_superiore_kg,
        "kg",
        etichetta="Resa per colonia stimata",
        livello=risultato.livello,
    )
    st.caption(
        f"Stimata dal modello **{risultato.versione_modello}** · errore medio sul 2010–2012: "
        f"±{formatta_numero(risultato.errore_medio_kg)} kg."
    )
    if risultato.retrospettiva:
        st.caption(
            f"Il {risultato.anno} è già nei dati: è una prova a ritroso. La resa vera di "
            "quell'anno non entra nella stima."
        )
    if risultato.parametri_manuali:
        st.caption("Le simulazioni non si salvano: lo storico raccoglie le previsioni sui dati.")
    elif risultato.id is not None:
        st.caption("Salvata nello storico qui sotto.")
    with st.expander("I valori con cui il modello ha stimato"):
        st.dataframe(
            [
                {"Valore": ETICHETTE_FEATURE.get(nome, nome), "Dato": testo_feature(valore)}
                for nome, valore in risultato.feature.items()
            ],
            hide_index=True,
            width="stretch",
        )


def testo_feature(valore) -> str:
    """Stato e anno come sono, i numeri all'italiana; un valore mancante diventa «—»."""
    if isinstance(valore, str | int):
        return str(valore)
    return formatta_numero(valore, 2)


def riga_storico(previsione: dict, nomi_stati: dict[str, str]) -> dict:
    creata = previsione.get("creato_il")
    codice = previsione["codice_stato_riferimento"]
    return {
        "Creata il": creata.strftime("%d/%m/%Y %H:%M") if creata else DATO_MANCANTE,
        "Alveare": previsione.get("alveare") or DATO_MANCANTE,
        "Stato": nomi_stati.get(codice, codice),
        "Anno": str(previsione["anno_riferimento"]),
        # Chili interi per costruzione: dal database arrivano come Decimal («52.00»).
        "Stima (kg)": formatta_numero(previsione["stima_kg"], 0),
        "Banda (kg)": f"da {formatta_numero(previsione['limite_inferiore_kg'], 0)} "
        f"a {formatta_numero(previsione['limite_superiore_kg'], 0)}",
        "Modello": previsione["versione"],
    }


# --------------------------------------------------------------------------- #
# Pagina
# --------------------------------------------------------------------------- #

servizi = avvia("Previsione", "📈")
attivo = sidebar()
utente = st.session_state[CHIAVE_UTENTE]

intestazione(
    "📈 Previsione",
    "Una stima della produzione di miele per colonia, sempre con il suo margine d'errore.",
)

# Sempre visibile, prima di tutto il resto (DoD: non in un espansore).
st.warning(LIMITI, icon="⚠️")

try:
    stati = stati_prevedibili()
    alveari = alveari_dell_apiario(utente, attivo.id) if attivo else ()
except BeeWatchError as errore:
    mostra_errore(errore)
    st.stop()

if not stati:
    blocco_vuoto(
        "Nessuno stato su cui prevedere: i dati USDA non sono nel database.",
        "Caricali con `python scripts/run_etl.py`, poi ricarica la pagina.",
    )
    st.stop()

codici_alveari = {a.id: a.codice for a in alveari}
nomi_stati = {s.codice: s.nome for s in stati}

# --------------------------------------------------------------------------- #
# Il modello in uso: se manca, la pagina lo dice e mostra solo lo storico
# --------------------------------------------------------------------------- #

try:
    stato_modello = modello()
except BeeWatchError as errore:
    mostra_errore(errore)
    stato_modello = None

if stato_modello is not None:
    colonne = st.columns(4)
    with colonne[0]:
        metrica(
            "Errore medio del modello",
            stato_modello.mae_kg,
            "kg",
            aiuto="Scarto medio delle stime sul 2010–2012, anni che il modello non aveva visto.",
        )
    st.caption(
        f"Modello in uso: **{stato_modello.versione}** ({stato_modello.algoritmo}), "
        f"addestrato su {stato_modello.righe_addestramento} righe."
    )

# --------------------------------------------------------------------------- #
# Controlli
# --------------------------------------------------------------------------- #

storico_di = st.selectbox(
    "Storico di",
    options=[NESSUNO, *codici_alveari],
    format_func={NESSUNO: "Tutti gli alveari", **codici_alveari}.__getitem__,
    key="storico_alveare",
    help="Le previsioni salvate collegate a un alveare dell'apiario attivo, o tutte.",
)
alveare_filtro = None if storico_di == NESSUNO else storico_di

risultato = None
if stato_modello is not None:
    modo = st.radio("Come vuoi prevedere", [DAI_DATI, A_MANO], horizontal=True, key="modo")
    try:
        intervalli = intervalli_parametri() if modo == A_MANO else ()
    except BeeWatchError as errore:
        mostra_errore(errore)
        intervalli = None

    if intervalli is not None:
        primo = min(s.primo_anno for s in stati)
        ultimo = max(s.ultimo_anno for s in stati)
        with st.form("previsione"):
            colonne = st.columns(2)
            codice = colonne[0].selectbox(
                "Stato USA",
                options=list(nomi_stati),
                format_func=nomi_stati.__getitem__,
                key="previsione_stato",
            )
            anno = colonne[1].number_input(
                "Anno",
                min_value=primo,
                max_value=ultimo,
                value=ultimo,
                step=1,
                key="previsione_anno",
                help=f"Dal {primo} al {ultimo}: il {ultimo} è il solo anno davvero futuro.",
            )
            valori = {}
            if modo == DAI_DATI:
                if codici_alveari:
                    collegato = st.selectbox(
                        "Collega a un alveare (facoltativo)",
                        options=[NESSUNO, *codici_alveari],
                        index=[NESSUNO, *codici_alveari].index(storico_di),
                        format_func={NESSUNO: "Nessun alveare", **codici_alveari}.__getitem__,
                        # La chiave segue lo storico scelto: così la proposta si aggiorna.
                        key=f"previsione_alveare_{storico_di}",
                    )
                else:
                    collegato = NESSUNO
                    st.caption("Nessun alveare nell'apiario attivo: la previsione resta libera.")
            else:
                for intervallo in intervalli:
                    valori[intervallo.campo] = campo_parametro(intervallo)
            premuto = st.form_submit_button(
                "Calcola la previsione", type="primary", key="previsione_invia"
            )

        if premuto:
            problemi = problemi_parametri(valori, intervalli) if modo == A_MANO else []
            for problema in problemi:
                mostra_errore(problema)
            if not problemi:
                try:
                    with st.spinner("Calcolo la previsione..."):
                        if modo == DAI_DATI:
                            risultato = servizi.prevedi_produzione(
                                utente, None if collegato == NESSUNO else collegato, codice,
                                int(anno),
                            )  # fmt: skip
                        else:
                            risultato = servizi.prevedi_con_parametri(
                                utente, codice, int(anno), **valori
                            )
                except BeeWatchError as errore:  # anche ModelError: modello o feature
                    mostra_errore(errore)
                else:
                    if risultato.id is not None:
                        svuota_letture()  # lo storico qui sotto deve vederla

# --------------------------------------------------------------------------- #
# Contenuto
# --------------------------------------------------------------------------- #

if risultato is not None:
    mostra_risultato(risultato)

titolo_storico = (
    "Storico delle previsioni"
    if alveare_filtro is None
    else f"Storico delle previsioni dell'alveare {codici_alveari[alveare_filtro]}"
)
st.subheader(titolo_storico)
try:
    storico = storico_previsioni(utente, alveare_filtro)
except BeeWatchError as errore:
    mostra_errore(errore)
    storico = None

if storico is not None:
    if storico:
        st.dataframe(
            [riga_storico(p, nomi_stati) for p in storico], hide_index=True, width="stretch"
        )
    elif alveare_filtro is None:
        blocco_vuoto(
            "Nessuna previsione salvata.",
            "Calcolane una qui sopra: quelle sui dati storici restano qui.",
        )
    else:
        blocco_vuoto(
            f"Nessuna previsione collegata all'alveare {codici_alveari[alveare_filtro]}.",
            "Calcolane una scegliendo l'alveare in «Collega a un alveare».",
        )

# --------------------------------------------------------------------------- #
# Note
# --------------------------------------------------------------------------- #

st.caption(
    "Le stime sono in chili di miele per colonia, arrotondati al chilo: i dati di partenza non "
    "hanno più precisione. La banda contiene la parte di errori indicata accanto alla stima; "
    "quando è più larga della stima stessa, il valore centrale non si mostra. Fonte: USDA NASS, "
    "Honey Production 1998–2012."
)
