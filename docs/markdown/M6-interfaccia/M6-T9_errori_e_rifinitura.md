# M6 - T9 · Gestione errori e rifinitura

> **Milestone** M6 · Interfaccia Streamlit
> **Task** M6-T9 (issue #40)
> **Stato** completata
> **Commit** `feat(m6): fail fast when the database is down and verify every page state`
> **Collegati** → [`ui_spec.md`](ui_spec.md) §11, §12 · `app/avvio.py` · `beewatch/database.py` · `beewatch/exceptions.py`

## Obiettivo

Nessun traceback rosso davanti al docente: ogni pagina regge i dati, il vuoto e l'errore, anche con
il database spento, il provider AI irraggiungibile o il database completamente vuoto.

## Cosa cambia

### L'interruttore del database

Il punto aperto da M6-T2: con il server che non risponde passavano circa 30 secondi prima del
messaggio d'errore. La causa: ogni lettura ritenta la connessione (tre tentativi, `database.py`), e
la sidebar e il corpo della pagina leggono ciascuno per conto suo.

- `DatabaseError` ha ora `connessione`: vero solo quando non si è riusciti ad aprire la connessione
  (`Database._apri`). Una query fallita su una connessione aperta resta `connessione=False`.
- In `app/avvio.py` le letture dal database passano da `_interruttore`: dopo un errore **di
  connessione**, per `PAUSA_DOPO_ERRORE_DB_SECONDI` (10) le letture successive sollevano subito lo
  stesso errore, senza ritentare; dopo la pausa si riprova davvero, e una lettura riuscita lo
  richiude. Anche `svuota_letture` lo richiude: si chiama dopo una scrittura riuscita, quindi con il
  database acceso. L'errore di una singola query non blocca le altre letture.

Effetto, provato con i finti: con il server spento la Home tenta la connessione **una volta**
invece di due (sidebar e corpo), e il messaggio è lo stesso.

### Le tre condizioni, più severe

- «Database vuoto» in AppTest ora vuol dire vuoto davvero: nessun apiario **e** nessun dato USDA.
- Un test d'integrazione apre ogni pagina, dalla Home come nel browser, con un utente appena creato
  su MySQL e senza nessun dato: nessuna eccezione, nessun errore.
- Un test ripete alla lettera i due `grep` della DoD.

## Checklist del §12 (allegata alla issue #40)

| Voce | Esito | Prova |
|---|---|---|
| Le sei pagine hanno l'ordine di sezioni del §6 | ✅ | intestazione, (banner), controlli, contenuto, note in ogni pagina; documenti M6-T3…T8 e i test AppTest di ciascuna |
| La sidebar è identica ovunque e generata da `ui.sidebar()` | ✅ | `test_la_sidebar_e_identica_su_tutte_le_schermate` |
| Nessuna query SQL, `joblib.load` o chiamata LLM dentro `app/` | ✅ | `test_nessun_sql_nei_file_di_app`, `test_nessun_import_proibito_dentro_app`, `test_il_client_del_modello_di_linguaggio_non_si_importa_nemmeno_per_nome`, `test_i_due_grep_della_dod_di_m6_t9` |
| `unsafe_allow_html` compare solo dentro `badge_stato()` | ✅ | `test_nessun_css_ne_html_iniettato_fuori_da_badge_stato`, `test_i_due_grep_della_dod_di_m6_t9` |
| Ogni grafico ha assi etichettati con unità e una didascalia con la fonte | ✅ | `grafico_serie`/`grafico_barre` rendono obbligatorie etichette e fonte; `test_tre_grafici_con_assi_in_unita_palette_e_fonte`; la barra della stima ha l'asse «Produzione (kg)» |
| Ogni stato colorato ha anche un'etichetta testuale | ✅ | `badge_stato` (icona + testo), rischio a parole, stato di salute con icona e testo; test in `test_ui.py`, `test_pagina_ispezioni.py`, `test_pagina_assistente.py` |
| Le tre condizioni (dati, vuoto, errore) sono state provate su ogni pagina | ✅ | `test_ogni_pagina_con_dati_ha_intestazione_e_un_numero_di_contesto`, `test_ogni_pagina_regge_il_database_vuoto`, `test_ogni_pagina_regge_il_database_spento`, `test_ogni_pagina_regge_il_modello_mancante`, più i test di ogni pagina e `test_con_un_utente_senza_dati_ogni_pagina_resta_usabile` (MySQL) |
| Il banner AI è presente e non nascondibile | ✅ | `test_banner_ai_e_un_avviso_blu_non_richiudibile`, `test_solo_la_pagina_dellassistente_ha_il_banner_ai` |
| Nessuna previsione è mostrata senza banda di incertezza | ✅ | `stima_con_incertezza` rifiuta una stima senza banda (`controlla_banda`); `test_prevedere_dai_dati_mostra_stima_banda_modello_e_la_salva`; nella Dashboard il previsto ha la banda |
| L'app è leggibile a 1366×768 | ✅ | verifica nel browser (sotto) |
| Nessuna pagina supera i 3 secondi con i dati demo | ✅ | misura (sotto): massimo 1,46 s |

## Verifiche a mano

**1366×768** (stack MySQL isolato, seed ed ETL, finestra emulata a 1366×768): su tutte e sette le
schermate nessun valore o etichetta di metrica troncato e nessuno scorrimento orizzontale, misurati
nel DOM (`scrollWidth` contro `clientWidth`). Controprova: a 800 px lo stesso controllo trova troncate
le metriche della Dashboard, come visto in M6-T7. Il troncamento sotto i 1366 px riguarda la griglia
a quattro colonne: è materia di M6-T10 (tema).

**Tempi con i dati demo** (stack isolato, seed ed ETL, servizi e modello veri, AppTest, cache delle
letture svuotata prima di ogni pagina):

| Pagina | Secondi |
|---|---|
| Home al primo avvio (carica il modello) | 1,46 |
| Home | 0,22 |
| Alveari | 0,06 |
| Ispezioni | 0,21 |
| Previsione | 0,07 |
| Assistente AI (senza generare) | 0,19 |
| Dashboard (sei stime per il confronto) | 0,55 |
| Trasparenza | 0,01 |

Generare un riepilogo dipende dal modello di linguaggio (20,7 s con `llama3.1:8b` in M6-T6): lo
spinner lo dichiara. Risorse Docker reali non toccate in nessuna prova.

## Come si prova

| Cosa | Dove |
|---|---|
| l'interruttore: una sola connessione con il server spento, nessun blocco per una query sbagliata, nuovo tentativo dopo la pausa, chiusura dopo una lettura riuscita e dopo `svuota_letture` | `tests/test_interruttore_db.py` |
| `connessione` vero per la connessione fallita, falso per la query fallita | `tests/test_database.py` |
| database vuoto davvero (anche senza USDA) su ogni pagina | `tests/test_ui.py` |
| un utente senza dati, ogni pagina, MySQL vero | `tests/test_app_database.py` (integration) |
| i due `grep` della DoD | `tests/test_app_struttura.py` |

## File coinvolti

| File | Azione |
|---|---|
| `app/avvio.py` | `_interruttore`, `azzera_interruttore`, `PAUSA_DOPO_ERRORE_DB_SECONDI`; `svuota_letture` lo richiude |
| `beewatch/exceptions.py` | `DatabaseError.connessione` |
| `beewatch/database.py` | la connessione fallita solleva `DatabaseError(..., connessione=True)` |
| `tests/test_interruttore_db.py` | creato |
| `tests/test_database.py`, `tests/test_ui.py`, `tests/test_app_database.py`, `tests/test_app_struttura.py`, `tests/app_finta.py` | adeguati |
| `README.md` | conteggio dei test |

## Definition of Done

| Voce | Esito |
|---|---|
| checklist del §12 di `docs/ui_spec.md` compilata e allegata alla issue | fatto: sopra, e in un commento della issue #40 |
| le tre condizioni (con dati, senza dati, in errore) provate su ogni pagina | fatto: vedi checklist |
| nessun traceback visibile in nessun percorso testato | fatto: ogni test di pagina controlla `not at.exception` |
| l'app è usabile con database completamente vuoto | fatto; `test_ogni_pagina_regge_il_database_vuoto`, `test_con_un_utente_senza_dati_ogni_pagina_resta_usabile` |
| database irraggiungibile: messaggio comprensibile, non crash | fatto, e ora in metà del tempo; `test_ogni_pagina_regge_il_database_spento`, `test_con_il_server_spento_la_connessione_si_tenta_una_volta_sola` |
| provider LLM irraggiungibile: la pagina Assistente resta usabile | fatto; `test_un_timeout_del_modello_si_spiega_senza_traceback` (il bottone resta), `info_assistente` non crea il client |
| layout verificato a 1366×768 | fatto: nessun troncamento, nessuno scorrimento orizzontale |
| nessuna pagina supera i 3 secondi con i dati demo | fatto: massimo 1,46 s |
| `grep -r unsafe_allow_html app/` restituisce solo `badge_stato()` | fatto; `test_i_due_grep_della_dod_di_m6_t9` |
| `grep -rE "SELECT\|joblib.load\|requests.post" app/` non restituisce nulla | fatto; stesso test |
