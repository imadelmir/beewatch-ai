# BeeWatch AI — Specifica dell'interfaccia

> **Stato:** approvata · **Versione:** 1.0 · **Milestone di riferimento:** M6
> **File coinvolti:** `app/Home.py`, `app/ui.py`, `app/pages/`, `.streamlit/config.toml`

---

## 1. Perché questo documento esiste

M6 sono nove task su sei pagine, distribuite fra tre persone. Senza una
specifica scritta si ottengono sei pagine con sei stili diversi, e `ui.py` non
ha un riferimento contro cui essere implementato.

Questo documento fissa **tutto ciò che non dipende da `services.py`**: colori,
tipografia, anatomia delle pagine, catalogo dei componenti, tipi di grafico,
stati. È la parte della UI che si può decidere oggi e che non invecchia.

I dettagli funzionali (quale funzione chiama ogni pagina, quali campi mostra)
**non** stanno qui: si definiscono a M6, quando `services.py` esiste.

### Deviazione dalla struttura, dichiarata

La struttura approvata elenca sette file in `docs/`. Questo è l'ottavo.
Motivazione: serve la Definition of Done di **M6-T2** (*"ottenere un aspetto
coerente"*), che senza un riferimento scritto non è verificabile. Il costo è un
file; il beneficio è che tre persone producono la stessa interfaccia.

Introduce inoltre `.streamlit/config.toml` alla radice — file richiesto da
Streamlit per il tema, creato in **M6-T1**.

---

## 2. Principi

1. **La UI non pensa.** Le pagine raccolgono input, chiamano `services.py`,
   mostrano il risultato. Nessuna query SQL, nessun `joblib.load`, nessuna
   chiamata all'LLM dentro `app/`.
2. **Lo stile in due punti, e solo lì.** Il tema nativo (`.streamlit/config.toml`)
   e un solo file CSS (`app/stile/beewatch.css`), applicato da `app/tema.py`. Il
   CSS usa solo ciò che Streamlit espone (attributi `data-testid`, classi
   `st-key-…` dei contenitori con chiave). L'HTML nelle pagine resta vietato:
   `st.html` solo in `tema.py`, `avvio.py` (il cookie) e `ui.py` (pastiglie,
   blocco dell'utente), con i dati dell'utente sempre protetti con `html.escape`.
   Senza il CSS l'app funziona uguale. *(Decisione del 2026-11-14: l'aspetto deve
   essere quello del mockup ad alta fedeltà; prima era vietato ogni CSS.)*
3. **Nessun numero senza contesto.** Ogni stima ha la sua incertezza, ogni
   output dell'AI ha il suo banner.
4. **Ogni schermata ha tre stati**: con dati, senza dati, in errore. Tutti e tre
   vanno progettati, non solo il primo.

---

## 3. Palette

I colori sono quelli delle tavole «Design System» del mockup ad alta fedeltà, in
due temi: **chiaro** e **scuro**, scelti con l'interruttore «Scuro | Chiaro»
(pagina Accedi e Impostazioni → Profilo → Aspetto). Stanno in
`.streamlit/config.toml` (tema nativo) e in `app/tema.py` (`PALETTE`, per il CSS);
un test controlla che coincidano.

| Token | Chiaro | Scuro | Uso |
|---|---|---|---|
| Accent | `#F5B301` | `#FFC709` | bottoni primari (con il testo scuro), voce attiva del menu, elementi attivi |
| Accent 2 | `#FFD256` | `#FFDD55` | secondo giallo: grafici, logo |
| Sfondo | `#FDF9EC` | `#0A0A0A` | corpo della pagina, con il nido d'ape |
| Superficie | `#FFFFFF` | `#151412` | card, sidebar, form |
| Bordo | `#F2E9D2` | `#2A2620` | contorni e separatori |
| Testo | `#1E1A12` | `#FFFFFF` | testo principale |
| Testo 2 | `#7C7566` | `#9B968D` | didascalie, etichette, voci del menu |
| Successo | `#2FA96A` | `#4ADE80` | stato attivo, delta in crescita |
| Attenzione | `#E8890B` | `#FFA726` | alveari da controllare, rischio medio |
| Critico | `#E0524A` | `#FF6B6B` | errori, rischio alto, Elimina |

**Regola di accessibilità:** il colore non è mai l'unico veicolo
dell'informazione. Ogni stato colorato porta anche un'etichetta testuale o
un'icona. Sul giallo il testo è sempre scuro (`#1E1A12`): il bianco non si legge.

---

## 4. Tipografia e spaziatura

Font **Poppins** (licenza OFL), nel repository in `app/static/fonts` e servito
dall'app stessa: nessuna richiesta a Google, funziona anche senza rete. Scala del
mockup: titolo pagina Bold 38, titolo card Bold 18, etichette e bottoni Medium 15,
corpo Regular 14, didascalie Regular 12.

| Elemento | Come si ottiene | Quando |
|---|---|---|
| Titolo pagina | `st.title()` | una sola volta per pagina, in cima |
| Sezione | `st.header()` | blocchi principali |
| Sottosezione | `st.subheader()` | dentro una sezione |
| Corpo | `st.write()` / `st.markdown()` | testo normale |
| Didascalia | `st.caption()` | unità di misura, fonte del dato, timestamp |

Spaziatura: `st.divider()` fra sezioni concettualmente diverse, mai due di
seguito. Le colonne (`st.columns`) non superano **quattro** per riga: oltre
diventano illeggibili su portatile.

---

## 5. Tema Streamlit

File `.streamlit/config.toml`, creato in **M6-T1**, esteso in **M6-T10** e rifatto
sul mockup (due temi, Poppins) il 2026-11-14. Un test lo confronta con questo
blocco:

```toml
# Tema e server di Streamlit: i colori sono quelli del design system del mockup ad alta fedeltà
# (tavole «Design System», tema chiaro e scuro), riportati nel §5 di
# docs/markdown/M6-interfaccia/ui_spec.md. Streamlit lo legge dalla cartella da cui si lancia
# `streamlit run`: la radice del progetto (e /app nel contenitore, dove il Dockerfile lo copia).
#
# Qui c'è tutto ciò che il tema nativo sa fare: colori dei due temi, font, raggi. Il resto del
# mockup (sfondo a nido d'ape, card, sidebar) è in un solo file CSS, app/stile/beewatch.css.

[theme]
font = "Poppins"
headingFontWeights = [700, 700, 600, 600, 600, 600]
headingFontSizes = ["2.375rem", "1.375rem", "1.125rem", "1rem", "0.9375rem", "0.875rem"]
baseFontSize = 14
baseRadius = "10px"
buttonRadius = "10px"
showWidgetBorder = true
showSidebarBorder = true
metricValueFontSize = "1.75rem"
# Leggibili su entrambi gli sfondi (in 1.60 non si possono dare per singolo tema)
chartCategoricalColors = ["#F5B301", "#E8890B", "#2FA96A", "#9B968D", "#E0524A", "#7C7566"]

[[theme.fontFaces]]
family = "Poppins"
url = "app/static/fonts/Poppins-Regular.ttf"
weight = 400

[[theme.fontFaces]]
family = "Poppins"
url = "app/static/fonts/Poppins-Medium.ttf"
weight = 500

[[theme.fontFaces]]
family = "Poppins"
url = "app/static/fonts/Poppins-SemiBold.ttf"
weight = 600

[[theme.fontFaces]]
family = "Poppins"
url = "app/static/fonts/Poppins-Bold.ttf"
weight = 700

[theme.light]
primaryColor = "#F5B301"
backgroundColor = "#FDF9EC"
secondaryBackgroundColor = "#FBF5E6"
textColor = "#1E1A12"
borderColor = "#F2E9D2"
linkColor = "#B98200"
dataframeHeaderBackgroundColor = "#FBF5E6"
greenColor = "#2FA96A"
orangeColor = "#E8890B"
redColor = "#E0524A"
yellowColor = "#F5B301"

[theme.light.sidebar]
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#FDF9EC"

[theme.dark]
primaryColor = "#FFC709"
backgroundColor = "#0A0A0A"
secondaryBackgroundColor = "#1C1A16"
textColor = "#FFFFFF"
borderColor = "#2A2620"
linkColor = "#FFC709"
dataframeHeaderBackgroundColor = "#1C1A16"
greenColor = "#4ADE80"
orangeColor = "#FFA726"
redColor = "#FF6B6B"
yellowColor = "#FFC709"

[theme.dark.sidebar]
backgroundColor = "#0F0E0C"
secondaryBackgroundColor = "#1C1A16"

[client]
# Come nel mockup: niente bottone Deploy né menu dello sviluppatore. Il tema si sceglie
# dall'interruttore Scuro/Chiaro dell'app.
toolbarMode = "minimal"

[server]
# Evita che il file watcher rilanci l'app durante la demo
runOnSave = false
# Serve app/static: i file del font Poppins (licenza OFL, nel repository: nessuna richiesta a Google)
enableStaticServing = true

[browser]
gatherUsageStats = false
```

Il file **va committato**: senza, chi clona il repository vede l'app con il tema
di default e la demo non corrisponde agli screenshot della documentazione.

**Il resto del mockup** (sfondo a nido d'ape, card con l'ombra, sidebar con il
blocco dell'utente, pastiglie) è in `app/stile/beewatch.css`, con i colori del
tema attivo passati come variabili `--bw-*` da `app/tema.py`. Il file non deve
contenere il carattere «<»: Streamlit scarta un blocco di stile che lo contenga
(c'è un test).

**Come si cambia tema.** Streamlit non ha un comando Python per farlo: il tema
lo sceglie il browser e lo ricorda (`localStorage`). L'interruttore scrive quella
scelta e ricarica la pagina; la sessione riprende grazie al cookie «Ricordami»
(`sql/schema_06_sessioni.sql`), quindi cambiare tema non fa uscire. La barra
degli strumenti di Streamlit è ridotta (`toolbarMode = "minimal"`, niente Deploy,
come nel mockup). Le versioni di Streamlit sono bloccate (`<1.68`) e un test
controlla che il formato della chiave usata dal browser ci sia ancora.

---

## 6. Anatomia di una pagina

Ogni pagina, senza eccezioni, ha questa struttura verticale:

```
┌──────────────┬──────────────────────────────────────────────┐
│              │  1. INTESTAZIONE                             │
│   SIDEBAR    │     titolo + una riga che spiega la pagina   │
│              ├──────────────────────────────────────────────┤
│  (uguale su  │  2. BANNER  (solo se la pagina usa l'AI)     │
│   tutte le   ├──────────────────────────────────────────────┤
│   pagine)    │  3. CONTROLLI                                │
│              │     form, filtri, selettori                  │
│              ├──────────────────────────────────────────────┤
│              │  4. CONTENUTO                                │
│              │     metriche, grafici, tabelle               │
│              ├──────────────────────────────────────────────┤
│              │  5. NOTE                                     │
│              │     st.caption: fonte, limiti, disclaimer    │
└──────────────┴──────────────────────────────────────────────┘
```

L'ordine non si negozia. Un utente che passa da una pagina all'altra deve
trovare le stesse cose negli stessi posti.

---

## 7. Sidebar

Definita **una sola volta** in `app/ui.py`, richiamata da ogni pagina. Non si
duplica il codice in sei file. Larga 258 px, come nel mockup.

Contenuto, dall'alto in basso:

1. **Logo** — `st.logo()` con il marchio del mockup (cinque esagoni e
   «BeeWatch **AI**»), in due varianti per il tema chiaro e scuro
   (`app/static/logo_*.svg`, generate da `scripts/genera_logo.py`).
2. **Navigazione** — la costruisce `app/Home.py` con `st.navigation()`, in base
   all'accesso: prima solo Accedi e Registrati, dopo la Home e le pagine di
   `app/pages/`, con le icone a linea del mockup (Material Symbols):

   | File | Voce nel menu |
   |---|---|
   | `schermate/home.py` | Dashboard (la prima pagina, come nel mockup) |
   | `1_Alveari.py` | Alveari |
   | `2_Ispezioni.py` | Ispezioni |
   | `3_Previsione.py` | Previsioni |
   | `4_Assistente_AI.py` | AI Assistant |
   | `5_Dashboard.py` | Statistiche (finché il contenuto non passa in Previsioni, come nel mockup) |
   | `6_Trasparenza.py` | Trasparenza |
   | `7_Report.py` | Report (M6-T12, oltre alle sei originali) |
   | `8_Impostazioni.py` | Impostazioni (M6-T13, oltre alle sei originali) |

   La voce della pagina aperta è evidenziata in giallo.
3. **Apiario attivo** — `st.selectbox`. È il contesto globale: la scelta vive in
   `st.session_state` e tutte le pagine la leggono da lì. Cambiare apiario
   aggiorna ogni pagina. (Il mockup non lo ha, ma senza non si sceglie l'apiario.)
4. **Chi ha fatto l'accesso** — in fondo: avatar con le iniziali, nome e
   «Apicoltore», e un menu (⌄) con **Impostazioni** ed **Esci**.

Lo **stato del sistema** (modello, assistente, database) non è più qui: è nella
Home e nelle Impostazioni (schede AI e Modelli, Database).

**Cosa NON mettere in sidebar:** filtri specifici di una singola pagina. Quelli
stanno nel corpo, altrimenti l'utente non capisce cosa stia filtrando.

---

## 8. Catalogo dei componenti — `app/ui.py`

Un solo file, non una cartella `components/`: sono nove funzioni brevi.

| Funzione | Cosa fa |
|---|---|
| `intestazione(titolo, descrizione)` | titolo + riga di contesto. Prima chiamata di ogni pagina |
| `sidebar()` | disegna la sidebar del §7 e restituisce l'apiario attivo |
| `banner_ai()` | avviso permanente di contenuto generato da AI (§9) |
| `metrica(etichetta, valore, unita, delta=None, aiuto=None)` | `st.metric` con unità e tooltip uniformi |
| `badge_stato(stato)` | pastiglia colorata + testo per `StatoAlveare` |
| `blocco_vuoto(messaggio, azione=None)` | stato "nessun dato", con invito all'azione |
| `mostra_errore(eccezione)` | traduce una `BeeWatchError` in messaggio comprensibile |
| `grafico_serie(df, x, y, titolo)` | grafico temporale con stile uniforme |
| `stima_con_incertezza(valore, minimo, massimo, unita)` | previsione + banda + disclaimer |

**Regola:** se un elemento visivo compare in più di una pagina, diventa una
funzione qui. La Definition of Done di M6-T2 chiede almeno quattro helper usati
in più pagine: questo catalogo ne prevede nove, e `intestazione`, `sidebar`,
`metrica` e `mostra_errore` sono usati da tutte e sei.

---

## 9. Banner AI — regole non negoziabili

La slide 10 del PDF richiede che **l'utente sappia quando sta interagendo con
un'intelligenza artificiale**. Il soggetto è l'utente, non il lettore della
documentazione: il banner sta nell'app, non solo in `docs/etica.md`.

- Compare in cima a **ogni pagina che mostra output di un LLM**: `4_Assistente_AI.py`
  e ovunque si visualizzi un `ai_report`.
- Implementato con `st.info` (blu informativo `#1565C0`).
- Testo: *"Il riepilogo qui sotto è generato da un'intelligenza artificiale.
  Può contenere errori: verifica sempre con la tua osservazione diretta. Non
  sostituisce il parere di un veterinario o di un tecnico apistico."*
- **Non nascondibile, non richiudibile.** Niente `st.expander`.
- Ogni riepilogo mostra anche il **livello di confidenza** dichiarato dal modello
  e la lista dei campi che l'AI **non** ha potuto dedurre dalle note.

---

## 10. Grafici

Libreria unica: **Plotly** (già in `requirements.txt`). Niente matplotlib nelle
pagine: produce immagini statiche, non interattive, e stona con Streamlit.

| Pagina | Grafico | Perché questo |
|---|---|---|
| `3_Previsione` | barra orizzontale con banda di errore | mostra l'incertezza visivamente, non come nota a piè di pagina |
| `5_Dashboard` | serie storica per alveare | l'andamento nel tempo è la domanda principale dell'apicoltore |
| `5_Dashboard` | barre raggruppate: previsto vs reale | è la prova visiva della qualità del modello |
| `5_Dashboard` | distribuzione della produzione | mostra la variabilità fra alveari |
| `5_Dashboard` | KPI in `st.metric` | quattro numeri in cima, prima dei grafici |

Le metriche del modello mostrate in Dashboard vengono **lette** da
`models/produzione_v1.json`, mai scritte a mano nel codice: se il modello viene
riaddestrato, la pagina si aggiorna da sola.

Regole comuni:

- ogni asse ha **etichetta e unità di misura** (`kg`, `anno`, `n. telaini`);
- i colori vengono dalla palette del §3, mai dal default di Plotly;
- ogni grafico ha sotto un `st.caption` con la fonte del dato;
- `use_container_width=True` sempre, così il layout regge su schermo piccolo.

---

## 11. Stati: caricamento, vuoto, errore

Progettarli è ciò che separa un prototipo da un'applicazione. Valgono per tutte
le pagine.

**Caricamento** — qualsiasi operazione oltre il secondo mostra un indicatore:

```python
with st.spinner("Genero il riepilogo..."):
    ...
```

Per la chiamata all'LLM il messaggio dichiara l'attesa: *"Sto interrogando il
modello, può richiedere fino a 30 secondi."*

**Vuoto** — database appena inizializzato o filtri troppo stretti. Mai una
tabella vuota senza spiegazione: si usa `blocco_vuoto()` con un messaggio e
l'azione suggerita (*"Nessun alveare registrato. Vai su Alveari per aggiungerne
uno."*). La DoD di M6-T9 richiede che l'app sia usabile con database vuoto.

**Errore** — nessun traceback raggiunge l'utente. Ogni pagina cattura
`BeeWatchError` e la passa a `mostra_errore()`, che produce un `st.error` con:
cosa è andato storto in italiano comprensibile, e cosa può fare l'utente. Il
dettaglio tecnico va nei log, non a schermo.

**Unica eccezione al divieto di HTML:** `badge_stato()` può usare
`unsafe_allow_html=True` per la pastiglia colorata, perché Streamlit non ha un
componente badge nativo. È confinata a una funzione di cinque righe in `ui.py`,
documentata, e se un aggiornamento la rompe si sistema in un punto solo.

---

## 12. Checklist di verifica finale

Da usare a **M6-T9**, prima di considerare chiusa la milestone.

- [ ] Le sei pagine hanno l'ordine di sezioni del §6
- [ ] La sidebar è identica ovunque e generata da `ui.sidebar()`
- [ ] Nessuna query SQL, `joblib.load` o chiamata LLM dentro `app/`
- [ ] `unsafe_allow_html` compare solo dentro `badge_stato()`
- [ ] Ogni grafico ha assi etichettati con unità e una didascalia con la fonte
- [ ] Ogni stato colorato ha anche un'etichetta testuale
- [ ] Le tre condizioni (dati, vuoto, errore) sono state provate su ogni pagina
- [ ] Il banner AI è presente e non nascondibile
- [ ] Nessuna previsione è mostrata senza banda di incertezza
- [ ] L'app è leggibile a 1366×768 (risoluzione tipica del proiettore d'aula)
- [ ] Nessuna pagina supera i 3 secondi con i dati demo

---

## 13. Cosa non faremo, e perché

| Tentazione | Perché no |
|---|---|
| Animazioni e transizioni CSS | non servono a nessuna informazione e rallentano su un portatile |
| Selettori delle classi interne di Streamlit (`st-emotion-cache-…`) | cambiano a ogni versione: il CSS usa solo `data-testid` e le classi `st-key-…` |
| Font da Google Fonts | Poppins è nel repository: nessuna richiesta di rete, nessun indirizzo IP a Google |
| Componenti di terze parti | dipendenze in più da installare e far funzionare su tre PC diversi |
| Funzioni del mockup senza un servizio dietro (accesso con Google, 2FA, backup del database, lingua e unità di misura) | un bottone che non fa nulla inganna l'utente: si mostrano solo le funzioni vere |

*Superato il 2026-11-14:* tema scuro, font Poppins, sfondo a nido d'ape e sidebar
personalizzata erano esclusi; l'utente ha chiesto l'aspetto del mockup, e ora ci
sono, nei due punti del §2.

Il criterio: ogni ora spesa sull'interfaccia deve produrre qualcosa che il
docente **vede** o che riduce il rischio di crash durante la demo. Un'animazione
non fa né l'uno né l'altro.
