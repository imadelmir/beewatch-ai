# M4 - T4 · Validazione: split temporale e cross-validation

> **Milestone** M4 · Machine Learning
> **Task** M4-T4
> **Stato** completata nel codice e nei documenti; manca la verifica umana della DoD (vedi sotto)
> **Commit** `feat(m4): add yearly expanding-window cross-validation`
> **Collegati** → [`model_card.md`](../../model_card.md#validazione-temporale-m4-t4) · [`M4-T3_confronto_modelli.md`](M4-T3_confronto_modelli.md) · [`DA-05_criterio_di_accettazione.md`](DA-05_criterio_di_accettazione.md)

## Obiettivo

Evitare il leakage temporale, l'errore più comune su dati annuali, e sapere se il
risultato di M4-T3 regge su anni diversi da quelli usati per scegliere il modello.

## Descrizione

`beewatch/ml/validazione.py`:

```python
from beewatch.ml.validazione import cross_validation_temporale, fold_temporali

cv = cross_validation_temporale(dati)   # tre fold, seed 42
cv.risultati_per_fold()                 # [{nome: Metriche}, ...] per modelli e baseline
cv.riepilogo()                          # {nome: Riepilogo(media, dev_std)}
cv.fold_sotto_la_persistenza()          # {modello: fold in cui batte la persistenza}
list(fold_temporali(dati))              # [(indici addestramento, indici valutazione), ...]
```

| Elemento | Cosa fa |
|---|---|
| `FOLD_TEMPORALI` | i tre fold del backlog: ≤2003 → 2004–05, ≤2005 → 2006–07, ≤2007 → 2008–09 |
| `cross_validation_temporale(dati)` | per ogni fold, `confronta_modelli` (M4-T3) sui dati fino all'ultimo anno di valutazione |
| `CrossValidazione` | un `Confronto` per fold; aggregati con `statistics.fmean` e `statistics.stdev` (n − 1) |
| `fold_temporali(dati)` | gli stessi fold come indici posizionali, per il parametro `cv` di scikit-learn (M4-T5) |

Il notebook `notebooks/02_modelli.ipynb` ha una sezione che richiama
`cross_validation_temporale`; rieseguito su uno stack MySQL temporaneo.

## Protocollo effettivo

| Fold | Addestramento | Valutazione | Righe |
|---|---|---|---|
| 1 | 1998–2003 | 2004–2005 | 240 → 80 |
| 2 | 1998–2005 | 2006–2007 | 320 → 80 |
| 3 | 1998–2007 | 2008–2009 | 400 → 80 |

Fuori dalla cross-validation resta l'hold-out di M2-T3 (≤2009 → 2010–2012), su cui
è deciso DA-05.

## Risultati

MAE in kg per colonia, seed 42 (RMSE, R² e tutte le baseline nella model card):

| | 2004–05 | 2006–07 | 2008–09 | Media ± std | Fold sotto la persistenza |
|---|---|---|---|---|---|
| Random forest | 4,1389 | 4,1783 | 4,0962 | 4,1378 ± 0,0410 | 3 su 3 |
| Regressione lineare | 3,9996 | 4,4533 | 4,1897 | 4,2142 ± 0,2279 | 2 su 3 |
| Albero di decisione | 6,0838 | 5,1086 | 5,9307 | 5,7077 ± 0,5245 | 0 su 3 |
| Media dello stato + tendenza | 3,7657 | 4,3961 | 4,1400 | 4,1006 ± 0,3170 | baseline |
| Persistenza | 5,1596 | 4,2694 | 4,9101 | 4,7797 ± 0,4592 | baseline |

La random forest batte la persistenza in ogni fold ed è il modello più stabile;
sul MAE medio è alla pari con la baseline «media dello stato + tendenza»
(+0,037 kg) e nel 2004–05 perde con essa. **La generalizzazione del vantaggio su
ogni metodo semplice non è dimostrata.** DA-05 non cambia ed è soddisfatto sul
2010–2012 (3,6558 contro 4,063428333…).

## Decisioni progettuali

**1. I fold del backlog, fissati prima dei risultati.** Finestra espandente, due
anni di valutazione per fold, tutto dentro l'addestramento: così si valutano anni
diversi dal 2010–2012, che in M4-T3 è servito anche a scegliere. Nessun fold è
stato aggiunto, tolto o spostato dopo aver visto i numeri.

**2. Un fold è un `confronta_modelli`.** Non c'è un secondo percorso di
valutazione: pipeline, feature, baseline e metriche sono quelle di M4-T1…M4-T3.
Il fold riceve solo le righe fino al suo ultimo anno di valutazione, e
`confronta_modelli` addestra sugli anni fino a `fine_addestramento`. Il
preprocessore fa `fit` solo su quelle righe.

**3. I fold non possono toccare l'hold-out.** `fold_temporali` e
`cross_validation_temporale` rifiutano un fold con anni di valutazione oltre il
2009, con buchi o vuoto.

**4. Deviazione standard campionaria.** Con tre fold `statistics.stdev` (n − 1)
è la stima corretta; la popolazione sarebbe più piccola del ≈ 18 % e farebbe
sembrare i risultati più stabili di quanto sono.

**5. Il criterio DA-05 resta sul 2010–2012.** Nei fold si conta quante volte un
modello batte la persistenza, per misurare la stabilità; non è un nuovo
criterio e non sostituisce DA-05.

**6. Indici per anno per il tuning.** `fold_temporali` produce le coppie
`(addestramento, valutazione)` che `GridSearchCV(cv=...)` accetta; il tuning è di
M4-T5 e non è stato fatto qui.

## File coinvolti

| File | Azione |
|---|---|
| `beewatch/ml/validazione.py` | creato |
| `tests/test_validazione.py` | creato: fold del backlog, indici senza sovrapposizioni, fold non validi, stesse righe per modelli e baseline, baseline del solo addestramento del fold, anni futuri e hold-out che non cambiano nulla, target non visto, riproducibilità, media e std, conteggio sui fold; integrazione sul pannello Q8 con i numeri della model card |
| `notebooks/02_modelli.ipynb` | sezione 5, conclusioni |
| `docs/model_card.md` | sezione *Validazione temporale*, nota sull'indipendenza del 2010–2012 |
| `docs/README.md`, `README.md` | indice, conteggio dei test |

## Definition of Done

| Voce | Prova |
|---|---|
| strategia scritta e motivata in `docs/model_card.md` | sezione *Validazione temporale · Strategia* |
| spiegato PERCHÉ non si usa uno split casuale | stessa sezione, *Perché non uno split casuale* (e perché non `TimeSeriesSplit`) |
| risultati CV con media e deviazione standard | tabelle per fold e *Media e deviazione standard sui tre fold*; `test_media_e_deviazione_standard_campionaria_dei_fold`, `test_integrazione_la_cross_validation_della_model_card` |
| verificato da una seconda persona che non ci sia informazione futura | **da fare**: è un passo umano. La model card elenca cosa controllare; i test di leakage lo preparano ma non lo sostituiscono |

## Miglioramenti futuri

- Tuning (M4-T5) con `fold_temporali`, senza guardare il 2010–2012.
- Considerare, in M4-T6, di presentare accanto alla random forest la baseline con
  la tendenza, visto che nella cross-validation sono alla pari.
