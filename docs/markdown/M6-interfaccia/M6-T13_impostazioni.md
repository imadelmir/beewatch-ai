# M6 - T13 · Pagina Impostazioni

> **Milestone** M6 · Interfaccia Streamlit
> **Task** M6-T13 (issue #59, P3)
> **Stato** completata
> **Commit** `feat(m6): add the Settings page with profile, reminders, the external-assistant consent and a read-only configuration`
> **Collegati** → `app/pages/8_Impostazioni.py` · `beewatch/services.py` · `beewatch/repositories_riferimento.py` · `sql/schema_05_preferenze.sql`

## Obiettivo

Dalla issue: «pagina Impostazioni con quattro linguette (`st.tabs`): Profilo, Notifiche, AI e Modelli,
Database. Le prime tre scrivono su MySQL. La quarta è di sola lettura: mostra la configurazione che
arriva da `.env`». La issue non ha caselle compilate: la Definition of Done usata è in fondo.

## Cosa c'è

**La pagina** (`app/pages/8_Impostazioni.py`, ottava voce del menu), quattro schede:

| Scheda | Cosa si fa | Dove finisce |
|---|---|---|
| **Profilo** | nome ed email; la password (serve quella attuale); la cancellazione dell'account con password e spunta | `utenti` |
| **Notifiche** | dopo quanti giorni (7–90) un alveare va ricontrollato; se avvisare delle ispezioni recenti a rischio medio o alto | `preferenze_utente` |
| **AI e Modelli** | quale assistente è in uso e dove gira; il consenso a inviare le note a un servizio esterno; il modello di previsione | `preferenze_utente` |
| **Database** | la configurazione da `.env`, in sola lettura: server, database, utente, assistente, modello, livello dei log | — |

**Le preferenze contano davvero**, non sono solo salvate:

- la **Home** ha una sezione «Promemoria»: gli alveari da ricontrollare secondo i giorni scelti e le
  ispezioni a rischio degli ultimi 60 giorni (se gli avvisi sono attivi); il numero «Da controllare»
  usa gli stessi giorni;
- l'**Assistente AI**, se è esterno (OpenRouter) e il consenso è tolto, non propone il bottone e lo
  dice; il **servizio** rifiuta comunque la richiesta prima di chiamare il modello, così il consenso
  vale anche fuori dall'interfaccia.

**Lo schema** (`sql/schema_05_preferenze.sql`): una riga per utente, con i predefiniti (30 giorni,
avvisi sì, assistente esterno sì) quando la riga non c'è. Si salva con un upsert. Cancellando l'utente
la riga sparisce (`ON DELETE CASCADE`).

## Decisioni

**1. La cancellazione dell'account chiede la password e una spunta.** Il bottone resta disabilitato
senza spunta, e la spunta si ricontrolla nel codice (un bottone disabilitato non è una garanzia). Dopo
la cancellazione si esce e si torna al lucchetto. Il resto lo fanno le chiavi esterne a cascata
(GDPR art. 17), già provate in M3.

**2. Cambiare la password richiede quella attuale**, anche con l'accesso già fatto: chi trova il PC
sbloccato non può cambiarla. Le regole della password nuova sono le stesse della registrazione.

**3. L'email resta unica**: riscrivere la propria va bene, usare quella di un altro account no. Il
controllo è nel repository, prima dell'`UPDATE`, con un messaggio chiaro sul campo.

**4. La scheda Database non mostra segreti.** `Servizi.configurazione_visibile()` restituisce righe già
pronte: password e chiave API diventano «impostata» o «mancante», il percorso del modello solo il nome
del file. La pagina non riceve mai l'oggetto `Config` (regola del progetto: niente `config.database` o
`config.llm` a `st.write`).

**5. Gli avvisi di rischio partono dagli alveari attivi.** Un alveare eliminato non ha bisogno di
promemoria: la prima versione, che leggeva tutte le ispezioni a rischio, mostrava anche quelle, e un
test l'ha trovato. `oggi` si può passare al servizio, così la finestra di 60 giorni si prova con date
fisse.

**6. Niente email o notifiche push.** I promemoria compaiono nella Home, ogni volta che la si apre; la
pagina lo dice. Le email avrebbero chiesto un server SMTP e credenziali in più.

## Come si prova

| Cosa | Dove |
|---|---|
| profilo (leggere, aggiornare, email di un altro, campi non validi, utente assente), password (attuale sbagliata, regole, conferma), cancellazione con la password, preferenze (predefiniti, salvate, non valide con il campo), promemoria con le preferenze e la finestra di 60 giorni, consenso all'assistente esterno (il modello non viene chiamato), configurazione senza segreti | `tests/test_servizi_impostazioni.py` |
| su MySQL: preferenze predefinite, salvate e sostituite, profilo, password, cancellazione a cascata | `tests/test_servizi_impostazioni.py` (integration) |
| la pagina: le quattro schede, il nome aggiornato anche nella sidebar, email già usata, password, cancellazione dell'account che riporta al lucchetto, notifiche e consenso salvati, configurazione senza segreti, database spento | `tests/test_pagina_impostazioni.py` |
| la Home con i promemoria, l'Assistente senza e con il consenso | `tests/test_pagina_impostazioni.py` |
| i giorni scelti nel numero «Da controllare» della Home | `tests/test_servizi_home.py` |

## File coinvolti

| File | Azione |
|---|---|
| `app/pages/8_Impostazioni.py` | creato |
| `app/Home.py` | la voce Impostazioni nel menu |
| `app/avvio.py` | letture in cache di profilo, preferenze e promemoria; nome nell'accesso; uscita dopo la cancellazione |
| `app/schermate/home.py` | la sezione Promemoria |
| `app/pages/4_Assistente_AI.py` | il consenso all'assistente esterno |
| `beewatch/services.py` | `Preferenze`, `Promemoria`, profilo, password, cancellazione, preferenze, promemoria, `configurazione_visibile` |
| `beewatch/repositories_riferimento.py` | `PreferenzeRepository`; `UtentiRepository.trova`, `aggiorna_profilo`, `cambia_password` |
| `sql/schema_05_preferenze.sql` | creato |
| `docs/markdown/M6-interfaccia/ui_spec.md` | §7: l'ottava pagina |
| `tests/test_servizi_impostazioni.py`, `tests/test_pagina_impostazioni.py`, `tests/preferenze_finte.py` | creati |
| `tests/accesso_finto.py`, `tests/anagrafica_finta.py`, `tests/app_finta.py`, `tests/test_accesso.py`, `tests/test_servizi_home.py`, `tests/test_ui.py`, `tests/test_app_struttura.py`, `tests/test_app_streamlit.py`, `tests/test_database.py` | adeguati |
| `README.md` | la pagina Impostazioni |

## Definition of Done (ricavata dalla descrizione della issue)

| Voce | Esito |
|---|---|
| quattro linguette con `st.tabs`: Profilo, Notifiche, AI e Modelli, Database | fatto |
| le prime tre scrivono su MySQL | fatto: `utenti` e `preferenze_utente`, provate anche su MySQL vero |
| la quarta in sola lettura, con la configurazione da `.env` | fatto, senza password né chiavi |
| le scelte hanno effetto | fatto: promemoria nella Home e consenso rispettato dal servizio |
