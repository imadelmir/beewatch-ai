# BeeWatch AI — Documento etico

> **Milestone** M6-T8 (pagina Trasparenza) · prepara M7-T4 (issue #44)
> **Collegati** → `app/pages/6_Trasparenza.py` · [`M2-dati/dati.md`](markdown/M2-dati/dati.md) (limiti di trasferibilità) · `beewatch/ai/assistant.py` · `sql/schema.sql`

Questo documento e la pagina **Trasparenza** dell'applicazione dicono le stesse cose. Il testo
che apre ogni sezione è quello della pagina, **parola per parola** (un test,
`tests/test_pagina_trasparenza.py`, lo controlla a ogni modifica); i paragrafi «Nel progetto» che
seguono aggiungono i riferimenti al codice, che la pagina, scritta per chi non è tecnico, non
riporta.

## Che cosa fa BeeWatch AI

BeeWatch AI è un quaderno di campo per l'apicoltore amatoriale. Tiene l'anagrafica di apiari e alveari, il registro delle ispezioni e dei raccolti, e offre due aiuti: una stima della produzione di miele e un riepilogo scritto delle note di campo.

Entrambi gli aiuti possono sbagliare. Questa pagina spiega come funzionano, dove possono sbagliare e che cosa succede ai tuoi dati.

---

## 1. Bias: dati USA 1998–2012 per un apicoltore amatoriale italiano

Il modello di previsione ha imparato dalle rese medie per colonia degli stati USA, rilevate dal Dipartimento dell'Agricoltura statunitense (USDA) fra il 1998 e il 2012. Stima quanto miele produce in media una colonia in uno stato e in un anno.

Fra quei dati e il tuo apiario ci sono cinque distanze. Sono medie di stati interi, non di un apiario. Vengono da apicoltura commerciale, con nomadismo e selezione, non da poche arnie fisse. Nessuno stato del dataset ha il clima italiano. I dati si fermano al 2012. E mancano le cose che osservi davvero: forza della famiglia, regina, varroa, fioriture, meteo.

Per questo una stima non è mai un numero solo: è sempre un intervallo, e quando l'intervallo è più largo della stima il valore centrale non si mostra. Va letta come ordine di grandezza, non come la produzione del tuo alveare.

**Nel progetto.** Le cinque distanze sono analizzate in `docs/markdown/M2-dati/dati.md`
(«Limiti di trasferibilità»). Il modello usa solo stato, anno e tre valori storici (M4-T2); il
servizio rifiuta i parametri scritti a mano fuori dall'intervallo visto in addestramento (M6-T5),
perché una foresta casuale non sa estrapolare. La regola «se l'intervallo è più largo della stima,
la stima non si mostra» è in `Servizi._stima`; l'intervallo viene dai residui fuori campione salvati
nei metadati del modello (M4-T6). La Dashboard dichiara che il confronto previsto/reale è dentro il
campione (M6-T7).

---

## 2. Privacy e GDPR

L'applicazione conserva i dati che scrivi tu: il nome e l'indirizzo email del profilo, gli apiari con la località e, se le inserisci, le coordinate, gli alveari, le ispezioni con le note di campo, i raccolti, le stime di produzione e i riepiloghi scritti dall'assistente.

Tutto sta in un database MySQL sul computer dove gira l'applicazione, dentro un contenitore Docker. Nessun dato viene copiato su un servizio esterno, con una sola eccezione possibile: le note di un'ispezione, quando chiedi un riepilogo e l'assistente usa un servizio esterno (vedi sotto).

Le coordinate e la località degli apiari non vengono mai inviate all'assistente: per riassumere le note non servono. I file di registro (log) annotano che cosa è successo, ma non contengono il testo delle note.

Il database è costruito per cancellare tutto: eliminando un utente spariscono con lui apiari, alveari, ispezioni, raccolti, stime e riepiloghi.

GDPR, il regolamento europeo sulla protezione dei dati. Art. 5: si raccolgono solo i dati che servono, per lo scopo dichiarato, e si conservano al sicuro. Art. 6: i dati si trattano perché sei tu a usare l'applicazione e a inserirli. Art. 17: hai il diritto di farli cancellare, e il database è costruito per cancellarli tutti.

**Nel progetto.**

- *Dove stanno i dati:* il database MySQL del `docker-compose.yml`, con un volume locale; nessuna
  tabella viene sincronizzata altrove. Lo schema è in `sql/schema.sql`.
- *Geolocalizzazione:* `apiari.latitudine` e `apiari.longitudine` sono facoltative e marcate nello
  schema come «dato personale indiretto: mai inviato a un LLM esterno». Il contesto dell'assistente
  non le contiene (`beewatch/ai/assistant.py`); lo verifica
  `test_coordinate_e_localita_non_entrano_nel_contesto_ne_nel_prompt`.
- *Log senza note:* i log (`logs/beewatch.log`) registrano provider, modello, durata e token, mai il
  testo delle note; lo verificano i test con la nota `NOTA-SEGRETA-777` (`tests/test_ai_offline.py`,
  `tests/test_assistente.py`).
- *Note a un servizio esterno:* solo con `LLM_PROVIDER=openrouter`. La pagina Assistente lo dice
  prima di generare e lo ripete sotto il riepilogo; la pagina Trasparenza lo dice in base alla
  configurazione (`ConfigLLM.in_locale`).
- *Art. 5 (minimizzazione):* si chiedono solo i dati che servono alle funzioni; le coordinate sono
  facoltative.
- *Art. 6 (base giuridica):* i dati li inserisce l'utente per usare l'applicazione (esecuzione del
  servizio che ha chiesto).
- *Art. 17 (cancellazione):* tutte le tabelle personali dipendono da `utenti` con `ON DELETE
  CASCADE`; `UtentiRepository.elimina` (query Q11) cancella un utente e con lui tutto il resto,
  riepiloghi compresi (`tests/test_riepiloghi_repository.py`).

---

## 3. Trasparenza

I riepiloghi della pagina Assistente AI li scrive un modello di linguaggio: un programma che ha imparato a produrre testo leggendone moltissimo. Non legge l'arnia: legge solo le note che hai scritto e qualche dato dell'alveare.

Può sbagliare, inventare o fraintendere un'abbreviazione. Per questo ogni riepilogo dichiara quanto il modello si fida di sé (la confidenza), elenca che cosa le note non dicono, porta il nome del modello e la versione delle istruzioni che ha ricevuto (il prompt), e sta sotto un avviso che non si può chiudere.

Se l'assistente gira sul tuo computer (Ollama), le note restano lì. Se usa un servizio esterno (OpenRouter), le note di quell'ispezione escono dal PC e vengono lette da quel servizio: l'applicazione lo dice prima di generare e lo ripete sotto il riepilogo.

**Nel progetto.** Il banner del §9 della specifica (`ui.banner_ai`, permanente e non richiudibile);
la confidenza e i «campi non deducibili» fanno parte dello schema del riepilogo
(`beewatch/ai/riepilogo.py`); ogni riepilogo salvato porta provider, modello, versione del prompt,
durata, token e tentativi (`riepiloghi_ispezione`, DA-03). Il testo del modello si mostra come testo
semplice (M6-T6). Per la previsione: mai un numero secco, sempre l'intervallo, la versione del
modello a schermo e le metriche lette dal file dei metadati (M6-T5, M6-T7).

---

## 4. EU AI Act

AI Act, il regolamento europeo sull'intelligenza artificiale. BeeWatch AI non rientra fra i sistemi ad alto rischio: è un aiuto per un hobby, a rischio minimo. Vale però l'art. 50, sulla trasparenza: chi legge un testo scritto da un'intelligenza artificiale deve saperlo. Per questo c'è l'avviso sopra ogni riepilogo e c'è questa pagina.

**Nel progetto.** BeeWatch AI non rientra nei casi dell'allegato III (sistemi ad alto rischio): non
decide nulla sulle persone, è un supporto a un'attività amatoriale. Gli obblighi di trasparenza
dell'art. 50 per i contenuti generati sono coperti dal banner, dalla provenienza sotto ogni
riepilogo e da questa pagina.

---

## 5. Limiti e usi impropri

BeeWatch AI non è uno strumento diagnostico. Non sostituisce un veterinario né un tecnico apistico: per malattie, parassiti o una famiglia in difficoltà, rivolgiti al servizio veterinario della tua ASL o a un tecnico.

**Usi impropri da evitare.**

- Prendere la stima di produzione come la resa del proprio alveare, o usarla per decidere quando
  smielare o nutrire: il modello non sa nulla del singolo alveare (`dati.md`, «Quattro cose che non
  faremo»).
- Prendere un riepilogo dell'assistente come una diagnosi: legge solo le note, può sbagliare, e lo
  dichiara con la confidenza e con le lacune.
- Inviare a un servizio esterno note che contengono dati di altre persone: con un provider esterno
  le note escono dal PC.

**Nel progetto.** La frase sul veterinario è in cima alla pagina Trasparenza, nel banner della
pagina Assistente e nel README; l'assistente stesso, per malattie o parassiti, suggerisce il servizio
veterinario dell'ASL o un tecnico (prompt `v2`, M5-T4).
