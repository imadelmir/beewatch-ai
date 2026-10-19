# M4 - T1 · Dataset di training dal database e baseline

> **Milestone** M4 · Machine Learning
> **Task** M4-T1
> **Stato** completata
> **Commit** `feat(m4): build the training dataset from MySQL and measure baselines`
> **Collegati** → [`model_card.md`](../../model_card.md) · [`DA-04_dataset_nel_repository.md`](DA-04_dataset_nel_repository.md) · [`M2-T3_target_e_limiti.md`](../M2-dati/M2-T3_target_e_limiti.md)

## Obiettivo

Avere un termine di paragone onesto prima di costruire un modello: un modello
che non batte una media non serve. E dimostrare che MySQL è lo storage primario:
il training legge dal database, non dal CSV.

## Descrizione

`beewatch/ml/train.py`:

```python
from beewatch.config import ottieni
from beewatch.database import Database
from beewatch.ml.train import carica_dataset_training, migliore_baseline, valuta_baseline

dati = carica_dataset_training(Database(ottieni().database))   # Q8 → DataFrame
risultati = valuta_baseline(dati)                               # {nome: Metriche}
migliore_baseline(risultati)                                    # ("persistenza ...", Metriche(4.063, ...))
```

| Funzione | Cosa fa |
|---|---|
| `carica_dataset_training(database)` | Q8 attraverso `ProduzioneUsdaRepository.dati_addestramento()`, in un `DataFrame` con tipi numerici (i `DECIMAL` diventano `float`). Database vuoto: `ModelError` che dice di lanciare l'ETL |
| `dividi_temporale(dati)` | addestramento fino al 2009, verifica dal 2010 (M2-T3) |
| `metriche(vero, previsto)` | MAE, RMSE, R²: l'unico codice di valutazione, per baseline e modelli |
| `previsioni_baseline(...)`, `valuta_baseline(dati)` | le quattro baseline: media globale, media dello stato, media dello stato + tendenza, persistenza |
| `migliore_baseline(risultati)` | quella con il MAE più basso |

Risultati e definizioni sono nella [model card](../../model_card.md): sul pannello
di 600 righe la baseline più forte è la **persistenza, MAE 4,063 kg**.

## File coinvolti

| File | Azione |
|---|---|
| `beewatch/ml/train.py` | creato |
| `beewatch/exceptions.py` | modificato: docstring di `ModelError` (anche «mancano i dati per addestrare») |
| `tests/test_train.py` | creato |
| `docs/model_card.md` | creato |
| `docs/README.md` | modificato: indice |

## Decisioni progettuali

**1. La logica sta in `train.py`.** È il modulo previsto dalla struttura; M4-T3
dice che il confronto fra modelli vive lì. Feature (`features.py`) e predizione
(`predictor.py`) arriveranno con le loro task.

**2. Il repository resta senza pandas.** `dati_addestramento()` (M3-T3)
restituisce righe; il `DataFrame` si costruisce in `beewatch/ml/`. Il nome
suggerito dal backlog (`dataset_training`) non è stato introdotto: la query
esiste già con il nome di M3.

**3. La tendenza toglie prima la media dello stato.** M2-T3 non scrive come
stimava la pendenza. Qui la pendenza è comune a tutti gli stati e stimata sugli
scarti dalla media del proprio stato, il modo che non confonde la differenza fra
stati con l'andamento nel tempo. Sul pannello bilanciato di Q8 coincide con la
retta stimata su tutte le righe insieme. La model card riporta il confronto
completo con i numeri di M2-T3.

**4. La persistenza prevede un anno alla volta.** Per il 2011 usa la resa vera
del 2010, come faranno le feature con l'anno precedente (M4-T2). Le medie e la
pendenza usano solo l'addestramento: un test verifica che cambiando i valori
della verifica le loro previsioni non cambino.

**5. La model card sta in `docs/model_card.md`.** È il percorso della DoD e dei
requisiti del docente; corrisponde all'opzione raccomandata di DA-07.

## Definition of Done

| Voce | Prova |
|---|---|
| il dataframe viene da una query, non da `read_csv` | `test_integrazione_il_dataset_di_training_e_il_pannello_q8` (600 righe, 40 stati, dal database di test); `test_in_beewatch_ml_non_si_legge_mai_il_csv` |
| metriche di baseline calcolate e scritte in `docs/model_card.md` | `test_integrazione_le_baseline_della_model_card` (gli stessi numeri della tabella, dal database) |
| *(backlog)* rifare le baseline di M2-T3 con lo stesso codice | `test_integrazione_sulle_626_righe_si_ritrovano_i_numeri_di_m2_t3`: 6,46, 5,73 e 4,06 coincidono; la tendenza dà 4,17 invece di 4,25, spiegato nella model card |

## Decisione collegata

**DA-05**, aperta da questa task, è stata decisa dopo: un modello è accettabile
solo se batte la persistenza sulla stessa verifica (`MAE_modello <
MAE_persistenza`, valori non arrotondati). Vedi
[`DA-05_criterio_di_accettazione.md`](DA-05_criterio_di_accettazione.md).
