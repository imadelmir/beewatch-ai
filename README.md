<div align="center">

# 🐝 BeeWatch AI

**Monitoraggio intelligente dell'apiario per apicoltori amatoriali**

Registra apiari, alveari, ispezioni e raccolti. Stima la resa attesa con un
modello di regressione. Riassume le note di campo con un assistente
conversazionale che può girare interamente sul tuo computer.

[![CI](https://github.com/imadelmir/beewatch-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/imadelmir/beewatch-ai/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

[Documentazione](docs/README.md) ·
[Schema del database](docs/markdown/M2-dati/M2-T4_schema.md) ·
[I dati](docs/markdown/M2-dati/dati.md) ·
[Backlog](../../issues)

</div>

---

## In breve

> **Progetto in corso.** Fondamenta, livello dati e accesso ai dati con l'ETL
> sono chiusi; modello di previsione, assistente AI e interfaccia Streamlit sono
> ancora da costruire. Quello che segue
> descrive il progetto completo, e la tabella di marcia dice a che punto e.

| | |
|---|---|
| **Problema** | Un apicoltore amatoriale annota apiari, ispezioni e raccolti su carta o su un foglio: i dati esistono, ma non dicono niente sulla resa attesa |
| **Il mio ruolo** | Progetto personale. Finora: configurazione e gestione dei segreti, gerarchia delle eccezioni, logging, CI, schema del database e dati di partenza, accesso ai dati (transazioni, repository) ed ETL del dataset USDA |
| **Risultato finora** | 3 milestone su 8 chiuse, 971 test automatici (854 rapidi + 117 con MySQL in Docker), CI verde |
| **Stack** | Python · MySQL · Docker · scikit-learn · Streamlit · pandas |
| **Demo** | Non ancora: l'interfaccia e la milestone M6. [Case study](https://portfolio-imad-el-mir.vercel.app/it/projects/beewatch-ai) |
| **Avvio** | `pip install -e ".[dev]"` e Docker per MySQL — [istruzioni](#avvio-rapido) |
| **Stato** | In corso, iniziato ad agosto 2026 — [roadmap](#stato-e-roadmap) · [backlog](../../issues) |

---

## Indice

- [Cosa fa](#cosa-fa)
- [Tecnologie](#tecnologie)
- [Avvio rapido](#avvio-rapido)
- [Struttura del progetto](#struttura-del-progetto)
- [Sviluppo](#sviluppo)
- [Documentazione](#documentazione)
- [Stato e roadmap](#stato-e-roadmap)
- [Limiti dichiarati](#limiti-dichiarati)
- [Licenza](#licenza)

## Cosa fa

| | Funzionalità | Consegnata in |
|---|---|---|
| 📋 | **Gestione dell'apiario** — apiari, alveari, ispezioni e raccolti, con storico completo | M6 |
| 📊 | **Dashboard** — alveari attivi, ispezioni recenti, produzione della stagione, avvisi sugli alveari trascurati | M6 |
| 📈 | **Stima della resa** — previsione con banda di incertezza, basata su quindici anni di rilevazioni USDA | M4 · M6 |
| 🤖 | **Assistente conversazionale** — riassume le note di ispezione e risponde a domande, in locale con Ollama o via OpenRouter | M5 · M6 |
| 📄 | **Report** — esportazione dei dati della stagione | M6 |
| 🔍 | **Trasparenza** — una pagina che dichiara da dove vengono i dati, cosa il modello non può sapere, e come vengono trattati i dati personali | M6 · M7 |

> Le funzionalità sono elencate in ordine di priorità del backlog. Lo stato di
> avanzamento è nella [roadmap](#stato-e-roadmap).

## Tecnologie

| Ambito | Scelta | Perché |
|---|---|---|
| Linguaggio | **Python 3.11+** | requisito di progetto |
| Interfaccia | **Streamlit** | interfaccia dati in Python puro, senza frontend separato |
| Database | **MySQL 8** in Docker | nessuna installazione locale, stesso ambiente per tutto il gruppo |
| Machine Learning | **scikit-learn** + joblib | pipeline, metriche e serializzazione del modello |
| Assistente | **Ollama** (locale) o **OpenRouter** (remoto) | in locale le note non lasciano il computer |
| Qualità | **pytest** · **ruff** · **GitHub Actions** | test e lint automatici a ogni pull request |

## Avvio rapido

### Requisiti

| | |
|---|---|
| **Python 3.11+** | [python.org](https://www.python.org/downloads/) |
| **Docker Desktop** | MySQL gira in un contenitore: non serve installarlo |
| **Ollama** *(facoltativo)* | solo per l'assistente in locale invece che via OpenRouter |

### Installazione

```bash
git clone https://github.com/imadelmir/beewatch-ai.git
cd beewatch-ai

python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS e Linux

pip install -e ".[dev]"
```

### Configurazione

```bash
copy .env.example .env          # Windows
cp .env.example .env            # macOS e Linux
```

Le variabili sono documentate una per una dentro `.env.example`. Le obbligatorie
sono tre: `DB_NAME`, `DB_USER`, `DB_PASSWORD`.

L'applicazione **valida la configurazione all'avvio** e si ferma con un
messaggio che elenca tutti i problemi insieme, invece di farteli scoprire uno
alla volta.

### Il dataset

Il dataset USDA è **già nel repository**, in `data/honeyproduction.csv`: la
licenza (CC0, pubblico dominio) lo permette. Provenienza, versione e checksum
sono in [`data/README.md`](data/README.md).

Per caricarlo nel database (si può rilanciare: non duplica nulla):

```bash
docker compose up -d mysql
python scripts/run_etl.py
```

Oppure, senza Python sul computer, dentro il contenitore dell'app:

```bash
docker compose run --rm app python scripts/run_etl.py
```

Come è fatto, cosa dice e cosa non può dire: [`docs/markdown/M2-dati/dati.md`](docs/markdown/M2-dati/dati.md).

### Il modello

Il modello di previsione è già nel repository, addestrato e documentato:
`models/produzione_v1.joblib` e, accanto, `models/produzione_v1.json` (versione, dati usati,
metriche, intervallo, versioni delle librerie). L'applicazione lo carica, **non lo addestra mai**
da sola. Per rifarlo da zero, dopo aver caricato il dataset (si usa sempre il database, mai il CSV):

```bash
python scripts/train_model.py
```

Stessi dati, stesso seme e stesse librerie danno le stesse previsioni. Cosa sa fare, quanto
sbaglia e quando non usarlo: [`docs/model_card.md`](docs/model_card.md).

### Il modello di linguaggio

L'assistente AI usa Ollama in locale (predefinito: gratis, le note non escono dal computer) oppure
OpenRouter nel cloud. Si sceglie con una variabile in `.env` (`LLM_PROVIDER`, più `LLM_API_KEY` per
OpenRouter e `OLLAMA_BASE_URL` se Ollama non è su `localhost`; dal contenitore usa
`http://host.docker.internal:11434`). Per provare che il provider risponde davvero:

```bash
python scripts/verifica_llm.py
```

### Aggiornare un database che esiste già

Gli script di `sql/` girano da soli solo alla creazione del database (volume vuoto). Chi ha già
un volume e riceve una modifica dello schema la applica a mano, **come root** (l'utente
dell'applicazione non può modificare lo schema, ed è voluto). Ogni file `sql/schema_*.sql` è
ripetibile e non tocca i dati; il comando è scritto in testa a ciascuno. Per esempio, per la
colonna `previsioni.feature_json` (M4-T8):

```bash
docker compose exec -T mysql sh -c \
  'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --database="$MYSQL_DATABASE"' \
  < sql/schema_02_previsioni_feature_json.sql
```

Se manca una modifica, l'applicazione lo dice con un messaggio che rimanda a questo comando.

## Struttura del progetto

```
beewatch-ai/
├── app/           interfaccia Streamlit — nessuna logica applicativa
├── beewatch/      il pacchetto: configurazione, database, ML, AI
├── data/          dataset locali (ignorata da git)
├── docs/          documentazione: markdown/, diagrams/, images/
├── models/        modelli addestrati (.joblib)
├── notebooks/     analisi esplorativa (M2) e confronto fra modelli (M4)
├── scripts/       utilità eseguibili
├── sql/           schema e seed del database
└── tests/         test automatici
```

**La separazione fra `app/` e `beewatch/` è deliberata.** L'interfaccia chiama
il pacchetto; il pacchetto non sa che Streamlit esiste. I test girano senza
avviare l'interfaccia, e se un giorno l'interfaccia cambiasse tecnologia la
logica resterebbe intatta.

## Sviluppo

```bash
pytest -m "not integration"   # suite rapida, senza Docker (è quella del controllo obbligatorio)
pytest -m integration         # test con MySQL vero: richiede Docker in esecuzione
ruff check .                  # lint e ordine degli import
ruff check . --fix            # correzione automatica di ciò che è correggibile
```

I test `integration` avviano da soli uno stack Docker temporaneo e lo smontano
alla fine: il database di sviluppo non viene mai toccato. `pytest` senza
opzioni li esegue tutti, quindi senza Docker va in errore.

Ogni pull request installa il progetto **su una macchina pulita** ed esegue lint
e test rapidi: se il controllo `Lint e test` è rosso, il merge è bloccato. Un
secondo job esegue i test `integration` con MySQL in Docker. È anche la
sola prova che il progetto si installa davvero da zero — sul computer di chi
sviluppa funziona sempre.

Convenzioni di ramo, messaggi di commit e flusso di lavoro:
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## Documentazione

Ogni task completata ha il proprio documento, nella cartella della sua
milestone. L'indice è in [`docs/README.md`](docs/README.md).

| Documento | Perché leggerlo |
|---|---|
| [I dati](docs/markdown/M2-dati/dati.md) | da dove vengono, cosa dicono, cosa **non** possono dire |
| [Schema del database](docs/markdown/M2-dati/M2-T4_schema.md) | quattordici tabelle, con le undici query che le giustificano |
| [Specifica dell'interfaccia](docs/markdown/M6-interfaccia/ui_spec.md) | palette, layout, comportamento di ogni schermata |
| [Diagrammi](docs/diagrams/) | sorgenti versionati, non solo immagini |

## Stato e roadmap

| Milestone | Contenuto | Stato |
|---|---|---|
| **M1** | Fondamenta e setup | ✅ completata |
| **M2** | Dati e database | ✅ completata |
| **M3** | Accesso ai dati ed ETL | ✅ completata |
| M4 | Machine Learning | ⬜ |
| M5 | Componente AI generativa | ⬜ |
| M6 | Interfaccia Streamlit | ⬜ |
| M7 | Qualità, Docker, etica | ⬜ |
| M8 | Documentazione, demo e consegna | ⬜ |

Il backlog completo — **55 task su 9 milestone**, ciascuna con la propria
Definition of Done — è nelle [issue](../../issues) e nella board *Projects*.

## Limiti dichiarati

Le stime prodotte da questo sistema sono **indicative** e si basano su
rilevazioni di apicoltura **commerciale statunitense** del periodo **1998-2012**,
aggregate per stato.

Non descrivono un apiario amatoriale italiano: vanno lette come ordine di
grandezza, mai come previsione puntuale. Per questo ogni stima è mostrata come
**intervallo** e mai come numero singolo.

> **Questo software non è uno strumento diagnostico.** Non sostituisce un
> veterinario né un tecnico apistico.

L'analisi completa dei limiti — bias dei dati, privacy e GDPR, trasparenza, EU
AI Act, usi impropri — è in
[`docs/markdown/M2-dati/dati.md`](docs/markdown/M2-dati/dati.md).

## Licenza

[MIT](LICENSE) — Imad El Mir , progetto finale ITS.
