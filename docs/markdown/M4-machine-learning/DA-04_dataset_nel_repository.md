# DA-04 · Il dataset su un clone pulito e in Docker

> **Milestone** M4 · Machine Learning (decisione presa prima di M4-T1)
> **Stato** decisa e applicata
> **Commit** `feat(data): version the CC0 USDA dataset and run the ETL in Docker`
> **Collegati** → [`data/README.md`](../../../data/README.md) · [`dati.md`](../M2-dati/dati.md) · [`M3-T5_etl_load_report_cli.md`](../M3-etl/M3-T5_etl_load_report_cli.md)

## Il problema

Fino a M3 il CSV USDA non era nel repository, «per la licenza Kaggle». Su un
clone pulito la tabella `produzione_usda` restava vuota: niente dati per il
training (M4), per la previsione (M4-T8) e per la dashboard, finché qualcuno non
scaricava il file a mano. Il contenitore dell'app, poi, non aveva né il CSV né i
comandi per caricarlo.

## La decisione: opzione A, il CSV entra nel repository

La licenza **lo consente**, ed è stata verificata invece che presunta:

| Evidenza | Esito |
|---|---|
| API pubblica di Kaggle (`/api/v1/datasets/view/jessicali9530/honey-production`) | `licenseName`: «CC0: Public Domain»; versione 2 del 9 aprile 2018; 81 814 byte in tutto |
| Scheda Croissant del dataset | licenza CC0 con URL <https://creativecommons.org/publicdomain/zero/1.0/>; MD5 di `archive.zip` = `M0EsHb8hGJlaerlCtuF2Lw==` |
| Archivio Kaggle usato in M2 (25 050 byte) | stesso MD5 della versione 2; quattro file per 81 814 byte |
| `honeyproduction.csv` di quell'archivio e `data/honeyproduction.csv` | identici byte per byte, SHA-256 `70a831b5…ed038e` |

La provenienza USDA da sola non bastava: decide la licenza del file
pubblicato su Kaggle, e quella è CC0, che permette di ridistribuirlo senza
condizioni.

Il file non è stato modificato né riscaricato: è lo stesso usato in M2 e in M3.
Rispetto alle regole di dati.md: 626 righe × 8 colonne, 44 stati, 1998–2012,
nessun valore mancante, nessuna chiave duplicata, 4 stati con copertura parziale
(R10), una sola anomalia R11 (Nebraska 2006). Lo verificano i test.

## Cosa è cambiato

| File | Modifica |
|---|---|
| `data/honeyproduction.csv` | versionato (era ignorato) |
| `data/README.md` | provenienza, licenza, versione, SHA-256, come è stata verificata |
| `.gitignore` | `data/*` resta ignorato, tranne il dataset e la sua scheda |
| `.dockerignore`, `Dockerfile` | l'immagine contiene il dataset, `scripts/` e `models/` (anche P-03: il modello addestrato potrà entrare nell'immagine) |
| `beewatch/etl.py` | `SHA256_DATASET_UFFICIALE`, `impronta()`; il report dice se il file caricato è la versione documentata, il log avvisa se non lo è |
| `tests/test_dataset.py` | checksum, codifica, forma, nessuno scarto, le tre righe di dati.md sul file vero, i 40 stati completi |
| `tests/test_docker_stack.py` | l'ETL dentro il contenitore carica 626 righe e rilanciato non duplica |
| `README.md`, `dati.md` | il dataset è nel repository |

`tests/fixtures/honey_mini.csv` resta separato e sintetico; un test verifica che
non sia il dataset.

Nulla viene scaricato o caricato **in automatico**: l'ETL parte solo quando lo
si lancia.

## I comandi su un clone pulito

```bash
git clone https://github.com/imadelmir/beewatch-ai.git && cd beewatch-ai
cp .env.example .env              # e si compilano le password
docker compose up -d mysql        # schema e seed al primo avvio
python scripts/run_etl.py         # oppure: docker compose run --rm app python scripts/run_etl.py
```

## Il modello: cosa è deciso e quando arriva

| Voce | Decisione | Dove nasce |
|---|---|---|
| Sorgente dei dati | il **database**: Q8, `ProduzioneUsdaRepository.dati_addestramento()`; in `beewatch/ml/` non compare `read_csv` | M4-T1 |
| Comando di training | `python scripts/train_model.py` | M4-T7 |
| Output | `models/produzione_v1.joblib` (la Pipeline intera) + `models/produzione_v1.json` (versione, metriche, feature, SHA-256 del dataset) + riga nella tabella `modelli` | M4-T7 |
| Distribuzione | **artefatto versionato**: il `.joblib` e il `.json` si committano (regola 5 dell'architettura, DoD di M4-T7), così l'app parte da un clone pulito senza riaddestrare; il `.json` permette di ricostruirlo e confrontarlo | M4-T7 |
| Percorso | `MODEL_PATH` in `.env` (predefinito `models/produzione_v1.joblib`, già in `config.py`) | esistente |
| Modello assente | `ModelError` con un messaggio che dice di lanciare il training; l'app non addestra né scarica nulla all'avvio | M4-T7 (predictor) |
| Ricostruzione | dal clone pulito: ETL, poi training; con lo stesso dataset (SHA-256) e il seed fissato si ottiene lo stesso modello | M4-T7 |

Nessun `.joblib` viene committato adesso: non esiste ancora un training
documentato che lo produca.

## Verifica da clone pulito

Clone del branch in una cartella temporanea, nessun `.env`, MySQL in uno stack
Docker temporaneo e isolato (mai il database dello sviluppatore):

| Passo | Esito |
|---|---|
| dataset presente, SHA-256 corretto | ✅ |
| schema, seed e database di test applicati dall'inizializzazione | ✅ |
| `python scripts/run_etl.py` dal computer, due volte | 626 inserite, poi 626 invariate; «versione ufficiale» |
| ETL dentro il contenitore (immagine costruita dal clone), due volte | 626 righe, 44 stati; la seconda volta 626 invariate |
| test integration Docker, ETL e database dal clone | 57 passati |
| risorse Docker reali | identiche prima e dopo |

Training, salvataggio e inferenza del modello non si possono ancora verificare:
il codice arriva con M4-T7.
