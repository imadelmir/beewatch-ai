# M4 - T7 · Salvataggio joblib e predictor

> **Milestone** M4 · Machine Learning
> **Task** M4-T7
> **Stato** completata
> **Commit** `feat(m4): save the trained model with its metadata and load it with a predictor`
> **Collegati** → [`model_card.md`](../../model_card.md) · [`M4-T6_valutazione_finale.md`](M4-T6_valutazione_finale.md) · [`DA-04_dataset_nel_repository.md`](DA-04_dataset_nel_repository.md)

## Obiettivo

Soddisfare il requisito «modello salvato con joblib e ricaricato dentro l'app» in modo
**tracciabile**: non un file binario anonimo, ma un `.joblib` con accanto un `.json` che dice
come è nato, con quali dati, con quali numeri, e un predittore che controlla tutto prima di
prevedere.

## Descrizione

```bash
python scripts/train_model.py                 # models/produzione_v1.joblib + .json + riga in `modelli`
python scripts/train_model.py --senza-registrazione
python scripts/train_model.py --modello altra/cartella/m.joblib --versione v1.1.0 --seed 7
```

```python
from beewatch.ml.predictor import Predittore

predittore = Predittore()                         # percorso da MODEL_PATH
stima = predittore.stima({"codice_stato": "CA", "anno": 2013, "resa_anno_prima": 20.0,
                          "resa_media_3_anni_prima": 22.0, "colonie_anno_prima": 300_000.0})
stima.valore_kg, stima.inferiore_kg, stima.superiore_kg, stima.livello
```

| Modulo | Cosa fa |
|---|---|
| `beewatch/ml/artefatto.py` | il **formato**: scrive e legge i due file, controlla i metadati, calcola `sha256_file` e l'impronta del pannello, ricava la riga di `modelli` dal dizionario dei metadati |
| `beewatch/ml/addestramento.py` | l'orchestrazione: legge Q8, valuta (`valuta_finale`), riaddestra su tutte le righe, scrive i file, registra in `modelli` |
| `beewatch/ml/predictor.py` | `Predittore`: carica, controlla, prevede (`prevedi`) e stima con l'intervallo (`stima`) |
| `ModelliRepository` | `registra` (insert o update, e rende attiva la versione), `attivo`, `trova` |
| `scripts/train_model.py` | il wrapper da riga di comando; esce 1 se non può addestrare |

## Cosa contiene il `.json`

Versione, data (UTC), algoritmo e iperparametri; target e unità; **le feature in ordine** con il
motivo di ognuna e quelle escluse (leakage); il dataset (righe, stati, anni, **sha256 del
pannello** e sha256 del CSV ufficiale); la strategia di addestramento; le **metriche** (2010–2012,
cross-validation, baseline, esito di DA-05); l'**intervallo** (p10 e p90, copertura); l'importanza
delle variabili; le versioni di Python, scikit-learn, pandas, numpy e joblib; lo **sha256 del
`.joblib`**. La tabella `modelli` si riempie dallo stesso dizionario (DA-06): `mae_kg`, `rmse_kg` e
`r2` sono quelli del 2010–2012.

## Controlli del `Predittore` al caricamento

I file ci sono; il `.json` ha tutte le sezioni e lo schema giusto; lo **sha256 del `.joblib` è
quello dei metadati**; il file si carica ed è una Pipeline; le colonne che la Pipeline si aspetta
sono, nello stesso ordine, quelle dei metadati e quelle che il codice produce (`FEATURE`);
se scikit-learn è di un'altra versione, **avvisa nel log** e continua. Ogni problema è un
`ModelError` che dice come riaddestrare. A ogni caricamento scrive una riga INFO: nell'app deve
comparire una sola volta (M6-T1).

## Decisioni progettuali

**1. Il modello salvato è riaddestrato su tutte le righe; le metriche sono quelle del modello
fino al 2009.** Per prevedere il 2013 conviene che il modello conosca anche il 2010–2012;
ma per misurarlo servono anni che non ha visto. Quindi la valutazione (che dà le metriche, l'intervallo e
l'importanza) usa l'addestramento fino al 2009, e il modello salvato è la stessa configurazione
con tutti i dati. **Il modello salvato non ha una verifica propria.** Lo dicono il campo
`addestramento.strategia`, la nota nella tabella `modelli` e la model card.

**2. scikit-learn è bloccato alla serie 1.9** (`>=1.9,<1.10` in `pyproject.toml` e
`requirements.txt`). Un `.joblib` è un pickle di scikit-learn: con un'altra serie può non
caricarsi. Prima il vincolo era `>=1.5`, quindi un'installazione pulita avrebbe preso la versione
più recente, diversa da quella che ha addestrato il modello. Passare a un'altra serie vuol dire
riaddestrare (`python scripts/train_model.py`) e ricommittare i due file; il test sui valori
fissati dice se serve.

**3. Il `.json` è la fonte; la tabella serve alla chiave esterna.** Con un clone pulito il database
non ha righe in `modelli`: il servizio di previsione (M4-T8) registrerà il modello dai metadati
prima di salvare una previsione, perché `previsioni.versione_modello` ha una chiave esterna.

**4. `joblib` è `pickle`.** Caricare un file altrui esegue il suo codice. Lo sha256 evita un file
sbagliato o danneggiato, **non** uno malevolo: il modello del repository è nostro e committato,
e `MODEL_PATH` non va puntato a file di cui non ci si fida. È scritto nel codice, accanto a
`joblib.load`.

**5. L'addestramento sta in `addestramento.py`, non in `train.py`.** Il backlog dice «`train.py`
salva»; ma la valutazione importa `train`, e un `train` che importasse la valutazione
creerebbe un ciclo. `train.py` ha i mattoni, `addestramento.py` li assembla.

**6. Un'impronta del pannello, non solo quella del CSV.** Il training legge da MySQL, non dal
CSV: l'impronta dei dati che il modello ha davvero visto è quella di Q8 in una forma
canonica (righe ordinate, quattro decimali). Un test di integrazione verifica che sia quella
del database di oggi e che il training si rifaccia con gli stessi numeri.

**7. Solo le colonne di `FEATURE` entrano nella Pipeline salvata.** Il preprocessore scartava
comunque le altre, ma il contratto del modello è ora esplicito (`feature_names_in_`) e un test
verifica che le previsioni non cambino.

## Riproducibilità

Stessi dati (stessa impronta), stesso seed e stesse versioni delle librerie danno le stesse
previsioni (`test_lo_stesso_addestramento_due_volte_...`). Il modello ricaricato produce
previsioni identiche a quello addestrato (`test_il_modello_ricaricato_produce_predizioni_identiche`).
Il `.joblib` committato è stato addestrato con scikit-learn 1.9.0 e Python 3.14; la CI lo
carica con Python 3.11 e scikit-learn 1.9.x: se la versione differisce c'è un avviso nel log e
il test sui valori fissati (tolleranza 1e-6) verifica che le previsioni non cambino. Lo
stesso vale **dentro il contenitore** dell'app (Python 3.11, scikit-learn 1.9.1 al momento
della prova): il modello si carica e prevede lo stesso valore
(`test_m4_t7_il_modello_nel_contenitore_si_carica_e_prevede_come_sul_computer`, nello stack
Docker isolato).

## File coinvolti

| File | Azione |
|---|---|
| `beewatch/ml/artefatto.py`, `addestramento.py`, `predictor.py` | creati |
| `beewatch/repositories_riferimento.py` | `ModelliRepository` |
| `scripts/train_model.py` | creato |
| `models/produzione_v1.joblib`, `models/produzione_v1.json` | **committati**, addestrati da MySQL |
| `pyproject.toml`, `requirements.txt` | scikit-learn `>=1.9,<1.10`; filtro per un avviso di joblib con NumPy 2.5 nei test |
| `tests/test_artefatto.py`, `test_predictor.py`, `test_addestramento.py`, `test_modelli_repository.py`, `conftest.py` | test; fixture `artefatto_sintetico` |
| `README.md`, `docs/README.md`, `docs/model_card.md` | comando, indice, conteggio dei test |

## Definition of Done

| Voce | Prova |
|---|---|
| il modello ricaricato produce predizioni identiche (test) | `test_il_modello_ricaricato_produce_predizioni_identiche`, `test_il_modello_salvato_ricaricato_prevede_come_quello_in_memoria`, e in integrazione dal database |
| `models/produzione_v1.json` presente con metriche e feature | il file committato; `test_i_metadati_committati_hanno_le_metriche_della_model_card` |
| `python scripts/train_model.py` funziona da riga di comando | `tests/test_addestramento.py` (CLI) e un'esecuzione vera su uno stack MySQL isolato; esce 1 se non può addestrare |
| il `.joblib` è committato | `models/produzione_v1.joblib` (580 KB), non ignorato (`git check-ignore`); `test_il_modello_committato_prevede_i_valori_fissati` |

## Miglioramenti futuri

- Un `.joblib` non è un formato di scambio: se il progetto uscisse da un solo ambiente,
  `skops` o un export ONNX eviterebbero il problema delle versioni e del pickle.
- Versionare i modelli per cartella (`models/v1.0.0/`) se se ne tenessero più di uno.
