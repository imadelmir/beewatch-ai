# Model card · Previsione della resa per colonia

> **Stato** in costruzione: dati, validazione e baseline (M4-T1), criterio di
> accettazione (DA-05), feature (M4-T2), confronto fra modelli (M4-T3).
> Cross-validation, tuning, metriche finali, intervallo e limiti arrivano con
> M4-T4 … M4-T6.
> **Codice** `beewatch/ml/train.py`, `beewatch/ml/features.py` · **Notebook** `notebooks/02_modelli.ipynb` · **Test** `tests/test_train.py`, `tests/test_features.py`, `tests/test_confronto_modelli.py`

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

## Criterio di accettazione (DA-05)

Un modello soddisfa il criterio prestazionale **soltanto se**
`MAE_modello < MAE_persistenza`, con le due metriche calcolate da `metriche()`
sulle stesse 120 righe di verifica (2010–2012) del pannello Q8, sullo stesso
target. Il confronto usa i valori **non arrotondati**: la persistenza vale
**4,063428333… kg** (487,6114 kg di errore su 120 righe), e un modello che si
scrive «4,06» può stare sopra o sotto. Nel codice: `soddisfa_criterio()`.

| Soglia | Valore | Ruolo |
|---|---|---|
| battere la persistenza (DA-05) | MAE < 4,063428… kg | **criterio** |
| M2-T3 | MAE < 4,25 kg | riferimento storico: da sola non basta |

Motivazione e coerenza con la specifica:
[`DA-05_criterio_di_accettazione.md`](markdown/M4-machine-learning/DA-05_criterio_di_accettazione.md).
Se nessun modello batte la persistenza, questa model card lo dirà senza
indicare un vincitore.

## Feature

Costruite da `costruisci_feature_storiche()` (i valori degli anni precedenti
dello stesso stato, cercati per chiave) e trasformate da `crea_preprocessore()`,
il `ColumnTransformer` in testa a ogni Pipeline. Ogni feature della riga
(stato, anno *t*) usa solo ciò che si sa alla fine dell'anno *t − 1*.

| Feature | Trasformazione | Perché |
|---|---|---|
| `codice_stato` | one-hot (stato nuovo → tutti zeri) | il livello di resa dello stato |
| `anno` | standardizzato | la tendenza, −0,53 kg l'anno |
| `resa_anno_prima` | mediana se manca, standardizzata | la persistenza, la baseline più forte |
| `resa_media_3_anni_prima` | mediana se manca, standardizzata | un livello recente meno rumoroso di un anno solo |
| `colonie_anno_prima` | `log1p`, mediana se manca, standardizzata | la scala dell'apicoltura dello stato (da 2.000 a 510.000 colonie) |
| `senza_storia` | indicatore | 1 nel primo anno di uno stato (1998), dove le tre feature storiche sono imputate |

**Escluse:** il target dell'anno; `numero_colonie` dello stesso anno (non si
conosce alla fine dell'anno prima); `produzione_totale_kg` e
`valore_produzione_usd` (contengono il target, R5); `scorte_kg` e
`prezzo_per_kg_usd` (mercato, M2-T3; non sono in Q8). Il preprocessore scarta
ogni colonna che non è una feature.

Mediane, medie e scale si imparano solo dalle righe di addestramento. Sulla
verifica 2010–2012 nessuna feature storica manca, e `resa_anno_prima` coincide
con la previsione della persistenza. Motivazioni:
[`M4-T2_feature_preprocessore.md`](markdown/M4-machine-learning/M4-T2_feature_preprocessore.md).

## Confronto fra modelli (M4-T3)

Tre Pipeline con lo stesso preprocessore (M4-T2) e tre regressori con gli
iperparametri di default (il tuning è di M4-T5): **regressione lineare**
(`LinearRegression`), **albero di decisione** (`DecisionTreeRegressor`),
**random forest** (`RandomForestRegressor`, 100 alberi); `random_state = 42`.
Codice: `crea_modelli()` e `confronta_modelli()` in `train.py`.

Tutte le righe della tabella vengono dallo stesso `Confronto`: addestramento
1998–2009 (480 righe), verifica **2010–2012, le stesse 120 righe** per modelli e
baseline, stessa funzione `metriche()`. Kg per colonia:

| | Tipo | MAE | RMSE | R² | DA-05 |
|---|---|---|---|---|---|
| **Random forest** | modello | **3,6558** | **4,5698** | **0,6088** | ✅ soddisfa |
| Regressione lineare | modello | 4,0254 | 5,3358 | 0,4666 | ✅ soddisfa |
| Persistenza | baseline | 4,0634 | 5,2964 | 0,4745 | riferimento |
| Media dello stato + tendenza | baseline | 4,1681 | 5,4350 | 0,4466 | — |
| Albero di decisione | modello | 5,5792 | 6,8581 | 0,1189 | ❌ non soddisfa |
| Media dello stato | baseline | 5,7272 | 6,7982 | 0,1342 | — |
| Media globale | baseline | 6,6546 | 8,3711 | −0,3128 | — |

**Il criterio DA-05, sui valori non arrotondati** (MAE):

| Modello | MAE | MAE − persistenza (4,063428333…) | Esito |
|---|---|---|---|
| Random forest | 3,655800750 | −0,407628 | soddisfa |
| Regressione lineare | 4,025411865 | −0,038016 | soddisfa, di poco |
| Albero di decisione | 5,579183333 | +1,515755 | non soddisfa |

**Anno per anno** (MAE; media e deviazione standard dei tre anni). Il criterio si
decide sulle 120 righe insieme; questa tabella dice quanto il risultato è stabile:

| | 2010 | 2011 | 2012 | media ± dev. std |
|---|---|---|---|---|
| Random forest | 3,499 | 3,387 | 4,082 | 3,656 ± 0,373 |
| Regressione lineare | 4,418 | 3,964 | 3,694 | 4,025 ± 0,366 |
| Persistenza | 4,048 | 4,604 | **3,538** | 4,063 ± 0,533 |
| Media dello stato + tendenza | 4,568 | 4,049 | 3,888 | 4,168 ± 0,355 |
| Albero di decisione | 5,182 | 5,160 | 6,396 | 5,579 ± 0,707 |

La «media ± deviazione standard» chiesta dal backlog qui è fra i tre anni di
verifica; quella fra le pieghe della cross-validation temporale arriva con M4-T4.

**Sensibilità al seed** (informativa, non usata per scegliere): con i seed 0–9 la
random forest va da 3,613 a 3,778 di MAE, sempre sotto la persistenza; l'albero
da 5,213 a 5,511. La regressione lineare non ha casualità.

### Scelta

**Random forest.** È il solo modello che batte la persistenza con un margine
chiaro (−0,41 kg, il 10 %), su tutte e tre le metriche, e il margine regge con
tutti i seed provati. La regressione lineare soddisfa DA-05 ma per 0,038 kg, e
perde con la persistenza nel 2010 e nel 2012. L'albero singolo fa peggio di
persistenza e tendenza, appena meglio della media dello stato: con gli
iperparametri di default cresce senza limiti di profondità, e probabilmente
impara il rumore dell'addestramento (il tuning di M4-T5 lo verificherà).

Cosa questa scelta **non** dimostra:

- la verifica 2010–2012 è servita anche a scegliere, quindi il 3,656 è un po'
  ottimista; la cross-validation temporale sull'addestramento (M4-T4) dirà se il
  vantaggio regge su altri anni;
- nel 2012 la persistenza (3,538) fa meglio di tutti i modelli: il vantaggio è
  sulla media dei tre anni, non su ogni anno;
- 120 righe sono poche: differenze di qualche centesimo, come quella della
  regressione lineare, non sono distinguibili dal caso.

Il funzionamento tecnico (stesse righe, nessuna informazione dal futuro, seed
riproducibile) è verificato dai test; il risultato prestazionale è quello della
tabella. Il notebook `notebooks/02_modelli.ipynb` rifà il confronto dal database
richiamando `train.py`. Motivazioni:
[`M4-T3_confronto_modelli.md`](markdown/M4-machine-learning/M4-T3_confronto_modelli.md).

## Da completare

- Cross-validation temporale (M4-T4), tuning (M4-T5)
- Metriche finali, residui, importanza delle variabili, intervallo di
  previsione, limiti, quando non usarlo (M4-T6)
