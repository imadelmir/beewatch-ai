# M6 - T1 · Scheletro dell'app, navigazione e caching

> **Milestone** M6 · Interfaccia Streamlit
> **Task** M6-T1
> **Stato** completata
> **Commit** `feat(m6): add the Streamlit skeleton with navigation, theme and caching`
> **Collegati** → [`ui_spec.md`](ui_spec.md) · `app/Home.py` · `app/avvio.py` · `app/pages/` · `.streamlit/config.toml`

## Obiettivo

Le fondamenta prima delle pagine: il caching sbagliato in Streamlit si paga con un'app lenta o con dati
stantii proprio durante la demo. Qui si decidono il tema, il menu, dove vivono le risorse pesanti, quanto
dura una lettura in cache e dove nasce lo stato della sessione. Non si implementa nessuna pagina vera
(sono le task M6-T3…T8) e nemmeno gli helper visivi di `app/ui.py` (M6-T2).

## Cosa c'è

```
.streamlit/config.toml     il tema del §5 della specifica (committato, copiato nell'immagine Docker)
app/Home.py                la panoramica: quattro numeri, apiario attivo, stato del modello
app/avvio.py               avvio comune: cache delle risorse e delle letture, stato della sessione
app/pages/1_Alveari.py     ┐
app/pages/2_Ispezioni.py   │ le sei pagine, scheletri: titolo e «in costruzione»
app/pages/3_Previsione.py  │ (il prefisso numerico decide l'ordine nel menu)
app/pages/4_Assistente_AI.py │
app/pages/5_Dashboard.py   │
app/pages/6_Trasparenza.py ┘
```

`app/main.py` (la pagina di diagnostica di M1) è diventato `app/Home.py`; il `CMD` del Dockerfile e i
commenti di `docker-compose.yml` puntano al nuovo file.

### `app/avvio.py`: il punto in cui tutto nasce

| Cosa | Come | Perché |
|---|---|---|
| `servizi()` | `@st.cache_resource` | i servizi (database, predittore, assistente) si creano **una volta per processo**; `configura()` del logging parte qui |
| `modello()` | `@st.cache_resource` | il modello si carica **una volta sola** attraverso tutte le navigazioni; se manca il file l'errore non si ricorda e il caricamento si riprova |
| `panoramica(utente_id)` | `@st.cache_data(ttl=TTL_LETTURE_SECONDI)` | lettura di sola lettura, **60 secondi**, dichiarati in una costante; nessun `@st.cache_data` senza `ttl` (un test lo verifica sul codice) |
| `svuota_letture()` | `st.cache_data.clear()` | da chiamare subito dopo una scrittura, perché il dato nuovo si veda senza aspettare |
| `inizializza_stato()` | `st.session_state.setdefault` | **l'unico punto** in cui nascono le chiavi: `utente_id` (DA-02: l'utente dimostrativo) e `apiario_attivo_id`; un test impedisce di scrivere in `session_state` fuori da qui |
| `scegli_apiario_iniziale()` | — | l'apiario attivo diventa il primo dell'utente; se quello scelto non esiste più, torna al primo |
| `avvia(titolo)` | prima riga di ogni pagina | `st.set_page_config` (deve essere il primo comando), stato, servizi; se la configurazione non è valida mostra il motivo e ferma la pagina |

Le pagine **non** importano il livello dati, `joblib`, `beewatch.ml`, `beewatch.ai` né il client del modello
di linguaggio: chiamano `beewatch.services` (un test legge gli `import` di ogni file di `app/`).

### Servizi aggiunti per la Home (`beewatch/services.py`)

`Servizi.panoramica(utente_id)` (le quattro caselle: query Q1 e Q3 più l'elenco degli apiari),
`Servizi.elenca_apiari(utente_id)` (solo id e nome: **niente coordinate**), `Servizi.stato_modello()` (versione,
algoritmo, errore medio) e `Servizi.descrizione_llm` (provider e modello, senza segreti).

## Decisioni

**1. `avvio.py` e non `ui.py`.** La specifica riserva `app/ui.py` agli helper visivi (M6-T2). Qui c'è ciò che
non è visivo: risorse, cache, stato. Tenerli separati evita che `ui.py` diventi un contenitore di tutto.

**2. Le pagine chiamano `avvia()` da sole.** In Streamlit con la cartella `pages/` non gira prima la Home:
ogni pagina è uno script a sé e deve preparare stato e servizi per conto proprio. Le risorse costose sono
in cache di processo, quindi il costo si paga una volta.

**3. 60 secondi di cache.** Abbastanza per non rifare le stesse query a ogni clic, abbastanza poco perché
un dato nuovo compaia presto; e `svuota_letture()` dopo ogni scrittura rende il TTL irrilevante per i dati
che l'utente stesso modifica.

**4. Nessun CSS «centralizzato».** La richiesta di una struttura CSS centralizzata si scontra con la
specifica (§2 e §13: *niente CSS iniettato*, tema nativo). Si è seguita la specifica: il tema vive solo in
`.streamlit/config.toml` e un test impedisce `unsafe_allow_html` e `<style` in `app/`. L'unica eccezione
prevista (`badge_stato`, M6-T2) non esiste ancora.

**5. L'errore di configurazione ferma la pagina, gli altri no.** Senza configurazione valida non c'è nulla
da mostrare; un database spento, invece, lascia viva la pagina con il messaggio in chiaro, e un modello
mancante lascia viva la Home con un avviso.

**6. Gli stati della Home** (specifica §11): con dati (quattro numeri), vuoto (invito a creare un apiario),
errore (messaggio e rimedio, mai un traceback). Il banner AI non serve: la Home non mostra output di un LLM.

## Come si prova

| Cosa | Dove |
|---|---|
| tema identico al §5 della specifica (il test legge il blocco `toml` del documento), sei pagine nell'ordine, import vietati, niente SQL/CSS, `ttl` dichiarato, stato in un punto solo, Dockerfile | `tests/test_app_struttura.py` (32) |
| Home e pagine **eseguite** con `AppTest`: numeri, stato della sessione, vuoto, errore del database, configurazione non valida, modello mancante, **servizi creati una volta e modello caricato una volta su otto navigazioni, con il log che lo dimostra**, cache e svuotamento | `tests/test_app_streamlit.py` (20) |
| `streamlit run app/Home.py` **parte davvero** in un sottoprocesso, risponde sul controllo di salute e serve la pagina | `tests/test_app_processo.py` (1) |
| Home e pagine con MySQL vero e il seed | `tests/test_app_database.py` (2, integrazione) |

**Verifica a mano in un browser** (stack MySQL isolato, `streamlit run app/Home.py` vero): la Home mostra
i dati del seed (4 alveari attivi, apiario «Apiario del Noce», modello v1.0.0, errore medio ±3,5 kg), il menu
ha le sette voci nell'ordine Home, Alveari, Ispezioni, Previsione, Assistente AI, Dashboard, Trasparenza, la
sidebar è color crema (`#FAF6F0`) come da tema, le sei pagine si aprono dal menu, e dopo otto navigazioni il
log del progetto contiene **una sola riga** «Modello v1.0.0 caricato da …». Le risorse Docker reali non sono
state toccate (fotografia prima/dopo).

## Cosa NON c'è

Il contenuto delle pagine (M6-T3…T8), gli helper `app/ui.py` (sidebar con il selettore dell'apiario, banner AI,
`mostra_errore`, grafici: M6-T2), l'autenticazione (M6-T11: per ora l'utente è quello dimostrativo, DA-02). Il
menu laterale e l'aspetto grafico non sono verificabili da `AppTest`: li copre la prova a mano qui sopra.

## File coinvolti

| File | Azione |
|---|---|
| `.streamlit/config.toml` | creato (palette del §5) |
| `app/Home.py` | rinominato da `main.py` e riscritto: panoramica |
| `app/avvio.py` | creato |
| `app/pages/1_Alveari.py` … `6_Trasparenza.py` | creati (scheletri) |
| `beewatch/services.py` | `panoramica`, `elenca_apiari`, `stato_modello`, `descrizione_llm`, `Panoramica`, `StatoModello`, `ApiarioScelta` |
| `Dockerfile`, `docker-compose.yml`, `README.md` | `app/Home.py`, copia di `.streamlit/`, comando di avvio |
| `tests/test_app_*.py` | creati |

## Definition of Done

| Voce | Esito |
|---|---|
| `.streamlit/config.toml` con la palette del §5, committato | fatto; `test_il_config_toml_esiste_ed_e_identico_al_paragrafo_5_della_specifica` |
| `streamlit run app/Home.py` parte senza errori | fatto; `test_streamlit_run_app_home_py_parte_e_risponde` e prova a mano nel browser |
| le sei pagine nel menu, nell'ordine del prefisso | fatto; `test_lordine_nel_menu_…` e prova a mano |
| `@st.cache_resource` su modello e connessione | fatto: `servizi()` (contiene database e predittore) e `modello()` |
| `@st.cache_data` sulle query di sola lettura, con TTL | fatto: `panoramica` con `ttl=60`; `test_ogni_lettura_in_cache_ha_un_tempo_dichiarato` |
| un log dimostra che il modello si carica UNA volta su più navigazioni | fatto; `test_il_modello_si_carica_una_volta_sola_e_un_log_lo_dimostra` e riga unica nel log del browser |
| `st.session_state` inizializzato in un punto solo, con l'apiario attivo | fatto; `inizializza_stato`, `test_lo_stato_della_sessione_nasce_solo_in_avvio_py` |
| `Home.py` mostra la panoramica e non contiene logica applicativa | fatto; `test_home_non_definisce_funzioni_ne_classi_ne_cicli` (euristica) |
| nessun import di `beewatch.database`, `joblib` o del client LLM in `app/` | fatto; `test_nessun_import_proibito_dentro_app` |
