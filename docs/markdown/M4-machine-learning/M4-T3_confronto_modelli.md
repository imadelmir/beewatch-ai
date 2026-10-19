# M4 - T3 · Pipeline scikit-learn e confronto tra modelli

> **Milestone** M4 · Machine Learning
> **Task** M4-T3
> **Stato** completata
> **Commit** `feat(m4): compare three model pipelines with the baselines`
> **Collegati** → [`model_card.md`](../../model_card.md) · [`DA-05_criterio_di_accettazione.md`](DA-05_criterio_di_accettazione.md) · [`M4-T2_feature_preprocessore.md`](M4-T2_feature_preprocessore.md) · [`02_modelli.ipynb`](../../../notebooks/02_modelli.ipynb)

## Obiettivo

Mettere preprocessore e regressore in una Pipeline, come chiede il docente, e
scegliere il modello con un criterio, non a intuito: tre alternative valutate con
la stessa procedura, e confrontate con le baseline secondo DA-05.

## Descrizione

`beewatch/ml/train.py`:

```python
dati = carica_dataset_training(Database(ottieni().database))   # Q8 da MySQL
confronto = confronta_modelli(dati)                             # seed 42
confronto.risultati()          # {nome: Metriche} per modelli e baseline
confronto.risultati_per_anno() # le stesse, separate per 2010, 2011, 2012
confronto.vincitore()          # "random forest", o None se nessuno batte la persistenza
```

| Funzione | Cosa fa |
|---|---|
| `crea_modelli(seed)` | tre `Pipeline([("prep", crea_preprocessore()), ("modello", ...)])`: `LinearRegression`, `DecisionTreeRegressor`, `RandomForestRegressor`, con `random_state=seed` dove serve |
| `confronta_modelli(dati, seed)` | split di M4-T1, feature di M4-T2, addestra i tre modelli sull'addestramento, prevede la verifica con modelli e baseline |
| `Confronto` | le righe di verifica e un vettore di previsioni per nome; `risultati()`, `risultati_per_anno()`, `vincitore()` |

`notebooks/02_modelli.ipynb` richiama queste funzioni e mostra tabelle, criterio,
anni e sensibilità al seed; un test controlla che non legga il CSV e non addestri
da sé. È stato eseguito contro uno stack MySQL temporaneo, con il dataset caricato
dall'ETL: non contiene indirizzi né credenziali.

## Risultati

Verifica 2010–2012, 120 righe, kg per colonia (dettaglio, anni e seed nella
[model card](../../model_card.md#confronto-fra-modelli-m4-t3)):

| | MAE | RMSE | R² | DA-05 |
|---|---|---|---|---|
| Random forest | 3,6558 | 4,5698 | 0,6088 | soddisfa (−0,4076) |
| Regressione lineare | 4,0254 | 5,3358 | 0,4666 | soddisfa (−0,0380) |
| **Persistenza** | **4,063428333…** | 5,2964 | 0,4745 | riferimento |
| Media dello stato + tendenza | 4,1681 | 5,4350 | 0,4466 | |
| Albero di decisione | 5,5792 | 6,8581 | 0,1189 | non soddisfa (+1,5158) |
| Media dello stato | 5,7272 | 6,7982 | 0,1342 | |
| Media globale | 6,6546 | 8,3711 | −0,3128 | |

**Esito DA-05: soddisfatto** da random forest e regressione lineare. Scelta:
**random forest**, con le riserve scritte nella model card (verifica usata anche
per scegliere; nel 2012 la persistenza fa meglio di tutti; 120 righe).

## Decisioni progettuali

**1. Modelli e iperparametri fissati prima di guardare i risultati.** I tre
regressori sono quelli del backlog, con i parametri di default; il seed è 42.
Nessun parametro è stato cambiato dopo aver visto la verifica: il tuning è di
M4-T5 e userà la cross-validation sull'addestramento (M4-T4).

**2. `LinearRegression`, non `Ridge`.** Il backlog le ammette entrambe; la
descrizione della task dice «regressione lineare». `Ridge` avrebbe richiesto di
scegliere `alpha`, cioè un tuning in più fatto senza ancora la cross-validation.
La collinearità dello one-hot completo non è un problema: scikit-learn risolve con
i minimi quadrati a norma minima.

**3. Un solo oggetto per tutte le metriche.** `Confronto` tiene le righe di
verifica e le previsioni di modelli e baseline nello stesso ordine; ogni metrica
(totale e per anno) si calcola da lì con `metriche()`. Non esiste un percorso in
cui due numeri della tabella vengano da campioni diversi; un test lo verifica, e
un altro che le baseline del confronto sono esattamente quelle di M4-T1.

**4. Il target non entra mai fra gli ingressi.** `confronta_modelli` toglie la
colonna del target prima di `fit` e `predict`, anche se il preprocessore la
scarterebbe comunque. I test cambiano le rese del 2012 (che nessuno usa come
storia) e controllano che nessuna previsione cambi; cambiano quelle del 2010 e
controllano che cambino le previsioni del 2011 ma non quelle del 2010: è
l'orizzonte della persistenza, un anno alla volta.

**5. «Media ± std» fra gli anni, per ora.** Il backlog chiede una tabella con
media e deviazione standard, che presuppone più valutazioni. Con un solo hold-out
la model card riporta la media ± deviazione standard dei tre anni di verifica;
quella fra le pieghe della cross-validation è di M4-T4 e non è stata anticipata.

**6. La sensibilità al seed è informativa.** Il notebook rifà il confronto con i
seed 0–9 per mostrare che la conclusione non dipende dal 42; la scelta resta sul
42, fissato prima.

**7. Il vincitore esiste solo se soddisfa DA-05.** `vincitore()` sceglie il MAE
più basso fra i modelli con `soddisfa_criterio()`; se nessuno batte la
persistenza restituisce `None`, e la tabella va presentata senza vincitore.

## File coinvolti

| File | Azione |
|---|---|
| `beewatch/ml/train.py` | modificato: `crea_modelli`, `Confronto`, `confronta_modelli` |
| `tests/test_confronto_modelli.py` | creato: pipeline e seed, stesse righe e stessa funzione, baseline uguali a M4-T1, metriche per anno, nessun leakage, riproducibilità, ingresso intatto, indice ripetuto, vincitore e assenza di vincitore, notebook senza logica propria; integrazione sul pannello Q8 con i numeri della model card |
| `notebooks/02_modelli.ipynb` | creato, eseguito su uno stack MySQL isolato |
| `docs/model_card.md` | sezione *Confronto fra modelli* |
| `docs/README.md`, `README.md` | indice, conteggio dei test |

## Definition of Done

| Voce | Prova |
|---|---|
| tre modelli confrontati sulle stesse metriche, in tabella | tabella della model card (MAE, RMSE, R² per tre modelli e quattro baseline); `test_modelli_e_baseline_sono_misurati_sulle_stesse_righe_di_verifica`, `test_integrazione_il_confronto_della_model_card` |
| scelta motivata per iscritto in `docs/model_card.md` | sezione *Scelta*, con ciò che la scelta non dimostra |
| il confronto è riproducibile (seed fissato) | `SEED = 42`; `test_lo_stesso_seed_da_lo_stesso_confronto`; i MAE del database controllati a 1e-6 in integrazione |

## Miglioramenti futuri

- Cross-validation temporale per anno sull'addestramento (M4-T4): media ± std
  vera, e conferma del vantaggio su anni diversi dal 2010–2012.
- Tuning della random forest (M4-T5), con la stessa cross-validation.
- Intervallo di previsione dai residui e importanza delle variabili (M4-T6).
