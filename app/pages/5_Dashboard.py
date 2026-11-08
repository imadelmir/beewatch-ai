"""
BeeWatch AI - pagina Dashboard: la visione d'insieme dell'apiario e del modello (M6-T7).

L'anatomia del §6 della specifica:

- **contenuto**, in cima, i quattro KPI dell'apiario attivo; poi la serie annuale dei raccolti per
  alveare e la loro distribuzione; poi il modello: le metriche lette dal suo file di metadati e
  le barre raggruppate previsto/reale per uno stato (il solo **controllo** della pagina);
- **note** in fondo.

Le tabelle arrivano già aggregate con pandas da `dashboard_apiario` e `confronto_previsto_reale`
dei servizi; i grafici usano gli helper di `ui.py` (assi con unità, palette del §3, fonte sotto).
I raccolti registrati per tutto l'apiario, senza indicare l'alveare, compaiono come «Intero
apiario»: non si dividono fra gli alveari per farli tornare.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from avvio import (
    CHIAVE_UTENTE,
    apiari,
    avvia,
    confronto_previsto_reale,
    dashboard_apiario,
    metriche_modello,
    stati_prevedibili,
)
from ui import (
    AZIONE_NESSUN_APIARIO,
    NESSUN_APIARIO,
    blocco_vuoto,
    formatta_numero,
    grafico_barre,
    grafico_serie,
    intestazione,
    metrica,
    mostra_errore,
    sidebar,
)

from beewatch.exceptions import BeeWatchError

FONTE_RACCOLTI = "raccolti registrati nel quaderno dell'apiario (pagina Alveari e seed)."
FONTE_USDA = "USDA NASS, Honey Production 1998–2012; stime del modello in uso."
PREVISTO = "Previsto dal modello"
REALE = "Reale (USDA)"
STATO_PREDEFINITO = "CA"  # California: il primo produttore del dataset


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


# --------------------------------------------------------------------------- #
# Pagina
# --------------------------------------------------------------------------- #

avvia("Dashboard", "📊")
attivo = sidebar()
utente = st.session_state[CHIAVE_UTENTE]

intestazione(
    "📊 Dashboard",
    "L'andamento della produzione nel tempo e il confronto fra previsto e reale.",
)

try:
    apiari(utente)  # la sidebar non solleva: se il database è giù, lo dice il corpo
    dati = dashboard_apiario(utente, attivo.id) if attivo else None
except BeeWatchError as errore:
    mostra_errore(errore)
    st.stop()

# --------------------------------------------------------------------------- #
# L'apiario: KPI e raccolti
# --------------------------------------------------------------------------- #

if dati is None:
    blocco_vuoto(NESSUN_APIARIO, AZIONE_NESSUN_APIARIO)
else:
    st.subheader(f"Raccolti di {attivo.nome}")
    colonne = st.columns(4)
    with colonne[0]:
        metrica("Alveari", dati.numero_alveari, None, aiuto="Gli alveari attivi dell'apiario.")
    with colonne[1]:
        metrica(
            "Produzione totale",
            dati.produzione_totale_kg,
            "kg",
            aiuto="La somma di tutti i raccolti registrati per l'apiario.",
        )
    with colonne[2]:
        metrica(
            "Media per alveare",
            dati.media_per_alveare_kg,
            "kg",
            aiuto="La produzione totale divisa per gli alveari attivi: una media, non la resa "
            "di ciascuno.",
        )
    with colonne[3]:
        metrica("Ultima ispezione", dati.ultima_ispezione, None)

    if dati.raccolti_per_anno.empty:
        blocco_vuoto(
            f"Nessun raccolto registrato per {attivo.nome}.",
            "I grafici della produzione compaiono con il primo raccolto.",
        )
    else:
        grafico_serie(
            dati.raccolti_per_anno.assign(anno=dati.raccolti_per_anno["anno"].astype(str)),
            "anno",
            "kg",
            "Produzione per anno e per alveare",
            etichetta_x="Anno",
            etichetta_y="Miele raccolto (kg)",
            fonte=FONTE_RACCOLTI,
            gruppo="alveare",
        )
        grafico_barre(
            dati.per_alveare,
            "alveare",
            "kg",
            "Distribuzione della produzione fra gli alveari",
            etichetta_x="Alveare",
            etichetta_y="Miele raccolto in tutto (kg)",
            fonte=FONTE_RACCOLTI,
        )
        st.caption(
            "«Intero apiario» raccoglie i chili registrati senza indicare l'alveare: sono "
            "smielature comuni, e dividerle fra gli alveari sarebbe inventare."
        )

# --------------------------------------------------------------------------- #
# Il modello: metriche lette dal file e previsto contro reale
# --------------------------------------------------------------------------- #

st.subheader("Il modello di previsione")
try:
    metriche = metriche_modello()
    stati = stati_prevedibili()
except BeeWatchError as errore:
    mostra_errore(errore)
    st.stop()

colonne = st.columns(4)
with colonne[0]:
    metrica(
        "Errore medio (MAE)",
        metriche.mae_kg,
        "kg",
        aiuto="Di quanti chili per colonia sbaglia in media, sul 2010–2012 mai visto in "
        "addestramento.",
    )
with colonne[1]:
    metrica(
        "RMSE",
        metriche.rmse_kg,
        "kg",
        aiuto="Come il MAE, ma pesa di più gli errori grandi.",
    )
with colonne[2]:
    metrica(
        "R²",
        formatta_numero(metriche.r2, 2),
        None,
        aiuto="Quanta parte della variabilità delle rese il modello spiega (1 = tutta).",
    )
with colonne[3]:
    metrica(
        "Errore medio in validazione",
        metriche.cv_mae_kg,
        "kg",
        aiuto=f"Media su tre periodi diversi (±{formatta_numero(metriche.cv_mae_dev_std_kg)} "
        "kg fra un periodo e l'altro).",
    )
st.caption(
    f"Metriche lette da `models/` (modello **{metriche.versione}**, {metriche.algoritmo}, "
    f"{metriche.righe_addestramento} righe). Il riferimento più forte, "
    f"«{metriche.migliore_baseline}», sbaglia in media di "
    f"{formatta_numero(metriche.migliore_baseline_mae_kg)} kg."
)

if not stati:
    blocco_vuoto(
        "Nessuno stato su cui confrontare: i dati USDA non sono nel database.",
        "Caricali con `python scripts/run_etl.py`.",
    )
    st.stop()

nomi = {s.codice: s.nome for s in stati}
codice = st.selectbox(
    "Stato per il confronto previsto/reale",
    options=list(nomi),
    index=list(nomi).index(STATO_PREDEFINITO) if STATO_PREDEFINITO in nomi else 0,
    format_func=nomi.__getitem__,
    key="dashboard_stato",
)
try:
    confronto = confronto_previsto_reale(codice)
except BeeWatchError as errore:
    mostra_errore(errore)
else:
    grafico_barre(
        barre_previsto_reale(confronto).assign(anno=lambda d: d["anno"].astype(str)),
        "anno",
        "kg",
        f"Previsto e reale in {nomi[codice]}",
        etichetta_x="Anno",
        etichetta_y="Resa per colonia (kg)",
        fonte=FONTE_USDA,
        gruppo="serie",
        errore_su="errore_su",
        errore_giu="errore_giu",
    )
    st.caption(
        "Ogni stima usa solo gli anni precedenti a quello stimato. Il modello salvato però è "
        "stato addestrato anche su questi anni: il confronto mostra quanto si adatta ai dati, "
        "non quanto sa prevedere il futuro. Quella prova è l'errore medio qui sopra, misurato su "
        "anni che il modello non aveva visto."
    )

# --------------------------------------------------------------------------- #
# Note
# --------------------------------------------------------------------------- #

st.caption(
    "I raccolti sono quelli dell'apiario attivo, scelto nella sidebar. Le metriche del modello "
    "si aggiornano da sole se il modello viene riaddestrato: non sono scritte nella pagina."
)
