# M6 - T3 · Pagina Alveari: l'anagrafica di apiari e alveari

> **Milestone** M6 · Interfaccia Streamlit
> **Task** M6-T3 (issue #34)
> **Stato** completata
> **Commit** `feat(m6): add the Alveari page to manage apiaries and hives`
> **Collegati** → [`ui_spec.md`](ui_spec.md) §6, §8, §11 · [`M6-T2_helper_ui.md`](M6-T2_helper_ui.md) · `app/pages/1_Alveari.py` · `beewatch/services.py`

## Obiettivo

La prima funzionalità della scheda del progetto: l'anagrafica su cui poggia tutto il resto. Si creano,
modificano, eliminano ed elencano apiari e alveari, senza SQL nella pagina e senza traceback a schermo.

## Cosa c'è

La pagina ha due schede, ognuna con l'anatomia del §6: **controlli** (moduli in espansori), **contenuto**
(l'elenco), e in fondo le **note**.

| Scheda | Controlli | Contenuto |
|---|---|---|
| **Alveari** (dell'apiario attivo, scelto nella sidebar) | «Aggiungi un alveare»; «Modifica o elimina un alveare» (si sceglie l'alveare, si può anche spostarlo in un altro apiario) | due metriche (alveari nell'apiario, in salute) e una scheda per alveare: codice, installazione, anno della regina, **stato con `badge_stato()`**, ultima ispezione con il peso, note |
| **Apiari** | «Aggiungi un apiario» (diventa l'apiario attivo); «Modifica o elimina un apiario» | una scheda per apiario: nome, «apiario attivo», località, coordinate, note |

### Servizi nuovi (`beewatch/services.py`)

| Metodo | Cosa fa |
|---|---|
| `apiari_in_anagrafica(utente_id)` | gli apiari attivi con tutti i campi (anche le coordinate, che `elenca_apiari` non dà) |
| `crea_apiario`, `aggiorna_apiario`, `elimina_apiario` | anagrafica degli apiari |
| `alveari_dell_apiario(utente_id, apiario_id)` | gli alveari attivi di un apiario, per codice, con data e peso dell'ultima ispezione (`AlveareInElenco`) |
| `crea_alveare`, `aggiorna_alveare`, `elimina_alveare` | anagrafica degli alveari |

I servizi costruiscono `Apiario` e `Alveare` (che si rifiutano di esistere con valori non validi) e chiamano
i repository già esistenti, che controllano nome e codice già usati e l'appartenenza all'utente.
`repositories.py` non è stato toccato: è a 397 righe su un limite di 400, e aveva già tutto.

### In `app/avvio.py`

- due letture in cache (`apiari_in_anagrafica`, `alveari_dell_apiario`), con lo stesso TTL delle altre;
- `scrittura_riuscita(messaggio)`: dopo una scrittura svuota le letture, salva l'esito e riesegue la
  pagina (`st.rerun`), così l'elenco mostra subito i dati nuovi; `prendi_esito()` lo mostra **una volta**
  con `st.success`;
- `imposta_apiario_attivo(id)`: l'apiario appena creato diventa quello attivo su tutte le pagine.

La chiave nuova (`esito_operazione`) nasce in `inizializza_stato` come le altre: le scritture in
`session_state` restano tutte in `avvio.py`.

### In `app/ui.py`

`formatta_data(giorno)`: `30/10/2026`, «—» se manca. Servirà anche a Ispezioni e Dashboard.

## Decisioni

**1. Eliminare è una cancellazione logica.** I repository hanno `disattiva`, non `DELETE`: ispezioni,
raccolti e previsioni restano nello storico e i numeri passati non cambiano. La pagina lo dice prima
(didascalia sopra la conferma) e dopo (note). Conseguenza dichiarata: **il nome di un apiario eliminato
resta riservato** (la query di unicità conta anche i disattivati), e così il codice di un alveare eliminato
dentro il suo apiario. La pagina lo scrive accanto al bottone.

**2. Conferma esplicita.** Una casella «Confermo: elimina l'alveare A2» e un bottone che senza spunta è
disabilitato. La spunta si **ricontrolla nel codice**: un test ha mostrato che un clic arrivato al bottone
disabilitato (come lo manda AppTest, o un client manipolato) eliminava lo stesso.

**3. Due livelli di validazione.** La pagina controlla prima ciò che si vede nel form: campi obbligatori
vuoti, coordinate date a metà. I widget fanno il resto: lunghezze massime, anno della regina fra 2000 e
quest'anno, data di installazione non futura, latitudine e longitudine nei loro intervalli. Solo dopo si
chiama il servizio, che con modelli e repository resta l'ultima difesa (nome o codice già usati, apiario di
un altro utente). Entrambi i livelli mostrano l'errore con `mostra_errore` e il nome del campo, mai un
traceback. Per questo anche i problemi trovati dalla pagina sono `ValidationError`.

**4. Coordinate arrotondate a sei decimali** prima del servizio: il widget restituisce un float
approssimato e il modello rifiuterebbe più decimali di quanti ne tiene la colonna.

**5. Elenco a schede, non tabella.** `badge_stato` è HTML e non entra in `st.dataframe`: ogni alveare è una
scheda (`st.container(border=True)`) con tre colonne. Con pochi alveari per apiario (il caso reale) si legge
meglio di una tabella.

**6. Il test di M6-T1 su `avvia()`** chiedeva che fosse la prima istruzione in assoluto. Lo scopo era che
nessun comando Streamlit lo precedesse (`st.set_page_config`); ora il test ammette prima import, funzioni e
costanti senza chiamate a Streamlit.

**7. Un bug trovato dai test:** i due selettori usavano `lambda i: per_id[i]` e `per_id` veniva
riassegnata nella scheda successiva (closure tardiva). Ora usano un dizionario legato al momento della
chiamata.

## Come si prova

| Cosa | Dove |
|---|---|
| servizi dell'anagrafica: campi non validi con il campo indicato, nome e codice già usati, utente estraneo, cancellazione logica, ordinamento, ultima ispezione | `tests/test_servizi_anagrafica.py` |
| **lo stesso scenario** completo in memoria e su MySQL vero, così i finti non possono divergere dalle regole vere | `tests/test_servizi_anagrafica.py` (31 unitari e 1 integration) |
| la pagina con AppTest: elenco, pastiglie (mai il codice grezzo), date all'italiana, stato vuoto, database spento, aggiungere/modificare/spostare/eliminare alveari e apiari, conferma, controlli della pagina **prima** del servizio (il servizio non viene chiamato), errori del servizio, esito mostrato una volta | `tests/test_pagina_alveari.py` (27) |
| struttura: nessun SQL, nessun `st.error` scritto a mano, form non duplicati, `avvia` per primo | `tests/test_app_struttura.py`, `tests/test_ui.py` |

Copertura di `app/` al 100% (righe e rami). L'anagrafica in memoria è in `tests/anagrafica_finta.py`.

**Prova a mano nel browser** (stack MySQL isolato e usa-e-getta, `streamlit run app/Home.py` vero, dati del
seed): l'elenco di «Apiario del Noce» mostra i quattro alveari del seed con le pastiglie «In salute»,
«Debole», «In osservazione», «Sciamato», le date e i pesi dell'ultima ispezione. Aggiunto l'alveare A5 dal
form: esito verde «Alveare A5 aggiunto a Apiario del Noce.», A5 in elenco con «Mai ispezionato», metriche
aggiornate (5 alveari, 2 in salute). L'eliminazione nel browser non è stata completata (il pannello stretto
nascondeva la casella di conferma ai comandi automatici): è coperta dai test sopra. Risorse Docker reali
non toccate.

## Cosa NON c'è

Riattivare un apiario o un alveare eliminato (nessun requisito; i dati restano nel database); la scheda di
dettaglio di un alveare con lo storico delle ispezioni (M6-T4).

## File coinvolti

| File | Azione |
|---|---|
| `app/pages/1_Alveari.py` | riscritto: la pagina vera |
| `app/avvio.py` | letture dell'anagrafica, esito delle scritture, apiario attivo impostabile |
| `app/ui.py` | `formatta_data` |
| `beewatch/services.py` | `AlveareInElenco` e le otto operazioni dell'anagrafica |
| `tests/test_pagina_alveari.py`, `tests/test_servizi_anagrafica.py`, `tests/anagrafica_finta.py` | creati |
| `tests/app_finta.py`, `tests/test_app_streamlit.py`, `tests/test_app_struttura.py`, `tests/test_ui.py` | adeguati alla pagina vera |
| `README.md` | conteggio dei test |

## Definition of Done

| Voce | Esito |
|---|---|
| creazione, modifica, cancellazione e lista di apiari e alveari funzionanti | fatto (cancellazione logica, decisione 1); `test_aggiungere_…`, `test_modificare_…`, `test_eliminare_…`, scenario su MySQL |
| layout conforme al §6 (intestazione, controlli, contenuto, note) | fatto: in ogni scheda prima i moduli, poi l'elenco; note in fondo |
| validazione lato interfaccia PRIMA della chiamata al servizio | fatto; `test_un_codice_vuoto_si_ferma_nella_pagina_prima_del_servizio`, `test_i_controlli_della_pagina_sullapiario` |
| input non validi rifiutati con messaggio chiaro, non con traceback | fatto; `test_un_codice_gia_usato_…`, `test_modificare_un_alveare_con_un_codice_non_valido`, … |
| cancellazione protetta da conferma esplicita | fatto; `test_eliminare_chiede_una_conferma_esplicita` |
| esito di ogni operazione comunicato con `st.success` o `st.error` | fatto: successo con `st.success` (una volta), errori con `mostra_errore` (`st.error`) |
| stato dell'alveare mostrato con `badge_stato()`, mai come stringa grezza | fatto; `test_lo_stato_e_una_pastiglia_mai_il_codice_grezzo` |
| elenco vuoto gestito con `blocco_vuoto()` | fatto; `test_un_apiario_senza_alveari_…`, `test_senza_apiari_entrambe_le_schede_…` |
| nessun SQL nella pagina: solo chiamate a `services.py` | fatto; `test_nessun_sql_nei_file_di_app`, `test_nessun_import_proibito_dentro_app` |
