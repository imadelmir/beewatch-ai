# M6 - T7 · Pagina Dashboard: la visione d'insieme

> **Milestone** M6 · Interfaccia Streamlit
> **Task** M6-T7 (issue #38)
> **Stato** completata
> **Commit** `feat(m6): add the Dashboard page with KPIs, production charts and model metrics`
> **Collegati** → [`ui_spec.md`](ui_spec.md) §3, §6, §10 · [`M6-T5_pagina_previsione.md`](M6-T5_pagina_previsione.md) · `app/pages/5_Dashboard.py` · `beewatch/services.py`

## Obiettivo

Una visione d'insieme dell'apiario e del modello, con pandas al lavoro sui dati aggregati.

## Cosa c'è

| Parte | Cosa |
|---|---|
| **KPI** (in cima) | quattro `st.metric` dell'apiario attivo: alveari, produzione totale, media per alveare, ultima ispezione |
| **Produzione** | la serie annuale dei raccolti per alveare (linee con simboli) e la distribuzione dei chili fra gli alveari (barre), anche quelli a zero |
| **Il modello** | quattro metriche lette dal file dei metadati (MAE, RMSE, R², MAE in validazione incrociata) con il miglior riferimento; poi le **barre raggruppate previsto/reale** degli ultimi sei anni di uno stato, con la banda sul previsto; il selettore dello stato è l'unico controllo |
| **Note** | da dove vengono raccolti e metriche |

Ogni grafico ha assi con unità, colori della palette del §3 (`COLORI_SERIE`, con simboli o motivi
di riempimento oltre al colore) e sotto la didascalia «Fonte: …».

### Servizi (`beewatch/services.py`)

| Metodo | Cosa fa |
|---|---|
| `dashboard_apiario(utente_id, apiario_id)` | `DatiDashboard`: i KPI e due tabelle **aggregate con pandas** (`groupby` su anno e alveare; totali per alveare con gli alveari attivi a zero) |
| `metriche_modello()` | `MetricheModello`, dal dizionario `metadati` del predittore, che viene da `models/produzione_v1.json`: nessun numero scritto nel codice |
| `confronto_previsto_reale(codice_stato)` | per gli ultimi `ANNI_CONFRONTO` (6) anni dello stato, la stima con le sole feature degli anni precedenti, la banda e la resa vera; non salva nulla |

In `app/ui.py` c'è il nuovo `grafico_barre` (con `figura_barre`), con le stesse regole di
`grafico_serie`: asse x per categorie, barre raggruppate, motivi di riempimento per serie, stato
vuoto senza dati. In `app/avvio.py` ci sono tre letture in cache nuove.

## Decisioni

**1. «Intero apiario», non una divisione inventata.** Nel quaderno, e nel seed, quasi tutti i
raccolti sono di apiario intero: una smielatura comune non dice quanto ha dato ogni arnia. La
pagina li mostra come «Intero apiario», sia nella serie sia nella distribuzione, e lo spiega in una
didascalia. Un raccolto di un alveare poi eliminato compare come «Alveare eliminato». Così il totale
torna, e nessun chilo è attribuito a caso.

**2. La media per alveare è dichiarata per quello che è:** il totale diviso per gli alveari attivi.
Senza alveari è «—», non zero.

**3. «Previsto vs reale» è il modello, non l'apiario.** Il modello stima la resa per colonia di uno
stato USA: il solo confronto onesto è con la resa vera USDA. La didascalia dice anche il limite: il
modello salvato è stato riaddestrato su tutti gli anni, quindi le barre mostrano quanto si adatta ai
dati, non quanto prevede il futuro. Quella prova è l'errore medio sul 2010–2012 letto dal file, che
viene da un modello addestrato fino al 2009.

**4. Le metriche si leggono, non si scrivono.** `metriche_modello` legge `metadati["metriche"]` del
predittore; un test confronta ogni valore con `models/produzione_v1.json`. Il riferimento più forte
si sceglie dal file, come il minimo MAE fra le baseline.

**5. `width="stretch"` al posto di `use_container_width=True`**, come in tutte le pagine (deprecato in
Streamlit 1.60; la deviazione è dichiarata in M6-T2).

**6. Se manca il modello, l'apiario resta.** I KPI e i grafici dei raccolti si vedono; la sezione del
modello mostra l'errore.

## Come si prova

| Cosa | Dove |
|---|---|
| KPI, serie per anno con l'intero apiario separato, distribuzione con gli alveari a zero, apiario vuoto, apiario altrui, id non validi, metriche uguali al JSON vero, confronto (anni, stima con i soli anni prima, banda, resa vera, stato ignoto) | `tests/test_servizi_dashboard.py` (10) |
| con MySQL, il seed e il modello committato: KPI dell'apiario del seed, metriche uguali al JSON, previsto/reale della California senza salvare | `tests/test_services.py` (integration) |
| la pagina: quattro KPI in cima, tre grafici con assi in unità, palette e fonte, intero apiario separato, barre raggruppate con la banda, cambio di stato, metriche dal file, **un solo alveare e una sola ispezione**, apiario senza raccolti, nessun apiario, modello mancante, dati USDA assenti, database spento | `tests/test_pagina_dashboard.py` (12) |
| `figura_barre` e `grafico_barre` | `tests/test_ui.py` |

**Prova a mano nel browser** (stack MySQL isolato, ETL caricato, seed, modello `v1.0.0`): «Apiario
del Noce» mostra 4 alveari, 97,5 kg in tutto, 24,4 kg di media, ultima ispezione 16/05/2026. La serie
ha «Intero apiario» (55,5 kg nel 2025, 29,2 nel 2026) e A1 (12,8 kg nel 2025). Il confronto per la
California, dal 2007 al 2012, mostra barre ambra con la banda e barre scure a righe per il reale. Le
metriche (3,5 kg, 4,5 kg, R² 0,62, 4,1 kg in validazione) sono quelle del JSON. Dalla prova: corretto
il titolo che diceva «Apiario Apiario del Noce». Nel pannello stretto (circa 800 px) la data e
un'etichetta si troncano: è la griglia a quattro colonne, da verificare a 1366×768 in M6-T9.

## Cosa NON c'è

Il peso nel tempo dalle ispezioni (`andamento_peso`): una possibile aggiunta, ma non nella DoD. Il
confronto fra apiari diversi.

## File coinvolti

| File | Azione |
|---|---|
| `app/pages/5_Dashboard.py` | riscritto: la pagina vera |
| `app/ui.py` | `figura_barre`, `grafico_barre` |
| `app/avvio.py` | letture in cache della Dashboard |
| `beewatch/services.py` | `DatiDashboard`, `MetricheModello`, `dashboard_apiario`, `metriche_modello`, `confronto_previsto_reale` |
| `tests/test_servizi_dashboard.py`, `tests/test_pagina_dashboard.py` | creati |
| `tests/anagrafica_finta.py` | `RaccoltiInMemoria`, `raccolti_di_prova` |
| `tests/app_finta.py`, `tests/previsione_finta.py` | metadati completi, `stima` nel predittore finto, raccolti vuoti |
| `tests/test_services.py`, `tests/test_ui.py`, `tests/test_app_streamlit.py` | adeguati |
| `README.md` | conteggio dei test |

## Definition of Done

| Voce | Esito |
|---|---|
| quattro KPI in `st.metric` in cima: n. alveari, produzione totale, media per alveare, ultima ispezione | fatto; `test_quattro_kpi_in_cima` |
| serie storica della produzione per alveare | fatto, per anno; `test_la_serie_e_la_distribuzione_tengono_separato_lintero_apiario` |
| barre raggruppate previsto vs reale | fatto; `test_il_confronto_ha_barre_raggruppate_con_la_banda_sul_previsto` |
| distribuzione della produzione fra alveari | fatto, con gli alveari a zero; `test_la_distribuzione_mostra_anche_gli_alveari_senza_raccolti` |
| metriche del modello LETTE da `models/produzione_v1.json`, mai scritte a mano | fatto; `test_le_metriche_sono_quelle_del_file_dei_metadati`, integration |
| ogni grafico ha assi etichettati con unità e didascalia con la fonte | fatto; `test_tre_grafici_con_assi_in_unita_palette_e_fonte` |
| colori presi dalla palette del §3, mai dal default di Plotly | fatto; stesso test e `test_figura_barre_ha_assi_con_unita_categorie_palette_e_motivi` |
| `use_container_width=True` su tutti i grafici | fatto con `width="stretch"`, l'equivalente non deprecato (decisione 5) |
| la dashboard funziona e resta leggibile con un solo alveare e una sola ispezione | fatto; `test_con_un_solo_alveare_e_una_sola_ispezione_resta_leggibile` |
