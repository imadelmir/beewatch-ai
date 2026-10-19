# Il dataset USDA

`honeyproduction.csv` è il dataset su cui si basano l'analisi (M2), l'ETL (M3)
e il modello (M4). È nel repository perché la licenza lo permette (decisione
DA-04): un clone pulito ha già tutto ciò che serve.

| | |
|---|---|
| Titolo | *Honey Production in the USA (1998-2012)* |
| Autrice della raccolta | Jessica Li, su Kaggle |
| Pagina | <https://www.kaggle.com/datasets/jessicali9530/honey-production> |
| Versione | 2 (9 aprile 2018, «Added the three original raw datasets») |
| Dati di origine | USDA, National Agricultural Statistics Service (NASS) |
| Licenza | **CC0 1.0 — Public Domain** (<https://creativecommons.org/publicdomain/zero/1.0/>) |
| File | `honeyproduction.csv`, 29 143 byte, UTF-8 senza BOM, fine riga LF |
| SHA-256 | `70a831b5c9872904df3aa3fc4142a5749f968e7e64405f6e2e116c5c49ed038e` |
| Contenuto | 626 righe di dati + intestazione, 8 colonne, 44 stati, anni 1998–2012 |

## Come è stata verificata la provenienza

- La licenza e la versione vengono dai metadati ufficiali di Kaggle: l'API
  pubblica (`/api/v1/datasets/view/jessicali9530/honey-production`:
  `licenseName` «CC0: Public Domain», versione 2, 81 814 byte in tutto) e la
  scheda Croissant del dataset (licenza con l'URL CC0 qui sopra).
- L'archivio Kaggle usato all'inizio del progetto (25 050 byte, conservato sul
  computer di chi ha fatto l'analisi) ha lo stesso MD5 che Kaggle pubblica per
  `archive.zip` della versione 2 (`M0EsHb8hGJlaerlCtuF2Lw==`, in base64). I suoi
  quattro file sommano a 81 814 byte, come dichiarato dall'API.
- Il `honeyproduction.csv` contenuto in quell'archivio è **identico, byte per
  byte**, a questo file (stesso SHA-256). È anche il file usato in M2 e in M3:
  nessuna differenza.

I tre file `honeyraw_*.csv` dello stesso archivio non sono qui: il progetto non
li usa (decisione di M2-T1).

## Uso

Lo legge solo l'ETL (`beewatch/etl.py`), che lo carica nel database:

```bash
docker compose up -d mysql
python scripts/run_etl.py
```

o, senza Python sul computer:

```bash
docker compose run --rm app python scripts/run_etl.py
```

Il training (M4) legge i dati dal **database**, mai da questo file. Il report
dell'ETL dice se il file caricato è questa versione (SHA-256 verificato).

## Da non confondere

`tests/fixtures/honey_mini.csv` **non** è un estratto di questo dataset: sono
valori sintetici, costruiti per i test.

Non modificare questo file a mano: un test (`tests/test_dataset.py`) ne
controlla il SHA-256. Una nuova versione si aggiunge aggiornando insieme file,
SHA-256 (qui e in `beewatch/etl.py`) e documentazione.
