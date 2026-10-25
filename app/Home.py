"""
BeeWatch AI - Home: la panoramica (M6-T1).

Punto d'ingresso dell'interfaccia Streamlit. Mostra quattro numeri, l'apiario attivo e lo stato
del modello. Non contiene logica applicativa: chiede i dati ai servizi (tramite `avvio.py`, che li
tiene in cache) e li disegna. Le sei pagine sono nel menu a sinistra, nell'ordine del prefisso
numerico del file in `app/pages/`.

Avvio in locale (dalla radice del progetto, dove sta `.streamlit/config.toml`):

    streamlit run app/Home.py

Avvio nel contenitore:

    docker compose up -d
"""

from __future__ import annotations

import streamlit as st
from avvio import (
    CHIAVE_UTENTE,
    TTL_LETTURE_SECONDI,
    apiario_attivo,
    avvia,
    modello,
    panoramica,
    scegli_apiario_iniziale,
)

from beewatch.exceptions import BeeWatchError, ModelError

servizi = avvia("Home")

st.title("🐝 BeeWatch AI")
st.write(
    "Il quaderno di campo dell'apicoltore: le ispezioni, una stima della produzione con il suo "
    "margine d'errore e un assistente che riassume le note."
)

try:
    quadro = panoramica(st.session_state[CHIAVE_UTENTE])
except BeeWatchError as errore:
    st.error("Non riesco a leggere i dati.")
    st.code(str(errore), language="text")
    st.stop()

scegli_apiario_iniziale(quadro.apiari)
attivo = apiario_attivo(quadro.apiari)

if not quadro.apiari:
    st.info(
        "Nessun apiario registrato. Vai su **Alveari** per aggiungerne uno: da lì comincia tutto.",
        icon="🐝",
    )
else:
    st.caption(f"Apiario attivo: **{attivo.nome}** · {len(quadro.apiari)} in tutto")

colonne = st.columns(4)
colonne[0].metric("Alveari attivi", quadro.alveari_attivi)
colonne[1].metric("Ispezioni (30 giorni)", quadro.ispezioni_30_giorni)
colonne[2].metric(
    "Produzione stagione",
    f"{quadro.produzione_stagione_kg:,.1f} kg".replace(",", " ").replace(".", ","),
)
colonne[3].metric(
    "Da controllare",
    quadro.alveari_da_controllare,
    help="Attivi e mai ispezionati, o non ispezionati da oltre 30 giorni.",
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
