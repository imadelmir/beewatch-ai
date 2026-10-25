# M5 - T2 · Robustezza delle chiamate al modello

> **Milestone** M5 · Componente AI generativa
> **Task** M5-T2
> **Stato** completata
> **Commit** `feat(m5): retry transient LLM failures with backoff and a time cap`
> **Collegati** → [`M5-T1_client_llm.md`](M5-T1_client_llm.md) · `beewatch/ai/llm.py`

## Obiettivo

Impedire che l'app si pianti durante la demo perché il provider ha risposto lentamente, ha restituito
un 429 o si sta ancora avviando. Ogni chiamata o riesce, o finisce in un `LLMError` con un messaggio
comprensibile, in un tempo limitato.

## Cosa fa

Il ciclo sta in `LLMClient._invia`, in comune ai due provider, senza librerie: un `while` con un
limite.

| Caso | Comportamento |
|---|---|
| timeout, connessione che non riesce, 408, 429, 5xx | si riprova, al massimo **3 nuove volte** (4 tentativi), aspettando **1, 2 e 4 secondi** |
| 400, 401, 402, 403, 404, altri 4xx | `LLMError` subito, **mai** un nuovo tentativo |
| risposta arrivata ma inutilizzabile (non JSON, senza testo, formato inatteso) | `LLMError` subito |
| `Retry-After` (secondi o data HTTP) | si aspetta quello se è più lungo del backoff, **al massimo 30 secondi**; se chiede di più si smette e l'errore dice quanto attendere |
| tempo complessivo | non supera **tre volte il timeout**: raggiunto il tetto non si riprova più |
| eccezione imprevista nel client | registrata con lo stack e trasformata in `LLMError`: **nient'altro esce da `completa`** |

Dopo tentativi esauriti l'errore è quello del provider più «(dopo N tentativi)»: il suffisso compare
solo se i tentativi sono stati più di uno. `RispostaLLM.tentativi` dice quanti ne sono serviti.

## Decisioni progettuali

**1. Il timeout si ritenta.** Un modello che si sta caricando può scadere la prima volta e rispondere
alla seconda. Ma quattro timeout da 60 secondi sarebbero quattro minuti di interfaccia ferma: da qui il
**tetto di tre volte il timeout**. Con il timeout predefinito (60 s) i timeout ripetuti si fermano al
secondo tentativo (121 s); con errori veloci (connessione rifiutata, 5xx) tutti e quattro i tentativi
sono fatti in 7 secondi.

**2. `Retry-After` con un tetto.** Il backoff è il minimo, `Retry-After` può solo allungarlo. Un
provider che chiede di aspettare un'ora non blocca l'interfaccia: si rinuncia subito e lo si dice. La
documentazione di OpenRouter consultata non descrive questa intestazione: si rispetta se c'è, non ci
si conta.

**3. Si ritenta solo ciò che può passare da solo.** Una chiave rifiutata o un modello inesistente non
migliorano riprovando, e ogni tentativo costerebbe tempo (e forse credito).

**4. Pausa e orologio iniettabili** (`pausa=`, `orologio=`): i test non aspettano secondi veri e vedono
esattamente quanto il client avrebbe aspettato. `crea_client(cfg, attese=…, pausa=…, orologio=…)` li
inoltra; l'applicazione usa i valori predefiniti.

**5. Log.** Un avviso per ogni tentativo fallito (provider, numero, causa **solo come tipo o stato**,
attesa) e una riga finale con modello, durata, token e tentativi. Mai la chiave, mai il testo
dell'utente (solo la sua lunghezza), mai il testo di un errore del provider.

**6. Una risposta 200 che contiene un errore** (OpenRouter può farlo) non si ritenta: è un caso raro e
distinguerne i codici transitori sarebbe complessità senza una necessità dimostrata.

## Come si prova

`tests/test_llm_robustezza.py`: server HTTP finto su socket veri, più `requests.post` sostituito dove
serve un errore di rete immediato, pausa e orologio finti. Si controlla, per entrambi i provider,
gli stati transitori e permanenti, le attese esatte 1-2-4, la rinuncia dopo il quarto tentativo,
`Retry-After` in secondi, in data (anche senza fuso) e oltre i 30 secondi (con il confine esatto),
il timeout seguito da un successo, il tetto di tempo, il caso del provider irraggiungibile, il log
(tentativi, token, nessun segreto), quattordici corpi di risposta strani che devono dare solo
`LLMError`, e l'eccezione imprevista.

**Test di mutazione** sulla logica dei tentativi: 13 mutanti (un tentativo in meno, `Retry-After`
che accorcia il backoff, limite dei 30 s spostato, nessun tetto di tempo, 429 non ritentato, 400
ritentato, suffisso sul primo tentativo, connessione non ritentata, data senza fuso, eccezioni
impreviste che escono…). Dopo i test di confine aggiunti, **12 su 13 sono uccisi**; il tredicesimo
(un `Retry-After` negativo) è **equivalente**, perché il `max` con il backoff lo neutralizza già.

## File coinvolti

| File | Azione |
|---|---|
| `beewatch/ai/llm.py` | tentativi, `Retry-After`, tetto di tempo, `tentativi` in `RispostaLLM`, `LLMError` come unica eccezione |
| `tests/test_llm_robustezza.py` | creato (84 test) |
| `tests/test_llm.py`, `tests/test_verifica_llm.py` | i client provano una chiamata sola (`attese=()`) |

## Definition of Done

| Voce | Prova |
|---|---|
| comportamento verificato con un provider simulato irraggiungibile | `test_un_provider_irraggiungibile_da_un_errore_chiaro_dopo_quattro_tentativi`: 4 tentativi, attese 1-2-4, messaggio «Ollama non risponde su …» e «(dopo 4 tentativi)» |
| nessuna eccezione non gestita raggiunge l'interfaccia | `LLMError` è l'unica che esce da `completa`; `test_risposte_strane_diventano_llm_error_e_mai_un_altro_errore` (14 corpi × 2 provider) e `test_un_errore_imprevisto_diventa_llm_error_con_lo_stack_nel_log` |
| latenza e token loggati | riga finale `LLM provider/modello: N ms, token A→B, K tentativi, richiesta di N caratteri`; `test_il_log_finale_ha_modello_durata_token_e_tentativi` |

Non dipende dalla verifica con un provider vero (M5-T1, #26): tutto qui si prova senza rete.
