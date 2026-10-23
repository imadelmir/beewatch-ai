# Documentazione di BeeWatch AI

Un documento per ogni task completata, nella cartella della propria milestone.
I codici sono gli stessi del backlog su GitHub e dei messaggi di commit.

## Indice

### M1 · Fondamenta e setup

| Task | Documento | Cosa contiene |
|---|---|---|
| M1-T1 | [Repository e convenzioni](markdown/M1-fondamenta/M1-T1_repository_e_convenzioni.md) | protezione di `main`, convenzioni di ramo e commit, moduli issue e PR, backlog |
| M1-T2 | [Struttura e packaging](markdown/M1-fondamenta/M1-T2_struttura_e_packaging.md) | albero delle cartelle, `pyproject.toml`, ruff e pytest |
| M1-T3 | [Configurazione](markdown/M1-fondamenta/M1-T3_configurazione.md) | lettura di `.env`, validazione all'avvio, gestione dei segreti |
| M1-T4 | [Eccezioni e logging](markdown/M1-fondamenta/M1-T4_eccezioni_logging.md) | gerarchia degli errori, logging centralizzato |
| M1-T5 | [Test e CI](markdown/M1-fondamenta/M1-T5_test_ci.md) | 42 test, workflow GitHub Actions |

### M2 · Dati e database

| Task | Documento | Cosa contiene |
|---|---|---|
| M2-T1 | [Analisi esplorativa](markdown/M2-dati/M2-T1_analisi_esplorativa.md) | com'è fatto il dataset USDA e cosa ne consegue |
| M2-T2 | [Dizionario e pulizia](markdown/M2-dati/M2-T2_dizionario_e_pulizia.md) | le dodici regole di trasformazione |
| M2-T3 | [Target e limiti](markdown/M2-dati/M2-T3_target_e_limiti.md) | cosa prevede il modello, e la soglia che deve battere |
| M2-T4 | [Schema relazionale](markdown/M2-dati/M2-T4_schema.md) | quattordici tabelle, undici query, diagramma ER |
| M2-T5 | [Schema SQL e Docker](markdown/M2-dati/M2-T5_schema_sql.md) | il DDL e il contenitore MySQL |
| M2-T6 | [Seed e apiario demo](markdown/M2-dati/M2-T6_seed_demo.md) | valori fissi e dati dimostrativi |

### M3 · Accesso ai dati ed ETL

| Task | Documento | Cosa contiene |
|---|---|---|
| M3-T1 | [Connessione al database](markdown/M3-etl/M3-T1_connessione_database.md) | classe `Database`, transazioni, retry, errori, database di test |
| M3-T2 | [Modelli di dominio](markdown/M3-etl/M3-T2_modelli_dominio.md) | entità con validazione, Enum dei valori fissi |
| M3-T3 | [Repository](markdown/M3-etl/M3-T3_repository.md) | tutto l'SQL del progetto, query Q1–Q11, isolamento fra utenti |
| M3-T4 | [ETL: extract e transform](markdown/M3-etl/M3-T4_etl_extract_transform.md) | lettura del CSV USDA, regole R1–R12, scarti con motivo |
| M3-T5 | [ETL: load, report e CLI](markdown/M3-etl/M3-T5_etl_load_report_cli.md) | caricamento idempotente in una transazione, report, `scripts/run_etl.py` |
| M3-T6 | [Test del livello dati](markdown/M3-etl/M3-T6_test_livello_dati.md) | CSV mini, idempotenza e rollback, test MySQL in CI |

### M4 · Machine Learning

| Task | Documento | Cosa contiene |
|---|---|---|
| DA-04 | [Il dataset nel repository](markdown/M4-machine-learning/DA-04_dataset_nel_repository.md) | licenza verificata (CC0), checksum, ETL in Docker, piano del modello |
| M4-T1 | [Dataset di training e baseline](markdown/M4-machine-learning/M4-T1_dataset_baseline.md) | Q8 dal database, split temporale, quattro baseline · [model card](model_card.md) |
| DA-05 | [Il criterio di accettazione](markdown/M4-machine-learning/DA-05_criterio_di_accettazione.md) | il modello deve battere la persistenza (MAE < 4,0634 kg, non arrotondato); 4,25 kg resta storico |
| M4-T2 | [Feature e preprocessore](markdown/M4-machine-learning/M4-T2_feature_preprocessore.md) | storia per stato senza dati dal futuro, `ColumnTransformer`, feature escluse |
| M4-T3 | [Confronto fra modelli](markdown/M4-machine-learning/M4-T3_confronto_modelli.md) | tre Pipeline e quattro baseline sulle stesse 120 righe, criterio DA-05, scelta motivata · [notebook](../notebooks/02_modelli.ipynb) |
| M4-T4 | [Validazione temporale](markdown/M4-machine-learning/M4-T4_validazione_temporale.md) | cross-validation a finestra espandente per anno (2004–2009), perché niente split casuale, media ± std, limiti |
| M4-T5 | [Tuning](markdown/M4-machine-learning/M4-T5_tuning.md) | griglia del backlog sui fold temporali, hold-out escluso, default contro ottimizzata, guadagno marginale dichiarato |
| M4-T6 | [Valutazione finale](markdown/M4-machine-learning/M4-T6_valutazione_finale.md) | modello adottato, residui, intervallo p10–p90 (copertura 85 % sul 2010–2012), importanza, limiti · [grafici](images/) |
| M4-T7 | [Modello salvato e predittore](markdown/M4-machine-learning/M4-T7_modello_e_predittore.md) | `.joblib` + `.json` con metadati, `Predittore` con controlli al caricamento, tabella `modelli`, scikit-learn bloccato alla serie 1.9 |
| M4-T8 | [Servizio di previsione](markdown/M4-machine-learning/M4-T8_servizio_previsione.md) | `Servizi.prevedi_produzione`: validazione, feature solo dal passato, intervallo in chili interi, regola «intervallo più largo della stima», salvataggio con versione e `feature_json` |

### M5 · AI generativa

| Task | Documento | Cosa contiene |
|---|---|---|
| M5-T1 | [Client LLM](markdown/M5-ai-generativa/M5-T1_client_llm.md) | `LLMClient` con Ollama e OpenRouter, factory, `OLLAMA_BASE_URL`, test con server finto, verifica reale ancora da fare |

### M6 · Interfaccia Streamlit

| Documento | Cosa contiene |
|---|---|
| [Specifica dell'interfaccia](markdown/M6-interfaccia/ui_spec.md) | palette, layout, componenti, comportamento delle schermate |

### Documenti di riferimento

Non appartengono a una singola task: crescono con il progetto.

| Documento | Cosa contiene |
|---|---|
| [`markdown/M2-dati/dati.md`](markdown/M2-dati/dati.md) | tutto ciò che sappiamo sui dati: fonte, dizionario, regole, target, limiti |
| [`markdown/M6-interfaccia/ui_spec.md`](markdown/M6-interfaccia/ui_spec.md) | la specifica dell'interfaccia |

## Come è organizzata la cartella

Tre cartelle, tre ruoli distinti: **i testi**, **i diagrammi**, **le immagini**.

```
docs/
├── README.md                  questo indice
│
├── markdown/                  I TESTI — l'unica fonte di verità
│   ├── M1-fondamenta/         un file per task
│   ├── M2-dati/
│   ├── M3-etl/                (vuote finché la milestone non inizia)
│   ├── M4-machine-learning/
│   ├── M5-ai-generativa/
│   ├── M6-interfaccia/
│   ├── M7-qualita-etica/
│   ├── M8-consegna/
│   └── MX-estensioni/
│
├── diagrams/                  I DIAGRAMMI — sorgente ed esportazione insieme
│   ├── README.md              come si modificano
│   ├── er_diagram.dbml        schema del database        → dbdiagram.io
│   ├── er_diagram.png
│   ├── architecture.drawio    architettura (M3-T1)       → draw.io
│   └── workflow.drawio        flusso dei dati (M3-T4)    → draw.io
│
└── images/                    LE IMMAGINI — screenshot e grafici
```

`README.md` resta fuori da `markdown/` perché GitHub lo mostra automaticamente
quando si apre la cartella `docs/`: spostarlo significherebbe perdere l'indice
in bella vista.

### Perché `diagrams/` e `images/` sono separate

Un diagramma ha un **sorgente modificabile** — un `.dbml`, un `.drawio` — e una
sua esportazione. Le due cose stanno insieme e portano lo stesso nome: se un
giorno una freccia va corretta, si apre il sorgente e si riesporta.

Un `.png` senza sorgente è un vicolo cieco: il primo che deve cambiare qualcosa
ridisegna tutto da capo. È il motivo per cui i sorgenti vanno versionati, ed è
il motivo per cui hanno una cartella dedicata.

`images/` raccoglie invece ciò che un sorgente non ce l'ha: screenshot
dell'interfaccia, grafici prodotti dal notebook. Si rifanno eseguendo il
programma, non modificando un file.

Le regole di dettaglio sono in [`diagrams/README.md`](diagrams/README.md).

## Un solo formato

La documentazione si scrive in **Markdown**, e basta. Si legge direttamente su
GitHub, git ne mostra le differenze riga per riga e due persone possono
modificarla senza conflitti insanabili.

Niente Word, niente PDF nel repository. Se per la consegna servisse un formato
diverso, si converte al momento: da Markdown a PDF o DOCX è un passaggio
meccanico, mentre tenere allineate due versioni dello stesso documento non
funziona mai.

## Convenzioni di scrittura

- **Nome del file**: `<codice-task>_<argomento>.md` per i documenti legati a una
  singola task, nome parlante per quelli di riferimento che crescono nel tempo.
- **Prima riga**: un titolo di livello 1 (`# ...`) con il codice della task.
- **Subito dopo**: una citazione (`> ...`) con milestone, stato, commit e
  rimandi ai documenti collegati.
- **Sezioni**: livello 2 (`## ...`).
- Ogni decisione progettuale va scritta **con la sua motivazione**. Una
  decisione senza motivo, fra tre settimane, è indistinguibile da un caso.
- Ogni documento di task chiude con la **Definition of Done verificata** e i
  **miglioramenti futuri**: sapere cosa si è deciso di non fare vale quanto
  sapere cosa si è fatto.
