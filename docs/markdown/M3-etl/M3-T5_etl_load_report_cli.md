# M3 - T5 · ETL: load idempotente, report e CLI

> **Milestone** M3 · Accesso ai dati ed ETL
> **Task** M3-T5
> **Stato** completata
> **Commit** `feat(m3): add idempotent ETL load, report and CLI`
> **Collegati** → [`M3-T4_etl_extract_transform.md`](M3-T4_etl_extract_transform.md) · [`M3-T3_repository.md`](M3-T3_repository.md)

## Obiettivo

Poter rilanciare l'ETL quante volte serve senza duplicare né corrompere i dati,
e renderlo osservabile: ogni esecuzione dice quante righe ha letto, scartato
(e perché), inserito, aggiornato e lasciato com'erano.

## Descrizione

```bash
python scripts/run_etl.py                       # data/honeyproduction.csv
python scripts/run_etl.py --file altro.csv --report-dir altra/cartella
```

```text
BeeWatch AI · ETL produzione USDA
File:            data/honeyproduction.csv
Righe lette:     626
Righe scartate:  0
Inserite:        626
Aggiornate:      0
Invariate:       0
Durata:          0.43 s
```

| Pezzo | Dove | Cosa fa |
|---|---|---|
| `load(puliti, database)` | `beewatch/etl.py` | controlla che gli stati esistano in `stati_usa`, poi scrive con un upsert; restituisce `EsitoCaricamento(inserite, aggiornate, invariate)` |
| `ProduzioneUsdaRepository.carica(righe)` | `beewatch/repositories_riferimento.py` | l'SQL: `INSERT … AS nuovo ON DUPLICATE KEY UPDATE` sulla chiave `uq_produzione_usda_stato_anno`, tutte le righe in **una** transazione |
| `run_pipeline(percorso, database, cartella_report)` | `beewatch/etl.py` | extract → transform → load, un `INFO` nel log per ogni passo, `ReportETL` restituito e salvato in `cartella_report/etl_<data>_<ora>.txt` |
| `scripts/run_etl.py` | `scripts/` | solo argomenti e chiamata; esce con 1 e un messaggio (senza traceback) su ogni `BeeWatchError` |

Il report su file aggiunge, sotto il riepilogo, l'elenco delle righe scartate
(riga del file, stato, anno, motivo). I report vanno in `reports/`, già escluso
da git.

### Idempotenza e transazione

- **Doppia esecuzione**: la seconda volta ogni riga risulta *invariata*. MySQL
  dice per ogni upsert cosa è successo (1 inserita, 2 aggiornata, 0 identica):
  per questo le righe si scrivono una alla volta dentro la stessa transazione
  invece che con `executemany`, che darebbe un solo conteggio complessivo. Sul
  file vero (626 righe) l'intero caricamento dura circa 0,4 s.
- **Errore a metà**: qualunque errore durante il caricamento annulla la
  transazione (M3-T1): nel database non resta nessuna riga di quell'esecuzione.
- **Seed mancante**: se `stati_usa` non contiene uno stato del dataset, `load`
  si ferma con un `ETLError` che lo spiega, prima di scrivere.
- **Privilegi**: l'upsert usa solo `INSERT` e `UPDATE`; l'utente applicativo
  non ha bisogno d'altro (Blocco 2).

## Verifica sul file vero

Su uno stack Docker temporaneo, sia sul database principale dello stack sia su
quello di test:

| Esecuzione | Lette | Scartate | Inserite | Aggiornate | Invariate |
|---|---|---|---|---|---|
| prima | 626 | 0 | 626 | 0 | 0 |
| seconda | 626 | 0 | 0 | 0 | 626 |

Dopo il caricamento, Q8 (`dati_addestramento`) restituisce 600 righe di 40
stati, come previsto dalla regola R10 (i 4 stati con copertura parziale restano
nel database ma fuori dal pannello di addestramento).

## File coinvolti

| File | Azione |
|---|---|
| `beewatch/etl.py` | modificato: `load`, `EsitoCaricamento`, `ReportETL`, `run_pipeline` |
| `beewatch/repositories_riferimento.py` | modificato: `COLONNE_PRODUZIONE`, `carica` |
| `scripts/run_etl.py` | creato |
| `tests/test_etl.py` | modificato: test di report, CLI, load, pipeline (integration) |
| `docs/README.md` | modificato: indice |

## Decisioni progettuali

**1. L'SQL dell'upsert sta nel repository.** È la regola di M3-T3: `etl.py`
decide *cosa* caricare, `repositories_riferimento.py` *come*. Le colonne sono
scritte una volta nel repository e un test verifica che coincidano con quelle
prodotte da `transform`.

**2. Righe una alla volta, transazione unica.** Il conteggio esatto di inserite,
aggiornate e invariate è parte della DoD; il costo (626 istruzioni sulla stessa
connessione) è trascurabile.

**3. Il report è un oggetto, il testo una sua rappresentazione.**
`run_pipeline` restituisce `ReportETL`: i test controllano i numeri, la CLI
stampa `testo()`, lo stesso testo va su file.

**4. Nessuno `scripts/init_db.py`.** Schema e seed li applica già il contenitore
MySQL (P-10 del documento di passaggio): un secondo modo di farlo sarebbe una
seconda verità da tenere allineata.

**5. Il dataset non è nell'immagine Docker.** `scripts/` e `data/` restano fuori
dall'immagine dell'app (`.dockerignore`). Se e come caricare il dataset su un
clone pulito o nel contenitore è la decisione aperta **DA-04**: oggi l'ETL si
lancia dal computer, con il database del contenitore raggiungibile su
`127.0.0.1`.

## Definition of Done

| Voce | Prova |
|---|---|
| doppia esecuzione = stesso numero di righe | `test_integrazione_due_esecuzioni_della_pipeline_stesse_righe_e_report_su_file`, `test_integrazione_load_inserisce_poi_non_duplica_poi_aggiorna`; file vero: tabella sopra |
| un errore a metà non lascia scritture parziali | `test_integrazione_un_errore_a_meta_non_lascia_scritture_parziali` (l'ultima riga viola un CHECK: nessuna delle tre resta) |
| `python scripts/run_etl.py` popola il DB e stampa il report | `test_integrazione_la_cli_popola_il_database_e_stampa_il_report` |
| il report viene salvato anche su file | `test_il_report_salvato_non_sovrascrive_quello_precedente`, test della pipeline |

## Miglioramenti futuri

- Esecuzione dell'ETL nel contenitore o automatica a database vuoto: dipende da
  DA-04.
- Se il dataset crescesse di ordini di grandezza, caricamento a blocchi con
  `executemany` e conteggi ricavati da una lettura preliminare delle chiavi.
