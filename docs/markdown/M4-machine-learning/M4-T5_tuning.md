# M4 - T5 · Tuning degli iperparametri

> **Milestone** M4 · Machine Learning
> **Task** M4-T5
> **Stato** completata
> **Commit** `feat(m4): tune the random forest on the temporal folds`
> **Collegati** → [`model_card.md`](../../model_card.md#tuning-m4-t5) · [`M4-T4_validazione_temporale.md`](M4-T4_validazione_temporale.md) · [`M4-T3_confronto_modelli.md`](M4-T3_confronto_modelli.md)

## Obiettivo

Migliorare la random forest scelta in M4-T3 senza inseguire il terzo decimale, e
dichiarare il guadagno, anche se nullo.

## Descrizione

`beewatch/ml/tuning.py`:

```python
from beewatch.ml.tuning import ottimizza_random_forest

esito = ottimizza_random_forest(dati)   # dati: Q8; dentro si tengono solo gli anni ≤ 2009
esito.migliori_parametri                # {"modello__n_estimators": 200, ...}
esito.ricerca                           # 18 righe: parametri, MAE medio, std, rango
esito.mae_per_fold(DEFAULT), esito.mae_per_fold(OTTIMIZZATA)
esito.guadagno_medio_kg(), esito.fold_migliorati(), esito.da_adottare()
```

| Passo | Come |
|---|---|
| dati | `dati` ristretto agli anni ≤ 2009, ordinato per (stato, anno), indice rifatto; feature e indici dei fold costruiti **su questo frame** |
| ricerca | `GridSearchCV(pipeline random forest, GRIGLIA_RANDOM_FOREST, scoring="neg_mean_absolute_error", cv=fold_temporali(...), refit=False)` |
| scelta | rango 1 di `GridSearchCV`: il MAE medio più basso sui tre fold |
| confronto | `cross_validation_temporale(..., modelli={default, ottimizzata})`: stessi fold, stesse righe e stessa `metriche()` di M4-T4, con le baseline accanto |

Per riusare la stessa valutazione, `confronta_modelli` e
`cross_validation_temporale` accettano ora un parametro facoltativo `modelli`; senza
di esso il comportamento è quello di M4-T3 e M4-T4 (i loro test e i numeri della
model card sono invariati).

## Risultati

Scelta: `n_estimators=200`, `max_depth=None`, `min_samples_leaf=5`.

| MAE, kg per colonia | 2004–05 | 2006–07 | 2008–09 | Media ± std |
|---|---|---|---|---|
| Default | 4,1389 | 4,1783 | 4,0962 | 4,1378 ± 0,0410 |
| Ottimizzata | 4,1365 | 3,9563 | 4,1723 | 4,0883 ± 0,1158 |

Guadagno medio **0,049 kg (1,2 %)**, due fold su tre migliorati (uno per 0,002 kg).
RMSE e R² medi peggiorano (5,2610 → 5,3225; 0,5787 → 0,5685). La regola di adozione
è soddisfatta, quindi la configurazione ottimizzata passa a M4-T6 e M4-T7, ma il
miglioramento è nell'ordine del rumore e non è robusto. Tutto nella
[model card](../../model_card.md#tuning-m4-t5).

## Decisioni progettuali

**1. La griglia del backlog, senza aggiunte.** 2 × 3 × 3 = 18 configurazioni,
ciascuna motivata nella model card. Nessun valore è stato aggiunto o tolto dopo
aver visto i risultati.

**2. L'hold-out fuori prima di costruire qualunque cosa.** Il frame passato a
`GridSearchCV` contiene solo gli anni ≤ 2009, e gli indici di `fold_temporali`
sono posizioni di quello stesso frame: nessun disallineamento fra indici ed
etichette è possibile. Un test altera il 2010–2012 e controlla che il risultato
non cambi; un altro passa un ingresso mescolato e con indice diverso.

**3. Ordine canonico delle righe.** La random forest dipende dall'ordine delle
righe (bootstrap): il frame si ordina per (stato, anno), l'ordine di Q8, così il
risultato non dipende da come arrivano i dati.

**4. Default e ottimizzata misurati dalla stessa funzione.** Il MAE di
`GridSearchCV` serve solo a scegliere. Il confronto passa da
`cross_validation_temporale` e `metriche()`, come M4-T4; un test verifica che i
due calcoli coincidano per la configurazione scelta (stesse righe), e che i
default siano esattamente la random forest di M4-T4.

**5. Regola di adozione fissata prima.** Meglio in media **e** in almeno due
fold su tre. È stata scritta prima di eseguire la ricerca e non è stata cambiata
dopo, anche se l'esito è al limite.

**6. Niente valutazione sul 2010–2012.** È della valutazione finale (M4-T6). Il
tuning non lo rende una verifica indipendente: quel pannello ha già scelto il
modello in M4-T3.

**7. Niente cross-validation annidata.** Con tre fold di 80 righe una
validazione annidata darebbe stime poco affidabili; il bias della scelta è
dichiarato invece che corretto.

## File coinvolti

| File | Azione |
|---|---|
| `beewatch/ml/tuning.py` | creato |
| `beewatch/ml/train.py`, `beewatch/ml/validazione.py` | modificati: parametro facoltativo `modelli` |
| `tests/test_tuning.py` | creato: griglia del backlog, tabella della ricerca, stesse righe fra ricerca e rivalutazione, default uguali a M4-T4, fold e baseline, hold-out escluso, ingresso mescolato, riproducibilità, griglia con i soli default (guadagno nullo), modelli passati non addestrati, regola di adozione; integrazione sul pannello Q8 |
| `docs/model_card.md` | sezione *Tuning*; esito della verifica di M4-T4 |
| `M4-T4_validazione_temporale.md` | verifica umana fatta (DEV-2, #21) |
| `docs/README.md`, `README.md` | indice, conteggio dei test |

## Definition of Done

| Voce | Prova |
|---|---|
| griglia documentata | model card, *Griglia e procedura*: valori e motivo di ciascun iperparametro; `test_la_griglia_e_quella_del_backlog` |
| miglioramento rispetto ai default dichiarato onestamente | model card, *Risultati* e *Il miglioramento, detto onestamente*: −0,049 kg di MAE medio, RMSE e R² peggiori, bias della scelta; `test_integrazione_il_tuning_della_model_card` |
| se NON migliora, scritto che non migliora e perché | il MAE medio migliora di poco; è scritto che non migliora RMSE e R², che il guadagno è nell'ordine del rumore e perché. Il caso «nessun guadagno» è gestito e testato (`test_se_la_griglia_contiene_solo_i_default_non_ce_guadagno`) |

## Miglioramenti futuri

- M4-T6: valutare sul 2010–2012 la configurazione adottata, presentando accanto
  i default e le baseline, senza trattare quel pannello come indipendente.
