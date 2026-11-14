"""
BeeWatch AI - Dashboard: la prima pagina dopo l'accesso (M6-T1; aspetto del mockup).

Come la tavola «Dashboard» del mockup:

- in cima il titolo con il benvenuto, la data di oggi e «Nuova ispezione»;
- quattro card: alveari attivi, ispezioni degli ultimi 30 giorni, miele della stagione, stato
  generale (ricavato dagli stati degli alveari dell'apiario attivo);
- la produzione registrata per anno e la ciambella «Stato alveari»;
- «Ultime notifiche» e «Prossime scadenze», cioè i promemoria delle Impostazioni (M6-T13);
- in basso a destra, «Hai bisogno di aiuto?» porta all'assistente.

Dove il mockup mostra numeri che l'app non ha (una produzione «stimata nei prossimi 3 mesi», un
«+2 questo mese»), qui ci sono quelli veri: la produzione registrata, e una riga che dice da dove
viene il numero. Nessun dato inventato. La pagina chiede tutto ai servizi, tramite `avvio.py`.
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st
from avvio import (
    CHIAVE_UTENTE,
    alveari_dell_apiario,
    avvia,
    dashboard_apiario,
    modello,
    nome_in_accesso,
    panoramica,
    promemoria,
)
from schede import (
    Fetta,
    Voce,
    disegna,
    elenco,
    figura_area,
    figura_ciambella,
    legenda_ciambella,
    pillola_data,
    scheda_kpi,
    testata,
    titolo_card,
)
from ui import (
    AZIONE_NESSUN_APIARIO,
    NESSUN_APIARIO,
    blocco_vuoto,
    formatta_data,
    mostra_errore,
    sidebar,
)

from beewatch.exceptions import BeeWatchError, ModelError
from beewatch.models import StatoAlveare

ATTENZIONE = (StatoAlveare.IN_OSSERVAZIONE, StatoAlveare.DEBOLE, StatoAlveare.SCIAMATO)
MASSIMO_VOCI = 4  # righe per card, come nel mockup

servizi = avvia("Home")
attivo = sidebar()
utente = st.session_state[CHIAVE_UTENTE]
oggi = date.today()

nome = (nome_in_accesso() or "").split(" ")[0]
azioni = testata("Dashboard", f"Benvenuto {nome}, ecco il riepilogo della tua attività.")
with azioni:
    data, nuova = st.columns([3, 2], vertical_alignment="center")
    with data:
        pillola_data(oggi)
    if nuova.button(
        "Nuova ispezione", type="primary", icon=":material/add:", key="home_nuova_ispezione"
    ):
        st.switch_page("pages/2_Ispezioni.py")

try:
    quadro = panoramica(utente)
except BeeWatchError as errore:
    mostra_errore(errore)
    st.stop()

if attivo is None:
    blocco_vuoto(NESSUN_APIARIO, AZIONE_NESSUN_APIARIO)
else:
    st.caption(f"Apiario attivo: **{attivo.nome}** · {len(quadro.apiari)} in tutto")

# --- Gli alveari dell'apiario attivo: servono alla card «Stato generale» e alla ciambella -------
try:
    alveari = alveari_dell_apiario(utente, attivo.id) if attivo else ()
except BeeWatchError as errore:
    mostra_errore(errore)
    alveari = ()
sani = sum(a.stato == StatoAlveare.IN_SALUTE for a in alveari)
in_attenzione = sum(a.stato in ATTENZIONE for a in alveari)
critici = sum(a.stato == StatoAlveare.MORTO for a in alveari)

if not quadro.alveari_attivi:
    stato_generale, nota_stato = "—", "Nessun alveare attivo"
elif critici:
    stato_generale, nota_stato = "Critico", f"{critici} alveari persi"
elif in_attenzione or quadro.alveari_da_controllare:
    stato_generale = "Attenzione"
    nota_stato = f"{in_attenzione + quadro.alveari_da_controllare} alveari da seguire"
else:
    stato_generale, nota_stato = "Buono", "Tutti gli alveari in salute"

# --- Le quattro card --------------------------------------------------------------------------
colonne = st.columns(4)
with colonne[0]:
    scheda_kpi(
        "alveare", "Alveari attivi", quadro.alveari_attivi, None,
        nota=f"in {len(quadro.apiari)} apiari" if len(quadro.apiari) != 1 else "in 1 apiario",
    )  # fmt: skip
with colonne[1]:
    scheda_kpi("ispezioni", "Ispezioni (30 giorni)", quadro.ispezioni_30_giorni, None,
               nota="negli ultimi 30 giorni")  # fmt: skip
with colonne[2]:
    scheda_kpi("miele", "Produzione stagione", quadro.produzione_stagione_kg, "kg",
               nota=f"miele raccolto nel {oggi.year}")  # fmt: skip
with colonne[3]:
    scheda_kpi(
        "salute", "Stato generale", stato_generale, None, nota=nota_stato, evidenzia=True,
        aiuto=f"Dagli stati degli alveari e dai promemoria. Da controllare: "
        f"{quadro.alveari_da_controllare} (mai ispezionati o non da oltre la soglia scelta).",
    )  # fmt: skip

# --- Produzione e stato degli alveari ---------------------------------------------------------
sinistra, destra = st.columns([3, 2])
with sinistra, st.container(key="bw_card_produzione"):
    titolo_card("Produzione registrata", "(per anno)")
    try:
        dati = dashboard_apiario(utente, attivo.id) if attivo else None
    except BeeWatchError as errore:
        mostra_errore(errore)
        dati = None
    if dati is None or dati.raccolti_per_anno.empty:
        st.caption("Ancora nessun raccolto registrato: si aggiungono dalla pagina Alveari.")
    else:
        per_anno = dati.raccolti_per_anno.groupby("anno", as_index=False)["kg"].sum()
        disegna(figura_area(per_anno["anno"].astype(str), per_anno["kg"], "kg"), "home_produzione")
        st.caption("Fonte: i raccolti registrati nel quaderno dell'apiario.")

with destra, st.container(key="bw_card_stato"):
    titolo_card("Stato alveari")
    fette = [
        Fetta("In salute", sani, "accento"),
        Fetta("Attenzione", in_attenzione, "attenzione"),
        Fetta("Critici", critici, "testo2"),
    ]
    if not alveari:
        st.caption("Nessun alveare attivo in questo apiario.")
    else:
        ciambella, legenda = st.columns([1, 1], vertical_alignment="center")
        with ciambella:
            disegna(figura_ciambella(fette, len(alveari)), "home_stato")
        with legenda:
            legenda_ciambella(fette, len(alveari))

# --- Notifiche e scadenze: i promemoria delle Impostazioni (M6-T13) ----------------------------
try:
    avvisi = promemoria(utente)
except BeeWatchError as errore:
    mostra_errore(errore)
    avvisi = None

notifiche: list[Voce] = []
scadenze: list[Voce] = []
if avvisi is not None:
    for codice, giorno, rischio in avvisi.a_rischio:
        notifiche.append(
            Voce(
                f"Ispezione con {rischio.lower()} per l'alveare {codice}.",
                formatta_data(giorno),
                "avviso",
                "attenzione",
            )  # fmt: skip
        )
    for codice, ultima in avvisi.da_controllare:
        quando = f"ultima il {formatta_data(ultima)}" if ultima else "mai ispezionato"
        notifiche.append(
            Voce(f"L'alveare {codice} va ricontrollato ({quando}).", "", "info", "accento")
        )
        scadenza = ultima + timedelta(days=avvisi.giorni) if ultima else None
        scadenze.append(
            Voce(f"Ispezione alveare {codice}",
                 "da fare" if scadenza is None else f"scaduta il {formatta_data(scadenza)}")
        )  # fmt: skip

sinistra, destra = st.columns(2)
with sinistra, st.container(key="bw_card_notifiche"):
    titolo_card("Ultime notifiche")
    elenco(notifiche[:MASSIMO_VOCI], "Nessuna notifica: tutti gli alveari sono stati visti di "
                                     "recente.")  # fmt: skip
    if st.button("Visualizza le ispezioni", key="home_notifiche", width="stretch"):
        st.switch_page("pages/2_Ispezioni.py")
with destra, st.container(key="bw_card_scadenze"):
    giorni = avvisi.giorni if avvisi else 30
    titolo_card("Prossime scadenze", f"(un'ispezione ogni {giorni} giorni)")
    elenco(scadenze[:MASSIMO_VOCI], "Nessuna ispezione in scadenza.")
    if st.button("Cambia la soglia", key="home_soglia", width="stretch"):
        st.switch_page("pages/8_Impostazioni.py")

# --- In fondo: lo stato del sistema, in piccolo, e l'avvertenza --------------------------------
try:
    stato = modello()
    riga_modello = (
        f"Modello di previsione **{stato.versione}** ({stato.algoritmo}), errore medio "
        f"±{stato.mae_kg:.1f} kg sul 2010–2012"
    )
except ModelError as errore:
    st.warning(f"Il modello di previsione non è disponibile: {errore}")
    riga_modello = "Modello di previsione non disponibile"
st.caption(
    f"{riga_modello} · Assistente AI: {servizi.descrizione_llm}. BeeWatch AI è un progetto "
    "didattico: stime e riepiloghi aiutano, non sostituiscono la tua osservazione né il parere di "
    "un veterinario o di un tecnico apistico."
)

# --- «Hai bisogno di aiuto?», in basso a destra -----------------------------------------------
with st.container(key="bw_aiuto"):
    testo, bottone = st.columns([4, 1], vertical_alignment="center")
    testo.markdown("**Hai bisogno di aiuto?**  \nChiedi al tuo assistente AI!")
    if bottone.button("", icon=":material/chat:", key="home_aiuto", help="Apri l'assistente AI"):
        st.switch_page("pages/4_Assistente_AI.py")
