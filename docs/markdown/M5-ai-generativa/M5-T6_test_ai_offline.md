# M5 - T6 · Test della componente AI senza rete

> **Milestone** M5 · Componente AI generativa
> **Task** M5-T6
> **Stato** completata (la verifica con un provider vero resta in #26)
> **Commit** `test(m5): run the whole AI component offline and block real network in the suite`
> **Collegati** → `tests/test_ai_offline.py` · `tests/test_rete_bloccata.py` · `tests/fixtures/llm/` · `tests/conftest.py`

## Obiettivo

Che la suite dica la verità sulla componente AI anche sul computer di chi non ha Ollama, non ha una
chiave OpenRouter e non ha Internet, e che non possa mai chiamare un provider vero per sbaglio. «Gira
senza rete» deve essere una proprietà verificata a ogni esecuzione, non una speranza.

## Cosa c'è

| Pezzo | Cosa fa |
|---|---|
| `tests/fixtures/llm/*.json` | 15 risposte dei provider, una per scenario (valida, JSON troncato, campi mancanti, 429, 401, 5xx, …) |
| `tests/llm_registrate.py` | le carica e le mette in coda sul server HTTP finto (`ServerFinto`, socket veri su 127.0.0.1) |
| `tests/llm_fake.py` | `LLMFinto`: un client che risponde con testi decisi dal test (parser, assistente, servizio) |
| `tests/dati_finti.py` | dati e repository finti condivisi (ispezioni, alveare, apiario, raccolti, riepiloghi) |
| `tests/test_ai_offline.py` | la catena intera con il client **vero** contro il server locale: richiesta HTTP → nuovi tentativi → lettura → parser → servizio |
| `tests/conftest.py` · `rete_bloccata` | fixture `autouse`: vieta connessioni e DNS verso qualunque macchina che non sia questa; toglie i proxy della shell |
| `tests/test_rete_bloccata.py` | verifica che il blocco funzioni e che l'ambiente di ogni test sia privo di chiavi, di `.env` vero e di proxy |

### Le fixture NON sono registrazioni vere

Sono **scritte a mano** nel formato documentato dei due provider (quello che `llm.py` legge), perché
quando sono state scritte non c'era nessun provider raggiungibile. Provano il **nostro** codice contro
risposte di forma realistica; **non provano** che i provider rispondano proprio così. Il README della
cartella lo dice, e spiega come sostituirle con registrazioni vere dopo la prima chiamata reale: se il
formato vero differisce, i test falliscono nel punto giusto.

## Casi coperti (tutti attraverso il client vero)

| Caso | Test |
|---|---|
| risposta valida, Ollama e OpenRouter (token, modello, intestazione `Authorization`) | `test_ollama_valido_…`, `test_openrouter_valido_…` |
| testo e recinto attorno al JSON | `test_testo_e_recinto_attorno_al_json_…` |
| **JSON rotto**: troncato poi corretto; due volte → fallback senza terza chiamata | `test_json_troncato_poi_corretto_…`, `test_risposta_inutilizzabile_due_volte_…` (4 scenari) |
| **429** con `Retry-After`: attesa 2 s poi successo; 429 sempre → `LLMError` dopo 4 tentativi, attese 2-2-4 | `test_429_…` |
| 503 poi successo; Ollama 500 sempre → errore dopo 4 tentativi | `test_503_…`, `test_ollama_500_…` |
| **401**, 404: un solo tentativo, messaggio con il rimedio, nessuna chiave nel messaggio | `test_401_…`, `test_ollama_senza_il_modello_…` |
| 200 con errore nel corpo, formato inatteso, corpo non JSON, contenuto vuoto | `test_risposte_200_inutilizzabili_…`, `test_corpo_non_json_…`, `test_ollama_con_contenuto_vuoto_…` |
| **timeout** (server lento, client con 1 s) | `test_timeout_…` |
| provider spento (porta chiusa) | `test_provider_spento_…` |
| chiave e testo dell'utente mai nei log né negli errori (5 scenari, log a DEBUG) | `test_ne_la_chiave_ne_il_testo_…` |
| il servizio intero con il client vero: salva con provider/modello/token reali, somma i token del correttivo, non salva se il modello sbaglia due volte, propaga `LLMError`, segnala `in_locale` | `test_servizio_…` |

## Cosa dimostra che non serve la rete né la chiave

1. **`rete_bloccata`** (autouse): `socket.connect`, `connect_ex` e `getaddrinfo` rifiutano ogni
   indirizzo non loopback con `RuntimeError("Test senza rete…")`. Il server finto e MySQL in Docker
   (127.0.0.1) funzionano; Ollama, OpenRouter e Internet no. Un test che per sbaglio chiamasse un
   provider vero **fallirebbe subito**, non passerebbe perché la rete c'era.
2. **`ambiente_pulito`** (già esistente) azzera `LLM_*` e `DB_*` e sposta la radice del progetto: nessun
   test legge il `.env` vero.
3. **Proxy**: un `HTTP_PROXY` nella shell dello sviluppatore instrada anche le richieste a 127.0.0.1 fuori
   dal computer. Lo ha mostrato una prova: lanciando i test con proxy e chiave impostati, quattro test
   fallivano. Ora il blocco toglie i proxy e imposta `NO_PROXY` sul loopback.
4. **Prova in un ambiente ostile**: le suite AI (`test_llm*`, `test_riepilogo`, `test_prompt`,
   `test_assistente`, `test_ai_offline`, `test_rete_bloccata`, `test_config`) passano con
   `LLM_API_KEY`, `LLM_PROVIDER=openrouter`, `LLM_TIMEOUT=1` e `HTTP(S)_PROXY` verso un indirizzo
   irraggiungibile impostati nella shell.

## Limiti

- Una chiamata vera a Ollama o OpenRouter **non è nella suite ordinaria e non deve esserlo**. Si fa con
  `scripts/verifica_llm.py` (#26) e `scripts/prova_prompt.py` (#29); finché non è stata fatta, il
  comportamento dei provider reali è una **assunzione documentata**, non una prova.
- Il test di timeout aspetta circa 1,6 secondi veri: è l'unico che dorme davvero. Gli altri usano una
  pausa iniettata.
- Il blocco non copre i sottoprocessi (Docker CLI) né connessioni fatte da codice C che non passa dal
  modulo `socket` di Python (il driver MySQL in C): per loro vale che parlano solo con 127.0.0.1 per
  costruzione dei test.

## Definition of Done

| Voce | Prova |
|---|---|
| la suite gira senza rete e senza chiave API | `rete_bloccata` (autouse) + `tests/test_rete_bloccata.py` (15 test) + esecuzione con ambiente ostile; tutta la suite rapida passa col blocco attivo |
| casi di errore coperti (timeout, JSON rotto, 429) | `test_timeout_…`; `test_json_troncato_poi_corretto_…`, `test_risposta_inutilizzabile_due_volte_…`; `test_429_con_retry_after_…`, `test_429_sempre_…` |
