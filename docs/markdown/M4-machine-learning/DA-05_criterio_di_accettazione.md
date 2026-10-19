# DA-05 · Il criterio di accettazione del modello

> **Milestone** M4 · Machine Learning (decisione presa dopo M4-T1, prima di M4-T3)
> **Stato** decisa e applicata
> **Commit** `feat(m4): adopt DA-05, the model must beat persistence`
> **Collegati** → [`model_card.md`](../../model_card.md) · [`M4-T1_dataset_baseline.md`](M4-T1_dataset_baseline.md) · [`M2-T3_target_e_limiti.md`](../M2-dati/M2-T3_target_e_limiti.md)

## Il problema

M2-T3 aveva dichiarato come criterio di accettazione di M4 **MAE < 4,25 kg**, il
MAE della baseline «media dello stato + tendenza». M4-T1, rifacendo le baseline
con il codice che valuterà i modelli, ha trovato una baseline più forte: la
**persistenza** (la resa dello stesso stato nell'anno prima) sbaglia in media di
4,06 kg. Un modello fra 4,06 e 4,25 kg avrebbe superato la vecchia soglia pur
facendo peggio di chi ripete il valore dell'anno scorso.

## La decisione

Un modello soddisfa il criterio prestazionale **soltanto se**

```
MAE_modello < MAE_persistenza
```

con tutte e due le metriche calcolate:

| Condizione | Valore |
|---|---|
| dati | pannello **Q8** (`ProduzioneUsdaRepository.dati_addestramento`), 40 stati × 15 anni, letto da MySQL |
| verifica | le stesse **120 righe del 2010–2012**; addestramento 1998–2009 (`dividi_temporale`) |
| target | `resa_per_colonia_kg` |
| valutazione | la stessa funzione `metriche()` di `beewatch/ml/train.py` |
| confronto | sui valori **non arrotondati**, disuguaglianza stretta (a parità di MAE il criterio non è soddisfatto) |

Il valore di riferimento, letto dal database con `valuta_baseline`:

| Baseline | MAE (piena precisione) | Come si scrive |
|---|---|---|
| Persistenza | **4,063428333…** kg (487,6114 kg di errore assoluto su 120 righe) | 4,063 · 4,06 |

Nel codice il criterio è `soddisfa_criterio(metriche_modello, valuta_baseline(dati))`:
confronta con la persistenza anche se un giorno un'altra baseline risultasse più
forte, e se la persistenza manca solleva `ModelError` invece di rispondere.

La soglia di M2-T3, **MAE < 4,25 kg**, resta scritta nei documenti come
riferimento storico; da sola non dimostra niente.

## Perché

- La persistenza è la previsione più semplice che un apicoltore fa da sé: un
  modello che non la batte non aggiunge informazione.
- Il backlog la raccomandava già quando ha aperto DA-05 (documento di passaggio,
  `08_DECISIONI_RISCHI_PROBLEMI.md`, opzione A); la vecchia soglia era stata
  scelta prima di misurare la persistenza.
- Stessi dati, stessa verifica e stessa funzione rendono il confronto una
  disuguaglianza fra due numeri, non un'interpretazione.

## Coerenza con la specifica

| Punto della specifica | Esito |
|---|---|
| M2-T3: «criterio di accettazione di M4: MAE < 4,25 kg sullo stesso split» | sostituito da DA-05, che il backlog stesso aveva lasciato aperta per questa scelta; lo split resta quello di M2-T3 |
| M4-T4: hold-out identico a M2-T3 «per rendere confrontabile la soglia» | invariato: è la verifica su cui si misura anche la persistenza |
| M4-T5: tuning con `neg_mean_absolute_error` «perché MAE è la metrica della soglia» | invariato: il criterio resta sul MAE |
| M4-T6: model card con «la soglia 4,25 kg e la persistenza 4,06 kg» | invariato: si riportano entrambe, decide la persistenza |

Nessuna contraddizione sostanziale: cambia quale numero si deve battere, non lo
split, il target o la metrica.

## Cosa comporta per M4-T3

Ogni modello si confronta con **tutte** le baseline sulla stessa verifica, con
MAE, RMSE e R². Se nessun modello batte la persistenza, la model card lo dice
esplicitamente e nessun modello viene presentato come vincitore prestazionale.
Lo split non si cambia per migliorare il risultato e il criterio non si abbassa.

## File

| File | Modifica |
|---|---|
| `beewatch/ml/train.py` | `soddisfa_criterio()` |
| `tests/test_train.py` | il criterio sui casi limite (uguale, «4,06» sopra e sotto, sotto 4,25 ma sopra la persistenza); il MAE della persistenza a piena precisione dal database |
| `docs/model_card.md` | sezione *Criterio di accettazione* |
| `M4-T1_dataset_baseline.md`, `M2-T3_target_e_limiti.md`, `dati.md`, `M2-T4_schema.md` | rimando a DA-05 dove compariva la soglia 4,25 |
| `docs/README.md` | indice |
