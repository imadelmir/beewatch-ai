# M4 - T6 · Valutazione finale e model card

> **Milestone** M4 · Machine Learning
> **Task** M4-T6
> **Stato** completata
> **Commit** `feat(m4): evaluate the adopted model and complete the model card`
> **Collegati** → [`model_card.md`](../../model_card.md#valutazione-finale-m4-t6) · [`M4-T5_tuning.md`](M4-T5_tuning.md) · [`M4-T4_validazione_temporale.md`](M4-T4_validazione_temporale.md) · [`DA-05_criterio_di_accettazione.md`](DA-05_criterio_di_accettazione.md)

## Obiettivo

Trasformare i numeri di M4-T3, M4-T4 e M4-T5 in un documento difendibile: le metriche del
modello adottato, i suoi errori, l'intervallo di previsione che userà l'app, i limiti e i casi
in cui non va usato. E tenere separato ciò che è **misurato** da ciò che si può **concludere**.

## Descrizione

`beewatch/ml/valutazione.py` (nessun matplotlib) e `scripts/genera_grafici.py` (il disegno):

```python
from beewatch.ml.valutazione import valuta_finale

v = valuta_finale(dati)             # dati: Q8 da MySQL
v.hold_out.risultati()              # modello adottato, default e baseline sul 2010–2012
v.cv.riepilogo()                    # media ± std sui tre fold
v.previsioni                        # 360 previsioni fuori campione con il loro residuo
v.intervallo_cv, v.copertura_hold_out, v.intervallo_finale
v.importanza, v.distribuzione
```

```bash
python scripts/genera_grafici.py    # scrive cinque PNG in docs/images/
```

| Elemento | Cosa fa |
|---|---|
| `crea_modello_finale()` (`train.py`) | la Pipeline adottata: preprocessore + random forest con i parametri di M4-T5 |
| `valuta_finale(dati)` | cross-validation e hold-out con lo stesso codice di M4-T3/T4, residui, intervallo, importanza, distribuzione |
| `calcola_intervallo`, `copertura` | quantili p10–p90 dei residui e quota di residui dentro |
| `importanza_variabili` | `permutation_importance` sulla Pipeline intera, sul 2010–2012 |
| `errori_per`, `errori_per_fascia`, `copertura_per_fascia` | errori per anno, stato e livello della previsione |
| `scripts/genera_grafici.py` | previsto/reale, residui, importanza, distribuzione del target, MAE per periodo |

## Risultati

(La model card ha tabelle, grafici e ragionamenti completi.)

- Sul **2010–2012** il modello adottato fa **MAE 3,4986 kg** (RMSE 4,4826, R² 0,6236), contro
  3,6558 del default e 4,063428… della persistenza: DA-05 soddisfatto per −0,5648 kg.
- In **cross-validation** fa 4,0883 ± 0,1158 kg: sotto la persistenza in tutti i fold, ma
  alla pari con «media dello stato + tendenza» (4,1006).
- **Intervallo** p10–p90 dei residui: −5,71 / +6,58 kg (ampiezza 12,3). Calibrato sulla sola
  cross-validation copre l'85 % del 2010–2012; con ampiezza costante copre il 72,5 % delle
  previsioni alte.
- **Importanza:** domina la resa media dei tre anni prima (+2,76 kg di MAE se mischiata);
  `anno` vale zero per costruzione.
- **Target:** asimmetria 0,67, nessuna trasformazione; lo sbilanciamento delle classi non si
  applica a una regressione.

## Decisioni progettuali

**1. L'intervallo si calibra sui residui della cross-validation e si controlla sul
2010–2012.** Calibrarlo e controllarlo sugli stessi dati darebbe un 80 % per costruzione.
Così la promessa è messa alla prova su 120 previsioni che non l'hanno costruito (85 %). Per
l'uso in produzione si usano tutti i 360 residui, che sono più numerosi.

**2. Residuo = vero − previsto.** Positivo se il modello sottostima: l'intervallo di un
valore vero è `previsto + p10 … previsto + p90`, e il segno dell'errore medio si legge
direttamente.

**3. Importanza per permutazione sulla Pipeline.** Si mischiano le colonne di ingresso, non
quelle trasformate: l'importanza è dello stato, dell'anno, dei ritardi, non delle singole
colonne dello one-hot. Si calcola sul 2010–2012 perché è descrittiva e non sceglie nulla.

**4. Lo zero di `anno` si dichiara, non si nasconde.** Tutti gli anni di verifica superano
quelli di addestramento: nessuna permutazione cambia il percorso negli alberi. Un test lo
fissa, così nessuno lo scambia per «anno è irrilevante».

**5. I grafici vengono dal codice, non a mano.** Lo script usa i risultati di
`valuta_finale`; la palette è stata validata con lo script della skill di visualizzazione
(blu e arancio, ΔE per daltonici 24,7 e per visione normale 33,6, contrasto ≥ 3:1). Il
disegno sta fuori dal pacchetto perché matplotlib è solo di sviluppo e non è nell'immagine
Docker.

**6. Il modello da servire non è deciso qui.** Questa task valuta il modello addestrato fino
al 2009, l'unico che ha una verifica. Come si addestra quello salvato è di M4-T7.

## File coinvolti

| File | Azione |
|---|---|
| `beewatch/ml/valutazione.py` | creato |
| `beewatch/ml/train.py` | modificato: `PARAMETRI_RF_OTTIMIZZATI`, `RANDOM_FOREST_OTTIMIZZATA`, `crea_modello_finale` |
| `beewatch/ml/tuning.py` | modificato: usa i nomi di `train.py` |
| `scripts/genera_grafici.py` | creato |
| `docs/images/*.png` | cinque grafici generati da MySQL |
| `tests/test_valutazione.py` | creato: intervallo e copertura a mano, previsioni fuori campione senza duplicati, hold-out fuori dalla calibrazione, importanza (anche lo zero di `anno`), distribuzione del target, errori per gruppo; integrazione con i numeri della model card |
| `tests/test_grafici.py` | creato: cinque PNG veri, rigenerazione, CLI con e senza dati |
| `docs/model_card.md` | sezione *Valutazione finale* |
| `docs/README.md`, `README.md` | indice, conteggio dei test |

## Definition of Done

| Voce | Prova |
|---|---|
| model card completa | sezione *Valutazione finale*: modello adottato, risultati, residui, intervallo, importanza, target, limiti, quando non usarlo |
| grafici salvati (residui, importance, previsto vs reale) | `docs/images/residui.png`, `importanza_variabili.png`, `previsto_vs_reale.png`, più `distribuzione_target.png` e `mae_per_periodo.png`; `test_i_cinque_grafici_sono_png_veri` |
| almeno tre limiti dichiarati esplicitamente | sette limiti numerati nella model card |
| nota sullo sbilanciamento | sezione *Il target e lo sbilanciamento*: non si applica alla regressione; distribuzione verificata (asimmetria 0,67) e trattata (nessuna trasformazione, con il motivo) |

## Miglioramenti futuri

- Un intervallo con ampiezza proporzionale al livello della previsione, se la copertura per
  fasce (72,5 % nella fascia alta) diventasse un problema per la pagina Previsione.
- Più anni di verifica quando ci saranno dati dopo il 2012.
