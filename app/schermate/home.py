"""
BeeWatch AI - Home: la panoramica (M6-T1, con gli helper condivisi di M6-T2).

Dopo l'accesso è la prima pagina del menu (M6-T11: il punto d'ingresso `app/Home.py` è diventato
il router che costruisce il menu). Mostra quattro numeri, l'apiario attivo e lo stato del modello.
Non contiene logica applicativa: chiede i dati ai servizi (tramite `avvio.py`, che li tiene in
cache) e li disegna con gli helper di `ui.py`.
"""

from __future__ import annotations

import streamlit as st
from avvio import CHIAVE_UTENTE, TTL_LETTURE_SECONDI, avvia, modello, panoramica
from ui import (
    AZIONE_NESSUN_APIARIO,
    NESSUN_APIARIO,
    blocco_vuoto,
    intestazione,
    metrica,
    mostra_errore,
    sidebar,
)

from beewatch.exceptions import BeeWatchError, ModelError

servizi = avvia("Home")
attivo = sidebar()

intestazione(
    "🐝 BeeWatch AI",
    "Il quaderno di campo dell'apicoltore: le ispezioni, una stima della produzione con il suo "
    "margine d'errore e un assistente che riassume le note.",
)

try:
    quadro = panoramica(st.session_state[CHIAVE_UTENTE])
except BeeWatchError as errore:
    mostra_errore(errore)
    st.stop()

if attivo is None:
    blocco_vuoto(NESSUN_APIARIO, AZIONE_NESSUN_APIARIO)
else:
    st.caption(f"Apiario attivo: **{attivo.nome}** · {len(quadro.apiari)} in tutto")

colonne = st.columns(4)
with colonne[0]:
    metrica("Alveari attivi", quadro.alveari_attivi, None)
with colonne[1]:
    metrica("Ispezioni (30 giorni)", quadro.ispezioni_30_giorni, None)
with colonne[2]:
    metrica("Produzione stagione", quadro.produzione_stagione_kg, "kg")
with colonne[3]:
    metrica(
        "Da controllare",
        quadro.alveari_da_controllare,
        None,
        aiuto="Attivi e mai ispezionati, o non ispezionati da oltre 30 giorni.",
    )
st.caption(f"Dati aggiornati al massimo {TTL_LETTURE_SECONDI} secondi fa.")

st.divider()

st.subheader("Stato del sistema")
try:
    stato = modello()
    st.caption(
        f"Modello di previsione **{stato.versione}** ({stato.algoritmo}), "
        f"errore medio ±{stato.mae_kg:.1f} kg sul 2010–2012."
    )
except ModelError as errore:
    st.warning(f"Il modello di previsione non è disponibile: {errore}")
st.caption(f"Assistente AI: {servizi.descrizione_llm}.")

st.divider()
st.caption(
    "BeeWatch AI è un progetto didattico: le stime e i riepiloghi sono strumenti di supporto, "
    "non sostituiscono la tua osservazione né il parere di un veterinario o di un tecnico apistico."
)
