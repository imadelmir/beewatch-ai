# M6 - T11 · Autenticazione e sessione

> **Milestone** M6 · Interfaccia Streamlit
> **Task** M6-T11 (issue #57, P3)
> **Stato** completata
> **Commit** `feat(m6): add login, registration and onboarding with a navigation built on access`
> **Collegati** → `app/Home.py` (router) · `app/schermate/` · `beewatch/sicurezza.py` · `beewatch/services.py` · `app/avvio.py` · DA-02

## Obiettivo

Dalla issue: «login, registrazione e onboarding guidato, con la navigazione costruita in base allo
stato di accesso tramite `st.navigation()` e `st.Page`. Password salvate solo come hash. La sessione
vive in `st.session_state`». La issue non ha caselle compilate: la Definition of Done usata è in fondo.

## Cosa c'è

**Il router.** `app/Home.py`, il punto d'ingresso di sempre (`streamlit run app/Home.py`, Dockerfile
invariato), ora costruisce il menu con `st.navigation()`:

| Stato | Menu |
|---|---|
| nessun accesso | Accedi, Registrati |
| appena registrato | Primi passi |
| accesso fatto | Home, Alveari, Ispezioni, Previsione, Assistente AI, Dashboard, Trasparenza |

Il contenuto della Home si è spostato in `app/schermate/home.py` (con `git mv`); le sei pagine restano
in `app/pages/`, con gli stessi indirizzi (`/Alveari`, `/Ispezioni`…).

**Le schermate nuove** (`app/schermate/`), con la struttura del mockup:

- **Accedi**: a sinistra cosa fa l'app, a destra email e password; il collegamento a Registrati e il
  bottone **«Entra con l'utente dimostrativo»** (DA-02: l'utente del seed resta, ma ora è una scelta
  esplicita).
- **Registrati**: nome e cognome, email, password due volte e il consenso esplicito («Ho letto come
  vengono trattati i miei dati»), con a fianco il riassunto di come sono trattati.
- **Primi passi**: tre passi come nel mockup (primo apiario, primo alveare, «tutto pronto»), con la
  barra di avanzamento; si possono saltare in qualsiasi momento.

**La sidebar** dice chi ha fatto l'accesso e ha il bottone **Esci**.

## Sicurezza

- **Solo l'hash bcrypt** (`beewatch/sicurezza.py`): la colonna `utenti.hash_password` è già `CHAR(60)`
  e il seed usa già bcrypt, quindi nessuna migrazione. 12 giri, come il seed.
- **Password**: almeno 8 caratteri, al massimo 72 byte (bcrypt non guarda oltre, e la versione 5 le
  rifiuta), niente spazi all'inizio o alla fine.
- **Nessuna enumerazione degli account**: email sconosciuta, malformata, password sbagliata e account
  disattivato danno lo stesso messaggio; con un'email sconosciuta la password si verifica comunque,
  contro un hash fittizio, così anche il tempo di risposta è lo stesso. I log non contengono né email
  né password.
- **Email in minuscolo**: «Mario@x.it» e «mario@x.it» sono lo stesso account.
- **Due lucchetti per le pagine.** Il router non mette le pagine nel menu prima dell'accesso. Un test
  ha però mostrato che in AppTest la cartella `pages/`, registrata da Streamlit in automatico, si
  raggiungeva lo stesso, e che lo stato partiva con l'utente dimostrativo: la pagina Alveari mostrava i
  suoi dati senza accesso. Ora prima dell'accesso **non c'è nessun utente** (`utente_id` è `None`), e
  `avvia()` ferma ogni pagina non pubblica senza accesso («Per vedere questa pagina accedi»). Pubblici
  sono solo il router, Accedi e Registrati.

## Decisioni

**1. DA-02 si chiude con il login, senza perdere la demo.** Il bottone dell'utente dimostrativo lo
rende raggiungibile in un clic (il suo hash e la sua password, `beewatch-demo`, sono nel seed e nella
sua documentazione); `accesso_dimostrativo()` non chiede la password perché quell'utente è pubblico
per definizione.

**2. bcrypt come dipendenza nuova**, bloccata (`bcrypt>=4.2,<6`): la colonna e il seed lo richiedevano
già. Provato prima su questo PC, dove il controllo applicazioni di Windows a volte blocca le estensioni
compilate: la 5.0 si importa e verifica l'hash del seed.

**3. Lo stato dell'accesso nasce in `avvio.py`**, come tutto lo stato: `accesso` (il nome di chi è
entrato), `onboarding` (il passo), e le funzioni `entra`, `avanza_onboarding`, `termina_onboarding`,
`esci`. «Esci» è un callback: azzera utente, apiario attivo, onboarding ed esito.

**4. I test partono con l'accesso fatto.** `app_finta.con_accesso` imposta l'accesso dell'utente
dimostrativo; `esegui` e i test delle singole pagine lo usano. I test dell'accesso
(`test_accesso.py`) partono invece da zero, come nel browser.

## Cosa NON c'è

«Ricordami», «Password dimenticata?» e «Continua con Google» del mockup: richiederebbero email in
uscita o un fornitore esterno. La cancellazione dell'account dall'interfaccia è in M6-T13
(Impostazioni). Nessun limite ai tentativi di accesso: è un'app locale, su un solo computer.

## Come si prova

| Cosa | Dove |
|---|---|
| hash bcrypt (60 caratteri, sale nuovo, verifica), hash rovinati, l'hash del seed, regole delle password, oltre 72 byte | `tests/test_servizi_accesso.py` |
| registrazione (solo hash, email in minuscolo, campi non validi, password diverse, email già usata anche con maiuscole), accesso (giusto; sbagliato con un solo messaggio per quattro casi; hash fittizio con email ignota; account disattivato), utente dimostrativo, nessun dato nei log | `tests/test_servizi_accesso.py` |
| su MySQL: registrazione e accesso, l'utente del seed con la sua password | `tests/test_servizi_accesso.py` (integration) |
| il router con AppTest: senza accesso solo Accedi; pagine irraggiungibili e senza dati; il lucchetto su ogni pagina; accesso giusto e sbagliato; utente dimostrativo; Esci; database spento; consenso obbligatorio; errori della registrazione; primi passi completi e saltati; campi obbligatori | `tests/test_accesso.py` |

**Nel browser** (stack MySQL isolato, seed, `streamlit run app/Home.py`): senza accesso il menu ha
solo Accedi e Registrati, e l'indirizzo `/Alveari` dà «Page not found» e riporta ad Accedi. Con
`demo@beewatch.local` e `beewatch-demo` si entra (bcrypt vero contro l'hash del seed): Home, sei pagine
nel menu, «Accesso: Apicoltore Dimostrativo» ed «Esci» nella sidebar. «Esci» riporta ad Accedi con il
menu di due voci. Risorse Docker reali non toccate.

Con Streamlit 1.67 `AppTest.switch_page` rifiuta da sé le pagine non registrate dal router (con 1.60
le apriva, e lì interviene il lucchetto di `avvia`): il test accetta i due comportamenti.

## File coinvolti

| File | Azione |
|---|---|
| `app/Home.py` | riscritto: il router |
| `app/schermate/home.py` | il contenuto della Home (spostato) |
| `app/schermate/accedi.py`, `registrati.py`, `onboarding.py` | creati |
| `app/avvio.py` | stato dell'accesso, `entra`/`esci`/onboarding, `avvia(pubblica=)`; nessun utente prima dell'accesso |
| `app/ui.py` | sidebar: chi c'è ed Esci |
| `app/pages/6_Trasparenza.py`, `docs/etica.md` | la frase sulle password (identica nei due) |
| `beewatch/sicurezza.py` | creato |
| `beewatch/services.py` | `UtenteAutenticato`, `registra_utente`, `accedi`, `accesso_dimostrativo` |
| `beewatch/repositories_riferimento.py` | `UtentiRepository.crea`, `trova_per_email` |
| `requirements.txt`, `pyproject.toml` | `bcrypt>=4.2,<6` |
| `tests/test_servizi_accesso.py`, `tests/test_accesso.py`, `tests/accesso_finto.py` | creati |
| `tests/app_finta.py`, `tests/test_ui.py`, `tests/test_app_struttura.py`, `tests/test_app_streamlit.py`, `tests/test_app_database.py`, `tests/test_pagina_*.py` | adeguati all'accesso |
| `README.md` | come si entra |

## Definition of Done (ricavata dalla descrizione della issue)

| Voce | Esito |
|---|---|
| login | fatto; `test_con_la_password_giusta_si_entra_nella_home` |
| registrazione | fatto; `test_registrarsi_porta_ai_primi_passi_e_poi_alla_home` |
| onboarding guidato | fatto, tre passi saltabili |
| navigazione costruita in base all'accesso con `st.navigation()` e `st.Page` | fatto: `app/Home.py`; `test_senza_accesso_si_vede_solo_accedi`, `test_dopo_laccesso_le_pagine_si_raggiungono` |
| password salvate solo come hash | fatto: bcrypt; `test_registrare_salva_solo_lhash_e_lemail_in_minuscolo`, integration |
| la sessione vive in `st.session_state` | fatto, e nasce in `avvio.py` come il resto dello stato |
