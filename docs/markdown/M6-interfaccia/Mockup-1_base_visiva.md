# Mockup · Blocco 1 · Base visiva, due temi e «Ricordami»

> **Richiesta** «vorrei che il progetto sia copia incolla del mockup» (2026-11-14), con due scelte:
> aspetto e disposizione di ogni schermata come nel mockup ma **solo con le funzioni vere**, e
> **entrambi i temi** con l'interruttore
> **Stato** completato
> **Collegati** → `.streamlit/config.toml` · `app/tema.py` · `app/stile/beewatch.css` · `app/ui.py`
> (sidebar) · `app/avvio.py` (cookie) · `sql/schema_06_sessioni.sql` · `ui_spec.md` §2–§5, §7, §13

## Obiettivo

Il mockup ad alta fedeltà (`BeeWatch-AI_Mockup-UI_corretto.pdf`, 57 tavole) diventa l'aspetto
dell'app. Il lavoro è diviso in blocchi; questo è la base comune a tutte le schermate: colori,
font, sfondo, card, bottoni, sidebar e i due temi. Le singole schermate (accesso, dashboard,
alveari, ispezioni, previsioni, assistente, report, impostazioni, trasparenza) vengono nei blocchi
successivi.

## Cosa c'è

| Elemento del mockup | Come | Dove |
|---|---|---|
| palette dei due temi (Accent `#F5B301`/`#FFC709`, Sfondo, Superficie, Bordo, Testo, Successo, Attenzione, Critico) | tema nativo `[theme.light]` e `[theme.dark]`, e le stesse variabili `--bw-*` per il CSS | `config.toml`, `tema.PALETTE` |
| font Poppins (Regular, Medium, SemiBold, Bold) | `[[theme.fontFaces]]` con i file nel repository, serviti dall'app | `app/static/fonts` (licenza OFL accanto) |
| sfondo a nido d'ape con l'alone dorato in alto a destra | CSS: una tessera SVG ripetuta e un gradiente | `beewatch.css` |
| card con raggio 16 px, bordo leggero e ombra; campi e bottoni con raggio 10 px | tema nativo (`baseRadius`) e CSS su `data-testid` | `config.toml`, `beewatch.css` |
| bottone primario giallo con il testo scuro | CSS (Streamlit metterebbe il testo bianco, illeggibile sul giallo) | `beewatch.css` |
| logo: cinque esagoni e «BeeWatch **AI**» | `st.logo` con due SVG (chiaro e scuro); lettere convertite in tracciati da Poppins | `app/static/logo_*.svg`, `scripts/genera_logo.py` |
| menu con le icone a linea, voce attiva gialla | `st.Page(icon=":material/…")` e CSS | `Home.py`, `beewatch.css` |
| in fondo alla sidebar: avatar con le iniziali, nome, «Apicoltore», menu ⌄ | `st.html` (con `html.escape`) e `st.popover` con Impostazioni ed Esci | `ui._blocco_utente` |
| interruttore «Scuro · Chiaro» | `st.segmented_control`; scrive il tema scelto nel browser e ricarica | `tema.interruttore_tema` (Accedi, Impostazioni → Aspetto) |
| «Ricordami» nella pagina di accesso | sessione nel database e cookie nel browser | `schema_06_sessioni.sql`, `services`, `avvio` |
| niente bottone «Deploy» | `client.toolbarMode = "minimal"` | `config.toml` |

## Decisioni

**1. Due punti per lo stile, e nessuna classe interna di Streamlit.** Il tema nativo fa quasi tutto
(colori dei widget, tabelle, grafici, messaggi, font, raggi); il resto è in un solo file CSS. I
selettori usano solo gli attributi `data-testid` e le classi `st-key-…` che Streamlit crea per un
contenitore con `key`: sono la parte stabile del DOM. Le classi `st-emotion-cache-…` cambiano a ogni
versione e non si usano. Senza il CSS l'app funziona uguale.

**2. I due temi sono nativi, e l'interruttore scrive la scelta nel browser.** Streamlit non ha un
comando Python per cambiare tema: lo sceglie il browser e lo ricorda in `localStorage`, con la
voce `stActiveTheme-<indirizzo>-v2`. L'interruttore scrive quella voce (per ogni indirizzo
dell'app) e ricarica. È un dettaglio di Streamlit: le versioni sono bloccate (`<1.68`) e un test
legge il formato della voce nel codice di Streamlit installato, così un aggiornamento che lo
cambiasse si vedrebbe nei test e non dagli utenti. Il valore va scritto in JSON: la prima versione
scriveva `Light` invece di `"Light"`, e Streamlit, che lo rilegge con `JSON.parse`, mostrava una
pagina bianca. Trovato provando nel browser, ora c'è un test.

**3. «Ricordami» serve anche al tema.** Ricaricare la pagina apre una sessione nuova di Streamlit,
e l'accesso (che vive nella sessione) si perdeva. Ora l'accesso apre una **sessione del browser**:

- un token casuale da 256 bit va nel cookie `bw_sessione` (`SameSite=Strict`, `Secure` in HTTPS);
- nel database (`sessioni`) va solo la sua impronta SHA-256: chi leggesse la tabella non potrebbe
  usarla;
- con «Ricordami» vale 30 giorni; senza, il cookie sparisce chiudendo il browser e la sessione
  dura al massimo un giorno;
- **Esci** cancella la riga e il cookie; cambiare la password chiude le sessioni di tutti gli altri
  browser; cancellando l'account spariscono a cascata (GDPR art. 17);
- la ripresa dal cookie si tenta **una volta per sessione**: Streamlit legge i cookie solo
  all'apertura, e dopo «Esci» quello vecchio risulterebbe ancora lì.

Il cookie si scrive con un piccolo script (Streamlit non ha un comando per scriverli), quindi non è
`HttpOnly`. Il rischio è basso perché nell'app non entra mai HTML scritto dall'utente: il nome
nella sidebar passa da `html.escape` (c'è un test).

**4. Lo stile va nel corpo della pagina, nascosto.** Un `st.html` con il solo `<style>` Streamlit lo
mette fra gli «eventi», e il router li svuota quando passa alla pagina: lo stile spariva. Ora porta
con sé un elemento vuoto, e il CSS stesso nasconde il contenitore.

**5. Nel CSS non può esserci il carattere «<».** Streamlit ripulisce l'HTML e scarta un blocco di
stile che lo contenga: bastava un commento con `st-key-<chiave>`, o il disegno SVG del nido d'ape.
L'SVG ora è codificato come URL, e un test controlla CSS e variabili.

**6. La sidebar segue il mockup.** Logo, menu, selettore dell'apiario (il mockup non lo ha, ma
senza non si sceglie l'apiario) e il blocco dell'utente. Lo stato del sistema non c'è più: resta
nella Home e nelle Impostazioni.

## Come si prova

| Cosa | Dove |
|---|---|
| colori di tema nativo e CSS uguali, i token del mockup, Poppins presente con la licenza, server e barra degli strumenti | `tests/test_app_struttura.py` |
| stile in due soli punti, HTML e JavaScript solo in `tema.py`, `avvio.py` e `ui.py` | `tests/test_app_struttura.py` |
| ogni `var(--bw-…)` del CSS definita in entrambi i temi, niente «<», indirizzi delle pagine, formato della voce del tema nel codice di Streamlit, lo script dell'interruttore, lo stile applicato dal router | `tests/test_tema.py` |
| sidebar: apiario, avatar con le iniziali, nome protetto dall'HTML, Impostazioni ed Esci | `tests/test_ui.py` |
| token e impronta, sessione aperta, ripresa, chiusa, scaduta, account disattivato, password cambiata; nell'app: cookie con e senza «Ricordami», scritto una volta, ingresso dal cookie, cookie scaduto cancellato, Esci senza rientrare, database spento | `tests/test_sessioni.py` |
| su MySQL: sessioni aperte, scadute, chiuse, e cancellate a cascata con l'utente | `tests/test_sessioni.py` (integration) |
| nel browser, con uno stack MySQL isolato: i due temi, l'interruttore nei due versi restando dentro, l'accesso che resta ricaricando la pagina | a mano |

## File coinvolti

| File | Azione |
|---|---|
| `.streamlit/config.toml` | rifatto: due temi, Poppins, file statici, barra minima |
| `app/tema.py`, `app/stile/beewatch.css` | creati |
| `app/static/fonts/*` (Poppins e `OFL.txt`), `app/static/logo_*.svg`, `app/static/icona_*.svg`, `scripts/genera_logo.py` | creati |
| `app/ui.py` | sidebar del mockup, `iniziali` |
| `app/avvio.py` | stile dal router, ripresa dal cookie, cookie da scrivere, `password_cambiata` |
| `app/Home.py` | icone a linea, nomi del mockup, `router=True` |
| `app/schermate/accedi.py` | interruttore e «Ricordami» |
| `app/pages/8_Impostazioni.py` | Aspetto (interruttore), sessione dopo il cambio di password |
| `beewatch/sicurezza.py` | `nuovo_token`, `impronta_token` |
| `beewatch/repositories_accesso.py`, `sql/schema_06_sessioni.sql` | creati |
| `beewatch/services.py` | `apri_sessione`, `riprendi_sessione`, `chiudi_sessione`; il cambio di password chiude le sessioni |
| `docs/markdown/M6-interfaccia/ui_spec.md` | §2, §3, §4, §5, §7, §13 |
| `tests/test_tema.py`, `tests/test_sessioni.py` | creati |
| `tests/test_app_struttura.py`, `tests/test_ui.py`, `tests/test_accesso.py`, `tests/test_interruttore_db.py`, `tests/test_pagina_impostazioni.py`, `tests/accesso_finto.py`, `tests/app_finta.py`, `tests/test_servizi_*.py`, `tests/test_database.py` | adeguati |
