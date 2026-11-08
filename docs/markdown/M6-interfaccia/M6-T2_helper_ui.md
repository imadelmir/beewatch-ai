# M6 - T2 · `app/ui.py`: gli helper condivisi

> **Milestone** M6 · Interfaccia Streamlit
> **Task** M6-T2 (issue #33)
> **Stato** completata
> **Commit** `feat(m6): add the shared UI helpers and use them on every page`
> **Collegati** → [`ui_spec.md`](ui_spec.md) §6–§11 · [`M6-T1_scheletro_app.md`](M6-T1_scheletro_app.md) · `app/ui.py` · `app/avvio.py`

## Obiettivo

Evitare il copia-incolla tra le pagine e ottenere un aspetto coerente prima di scrivere il contenuto vero
(M6-T3…T8). Ogni elemento visivo che compare in più di una pagina diventa una funzione di `app/ui.py`, e
le pagine la chiamano: si rifinisce in un punto solo.

## Le nove funzioni (specifica §8)

| Funzione | Cosa fa | Dove si usa oggi |
|---|---|---|
| `intestazione(titolo, descrizione)` | l'unico `st.title` della pagina e una riga di contesto | Home e sei pagine |
| `sidebar()` | la sidebar del §7; restituisce l'apiario attivo (o `None`) | Home e sei pagine |
| `banner_ai()` | `st.info` blu con il testo del §9, parola per parola; niente expander | Assistente AI |
| `metrica(etichetta, valore, unita, delta=None, aiuto=None)` | `st.metric` con numeri all'italiana (`1 234,5 kg`), unità, delta con segno, «—» se manca | Home e sei pagine |
| `badge_stato(stato)` | pastiglia colorata con icona e testo per ogni `StatoAlveare` | (M6-T3) |
| `blocco_vuoto(messaggio, azione=None)` | lo stato «nessun dato», con l'azione suggerita | Home e pagine con dati |
| `mostra_errore(eccezione)` | `st.error` con cosa è successo e cosa fare; dettaglio tecnico nel log | Home e sei pagine |
| `grafico_serie(df, x, y, titolo, *, etichetta_x, etichetta_y, fonte, gruppo=None)` | linea Plotly con assi, palette, simboli per serie e didascalia della fonte | (M6-T7) |
| `stima_con_incertezza(valore, minimo, massimo, unita, *, etichetta, livello)` | stima, banda, barra con banda d'errore e avvertenza | (M6-T5) |

Le quattro richieste dalla DoD in tutte le pagine (`intestazione`, `sidebar`, `metrica`, `mostra_errore`)
sono chiamate anche dalla Home. Gli scheletri delle sei pagine ora mostrano un numero di contesto vero
(alveari attivi, ispezioni recenti, errore medio del modello…) con i loro tre stati: con dati, vuoto, errore.

### Regole incorporate nelle funzioni

- **Palette (§3)** in costanti con nome (`PRIMARIO`, `POSITIVO`, `ATTENZIONE`…): un test le confronta con la
  tabella della specifica e un altro vieta colori esadecimali fuori palette in `app/`.
- **Il colore non basta mai (§3).** Ogni stato del badge ha icona e testo; ogni serie del grafico ha un
  simbolo suo oltre al colore. Il testo dei badge supera il contrasto WCAG AA (4,5:1): quasi-nero
  sull'arancio dell'attenzione, bianco sugli altri (verificato da un test).
- **Assi, unità e fonte obbligatori (§10)**: in `grafico_serie` sono parametri senza valore predefinito.
- **Nessuna stima senza banda (§2, §10)**: `stima_con_incertezza` solleva `ValueError` se manca un estremo,
  se la banda è rovesciata o se la stima ne è fuori, *prima* di disegnare. Con `valore=None` mostra la sola
  banda: è il caso `RisultatoPrevisione.mostra_stima` falso, in cui il valore centrale non va mostrato.
- **Errori (§11)**: ogni sottoclasse di `BeeWatchError` ha un titolo e un rimedio (un test verifica che non
  ne manchi nessuna). Il messaggio di una `BeeWatchError`, scritto per l'utente, si mostra; quello di
  un'eccezione imprevista no (potrebbe contenere SQL o percorsi): va nel log con lo stack. Il rimedio è il
  passo successivo («quando il database risponde di nuovo, ricarica la pagina») e non ripete il comando,
  che sta già nel messaggio dell'eccezione: la prova nel browser mostrava lo stesso `docker compose` due volte.
- **HTML (§11)**: `unsafe_allow_html` compare solo dentro `badge_stato`, con testo fisso e `html.escape`.

## Apiario attivo

Vive in `st.session_state["apiario_attivo_id"]` (nato in `avvio.inizializza_stato`, M6-T1). Il selettore
della sidebar ha una chiave sua (`selettore_apiario`): Streamlit dimentica lo stato dei widget quando si
cambia pagina, quindi la scelta vera sta nella chiave non legata a widget e `avvio` la ricopia nel
selettore a ogni esecuzione (`prepara_selettore_apiario`) e la riprende quando l'utente cambia
(`al_cambio_apiario`, callback). Le scritture in `session_state` restano tutte in `avvio.py`.

Un test sceglie «Valle» sulla Home, passa per tutte e sei le pagine e torna alla Home: la scelta resta.

## Decisioni e deviazioni dichiarate

**1. Ordine della sidebar.** La specifica (§7) mette la navigazione fra l'apiario attivo e lo stato del
sistema. Con la cartella `pages/` Streamlit disegna il menu **sempre in cima** alla sidebar; spostarlo
richiederebbe di riscrivere l'ingresso dell'app con `st.navigation` (rifacendo M6-T1). Resta quindi:
menu, identità, apiario attivo, divisore, stato del sistema. Un solo `st.divider`, perché il menu ha già
il suo separatore.

**2. Identità con `st.header`, non `st.title`.** Il §7 suggerisce `st.title("BeeWatch AI")`, ma il §4 vuole
un solo `st.title` per pagina (e lo mette `intestazione`). Due titoli di livello 1 confondono anche i
lettori di schermo. `st.logo` non si usa: non c'è un logo (§13).

**3. `width="stretch"` al posto di `use_container_width=True`.** Stesso effetto; in Streamlit 1.60 il
secondo è deprecato.

**4. `beewatch.models` ammesso in `app/`.** Serve solo per l'enum `StatoAlveare` in `badge_stato`; il modulo
non importa database né modello (il test degli import di M6-T1 lo elenca tra i consentiti, con il motivo).

**5. Funzioni pubbliche in più.** Oltre alle nove: `formatta_numero`, `stile_stato`, `spiega_errore`,
`controlla_banda`, `figura_serie`, `figura_stima`. Sono la parte pura delle nove, provata senza Streamlit;
le pagine usano le nove.

**6. Stato del sistema in sidebar.** Versione del modello (lo carica una volta per processo, come la Home),
provider LLM (senza segreti, `Servizi.descrizione_llm`), esito della lettura degli apiari come esito della
connessione al database. Se qualcosa non risponde la sidebar lo dice e non solleva: l'errore lo mostra il
corpo della pagina.

## Come si prova

| Cosa | Dove |
|---|---|
| catalogo e firme del §8 (letti dalla specifica), le quattro funzioni in ogni schermata, `mostra_errore` in ogni `except BeeWatchError`, niente `st.title`/`st.error`/`st.sidebar` a mano nelle pagine, banner solo sull'Assistente, form non duplicati, palette = §3, testo del banner = §9, una spiegazione per ogni eccezione | `tests/test_ui.py` (sul codice) |
| numeri all'italiana, stili e contrasto dei badge, scelta della spiegazione, banda rifiutata, figure Plotly | `tests/test_ui.py` (funzioni pure) |
| ogni helper disegnato con `AppTest`; sidebar uguale su tutte le schermate; apiario scelto che sopravvive al cambio di pagina; database spento, modello mancante e database vuoto su ogni pagina | `tests/test_ui.py` (AppTest) |
| unica eccezione HTML dentro `badge_stato` | `tests/test_app_struttura.py` |
| Home e pagine con MySQL vero | `tests/test_app_database.py` (integrazione) |

**Prova a mano nel browser** (stack MySQL isolato e usa-e-getta di `tests/docker_support`, `streamlit run
app/Home.py` vero, finestra 1366×768 del §12): sidebar con identità, selettore e stato del sistema
(«v1.0.0 (RandomForestRegressor)», «llama3.1:8b via ollama», «Database: connesso»); con un secondo apiario
aggiunto al database isolato, la scelta fatta sulla Home resta selezionata aprendo Assistente AI dal menu;
banner AI blu sotto l'intestazione; metriche leggibili a 1366×768 (a 800 px i valori a quattro colonne si
troncano). Fermato il MySQL dello stack: sidebar «Database: non raggiungibile» e nel corpo l'errore in
italiano, senza traceback. Le risorse Docker reali non sono state toccate (fotografia prima/dopo).

Copertura di `app/` al 100% (righe e rami) con `test_ui.py` e `test_app_streamlit.py`. Mutazioni provate a
mano: senza la ricopiatura nel selettore, o senza il callback, il test del cambio di pagina fallisce; con
tutti gli stati resi «sconosciuti» fallisce il test dei significati.

I finti condivisi dai test dell'interfaccia sono passati da `test_app_streamlit.py` a `tests/app_finta.py`
e la fixture `app_pronta` in `conftest.py` (ricarica insieme `avvio` e `ui`).

## Cosa NON c'è

Il contenuto delle pagine (M6-T3…T8), che userà `badge_stato`, `grafico_serie` e `stima_con_incertezza`;
la verifica della checklist finale del §12 (M6-T9).

**Punto aperto per M6-T9:** con il database spento la pagina impiega circa 30 secondi a mostrare l'errore,
perché la sidebar e il corpo tentano la connessione ciascuno per conto suo, con i riprovi di
`beewatch.database` (5 secondi per tentativo). Non si è toccato il livello dati in questa task.

## File coinvolti

| File | Azione |
|---|---|
| `app/ui.py` | creato |
| `app/avvio.py` | `apiari()` in cache, chiave e callback del selettore; `avvia` usa `mostra_errore` |
| `app/Home.py`, `app/pages/*.py` | usano gli helper; numeri di contesto (griglia a quattro colonne) e stati vuoto/errore |
| `README.md` | conteggio dei test |
| `tests/test_ui.py`, `tests/app_finta.py` | creati |
| `tests/conftest.py`, `tests/test_app_streamlit.py`, `tests/test_app_struttura.py` | fixture condivisa, nuovo testo degli errori, regola HTML aggiornata |

## Definition of Done

| Voce | Esito |
|---|---|
| le nove funzioni del catalogo (§8) sono implementate | fatto; `test_ogni_funzione_del_catalogo_esiste_con_la_firma_della_specifica` |
| `intestazione()`, `sidebar()`, `metrica()` e `mostra_errore()` usati da tutte e sei le pagine | fatto (anche dalla Home); `test_le_quattro_funzioni_comuni_sono_usate_da_ogni_schermata` |
| `sidebar()` disegna il §7: identità, apiario attivo, navigazione, stato del sistema | fatto, con l'ordine della deviazione 1; `test_la_sidebar_ha_identita_apiario_attivo_e_stato_del_sistema` |
| l'apiario attivo vive in `st.session_state` e cambiarlo aggiorna ogni pagina | fatto; `test_cambiare_apiario_aggiorna_lo_stato_e_ogni_pagina` |
| `badge_stato()` copre tutti i valori dell'enum `StatoAlveare` | fatto; `test_ogni_stato_dellalveare_ha_etichetta_icona_e_colore`, `test_badge_stato_disegna_…` |
| `mostra_errore()` traduce una `BeeWatchError` in messaggio italiano comprensibile | fatto; `test_mostra_errore_traduce_…`, `test_ogni_eccezione_del_progetto_ha_una_spiegazione` |
| `blocco_vuoto()` mostra messaggio più azione suggerita | fatto; `test_blocco_vuoto_mostra_messaggio_e_azione` |
| `stima_con_incertezza()` non permette di mostrare un valore senza banda | fatto; `test_una_stima_senza_banda_valida_non_si_puo_mostrare`, `test_stima_senza_banda_si_ferma_prima_di_disegnare` |
| nessuna duplicazione di form tra le pagine | fatto (oggi nessun form); `test_nessun_form_e_duplicato_tra_le_pagine` per i prossimi |
| `unsafe_allow_html` compare solo dentro `badge_stato()` | fatto; `test_nessun_css_ne_html_iniettato_fuori_da_badge_stato` |
