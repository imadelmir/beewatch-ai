# Risposte dei provider per i test offline

Quindici file JSON, uno per scenario, usati da `tests/test_ai_offline.py` tramite `tests/llm_registrate.py`.
Ognuno dice cosa risponde il provider: `stato` HTTP, `intestazioni` e `corpo`.

## Cosa sono (e cosa NON sono)

**Non sono registrazioni di chiamate vere.** Quando sono stati scritti non c'era alcun provider
raggiungibile (Ollama non installato, nessuna chiave OpenRouter: vedi la issue di M5-T1). Sono
**scritti a mano seguendo il formato documentato** dei due provider, lo stesso che `beewatch/ai/llm.py`
interpreta:

- Ollama `/api/chat` (`stream: false`): `message.content`, `prompt_eval_count`, `eval_count`;
- OpenRouter `/chat/completions`: `choices[0].message.content`, `usage.prompt_tokens`,
  `usage.completion_tokens`, errori in `error.message`.

Servono a provare il **nostro** codice (lettura della risposta, nuovi tentativi, parser, servizio) contro
risposte di forma realistica, senza rete e senza chiave. **Non provano** che i provider rispondano proprio
così: lo dimostra solo `scripts/verifica_llm.py` con un provider vero.

## Come sostituirli con registrazioni vere

Dopo aver fatto una chiamata vera (#26), sostituire il `corpo` dei file `*_valido.json` con quello
ricevuto (togliendo ogni dato personale) e rieseguire `pytest tests/test_ai_offline.py`: se il formato reale
differisce da quello documentato, il test fallisce nel punto giusto.

## Gli scenari

| File | Cosa simula |
|---|---|
| `ollama_valido` | risposta 200 con un riepilogo valido (812 → 164 token) |
| `ollama_con_testo_e_recinto` | il riepilogo, tra frasi e un recinto di codice |
| `ollama_json_troncato` | il modello si interrompe a metà |
| `ollama_campi_mancanti` | JSON ben formato, quattro campi su sei assenti |
| `ollama_stato_non_ammesso` | JSON completo con `stato_salute` fuori elenco |
| `ollama_solo_testo` | nessun JSON |
| `ollama_senza_testo` | contenuto vuoto |
| `ollama_modello_non_trovato` | 404, modello non scaricato |
| `ollama_errore_500` | 500, il processo del modello è terminato |
| `openrouter_valido` | risposta 200 con un riepilogo valido |
| `openrouter_429` | limite di richieste, con `Retry-After: 2` |
| `openrouter_401` | chiave rifiutata |
| `openrouter_503` | provider a monte non disponibile |
| `openrouter_200_con_errore` | stato 200 ma corpo con un errore |
| `openrouter_formato_inatteso` | 200 con `choices` vuoto |
