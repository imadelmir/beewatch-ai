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
2. **Niente CSS iniettato.** `unsafe_allow_html=True` è vietato salvo un caso
   documentato al §11. Si usa solo ciò che Streamlit offre nativamente.
3. **Nessun numero senza contesto.** Ogni stima ha la sua incertezza, ogni
   output dell'AI ha il suo banner.
4. **Ogni schermata ha tre stati**: con dati, senza dati, in errore. Tutti e tre
   vanno progettati, non solo il primo.

---

## 3. Palette

Il tema nasce dal dominio (miele, arnie, campo) ma resta sobrio: il colore
serve a **veicolare significato**, non a decorare.

### Colori di base

| Ruolo | Hex | Uso |
|---|---|---|
| Primario | `#C77D02` | ambra scura: bottoni, link, slider, elementi attivi |
| Sfondo | `#FFFFFF` | corpo della pagina |
| Sfondo secondario | `#FAF6F0` | crema: sidebar, card, `st.metric`, tabelle alternate |
| Testo | `#1A1A1A` | quasi-nero, contrasto 16:1 su bianco |
| Testo attenuato | `#6B6B6B` | didascalie, unità di misura, note |
| Bordo | `#E5DED4` | separatori, contorni delle card |

### Colori semantici

Da usare **solo** con questi significati. Non sono decorativi.

| Significato | Hex | Dove compare |
|---|---|---|
| Positivo / in salute | `#2E7D32` | stato alveare OK, delta di produzione in crescita |
| Attenzione | `#ED9C00` | scorte in calo, confidenza AI bassa, dati incompleti |
| Critico | `#C62828` | sospetta varroa, errori, alveare perso |
| Informazione / AI | `#1565C0` | banner "contenuto generato da un'AI", note metodologiche |
| Neutro | `#6B6B6B` | dato non disponibile, stato sconosciuto |

**Regola di accessibilità:** il colore non è mai l'unico veicolo
dell'informazione. Ogni stato colorato porta anche un'etichetta testuale o
un'icona. Circa l'8% degli uomini ha una forma di daltonismo, e il docente
potrebbe essere fra questi.

---

## 4. Tipografia e spaziatura

Si usa il font di sistema di Streamlit (`sans serif`). Nessun font esterno:
sarebbe una richiesta di rete in più che può fallire durante la demo.

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

File `.streamlit/config.toml`, creato in **M6-T1** ed esteso in **M6-T10**:

```toml
[theme]
base = "light"
primaryColor = "#C77D02"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#FAF6F0"
textColor = "#1A1A1A"
font = "sans serif"
# M6-T10 · l'identità del mockup con le sole chiavi native del tema (Streamlit 1.60–1.67)
borderColor = "#E5DED4"
showWidgetBorder = true
baseRadius = "0.75rem"
buttonRadius = "0.5rem"
linkColor = "#C77D02"
headingFontWeights = [700, 700, 600, 600, 600, 600]
metricValueFontSize = "1.875rem"
dataframeHeaderBackgroundColor = "#FAF6F0"
chartCategoricalColors = ["#C77D02", "#1A1A1A", "#6B6B6B", "#ED9C00", "#2E7D32", "#1565C0"]
showSidebarBorder = true

[theme.sidebar]
backgroundColor = "#FFF8E7"
secondaryBackgroundColor = "#FFFFFF"

[server]
# Evita che il file watcher rilanci l'app durante la demo
runOnSave = false

[browser]
gatherUsageStats = false
```

Il file **va committato**: senza, chi clona il repository vede l'app con il tema
di default e la demo non corrisponde agli screenshot della documentazione.

**M6-T10 · l'identità del mockup, in modo nativo.** Il mockup ad alta fedeltà
(`BeeWatch-AI_Mockup-UI_corretto`) ha card arrotondate con bordo leggero, titoli
in grassetto, una sidebar color miele e valori delle metriche ben leggibili. Tutto
questo si ottiene con le chiavi native del tema (`borderColor`, `baseRadius`,
`headingFontWeights`, `metricValueFontSize`, `[theme.sidebar]`…), disponibili da
Streamlit 1.60: **nessun CSS iniettato**, quindi le regole del §2 e del §13
restano valide. Restano fuori, per gli stessi motivi del §13, il tema scuro, il
font Poppins (richiederebbe un file esterno) e lo sfondo a nido d'ape (richiede
CSS). Le versioni di Streamlit e Plotly sono bloccate sull'intervallo provato
(`requirements.txt`), e un test controlla che ogni chiave del tema esista nella
versione installata.

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
duplica il codice in sei file.

Contenuto, dall'alto in basso:

1. **Identità** — `st.logo()` se disponibile, altrimenti `st.title("BeeWatch AI")`
   e una didascalia con la versione.
2. **Apiario attivo** — `st.selectbox`. È il contesto globale: la scelta vive in
   `st.session_state` e tutte le pagine la leggono da lì. Cambiare apiario
   aggiorna ogni pagina.
3. `st.divider()`
4. **Navigazione** — da **M6-T11** la costruisce `app/Home.py` con
   `st.navigation()`, in base all'accesso: prima solo Accedi e Registrati, dopo
   la Home e le pagine di `app/pages/`, nell'ordine del numero nel nome file:

   | File | Voce nel menu |
   |---|---|
   | `1_Alveari.py` | Alveari |
   | `2_Ispezioni.py` | Ispezioni |
   | `3_Previsione.py` | Previsione |
   | `4_Assistente_AI.py` | Assistente AI |
   | `5_Dashboard.py` | Dashboard |
   | `6_Trasparenza.py` | Trasparenza |
   | `7_Report.py` | Report (M6-T12, oltre alle sei originali) |

   In fondo alla sidebar, dopo l'accesso: chi è entrato e il bottone **Esci**.

5. `st.divider()`
6. **Stato del sistema** — tre righe compatte in `st.caption`: versione del
   modello caricato, provider LLM attivo, esito dell'ultima connessione al
   database. Serve a te in sviluppo e al docente in sede d'esame: dimostra che
   il modello è davvero ricaricato e quale provider sta rispondendo.

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
| Animazioni e transizioni CSS | richiedono HTML iniettato, si rompono agli aggiornamenti di Streamlit, non sono testabili |
| Sidebar personalizzata via CSS | Streamlit cambia le classi interne senza preavviso: si rompe silenziosamente |
| Font esterni da Google Fonts | una richiesta di rete che può fallire proprio durante la demo |
| Tema scuro come alternativa | raddoppia le combinazioni di colore da verificare, a fronte di zero requisiti |
| Componenti di terze parti | dipendenze in più da installare e far funzionare su tre PC diversi |
| Logo o illustrazioni generate | tempo sottratto alla documentazione, che invece è valutata |

Il criterio: ogni ora spesa sull'interfaccia deve produrre qualcosa che il
docente **vede** o che riduce il rischio di crash durante la demo. Un'animazione
non fa né l'uno né l'altro.
