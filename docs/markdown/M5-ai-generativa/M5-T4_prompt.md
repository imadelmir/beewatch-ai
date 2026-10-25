# M5 - T4 · Prompt engineering

> **Milestone** M5 · Componente AI generativa
> **Task** M5-T4
> **Stato** parziale: codice, prompt e documentazione fatti; **prova con un modello vero ancora da eseguire**
> **Commit** `feat(m5): add the versioned prompts for the inspection summary`
> **Collegati** → [`../../prompt_engineering.md`](../../prompt_engineering.md) · `beewatch/ai/prompt.py` · `beewatch/ai/prompts/`

## Cosa è stato fatto

- `beewatch/ai/prompts/system.md` e `riepilogo.md`: i prompt, con la versione nella prima riga
  (`<!-- versione: v1 -->`), separati dal codice, dalle chiamate al provider (M5-T1/T2), dalla
  validazione (M5-T3) e dalla logica dell'app (M5-T5).
- `beewatch/ai/prompt.py`: carica i file, ricava la versione, compone la richiesta (segnaposto, dati
  mancanti, nota delimitata e neutralizzata, nota lunga troncata).
- Le tre tecniche (role prompting, few-shot, output vincolato) più i guardrail: documentate una per
  una in [`docs/prompt_engineering.md`](../../prompt_engineering.md).
- Dieci note realistiche in `tests/fixtures/note/` con le attese in `attese.json`, e
  `scripts/prova_prompt.py` che le passa a un modello vero e controlla stato, confidenza e assenza
  di farmaci/dosi.
- `pyproject.toml`: i `.md` dei prompt entrano nel package.
- Nessun dato finto nei prompt: gli esempi sono dichiarati esempi, e non coincidono con le note di
  prova né con il seed (un test lo verifica).

## Cosa NON è stato fatto

La Definition of Done chiede due cose che richiedono un modello di linguaggio vero:

- *testato su almeno 10 note realistiche*: le note ci sono, lo script che le prova anche, ma **non
  sono state eseguite contro un modello** (Ollama non è installato e `LLM_API_KEY` è vuota: vedi la
  issue di M5-T1);
- *esempi di output prima e dopo le modifiche al prompt*: richiedono due esecuzioni reali; la
  tabella in `docs/prompt_engineering.md` è vuota di proposito. Compilarla con dati inventati
  sarebbe peggio che lasciarla vuota.

Per chiudere: installare Ollama (o impostare una chiave OpenRouter), poi

```bash
python scripts/prova_prompt.py --output risultati_v1.md
```

L'issue di M5-T4 resta aperta fino ad allora.

## Decisioni

**1. Un'etichetta di versione per entrambi i file.** `versione_prompt()` restituisce `v1` solo se i
due file concordano; altrimenti il programma si ferma con un errore chiaro. Una sola stringa nel
database basta a sapere quale insieme di istruzioni ha prodotto un riepilogo.

**2. Le regole negative hanno sempre un'alternativa positiva.** «Nessun farmaco» è accompagnato da
«rivolgiti alla ASL o a un tecnico»: i modelli piccoli seguono meglio «fai Y» di «non fare X».

**3. Il controllo dei farmaci è per parole, ed è dichiarato rozzo.** Serve a far vedere le
violazioni evidenti nella prova; non è un filtro di sicurezza né va presentato come tale.

**4. I test verificano la coerenza, non l'obbedienza.** Gli esempi few-shot passano per il parser, i
valori del prompt coincidono con quelli dello schema, la nota non può chiudere il suo blocco. Che un
modello obbedisca lo dice solo la prova con il modello.

## Test

`tests/test_prompt.py` (47 test, `prompt.py` al 100%): file e versioni, coerenza con lo schema, esempi
validi per il parser e senza termini vietati, guardrail presenti, composizione della richiesta
(segnaposto, dati mancanti, delimitatori, troncamento), dieci note con attese, e lo script di prova
con un modello finto.

## Definition of Done

| Voce | Esito |
|---|---|
| prompt in file versionati, non stringhe nel codice | fatto: `test_i_prompt_sono_file_versionati_non_stringhe_nel_codice` |
| le tre tecniche documentate una per una in `docs/prompt_engineering.md` | fatto |
| testato su almeno 10 note realistiche | **non completo**: note e script pronti, prova con modello vero da eseguire |
| esempi di output prima e dopo le modifiche al prompt | **non completo**: richiede due esecuzioni con un modello vero |
