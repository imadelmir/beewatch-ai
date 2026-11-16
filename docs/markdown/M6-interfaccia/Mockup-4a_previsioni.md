# Mockup · Blocco 4a · Previsioni

> **Richiesta** il progetto come il mockup ad alta fedeltà, solo con le funzioni vere (2026-11-14)
> **Stato** completato
> **Tavole** 30–32 («Intelligenza artificiale»: Previsioni), chiaro e scuro
> **Collegati** → `app/pages/3_Previsione.py` · `app/pages/5_Dashboard.py` (eliminata) ·
> `tests/test_pagina_previsioni_modello.py`

## Obiettivo

La pagina Previsioni del mockup, e dentro di lei quello che era la pagina Dashboard di M6-T7: il
mockup non ha una seconda «dashboard», e i suoi contenuti (modello e confronto previsto/reale)
sono proprio quelli delle card di Previsioni.

## Cosa c'è

| Parte del mockup | Nell'app | Da dove |
|---|---|---|
| «Previsioni», «Analisi e previsioni di produzione del miele tramite Machine Learning.» | sì | — |
| Esporta report (in alto a destra) | **Esporta storico**: le previsioni salvate in CSV per Excel | storico |
| Seleziona alveare · Periodo · Modello · Aggiorna previsione | modo (dai dati di uno stato / parametri a mano), **stato USA**, **anno**, alveare collegato facoltativo, «Aggiorna previsione»; il modello in uso sotto | servizi |
| Produzione prevista: «18.6 kg» e la linea dei mesi | la **resa per colonia** con la sua **banda d'incertezza** (mai un numero senza banda) | `prevedi_produzione` |
| Fattori principali (fioriture, temperatura, umidità…) | **i valori con cui il modello ha stimato**: resa dell'anno prima, media dei tre anni prima, colonie | la stima |
| Storico vs previsto (kg per mese) | **previsto e reale per anno** di uno stato, con la banda sul previsto | `confronto_previsto_reale` |
| Affidabilità modello: R², MAE, dataset, ultimo training | R², MAE, RMSE, errore in validazione, righe, versione e il confronto con il riferimento | metadati del modello |
| — | Storico delle previsioni salvate, filtrabile per alveare | storico |
| — | **I tuoi raccolti**: per anno e per alveare, con «Intero apiario» | raccolti |

L'avviso sui **limiti di trasferibilità** resta in cima e sempre visibile (DoD di M6-T5): il mockup
mostra una previsione per alveare e per mese, ma il modello stima la resa media di una colonia in
uno stato USA in un anno. La pagina mostra solo quello che il modello sa.

## Decisioni

**1. La Dashboard di M6-T7 entra in Previsioni.** `5_Dashboard.py` non c'è più (nel menu era
«Statistiche» dal blocco 3a). Il confronto previsto/reale e le metriche diventano le card «Storico
vs previsto» e «Affidabilità modello»; i grafici dei raccolti diventano la card «I tuoi raccolti».
I suoi test sono in `tests/test_pagina_previsioni_modello.py`, con gli stessi casi.

**2. Un errore si dice una volta.** Senza il modello, l'errore compare in cima; confronto e
affidabilità lo dicono con una riga, invece di ripeterlo.

**3. Col database spento la pagina si ferma**, come le altre che leggono gli apiari: ora mostra
anche i raccolti.

## Come si prova

| Cosa | Dove |
|---|---|
| limiti, modulo, stima con banda, fattori principali, storico, alveare collegato, simulazione a mano, parametri mancanti, senza modello, feature incompatibili, senza dati USDA, database spento | `tests/test_pagina_previsione.py` |
| le card del modello e dei raccolti, i tre grafici (assi, palette, fonte), intero apiario, confronto e cambio di stato, metriche dai metadati, un solo alveare, senza raccolti, senza apiari, senza modello, confronto che fallisce | `tests/test_pagina_previsioni_modello.py` |
