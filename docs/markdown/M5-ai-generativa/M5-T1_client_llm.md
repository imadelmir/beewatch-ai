# M5 - T1 · Client LLM astratto (Ollama e OpenRouter)

> **Milestone** M5 · Componente AI generativa
> **Task** M5-T1
> **Stato** codice e test completati; **la verifica con una chiamata reale a ciascun provider non è ancora stata fatta** (vedi sotto)
> **Commit** `feat(m5): add the LLM client with Ollama and OpenRouter providers`
> **Collegati** → [`.env.example`](../../../.env.example) · [`model_card.md`](../../model_card.md) (il modello di previsione, altra cosa)

## Obiettivo

Sviluppare gratis in locale (Ollama) e passare al cloud (OpenRouter) cambiando **una variabile in
`.env`**, senza toccare il codice. Una classe astratta `LLMClient`, due implementazioni, una factory.

## Descrizione

`beewatch/ai/llm.py`:

```python
from beewatch.ai.llm import crea_client
from beewatch.config import ottieni

client = crea_client(ottieni().llm)                       # il provider lo sceglie LLM_PROVIDER
r = client.completa("Sei un assistente apistico.", "Com'è la covata?",
                    temperatura=0.2, massimo_token=500, risposta_json=True)
r.testo, r.provider, r.modello, r.durata_ms, r.token_prompt, r.token_risposta
```

| Elemento | Cosa fa |
|---|---|
| `RispostaLLM` | `testo`, `provider`, `modello`, `durata_ms`, `token_prompt`, `token_risposta`: **gli stessi nomi delle colonne di `messaggi`** (un test lo verifica sullo schema) |
| `LLMClient` (astratta) | `completa(sistema, utente, *, temperatura, massimo_token, risposta_json)`; HTTP, errori e log in comune |
| `ClientOllama` | `POST {OLLAMA_BASE_URL}/api/chat`, `stream: false`, `options.temperature` e `num_predict`, `format: "json"` |
| `ClientOpenRouter` | `POST https://openrouter.ai/api/v1/chat/completions`, `Authorization: Bearer`, `temperature`, `max_tokens`, `response_format` |
| `crea_client(cfg.llm)` | sceglie il client da `LLM_PROVIDER`; `LLMError` per un provider sconosciuto o OpenRouter senza chiave |

`scripts/verifica_llm.py` fa una chiamata vera al provider di `.env` (e una seconda che chiede JSON,
per sapere se il modello rispetta il formato): è il passo manuale della DoD.

## Decisioni progettuali

**1. Solo `requests`, nessun SDK.** Sono due POST con un JSON; un SDK sarebbe una dipendenza in più da
tenere aggiornata per poche righe. I formati sono stati verificati sulla documentazione ufficiale
([Ollama](https://docs.ollama.com/api/chat), [OpenRouter](https://openrouter.ai/docs/api-reference/chat-completion))
al momento dell'implementazione. La documentazione di OpenRouter consultata non descrive un header
`Retry-After`: M5-T2 lo rispetterà se c'è, senza contarci.

**2. Nuova variabile `OLLAMA_BASE_URL`** (predefinito `http://localhost:11434`), validata come
indirizzo http o https all'avvio, senza la barra finale. Dal contenitore `localhost` è il
contenitore stesso: `.env.example` e `docker-compose.yml` indicano `host.docker.internal`, che
compose rende raggiungibile anche su Linux (`extra_hosts`).

**3. Una chiamata, non in streaming.** Il riepilogo di un'ispezione è un JSON che si valida intero
(M5-T3): mezzo JSON non serve a nessuno.

**4. La durata la misura il client**, con `time.perf_counter()`, non il provider: è ciò che aspetta
l'utente, e vale per entrambi.

**5. Il modello registrato è quello che ha risposto**, se il provider lo dichiara (OpenRouter può
instradare su un altro), altrimenti quello richiesto.

**6. Segreti e dati dell'utente.** La chiave API non compare in nessun messaggio né nel log; del
testo inviato si registra solo la lunghezza (le note di ispezione sono dati dell'utente); anche il
testo di un errore di rete sconosciuto resta fuori dal log (solo il tipo). Test su ogni scenario di errore.

**7. Ogni errore è un `LLMError` con un messaggio che dice cosa fare**: Ollama spento (`ollama serve`),
modello non scaricato (`ollama pull …`), chiave rifiutata, credito esaurito, limite di richieste,
timeout (`LLM_TIMEOUT`), risposta senza testo o in un formato inatteso, anche un 200 che contiene un errore.

**8. Il parametro è `risposta_json`, non `json`**, per non ombreggiare il modulo e perché è una
*richiesta* al provider, non una garanzia: chi la usa valida comunque.

## Come si prova senza rete

`tests/llm_server.py` è un server HTTP locale che imita i due provider su **socket veri**, con
risposte preparate in coda, ritardi e porta chiusa. I test (`tests/test_llm.py`, 45; `tests/test_verifica_llm.py`, 5)
controllano la richiesta byte per byte (percorso, intestazioni, JSON), la risposta, ogni errore, il
timeout, la connessione rifiutata, la factory e che **cambiare provider sia solo una modifica a
`.env`** (due `.env` che differiscono per `LLM_PROVIDER`: stesso codice, altro client, stessa risposta).

Questi test **non sostituiscono** la verifica con un provider vero: dicono che il codice parla il
formato documentato, non che il provider risponda oggi così.

## La verifica reale: il punto aperto

La DoD chiede «verificato con una chiamata reale a ciascuno». **Non è stata fatta**, perché sul computer
dove è stato sviluppato mancano le due condizioni:

| Provider | Cosa manca |
|---|---|
| Ollama | non è installato (e il modello `llama3.1:8b` pesa circa 4,7 GB) |
| OpenRouter | `LLM_API_KEY` è vuota |

Per chiuderla, quando sono disponibili:

```bash
python scripts/verifica_llm.py                                   # Ollama (LLM_PROVIDER=ollama)
python scripts/verifica_llm.py --provider openrouter             # con LLM_API_KEY in .env
```

Esce con 0 se la chiamata riesce e stampa provider, modello, durata e token; il secondo controllo
(JSON) è informativo. La issue #26 resta aperta finché entrambe non sono andate a buon fine.

## File coinvolti

| File | Azione |
|---|---|
| `beewatch/ai/llm.py` | creato |
| `beewatch/config.py` | `OLLAMA_BASE_URL` → `ConfigLLM.ollama_url` (validato) |
| `.env.example`, `docker-compose.yml` | la variabile; `extra_hosts` per `host.docker.internal` |
| `scripts/verifica_llm.py` | creato |
| `tests/llm_server.py`, `test_llm.py`, `test_verifica_llm.py` | creati; `test_config.py`, `test_docker_compose.py` estesi |

## Definition of Done

| Voce | Esito |
|---|---|
| entrambi i provider funzionanti | **nel codice e con il server finto**: sì; con i provider veri: non verificato |
| cambio provider = sola modifica a `.env`, zero modifiche al codice | sì, provato (`test_cambiare_provider_e_solo_una_modifica_a_env`) |
| verificato con una chiamata reale a ciascuno | **NO**: Ollama non installato, chiave OpenRouter assente (vedi sopra) |
