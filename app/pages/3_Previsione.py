"""
BeeWatch AI - pagina Previsioni (M6-T5 e M6-T7; aspetto del mockup, tavole 30–32).

Le card del mockup, con i dati del modello vero:

- **in cima** l'avviso sui limiti del modello (sempre visibile, mai in un espansore) e la card
  dei controlli: il modo (dai dati storici di uno stato, con un alveare collegato se si vuole,
  oppure con i parametri scritti a mano), stato, anno e «Aggiorna previsione»;
- **Produzione prevista**: la stima con `stima_con_incertezza` (mai un numero secco) e, accanto,
  **Fattori principali**: i valori con cui il modello ha stimato;
- **Storico vs previsto**: le barre raggruppate previsto/reale di uno stato, con la banda sul
  previsto, e **Affidabilità modello**: le metriche lette dai metadati del modello;
- **Storico delle previsioni** salvate e, in fondo, **i tuoi raccolti** per anno e per alveare.

Il mockup mostra una previsione per alveare e per mese: il modello stima la resa media per colonia
di uno stato USA in un anno (dati USDA). La pagina lo dice e mostra solo quello che il modello sa.
Contiene anche ciò che era la pagina Dashboard (M6-T7), che il mockup non ha. Non carica il modello
e non scrive query: chiama i servizi.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from avvio import (
    CHIAVE_UTENTE,
    alveari_dell_apiario,
    apiari,
    avvia,
    confronto_previsto_reale,
    dashboard_apiario,
    intervalli_parametri,
    metriche_modello,
    modello,
    stati_prevedibili,
    storico_previsioni,
    svuota_letture,
)
from schede import Voce, csv_per_excel, elenco, testata
from ui import (
    DATO_MANCANTE,
    blocco_vuoto,
    formatta_numero,
    grafico_barre,
    grafico_serie,
    mostra_errore,
    sidebar,
    stima_con_incertezza,
)

from beewatch.exceptions import BeeWatchError, ValidationError

DAI_DATI = "Dai dati storici di uno stato"
A_MANO = "Con parametri scritti a mano"
NESSUNO = 0  # nel selettore: nessun alveare collegato / tutti gli alveari
STATO_PREDEFINITO = "CA"  # California: il primo produttore del dataset
PREVISTO = "Previsto dal modello"
REALE = "Reale (USDA)"
FONTE_RACCOLTI = "raccolti registrati nel quaderno dell'apiario (pagina Alveari e seed)."
FONTE_USDA = "USDA NASS, Honey Production 1998–2012; stime del modello in uso."

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


def testo_feature(valore) -> str:
    """Stato e anno come sono, i numeri all'italiana; un valore mancante diventa «—»."""
    if isinstance(valore, str | int):
        return str(valore)
    return formatta_numero(valore, 2)


def mostra_risultato(risultato) -> None:
    """La card «Produzione prevista» e, accanto, «Fattori principali»."""
    sinistra, destra = st.columns([2, 1])
    with sinistra, st.container(key="bw_card_prevista"):
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
            f"Stimata dal modello **{risultato.versione_modello}** · errore medio sul "
            f"2010–2012: ±{formatta_numero(risultato.errore_medio_kg)} kg."
        )
        if risultato.retrospettiva:
            st.caption(
                f"Il {risultato.anno} è già nei dati: è una prova a ritroso. La resa vera di "
                "quell'anno non entra nella stima."
            )
        if risultato.parametri_manuali:
            st.caption(
                "Le simulazioni non si salvano: lo storico raccoglie le previsioni sui dati."
            )
        elif risultato.id is not None:
            st.caption("Salvata nello storico qui sotto.")
    with destra, st.container(key="bw_card_fattori"):
        st.subheader("Fattori principali")
        st.caption("I valori con cui il modello ha stimato.")
        elenco(
            [
                Voce(ETICHETTE_FEATURE.get(nome, nome), testo_feature(valore))
                for nome, valore in risultato.feature.items()
            ],  # fmt: skip
            "",
        )


def barre_previsto_reale(confronto: pd.DataFrame) -> pd.DataFrame:
    """Dalla tabella larga del servizio a quella lunga del grafico, con la banda sul previsto."""
    previsto = confronto.assign(
        serie=PREVISTO,
        kg=confronto["previsto_kg"],
        errore_su=confronto["superiore_kg"] - confronto["previsto_kg"],
        errore_giu=confronto["previsto_kg"] - confronto["inferiore_kg"],
    )
    # Il reale non ha banda: NaN e non zero, così non compare nemmeno la stanghetta.
    nessuna = float("nan")
    reale = confronto.assign(
        serie=REALE, kg=confronto["reale_kg"], errore_su=nessuna, errore_giu=nessuna
    )
    colonne = ["anno", "serie", "kg", "errore_su", "errore_giu"]
    return pd.concat([previsto[colonne], reale[colonne]], ignore_index=True)


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

servizi = avvia("Previsioni", "📈")
attivo = sidebar()
utente = st.session_state[CHIAVE_UTENTE]

azioni = testata("Previsioni", "Analisi e previsioni di produzione del miele tramite Machine "
                 "Learning.")  # fmt: skip

# Sempre visibile, prima di tutto il resto (DoD: non in un espansore).
st.warning(LIMITI, icon="⚠️")

try:
    apiari(utente)  # la sidebar non solleva: se il database è giù, lo dice il corpo
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

try:
    stato_modello = modello()
except BeeWatchError as errore:
    mostra_errore(errore)
    stato_modello = None

# --------------------------------------------------------------------------- #
# Controlli
# --------------------------------------------------------------------------- #

risultato = None
storico_di = st.session_state.get("storico_alveare", NESSUNO)
if storico_di not in (NESSUNO, *codici_alveari):
    storico_di = NESSUNO
if stato_modello is not None:
    with st.container(key="bw_card_controlli"):
        modo = st.radio("Come vuoi prevedere", [DAI_DATI, A_MANO], horizontal=True, key="modo")
        try:
            intervalli = intervalli_parametri() if modo == A_MANO else ()
        except BeeWatchError as errore:
            mostra_errore(errore)
            intervalli = None

        if intervalli is not None:
            primo = min(s.primo_anno for s in stati)
            ultimo = max(s.ultimo_anno for s in stati)
            with st.form("previsione", border=False):
                colonne = st.columns([1.3, 1, 1.3, 1.2], vertical_alignment="bottom")
                codice = colonne[0].selectbox(
                    "Stato USA", options=list(nomi_stati), format_func=nomi_stati.__getitem__,
                    key="previsione_stato",
                )  # fmt: skip
                anno = colonne[1].number_input(
                    "Anno", min_value=primo, max_value=ultimo, value=ultimo, step=1,
                    key="previsione_anno",
                    help=f"Dal {primo} al {ultimo}: il {ultimo} è il solo anno davvero futuro.",
                )  # fmt: skip
                valori = {}
                collegato = NESSUNO
                if modo == DAI_DATI:
                    if codici_alveari:
                        collegato = colonne[2].selectbox(
                            "Collega a un alveare (facoltativo)",
                            options=[NESSUNO, *codici_alveari],
                            index=[NESSUNO, *codici_alveari].index(storico_di),
                            format_func={NESSUNO: "Nessun alveare", **codici_alveari}.__getitem__,
                            # La chiave segue lo storico scelto: così la proposta si aggiorna.
                            key=f"previsione_alveare_{storico_di}",
                        )
                    else:
                        colonne[2].caption("Nessun alveare nell'apiario attivo.")
                premuto = colonne[3].form_submit_button(
                    "Aggiorna previsione", type="primary", key="previsione_invia",
                    icon=":material/refresh:", width="stretch",
                )  # fmt: skip
                if modo == A_MANO:
                    colonne = st.columns(len(intervalli) or 1)
                    for colonna, intervallo in zip(colonne, intervalli, strict=False):
                        with colonna:
                            valori[intervallo.campo] = campo_parametro(intervallo)
            st.caption(
                f"Modello in uso: **{stato_modello.versione}** ({stato_modello.algoritmo}), "
                f"addestrato su {stato_modello.righe_addestramento} righe."
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
# Produzione prevista e fattori principali
# --------------------------------------------------------------------------- #

if risultato is not None:
    mostra_risultato(risultato)

# --------------------------------------------------------------------------- #
# Storico vs previsto e affidabilità del modello (la pagina Dashboard di M6-T7)
# --------------------------------------------------------------------------- #

sinistra, destra = st.columns([2, 1])
with sinistra, st.container(key="bw_card_confronto"):
    st.subheader("Storico vs previsto")
    scelto = st.selectbox(
        "Stato per il confronto previsto/reale", options=list(nomi_stati),
        index=list(nomi_stati).index(STATO_PREDEFINITO) if STATO_PREDEFINITO in nomi_stati else 0,
        format_func=nomi_stati.__getitem__, key="dashboard_stato",
    )  # fmt: skip
    if stato_modello is None:  # l'errore è già detto in cima: qui una riga sola
        st.caption("Senza il modello di previsione non c'è un confronto da mostrare.")
    else:
        try:
            confronto = confronto_previsto_reale(scelto)
        except BeeWatchError as errore:
            mostra_errore(errore)
        else:
            grafico_barre(
                barre_previsto_reale(confronto).assign(anno=lambda d: d["anno"].astype(str)),
                "anno", "kg", f"Previsto e reale in {nomi_stati[scelto]}",
                etichetta_x="Anno", etichetta_y="Resa per colonia (kg)", fonte=FONTE_USDA,
                gruppo="serie", errore_su="errore_su", errore_giu="errore_giu",
            )  # fmt: skip
            st.caption(
                "Ogni stima usa solo gli anni precedenti a quello stimato. Il modello salvato però "
                "è stato addestrato anche su questi anni: il confronto mostra quanto si adatta ai "
                "dati, non quanto sa prevedere il futuro. Quella prova è l'errore medio accanto, "
                "misurato su anni che il modello non aveva visto."
            )

with destra, st.container(key="bw_card_affidabilita"):
    st.subheader("Affidabilità modello")
    metriche = None
    if stato_modello is None:  # l'errore è già detto in cima: qui una riga sola
        st.caption("Le metriche compaiono quando il modello è al suo posto.")
    else:
        try:
            metriche = metriche_modello()
        except BeeWatchError as errore:
            mostra_errore(errore)
    if metriche is not None:
        elenco([
            Voce("R²", formatta_numero(metriche.r2, 2)),
            Voce("Errore medio (MAE)", f"{formatta_numero(metriche.mae_kg)} kg"),
            Voce("RMSE", f"{formatta_numero(metriche.rmse_kg)} kg"),
            Voce("Errore in validazione", f"{formatta_numero(metriche.cv_mae_kg)} kg"),
            Voce("Dataset", f"{metriche.righe_addestramento} righe"),
            Voce("Modello", f"{metriche.versione} ({metriche.algoritmo})"),
        ], "")  # fmt: skip
        st.caption(
            f"Il riferimento più forte, «{metriche.migliore_baseline}», sbaglia in media di "
            f"{formatta_numero(metriche.migliore_baseline_mae_kg)} kg. Metriche lette da "
            "`models/`: si aggiornano da sole se il modello viene riaddestrato."
        )

# --------------------------------------------------------------------------- #
# Lo storico delle previsioni
# --------------------------------------------------------------------------- #

with st.container(key="bw_card_storico"):
    titolo, filtro = st.columns([2, 1], vertical_alignment="bottom")
    alveare_filtro = None if storico_di == NESSUNO else storico_di
    with titolo:
        st.subheader(
            "Storico delle previsioni"
            if alveare_filtro is None
            else f"Storico delle previsioni dell'alveare {codici_alveari[alveare_filtro]}"
        )
    filtro.selectbox(
        "Storico di", options=[NESSUNO, *codici_alveari],
        format_func={NESSUNO: "Tutti gli alveari", **codici_alveari}.__getitem__,
        key="storico_alveare",
        help="Le previsioni salvate collegate a un alveare dell'apiario attivo, o tutte.",
    )  # fmt: skip
    try:
        storico = storico_previsioni(utente, alveare_filtro)
    except BeeWatchError as errore:
        mostra_errore(errore)
        storico = None
    if storico is not None:
        if storico:
            righe = [riga_storico(p, nomi_stati) for p in storico]
            st.dataframe(righe, hide_index=True, width="stretch")
            with azioni:
                _, esporta = st.columns([1.4, 1])
                esporta.download_button(
                    "Esporta storico", data=csv_per_excel(pd.DataFrame(righe)),
                    file_name="previsioni.csv", mime="text/csv", key="previsioni_esporta",
                    icon=":material/download:", type="primary", width="stretch",
                )  # fmt: skip
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
# I raccolti dell'apiario (la pagina Dashboard di M6-T7)
# --------------------------------------------------------------------------- #

if attivo is not None:
    try:
        dati = dashboard_apiario(utente, attivo.id)
    except BeeWatchError as errore:
        mostra_errore(errore)
        dati = None
    if dati is not None and not dati.raccolti_per_anno.empty:
        with st.container(key="bw_card_raccolti"):
            st.subheader(f"I tuoi raccolti · {attivo.nome}")
            st.caption(
                f"{formatta_numero(dati.produzione_totale_kg)} kg in tutto, "
                f"{formatta_numero(dati.media_per_alveare_kg)} kg in media per alveare attivo."
            )
            serie, distribuzione = st.columns(2)
            with serie:
                grafico_serie(
                    dati.raccolti_per_anno.assign(anno=dati.raccolti_per_anno["anno"].astype(str)),
                    "anno", "kg", "Produzione per anno e per alveare", etichetta_x="Anno",
                    etichetta_y="Miele raccolto (kg)", fonte=FONTE_RACCOLTI, gruppo="alveare",
                )  # fmt: skip
            with distribuzione:
                grafico_barre(
                    dati.per_alveare, "alveare", "kg",
                    "Distribuzione della produzione fra gli alveari", etichetta_x="Alveare",
                    etichetta_y="Miele raccolto in tutto (kg)", fonte=FONTE_RACCOLTI,
                )  # fmt: skip
            st.caption(
                "«Intero apiario» raccoglie i chili registrati senza indicare l'alveare: sono "
                "smielature comuni, e dividerle fra gli alveari sarebbe inventare."
            )

st.caption(
    "Le stime sono in chili di miele per colonia, arrotondati al chilo: i dati di partenza non "
    "hanno più precisione. La banda contiene la parte di errori indicata accanto alla stima; "
    "quando è più larga della stima stessa, il valore centrale non si mostra. Fonte: USDA NASS, "
    "Honey Production 1998–2012."
)
