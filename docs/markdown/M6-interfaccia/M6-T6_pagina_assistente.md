# M6 - T6 · Pagina Assistente AI: il riepilogo delle note di un'ispezione

> **Milestone** M6 · Interfaccia Streamlit
> **Task** M6-T6 (issue #37)
> **Stato** completata
> **Commit** `feat(m6): add the Assistente AI page with structured summaries and history`
> **Collegati** → [`ui_spec.md`](ui_spec.md) §6, §9, §11 · [`M6-T4_pagina_ispezioni.md`](M6-T4_pagina_ispezioni.md) · M5 (`beewatch/ai/`) · `app/pages/4_Assistente_AI.py` · `beewatch/services.py`

## Obiettivo

La terza funzionalità della scheda del progetto e il punto in cui si soddisfa il requisito di
trasparenza verso l'utente: si vede sempre che il testo è scritto da un modello, con quale modello
e quale prompt, quanto il modello si fida di sé e che cosa le note non dicono.

## Cosa c'è

Anatomia del §6, con il banner del §9 subito sotto l'intestazione:

| Parte | Cosa |
|---|---|
| **Intestazione** e **banner AI** | il testo del §9 parola per parola, permanente e non richiudibile (`banner_ai`, M6-T2) |
| **Controlli** | l'assistente in uso (modello e provider, versione del prompt) e la frase «le note vengono inviate a questo modello»; l'ispezione da riassumere, fra quelle **con note** dell'apiario attivo, dalla più recente; le sue note in un campo di sola lettura («le note che il modello leggerà»); il bottone «Genera il riepilogo» |
| **Contenuto** | due metriche (ispezioni con note, riepiloghi salvati dell'ispezione); il riepilogo in forma strutturata; lo **storico dei riepiloghi** dell'ispezione, ognuno in un espansore con data, modello, prompt e confidenza |
| **Note** | che cosa legge il riepilogo, che le note non si modificano, che ogni riepilogo porta modello e prompt |

Il riepilogo strutturato mostra:

- **stato di salute** e **confidenza** come metriche (testo con icona: «⚠ Attenzione», «Media»);
- elementi rilevati;
- criticità, con la gravità;
- **azioni suggerite ordinate per priorità** (alta, media, bassa), con la scadenza se c'è;
- **«Cosa l'AI non ha potuto dedurre dalle note»**: il campo `campi_non_deducibili` dello schema;
- la provenienza: modello, provider, versione del prompt, durata, ed eventualmente «con un
  tentativo correttivo»; se il provider non è locale, la frase «le note sono state inviate a un
  servizio esterno».

### Servizi (`beewatch/services.py`)

| Metodo | Cosa fa |
|---|---|
| `info_assistente()` | `InfoAssistente`: descrizione del modello (senza segreti), versione del prompt, attesa massima. **Non crea il client**: si può mostrare anche se il provider non è raggiungibile |
| `riepiloghi_ispezione(utente_id, ispezione_id, limite=20)` | i riepiloghi salvati dal più recente, come `RiepilogoSalvato` con il `Riepilogo` ricostruito dallo **stesso schema** della validazione; una riga che non lo rispetta più si salta e va nel log |
| `genera_riepilogo_ispezione` | invariato (M5-T5) |

`Servizi` riceve `timeout_llm` (da `LLM_TIMEOUT`, in `crea_servizi`) per calcolare l'attesa massima.
`RiepiloghiRepository` ha `elenco(utente_id, ispezione_id, limite)`; `ultimo` ora lo usa.

### In `app/avvio.py` e `app/ui.py`

- `avvio.riepiloghi_ispezione`: la lettura in cache dello storico; dopo un riepilogo salvato la pagina
  la svuota.
- `ui.metrica` accetta anche un testo e lo mostra così com'è.

## Decisioni

**1. Il testo del modello si mostra come testo semplice.** La risposta di un modello di linguaggio è
contenuto non fidato: un `**` o un `[link](…)` nella risposta diventerebbero grassetto o un link
cliccabile. Ogni frase del modello passa da `testo_semplice`, che annulla i caratteri speciali di
Markdown; le note dell'ispezione si mostrano in un campo di sola lettura, come in M6-T4.

**2. L'attesa dichiarata è quella vera.** Il client ha un tetto di tre volte `LLM_TIMEOUT` per
chiamata, e una risposta malformata ne fa fare una seconda: con il timeout predefinito (60 s) il
massimo è 6 minuti. Lo spinner dice «di solito da pochi secondi a un minuto, ma con un modello
locale lento fino a circa N minuti», con N calcolato da `info_assistente`. La specifica suggeriva
«fino a 30 secondi»: con `llama3.1:8b` in locale non sarebbe onesto.

**3. Solo le ispezioni con note.** Il servizio rifiuta un'ispezione senza note; la pagina non le
propone nemmeno, e se nell'apiario non ce n'è nessuna rimanda a Ispezioni.

**4. Tre esiti oltre al successo, tre messaggi.** Il provider non risponde o va in timeout
(`LLMError`): `mostra_errore`, nulla salvato, il bottone resta per riprovare. Il modello risponde
male anche dopo il tentativo correttivo: un avviso con il messaggio del servizio, nessun riepilogo
inventato. Il database non salva: il riepilogo si vede comunque, con l'avviso di copiarlo. Senza
provider configurato: «La configurazione non è valida».

**5. Le note vanno al modello: lo si dice prima.** La riga sull'assistente dichiara che le note
saranno inviate a quel modello; dopo, se il provider non è locale, lo si ripete.

**6. Ogni riepilogo resta.** Generarne uno nuovo non cancella i precedenti (DA-03): lo storico li
mostra tutti, ognuno con il modello e il prompt che l'hanno scritto, così si possono confrontare
versioni del prompt diverse.

## Come si prova

| Cosa | Dove |
|---|---|
| informazioni (attesa dal timeout, nessun client creato), storico dal più recente, ispezioni altrui, riga fuori schema saltata con il log, id non validi | `tests/test_servizi_assistente_storico.py` (7) |
| `elenco` su MySQL (ordine, limite, JSON identico, ispezione altrui) e lo storico del servizio intero | `tests/test_riepiloghi_repository.py` (integration) |
| la pagina con AppTest: banner fuori da ogni espansore, solo ispezioni con note, note in sola lettura, modello e prompt a schermo, spinner, riepilogo strutturato con confidenza e lacune, salvataggio e storico, testo del modello senza formattazione, azioni per priorità, risposta illeggibile, timeout, nessun provider, salvataggio fallito, note inviate fuori, stati vuoti, database spento, storico illeggibile | `tests/test_pagina_assistente.py` (15) |
| `metrica` con un testo | `tests/test_ui.py` |

**Prova a mano nel browser con il modello vero** (stack MySQL isolato, `streamlit run app/Home.py`,
Ollama in locale con `llama3.1:8b`, prompt `v2`, dati del seed): la pagina propone le 14 ispezioni con
note di «Apiario del Noce». Su quella del 16/05/2026 (alveare A4, sciamato) lo spinner mostra «fino a
circa 6 minuti», e dopo **20,7 s** compare il riepilogo:
- stato «⚠ Attenzione», confidenza «Media»;
- gli elementi rilevati, una criticità di gravità media e un'azione di priorità alta;
- tre cose che le note non dicono, fra cui un dubbio vero: «sciamatura sì» vuol dire in corso o già
  avvenuta?

Il riepilogo è salvato, e lo storico lo rilegge dal database e lo mostra uguale. Dalla prova sono
venuti due ritocchi: stato e confidenza su due colonne invece di quattro, perché «⚠ Attenzione» si
troncava; e l'etichetta «Riepiloghi salvati», più corta. Le note restano sul PC: il provider è
locale. Risorse Docker reali non toccate.

I finti sono in `tests/assistente_finto.py` (riepiloghi in memoria, raccolti vuoti, una risposta con
Markdown); `IspezioniInMemoria` ha `trova`. Il servizio usato dalla pagina è quello vero.

## Cosa NON c'è

La conversazione libera con l'assistente (le tabelle `conversazioni` e `messaggi` esistono, la pagina
no); cancellare un riepilogo; confrontare due riepiloghi affiancati.

## File coinvolti

| File | Azione |
|---|---|
| `app/pages/4_Assistente_AI.py` | riscritto: la pagina vera |
| `app/avvio.py` | lettura in cache dello storico dei riepiloghi |
| `app/ui.py` | `metrica` con un testo |
| `beewatch/services.py` | `RiepilogoSalvato`, `InfoAssistente`, `info_assistente`, `riepiloghi_ispezione`, `timeout_llm` |
| `beewatch/repositories_riferimento.py` | `RiepiloghiRepository.elenco` |
| `tests/assistente_finto.py`, `tests/test_servizi_assistente_storico.py`, `tests/test_pagina_assistente.py` | creati |
| `tests/anagrafica_finta.py`, `tests/app_finta.py`, `tests/test_app_streamlit.py`, `tests/test_ui.py`, `tests/test_riepiloghi_repository.py` | adeguati |
| `README.md` | conteggio dei test |

## Definition of Done

| Voce | Esito |
|---|---|
| banner AI del §9 presente, permanente e non nascondibile | fatto; `test_la_pagina_ha_banner_ispezioni_con_note_e_le_note_da_leggere`, e i test di `banner_ai` in `test_ui.py` |
| selezione dell'ispezione da cui generare il riepilogo | fatto: le ispezioni con note dell'apiario attivo; `test_cambiando_ispezione_si_vedono_le_sue_note` |
| output mostrato in forma strutturata: criticità, azioni con priorità, confidenza | fatto; `test_il_riepilogo_si_mostra_strutturato_con_confidenza_e_lacune`, `test_il_testo_del_modello_non_diventa_formattazione_e_le_azioni_vanno_per_priorita` |
| livello di confidenza dichiarato e visibile | fatto: una metrica, e nell'etichetta di ogni riepilogo dello storico |
| elenco dei campi che l'AI NON ha potuto dedurre dalle note | fatto: «Cosa l'AI non ha potuto dedurre dalle note» |
| `st.spinner` con messaggio che dichiara l'attesa possibile | fatto, con l'attesa calcolata dal timeout; `test_lo_spinner_dichiara_lattesa_possibile` |
| timeout e `LLMError` gestiti con messaggio comprensibile, mai traceback | fatto; `test_un_timeout_del_modello_si_spiega_senza_traceback`, `test_una_risposta_illeggibile_lo_dice_e_non_salva`, `test_senza_provider_configurato_lo_dice` |
| storico dei report generati per quell'ispezione | fatto; `test_il_riepilogo_salvato_entra_nello_storico`, integration |
| versione del prompt e modello LLM usati mostrati a schermo | fatto: prima di generare (assistente in uso) e sotto ogni riepilogo |
| nessuna chiamata diretta all'LLM nella pagina | fatto; `test_il_client_del_modello_di_linguaggio_non_si_importa_nemmeno_per_nome`, `test_nessun_import_proibito_dentro_app` |
