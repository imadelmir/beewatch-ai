# M4 - T2 · Feature engineering e ColumnTransformer

> **Milestone** M4 · Machine Learning
> **Task** M4-T2
> **Stato** completata
> **Commit** `feat(m4): add history features and the preprocessing ColumnTransformer`
> **Collegati** → [`model_card.md`](../../model_card.md) · [`M4-T1_dataset_baseline.md`](M4-T1_dataset_baseline.md) · [`DA-05_criterio_di_accettazione.md`](DA-05_criterio_di_accettazione.md)

## Obiettivo

Trasformazioni riproducibili in modo **identico** fra addestramento e
previsione, dentro una Pipeline di scikit-learn, senza informazione dal futuro.

## Descrizione

`beewatch/ml/features.py`:

```python
from sklearn.pipeline import Pipeline
from beewatch.ml.features import TARGET, costruisci_feature_storiche, crea_preprocessore
from beewatch.ml.train import carica_dataset_training, dividi_temporale

dati = costruisci_feature_storiche(carica_dataset_training(database))  # Q8 + storia
addestramento, verifica = dividi_temporale(dati)                        # ≤ 2009 | 2010–2012
modello = Pipeline([("prep", crea_preprocessore()), ("modello", ...)])  # M4-T3
modello.fit(addestramento, addestramento[TARGET])
```

| Funzione | Cosa fa |
|---|---|
| `costruisci_feature_storiche(dati)` | aggiunge `resa_anno_prima`, `resa_media_3_anni_prima`, `colonie_anno_prima`, cercando ogni valore per chiave (stato, anno − k) |
| `crea_preprocessore()` | il `ColumnTransformer`: imputazione con la mediana, logaritmo delle colonie, standardizzazione, indicatore «senza storia», one-hot dello stato; scarta ogni altra colonna |
| `FEATURE`, `FEATURE_ESCLUSE` | le colonne usate e quelle escluse, ognuna con il motivo |

## Le feature

| Feature | Trasformazione | Perché |
|---|---|---|
| `codice_stato` | one-hot, `handle_unknown="ignore"` | il livello di resa di ogni stato (clima, flora, pratiche): la media dello stato porta il MAE da 6,66 a 5,73 kg |
| `anno` | standardizzato | la tendenza: −0,53 kg l'anno (M4-T1) |
| `resa_anno_prima` | mediana se manca, standardizzata | è la persistenza, la baseline più forte (MAE 4,063 kg) |
| `resa_media_3_anni_prima` | mediana se manca, standardizzata | un livello recente meno rumoroso di un anno solo |
| `colonie_anno_prima` | `log1p`, mediana, standardizzata | la scala dell'apicoltura dello stato; le colonie vanno da migliaia a mezzo milione, il logaritmo le rende confrontabili |
| `senza_storia` | `MissingIndicator` su `resa_anno_prima` | 1 nel primo anno di uno stato: il modello distingue una mediana imputata da un valore vero |

## Le feature escluse

| Colonna | Perché resta fuori |
|---|---|
| `resa_per_colonia_kg` dell'anno | è il target |
| `numero_colonie` dell'anno | è dello stesso anno: alla fine dell'anno prima non si conosce (si usa quella dell'anno prima) |
| `produzione_totale_kg`, `valore_produzione_usd` | derivate dal target (R5): leakage |
| `scorte_kg`, `prezzo_per_kg_usd` | mercato, non biologia (M2-T3); dello stesso anno sarebbero leakage. Non sono in Q8 |

## Decisioni progettuali

**1. Una sola trasformazione fuori dalla Pipeline, ed è dichiarata.** La DoD
chiede «nessuna trasformazione manuale fuori dalla pipeline», ma un ritardo per
stato ha bisogno delle righe degli anni precedenti, mentre un `ColumnTransformer`
trasforma una riga alla volta. `costruisci_feature_storiche` è quindi l'unica
funzione esterna, la stessa per addestramento e previsione, e **non impara nulla
dai dati**: legge valori passati. Tutto ciò che si stima (mediane, medie e
deviazioni per lo scaling, categorie dello one-hot) sta nel preprocessore e si
impara solo da `fit` sulle righe di addestramento. È la soluzione indicata dal
backlog.

**2. I ritardi si cercano per chiave, non con `shift`.** `shift(1)` prende la
riga precedente: se un anno manca, «l'anno prima» diventerebbe due anni prima.
Cercando (stato, anno − 1) un anno mancante dà un valore mancante. Così la
funzione vale anche per gli stati con serie incompleta e per un ingresso non
ordinato.

**3. La storia attraversa il confine dello split, come la persistenza.** Per il
2011 la resa dell'anno prima è quella vera del 2010: si prevede un anno alla
volta, con ciò che si sa alla fine dell'anno precedente (M4-T1). Nessuna feature
usa l'anno della riga: un test cambia resa e colonie di un anno e controlla che
cambino solo le feature dei tre anni successivi. Sulle 120 righe di verifica
`resa_anno_prima` coincide con la baseline di persistenza.

**4. Il primo anno resta nell'addestramento.** Il 1998 non ha storia: le tre
feature sono mancanti per 40 righe su 480. Le completa la mediana appresa
sull'addestramento, e `senza_storia` le segnala. Le 120 righe di verifica hanno
sempre tre anni di storia.

**5. `numero_colonie` è quella dello stato, mai l'alveare dell'utente.** Il
dataset parte da 2.000 colonie per stato: il numero di alveari di un hobbista è
fuori distribuzione. In previsione `colonie_anno_prima` sarà quella dello stato
di riferimento (M4-T8).

**6. `TARGET` è definito in `features.py`.** `train.py` lo importa da lì: in
M4-T3 `train.py` userà le feature, e la dipendenza va in un solo verso.
`train.TARGET` resta disponibile.

**7. Le feature non sono state scelte guardando la verifica.** Questa task non
misura modelli sul 2010–2012: le feature vengono dal backlog e da M2-T3. Il
confronto con le baseline e il criterio DA-05 sono di M4-T3.

## File coinvolti

| File | Azione |
|---|---|
| `beewatch/ml/features.py` | creato |
| `beewatch/ml/train.py` | modificato: `TARGET` importato da `features.py` |
| `tests/test_features.py` | creato: ritardi calcolati a mano, nessun valore dell'anno stesso, anni mancanti, ordine e indice, riga futura, errori, preprocessore (colonne, mediane solo dall'addestramento, colonne escluse ignorate, stato nuovo, Pipeline), integrazione su Q8 |
| `tests/conftest.py`, `tests/test_train.py` | la fixture `dataset_nel_database` passa in `conftest.py`, ora che la usano due moduli |
| `docs/model_card.md` | sezione *Feature* |
| `docs/README.md`, `README.md` | indice, conteggio dei test |

## Definition of Done

| Voce | Prova |
|---|---|
| ColumnTransformer funzionante | `test_il_preprocessore_produce_le_colonne_attese_senza_mancanti`, `test_il_preprocessore_apre_una_pipeline_di_scikit_learn`; su Q8: 120 × 45 senza mancanti (`test_integrazione_le_feature_sul_pannello_q8`) |
| ogni feature documentata con la sua motivazione | tabelle qui e nella model card; `FEATURE` e `FEATURE_ESCLUSE` nel codice, disgiunte per test |
| nessuna trasformazione manuale fuori dalla pipeline | tutte le trasformazioni che imparano dai dati sono nel `ColumnTransformer`; l'unica funzione esterna (i ritardi) è spiegata nella decisione 1 |

## Miglioramenti futuri

- La riga da prevedere in M4-T8 si costruirà con le stesse due funzioni:
  storia dello stato + una riga dell'anno nuovo con la resa vuota (già provato
  da `test_in_previsione_la_riga_futura_senza_resa_ha_le_sue_feature`).
- Se M4-T3 mostrasse che una feature non serve, si toglie motivandolo con la
  cross-validation di M4-T4, non con la verifica.
