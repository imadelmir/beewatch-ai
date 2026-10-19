# M3 - T6 · Test del livello dati

> **Milestone** M3 · Accesso ai dati ed ETL
> **Task** M3-T6
> **Stato** completata
> **Commit** `test(m3): add data layer tests and MySQL CI job`
> **Collegati** → [`M3-T4_etl_extract_transform.md`](M3-T4_etl_extract_transform.md) · [`M3-T5_etl_load_report_cli.md`](M3-T5_etl_load_report_cli.md) · [`M1-T5_test_ci.md`](../M1-fondamenta/M1-T5_test_ci.md)

## Obiettivo

Poter modificare l'ETL e il livello dati più avanti senza paura di rompere
qualcosa: un CSV piccolo e versionato su cui provare tutto il percorso, la prova
esplicita dell'idempotenza e del rollback, e i test con MySQL eseguiti anche su
GitHub a ogni pull request.

## Descrizione

### `tests/fixtures/honey_mini.csv`

17 righe con l'intestazione della fonte:

| Righe | Contenuto | Regola esercitata |
|---|---|---|
| 15 | AL, CA, ND × 2008–2012 | conversioni R3/R4, tipi R12 |
| AL 2010 | scorte superiori alla produzione | R11 (avviso, la riga resta) |
| PR 2011 | stato non fra i 44 | R7 (scartata) |
| CA 2013 senza scorte | campo vuoto | R2 (scartata) |

I valori sono **sintetici**, non USDA: hanno l'ordine di grandezza giusto e sono
coerenti (produzione = colonie × resa, valore ≈ produzione × prezzo), ma non
sono dati reali. Così il fixture non riapre la questione della licenza del
dataset (DA-04), che resta fuori dal repository.

### Test aggiunti (`tests/test_etl.py`)

| Test | Tipo | Cosa prova |
|---|---|---|
| `test_csv_mini_quindici_righe_pulite_e_due_scartate` | unitario | 17 lette, 15 pulite (5 anni per stato), 2 scartate con il loro motivo e la riga del file, avviso R11, nessun valore mancante |
| `test_csv_mini_coerente_produzione_uguale_a_colonie_per_resa` | unitario | il controllo di coerenza di dati.md sulle righe convertite |
| `test_solo_intestazione_nessuna_riga_nessun_errore` | unitario | caso limite: file senza righe |
| `test_integrazione_csv_mini_idempotenza` | integration | due esecuzioni: 15 inserite, poi 15 invariate; righe, valori e id identici |
| `test_integrazione_csv_mini_rollback_se_una_riga_fallisce` | integration | un aggiornamento e righe nuove nello stesso caricamento, l'ultima riga sfora la colonna: il database resta com'era prima |
| `test_integrazione_caricare_zero_righe_non_scrive_nulla` | integration | caso limite: caricamento vuoto |

### Job CI `integrazione`

`.github/workflows/ci.yml` ha ora due job paralleli:

| Job | Comando | Ruolo |
|---|---|---|
| `qualita` («Lint e test») | `ruff check .` + `pytest -m "not integration"` | invariato, è il controllo obbligatorio per il merge |
| `integrazione` | `pytest -m integration` con copertura | tutti i test con MySQL: database, modelli, repository, ETL e i test Docker del Blocco 2 |

Non c'è un servizio `mysql:8.4` dichiarato nel workflow, a differenza di quanto
ipotizzava il backlog: i test avviano da soli uno stack Docker temporaneo con lo
stesso `docker-compose.yml` e gli stessi script di `sql/` che usa chi sviluppa
(`tests/docker_support.py`, Blocco 2). Il vantaggio è che in CI si prova proprio
l'inizializzazione reale: schema, seed, privilegi e database di test. Su Linux
`sql/00_test_db.sh` viene incluso con `source` (non è eseguibile nel
repository), quindi la CI copre anche il percorso che su Windows non si vede.

Il job `integrazione` non è obbligatorio per il merge: renderlo tale è
un'impostazione di GitHub (ruleset di `main`), da decidere a mano.

## File coinvolti

| File | Azione |
|---|---|
| `tests/fixtures/honey_mini.csv` | creato |
| `tests/test_etl.py` | modificato: sezione «CSV mini» |
| `.github/workflows/ci.yml` | modificato: job `integrazione`, commento aggiornato |
| `docs/README.md` | modificato: indice |

## Definition of Done

| Voce | Prova |
|---|---|
| copertura del modulo `etl` ≥ 80% | `etl.py`: 90% righe con la sola suite rapida, 100% con gli integration |
| test di idempotenza presente e verde | `test_integrazione_csv_mini_idempotenza` (e quelli di M3-T5); verde in locale e nel job CI `integrazione` |
| (in più) test integration su GitHub | primo run del job `integrazione`: 85 test passati, nessuno saltato, in circa 3 minuti; repository 100% righe e rami |
| `fixtures/honey_mini.csv` committato | `tests/fixtures/honey_mini.csv` |

## Miglioramenti futuri

- Rendere obbligatorio anche il job `integrazione` nel ruleset di `main`
  (impostazione di GitHub, passo manuale).
- Unire la copertura dei due job in un solo numero (M7-T3, dove si fissano le
  soglie).
