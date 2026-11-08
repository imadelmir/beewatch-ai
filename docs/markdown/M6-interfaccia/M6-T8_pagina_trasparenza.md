# M6 - T8 · Pagina Trasparenza: la dichiarazione etica dentro il prodotto

> **Milestone** M6 · Interfaccia Streamlit
> **Task** M6-T8 (issue #39)
> **Stato** completata
> **Commit** `feat(m6): add the Trasparenza page and the ethics document it mirrors`
> **Collegati** → [`../../etica.md`](../../etica.md) · [`../M2-dati/dati.md`](../M2-dati/dati.md) (limiti di trasferibilità) · `app/pages/6_Trasparenza.py` · M7-T4 (issue #44)

## Obiettivo

Rendere la dichiarazione etica parte del prodotto, non solo una slide: una pagina del menu che dice,
in italiano semplice, quali dati usa l'applicazione, chi scrive i riepiloghi, dove le stime possono
sbagliare e quali regole valgono.

## Cosa c'è

**Nella pagina**, dall'alto:

1. l'avvertenza «non è uno strumento diagnostico, non sostituisce un veterinario né un tecnico
   apistico», in un `st.warning` **in cima**;
2. **l'assistente di questa installazione**: se è locale (Ollama), le note non escono dal PC; se è
   esterno (OpenRouter), le note di un'ispezione escono dal PC quando si chiede un riepilogo; se non
   è configurato, nessuna nota va a un modello. Lo dice in base alla configurazione
   (`ConfigLLM.in_locale`, portato in `InfoAssistente.in_locale`);
3. **il modello in uso**, con errore medio e righe di addestramento letti dai metadati;
4. sei sezioni di testo: che cosa fa l'applicazione; quali dati tratta e dove li conserva; l'AI
   generativa che scrive i riepiloghi; i limiti del modello; il veterinario; le regole (GDPR art. 5,
   6, 17 e AI Act art. 50).

**Il documento `docs/etica.md`**, nuovo, ha i cinque punti obbligatori della issue #44 (bias, privacy
e GDPR, trasparenza, EU AI Act, limiti e usi impropri). Ogni sezione si apre con i paragrafi della
pagina, identici, e prosegue con «Nel progetto»: i riferimenti al codice e ai test che la pagina,
scritta per chi non è tecnico, non riporta.

## Decisioni

**1. Un testo, due posti, un test.** I paragrafi stanno in `SEZIONI`, nella pagina; il documento li
contiene parola per parola (li ho inseriti estraendoli dal codice). Il test
`test_ogni_paragrafo_della_pagina_sta_nel_documento_etico_parola_per_parola` li confronta uno per uno:
se qualcuno cambia la pagina e non il documento, o viceversa, la suite si rompe. La pagina non legge
il file a runtime: l'immagine Docker non copia `docs/`, e una pagina etica che si rompe quando manca
un file non servirebbe.

**2. Linguaggio non tecnico, controllato.** Un test vieta nella pagina sigle e termini non spiegati
(LLM, MAE, RMSE, R², token, API…); i quattro termini che restano sono spiegati nella frase stessa
(«le istruzioni che ha ricevuto (il prompt)», «quanto il modello si fida di sé (la confidenza)», «file
di registro (log)», che cos'è un modello di linguaggio).

**3. Solo affermazioni verificate.** Ogni frase sui dati è vera nel codice: le coordinate non entrano
nel contesto dell'assistente (`test_coordinate_e_localita_non_entrano_nel_contesto_ne_nel_prompt`), i
log non contengono le note (i test con `NOTA-SEGRETA-777`), la cancellazione a cascata c'è
(`ON DELETE CASCADE` su `utenti`, `UtentiRepository.elimina`). Il documento cita questi riferimenti.

**4. AI Act detto con misura.** BeeWatch AI non rientra nei sistemi ad alto rischio dell'allegato III;
per i testi generati valgono gli obblighi di trasparenza dell'art. 50, ed è per questo che ci sono il
banner, la provenienza dei riepiloghi e questa pagina.

**5. M7-T4 resta aperta.** `docs/etica.md` copre i cinque punti, ma la issue #44 ha i suoi criteri
(revisione dell'owner A): la PR di questa task la cita senza chiuderla.

## Come si prova

| Cosa | Dove |
|---|---|
| ogni paragrafo della pagina nel documento, parola per parola; i cinque punti nel documento; i contenuti della DoD nella pagina; niente gergo non spiegato; i termini tecnici spiegati; la pagina nel menu | `tests/test_pagina_trasparenza.py` |
| la pagina con AppTest: avvertenza in cima, nessun espansore, tutte le sezioni, assistente locale / esterno / non configurato, modello con i numeri, modello mancante | `tests/test_pagina_trasparenza.py` |
| `crea_servizi` porta `in_locale` dalla configurazione | `tests/test_services.py` |

## File coinvolti

| File | Azione |
|---|---|
| `app/pages/6_Trasparenza.py` | riscritto: la pagina vera |
| `docs/etica.md` | creato |
| `beewatch/services.py` | `InfoAssistente.in_locale`, `Servizi(llm_in_locale=)` |
| `tests/test_pagina_trasparenza.py` | creato |
| `tests/app_finta.py`, `tests/test_app_streamlit.py`, `tests/test_app_struttura.py`, `tests/test_services.py` | adeguati (il test di struttura ammette costanti annotate prima di `avvia`) |
| `README.md` | rimando a `docs/etica.md`, conteggio dei test |

## Definition of Done

| Voce | Esito |
|---|---|
| quali dati sono trattati e dove sono conservati, in linguaggio non tecnico | fatto: sezione «Quali dati tratta e dove li conserva» |
| dichiarazione esplicita che il sistema usa un'AI generativa | fatto: sezione «Un'intelligenza artificiale generativa scrive i riepiloghi» |
| limiti del modello: dati USA 1998-2012, aggregati, applicati al contesto amatoriale italiano | fatto: sezione «I limiti del modello di previsione», le cinque distanze |
| riferimento a GDPR (art. 5, 6, 17) e a EU AI Act (art. 50, rischio minimo) | fatto: sezione «Le regole che valgono per i tuoi dati» |
| avvertenza che il sistema non sostituisce un veterinario o un tecnico apistico | fatto: in cima alla pagina e nella sua sezione |
| se il provider LLM è esterno, dichiarato che le note escono dal PC | fatto: riquadro «L'assistente di questa installazione», in base alla configurazione |
| leggibile da un non tecnico: nessun gergo non spiegato | fatto; `test_nessun_gergo_non_spiegato`, `test_i_termini_tecnici_che_restano_sono_spiegati` |
| raggiungibile dal menu principale, non nascosta in fondo | fatto: è una delle sei pagine del menu |
| coerente parola per parola con `docs/etica.md` | fatto; `test_ogni_paragrafo_della_pagina_sta_nel_documento_etico_parola_per_parola` |
