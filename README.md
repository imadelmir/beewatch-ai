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

Il dataset USDA **non è nel repository**: ha una licenza propria e non è nostro
da ridistribuire.

1. scaricalo da [Kaggle — Honey Production in the USA](https://www.kaggle.com/datasets/jessicali9530/honey-production)
2. metti `honeyproduction.csv` nella cartella `data/`

Come è fatto, cosa dice e cosa non può dire: [`docs/markdown/M2-dati/dati.md`](docs/markdown/M2-dati/dati.md).

## Struttura del progetto

```
beewatch-ai/
├── app/           interfaccia Streamlit — nessuna logica applicativa
├── beewatch/      il pacchetto: configurazione, database, ML, AI
├── data/          dataset locali (ignorata da git)
├── docs/          documentazione: markdown/, diagrams/, images/
├── models/        modelli addestrati (.joblib)
├── notebooks/     analisi esplorative
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
pytest                      # la suite di test
ruff check .                # lint e ordine degli import
ruff check . --fix          # correzione automatica di ciò che è correggibile
```

Ogni pull request installa il progetto **su una macchina pulita** ed esegue lint
e test: se il controllo `Lint e test` è rosso, il merge è bloccato. È anche la
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
| M3 | Accesso ai dati ed ETL | ⬜ |
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
