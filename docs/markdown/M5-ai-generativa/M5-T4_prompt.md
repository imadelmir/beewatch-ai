# M5 - T4 · Prompt engineering

> **Milestone** M5 · Componente AI generativa
> **Task** M5-T4
> **Stato** completata: `v1` (PR #97), poi prova con un modello vero e `v2` (2026-11-08)
> **Commit** `feat(m5): add the versioned prompts for the inspection summary` ·
> `feat(m5): prompt v2 tested on ten notes with a real model`
> **Collegati** → [`../../prompt_engineering.md`](../../prompt_engineering.md) · `beewatch/ai/prompt.py` · `beewatch/ai/prompts/`

## Cosa è stato fatto

- `beewatch/ai/prompts/system.md` e `riepilogo.md`: i prompt, con la versione nella prima riga
  (`<!-- versione: v2 -->`), separati dal codice, dalle chiamate al provider (M5-T1/T2), dalla
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

## La prova con un modello vero (2026-11-08)

Con Ollama 0.40.15 e `llama3.1:8b`, sulle dieci note di prova (dettagli, tabella «prima e dopo» ed
esempi in [`docs/prompt_engineering.md`](../../prompt_engineering.md); risposte complete in
[`prove_prompt/`](prove_prompt/)):

| Versione | Note superate |
|---|---|
| `v1` (rivalutata con i controlli di `v2`) | 5 / 10 |
| `v2`, prova 1 | 8 / 10 |
| `v2`, prova 2 | 9 / 10 |

La lettura umana delle risposte di `v1` ha trovato errori che i controlli di allora non vedevano. I
più gravi erano sulla nota della covata sospetta: un dettaglio inventato, nessun rimando alla ASL e il
consiglio di provare lo stuzzicadenti in altre celle. Quegli errori sono diventati controlli
automatici in `attese.json`, e `v2` li corregge.

Resta un limite dichiarato: `llama3.1:8b` non etichetta le contraddizioni (nota 09), con nessuna
versione del prompt. La nota delle abbreviazioni (08) passa in una prova su due.

## Decisioni

**1. Un'etichetta di versione per entrambi i file.** `versione_prompt()` restituisce la versione solo se i
due file concordano; altrimenti il programma si ferma con un errore chiaro. Una sola stringa nel
database basta a sapere quale insieme di istruzioni ha prodotto un riepilogo.

**2. Le regole negative hanno sempre un'alternativa positiva.** «Nessun farmaco» è accompagnato da
«rivolgiti alla ASL o a un tecnico»: i modelli piccoli seguono meglio «fai Y» di «non fare X».

**3. Il controllo dei farmaci è per parole, ed è dichiarato rozzo.** Serve a far vedere le
violazioni evidenti nella prova; non è un filtro di sicurezza né va presentato come tale.

**4. I test verificano la coerenza, non l'obbedienza.** Gli esempi few-shot passano per il parser, i
valori del prompt coincidono con quelli dello schema, la nota non può chiudere il suo blocco. Che un
modello obbedisca lo dice solo la prova con il modello.

**5. Gli errori trovati a mano diventano controlli.** Una volta visto un errore nella lettura umana
(un dettaglio inventato, un'azione pericolosa), lo si scrive in `attese.json` come espressione che deve
o non deve comparire. Le prove successive lo cercano da sole. Le risposte vecchie si rivalutano con gli
stessi controlli, perché il confronto sia alla pari.

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
| testato su almeno 10 note realistiche | fatto: 10 note con `llama3.1:8b`, tre prove (`v1`, `v2` due volte), risultati in `prove_prompt/` |
| esempi di output prima e dopo le modifiche al prompt | fatto: tabella nota per nota ed esempi delle note 06 e 10 in `docs/prompt_engineering.md` |
