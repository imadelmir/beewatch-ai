# Model card · Previsione della resa per colonia

> **Stato** in costruzione: dati, validazione e baseline (M4-T1). Feature,
> modelli, metriche finali, intervallo e limiti arrivano con M4-T2 … M4-T6.
> **Codice** `beewatch/ml/train.py` · **Test** `tests/test_train.py`

## Che cosa prevede

La **resa per colonia** (`resa_per_colonia_kg`, chili di miele per colonia in un
anno) di uno stato USA, a partire dalla sua storia. È il target scelto in M2-T3:
l'unica grandezza biologica del dataset, indipendente dalla scala. Il modello
non conosce il singolo alveare dell'utente (vedi i limiti in
[`dati.md`](markdown/M2-dati/dati.md)).

## Dati

| | |
|---|---|
| Sorgente | tabella `produzione_usda` di MySQL, query **Q8** (`ProduzioneUsdaRepository.dati_addestramento`); il CSV non viene mai letto dal codice di ML |
| Origine | `data/honeyproduction.csv`, USDA/NASS via Kaggle, CC0, SHA-256 `70a831b5…ed038e` ([scheda](../data/README.md)), caricato con `python scripts/run_etl.py` |
| Pannello | **40 stati con tutti i 15 anni (1998–2012), 600 righe**. I 4 stati con serie incompleta (MD, NV, OK, SC) restano nel database ma fuori dall'addestramento (regola R10) |
| Colonne | `codice_stato`, `anno`, `numero_colonie`, `resa_per_colonia_kg` |

## Validazione

**Hold-out temporale**: addestramento 1998–2009 (**480 righe**), verifica
2010–2012 (**120 righe**, gli stessi 40 stati). È la divisione di M2-T3. Uno
split casuale metterebbe nell'addestramento anni successivi a quelli da
prevedere: con dati che hanno una tendenza nel tempo, e con feature che useranno
l'anno precedente, sarebbe informazione dal futuro.

Ogni previsione riguarda **un anno alla volta**: per l'anno *t* si usa solo ciò
che si sa alla fine dell'anno *t − 1*.

La cross-validation temporale sull'addestramento è di M4-T4.

## Baseline

Le metriche vengono tutte dalla stessa funzione (`metriche()`), quella che
valuterà anche i modelli. Valori sulla verifica 2010–2012, kg per colonia:

| Baseline | Definizione | MAE | RMSE | R² |
|---|---|---|---|---|
| Media globale | resa media dell'addestramento | 6,655 | 8,371 | −0,313 |
| Media dello stato | resa media dello stato nell'addestramento | 5,727 | 6,798 | 0,134 |
| Media dello stato + tendenza annuale | media dello stato + pendenza comune × (anno − anno medio dello stato); pendenza stimata con i minimi quadrati sugli scarti dalla media del proprio stato: **−0,533 kg/anno** | 4,168 | 5,435 | 0,447 |
| **Persistenza** | resa dello stesso stato nell'anno precedente | **4,063** | **5,296** | **0,474** |

La baseline più forte è la **persistenza**: chi prevede «come l'anno scorso»
sbaglia in media di 4,06 kg.

### Confronto con M2-T3

M2-T3 aveva misurato le stesse baseline su **tutte le 626 righe** (44 stati,
addestramento di 506 righe). Rifatte con questo codice su quelle righe:

| Baseline | M2-T3 | Questo codice, 626 righe | Questo codice, pannello Q8 |
|---|---|---|---|
| Media globale | 6,46 | 6,46 | 6,66 |
| Media dello stato | 5,73 | 5,73 | 5,73 |
| Media dello stato + tendenza | 4,25 | 4,17 | 4,17 |
| Persistenza | — (4,06 nella verifica del 6 ottobre) | 4,06 | 4,06 |

- La **media globale** cambia fra 626 e 600 righe perché i 4 stati esclusi
  pesano sulla media; la verifica è la stessa.
- La **tendenza** non coincide con il 4,25 di M2-T3 perché M2-T3 non scrive
  come stimava la pendenza. Con una retta stimata su tutte le righe insieme,
  senza togliere prima la media di ogni stato, sulle 626 righe si ottiene 4,26.
  Questo codice toglie la media dello stato, il modo corretto quando gli stati
  hanno livelli diversi. Sul pannello Q8, che è bilanciato, i due metodi danno
  lo stesso valore: 4,17.

Gli stessi numeri sono controllati da test di integrazione sul database
(`tests/test_train.py`).

## Criterio di accettazione — da decidere (DA-05)

M2-T3 ha dichiarato la soglia **MAE < 4,25 kg**. Sul dataset di training reale
due baseline fanno già meglio: la tendenza (4,17) e la persistenza (4,06).

| Opzione | Soglia |
|---|---|
| mantenere la soglia dichiarata in M2-T3 | MAE < 4,25 kg |
| battere la baseline più forte (raccomandata nel documento di passaggio) | MAE < 4,06 kg |

La scelta va fatta prima di confrontare i modelli (M4-T3).

## Da completare

- Feature e feature escluse per leakage (M4-T2)
- Modelli confrontati e scelta motivata (M4-T3)
- Cross-validation temporale (M4-T4), tuning (M4-T5)
- Metriche finali, residui, importanza delle variabili, intervallo di
  previsione, limiti, quando non usarlo (M4-T6)
