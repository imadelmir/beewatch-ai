# M6 - T5 · Pagina Previsione: la resa per colonia con la sua banda

> **Milestone** M6 · Interfaccia Streamlit
> **Task** M6-T5 (issue #36)
> **Stato** completata
> **Commit** `feat(m6): add the Previsione page with estimates, limits and history`
> **Collegati** → [`ui_spec.md`](ui_spec.md) §2, §6, §10, §11 · [`M6-T4_pagina_ispezioni.md`](M6-T4_pagina_ispezioni.md) · `app/pages/3_Previsione.py` · `beewatch/services.py`

## Obiettivo

La seconda funzionalità della scheda del progetto: il modello joblib di M4 ricaricato davvero dentro
Streamlit, con la stima mostrata sempre insieme alla sua incertezza.

## Che cosa prevede il modello, e quindi la pagina

Il modello stima la **resa media per colonia di uno stato USA in un anno** (USDA, 1998–2012). Non
conosce gli alveari dell'utente. Per questo la pagina offre due modi:

| Modo | Che cosa si sceglie | Che cosa succede |
|---|---|---|
| **Dai dati storici di uno stato** (predefinito) | stato, anno e, se si vuole, un alveare dell'apiario attivo a cui collegare la previsione | le feature si costruiscono dalla storia dello stato (`prevedi_produzione`, come in M4-T8); la previsione **si salva** nello storico, con l'alveare se scelto |
| **Con parametri scritti a mano** | stato, anno, resa dell'anno prima, resa media dei 3 anni prima, colonie dell'anno prima | `prevedi_con_parametri`: i valori scritti sostituiscono la storia. È una **simulazione** e non si salva |

Collegare un alveare serve a ritrovare la previsione nel suo storico, non la trasforma in una
previsione per quell'alveare: lo dice l'avviso sui limiti.

## Cosa c'è

Anatomia del §6:

| Parte | Cosa |
|---|---|
| **Intestazione** | titolo e riga di spiegazione |
| **Controlli** | l'**avviso sui limiti di trasferibilità**, un `st.warning` sempre visibile in cima, non in un espansore; il modello in uso (errore medio come metrica, versione e algoritmo); il selettore «Storico di»; il modo; il modulo |
| **Contenuto** | la stima con **`stima_con_incertezza()`**: metrica, banda, la **barra orizzontale con la banda d'errore** del §10 e l'avvertenza; sotto, il modello che l'ha prodotta e l'errore medio, la nota «prova a ritroso» se l'anno è già nei dati, i valori usati in un espansore; poi lo **storico delle previsioni**, di tutti gli alveari o di quello scelto |
| **Note** | unità, arrotondamento, significato della banda, fonte |

### Servizi (`beewatch/services.py`)

| Metodo | Cosa fa |
|---|---|
| `intervalli_parametri()` | minimo e massimo visti in addestramento per i tre parametri (dal pannello Q8, letto una volta sola); senza dati, `ModelError` con il rimedio |
| `prevedi_con_parametri(utente_id, codice_stato, anno, *, resa_anno_prima, resa_media_3_anni_prima, colonie_anno_prima)` | stato e anno con le regole di sempre; ogni parametro deve essere un numero finito **dentro l'intervallo dell'addestramento**, altrimenti `ValidationError` con il campo e l'intervallo; la stima non si salva (`parametri_manuali=True`) |
| `storico_previsioni(..., alveare_id=None)` | con `alveare_id`, solo le previsioni di quell'alveare |
| `_stima(...)` | il cuore che prima stava in `prevedi_produzione` (stima, arrotondamenti, regola dell'intervallo, salvataggio), ora condiviso dai due modi |

`RisultatoPrevisione` ha un campo nuovo, `parametri_manuali`; `IntervalloParametro` descrive un
intervallo. `PrevisioniRepository.ultime_previsioni` accetta `alveare_id` e restituisce anche la
colonna `alveare_id`: prima dava solo il codice, che è unico solo dentro un apiario.

### In `app/avvio.py`

Tre letture in cache, con lo stesso TTL delle altre: `stati_prevedibili`, `intervalli_parametri`,
`storico_previsioni`. Dopo una previsione salvata la pagina chiama `svuota_letture`, così lo storico
sotto la mostra subito.

## Decisioni

**1. «Parametri a mano» vuol dire le feature del modello.** Il modello prende stato, anno e tre valori
storici: scriverli a mano permette di chiedere «e se l'anno scorso fosse andato peggio?». Sono
simulazioni, e lo storico raccoglie solo le previsioni sui dati veri: mescolarle renderebbe lo
storico illeggibile.

**2. Le feature incompatibili si rifiutano prima del modello.** Un modello a foreste casuali non sa
andare oltre i valori che ha visto: con una resa di 120 kg risponderebbe comunque, con un numero senza
senso. Il servizio confronta ogni parametro con il minimo e il massimo del pannello di addestramento
e, fuori da lì, dice quale campo, quale intervallo e perché. Il widget ha gli stessi limiti e li
scrive nell'aiuto. L'altra incompatibilità, un modello che chiede colonne diverse da quelle che il
servizio costruisce, è un `ModelError` del predittore («mancano le colonne: …»): la pagina lo mostra
con `mostra_errore`.

**3. Il modello che manca non spegne la pagina.** Con un `ModelError` al caricamento la pagina lo dice
(«Il modello di previsione non è disponibile», con il comando per riaddestrarlo), toglie il modulo e
mostra comunque l'avviso e lo storico, che stanno nel database.

**4. L'anno ha i limiti di tutti gli stati.** Dentro un form il cambio di stato non riesegue la
pagina, quindi il campo anno non può seguire lo stato scelto: va dal primo all'ultimo anno ammesso
per qualche stato, e il servizio controlla quello dello stato scelto (con un messaggio che dice
l'intervallo giusto). Con i dati veri tutti i 40 stati hanno lo stesso intervallo, 1999–2013.

**5. Lo storico mostra chili interi.** Stime ed estremi sono interi per costruzione (M4-T8), ma MySQL
li restituisce come `DECIMAL(6, 2)`: un test ha mostrato «52,0». Ora sono formattati senza decimali, e
il finto delle previsioni restituisce `Decimal` come il database.

**6. Il selettore dell'alveare nel modulo segue «Storico di»**, con la chiave legata alla scelta (la
stessa trappola di Streamlit vista in M6-T4).

## Come si prova

| Cosa | Dove |
|---|---|
| intervalli (valori, una lettura sola, dati mancanti), simulazione (valori al modello, non salvata, tipi numerici), parametri fuori intervallo o non numerici con il campo, stato e anno, feature incompatibili, banda più larga della stima, storico per alveare | `tests/test_servizi_previsione.py` (26) |
| su MySQL con il modello committato: storico per alveare (la query nuova), parametri a mano uguali ai dati danno la stessa stima e non si salvano, intervalli dal pannello vero | `tests/test_services.py` (integration) |
| la pagina con AppTest: avviso fuori da ogni espansore, modello e versione, limiti dei campi, stima con banda e grafico, «prova a ritroso», salvataggio e storico, alveare collegato e storico filtrato, banda troppo larga, simulazione non salvata, parametro mancante fermato prima del servizio, modello mancante, feature incompatibili, dati USDA assenti, database spento, storico illeggibile, nessun alveare | `tests/test_pagina_previsione.py` (16) |
| la pagina con il database vero, aperta dalla Home | `tests/test_app_database.py` (integration) |
| tutti i test dell'interfaccia anche con Streamlit 1.67, la versione della CI | venv laterale, in locale |

**Prova a mano nel browser** (stack MySQL isolato e usa-e-getta, `streamlit run app/Home.py` vero,
modello committato `v1.0.0`):

- senza i dati USDA la pagina mostra l'avviso sui limiti e lo stato vuoto con il comando dell'ETL;
- caricati i dati con `scripts/run_etl.py` (report nello scratchpad), «Dai dati storici», con i valori
  proposti (Alabama, 2013), dà **25 kg, banda da 18 a 32 kg (80%)**, con la barra orizzontale e la banda
  d'errore, «Stimata dal modello v1.0.0», «Salvata nello storico». Lo storico mostra la riga con i chili
  interi;
- «Con parametri scritti a mano» (30 kg, 31 kg, 60 000 colonie) dà **27 kg, banda da 21 a 34 kg**,
  con l'etichetta di simulazione e senza salvarla.

Non provati nel browser, perché il pannello era nascosto e i menu a tendina non rispondono ai comandi
automatici: la scelta di un altro stato e il collegamento a un alveare. Sono coperti dai test AppTest
e d'integrazione. Cambiando modo, la stima appena mostrata sparisce: la pagina la mostra solo dopo il
calcolo e non la conserva. Risorse Docker reali non toccate.

## Cosa NON c'è

Il confronto con la resa vera per gli anni già nei dati (la pagina dice solo che è una prova a
ritroso); il grafico dello storico nel tempo (Dashboard, M6-T7); cancellare una previsione salvata.

## File coinvolti

| File | Azione |
|---|---|
| `app/pages/3_Previsione.py` | riscritto: la pagina vera |
| `app/avvio.py` | letture in cache di stati, intervalli e storico |
| `beewatch/services.py` | `IntervalloParametro`, `intervalli_parametri`, `prevedi_con_parametri`, `_stima`, storico per alveare |
| `beewatch/repositories_riferimento.py` | `ultime_previsioni` con `alveare_id` |
| `tests/previsione_finta.py`, `tests/test_servizi_previsione.py`, `tests/test_pagina_previsione.py` | creati |
| `tests/test_services.py` | tre test d'integrazione |
| `tests/app_finta.py`, `tests/test_app_streamlit.py`, `tests/test_ui.py` | adeguati |
| `README.md` | conteggio dei test |

## Definition of Done

| Voce | Esito |
|---|---|
| selezione dell'alveare oppure inserimento manuale dei parametri | fatto: i due modi; `test_collegare_un_alveare_la_mette_nel_suo_storico`, `test_una_simulazione_mostra_la_stima_e_non_si_salva` |
| stima mostrata tramite `stima_con_incertezza()`: mai un numero secco | fatto; `test_prevedere_dai_dati_mostra_stima_banda_modello_e_la_salva`, `test_una_banda_piu_larga_della_stima_non_mostra_il_valore` |
| grafico a barra orizzontale con banda di errore (§10) | fatto, dentro `stima_con_incertezza` (`figura_stima`); il test controlla che il grafico ci sia |
| disclaimer sui limiti di trasferibilità sempre visibile, non in un expander | fatto; `test_la_pagina_mostra_limiti_modello_e_modulo`, e resta anche senza modello |
| versione del modello usata mostrata a schermo | fatto: in cima e sotto ogni stima, e in ogni riga dello storico |
| storico delle previsioni precedenti per quell'alveare | fatto; `test_collegare_un_alveare_la_mette_nel_suo_storico`, `test_integrazione_lo_storico_si_restringe_a_un_alveare` |
| `ModelError` gestita senza crash, con messaggio comprensibile | fatto; `test_senza_modello_la_pagina_lo_dice_e_mostra_lo_storico` |
| feature incompatibili col modello segnalate con messaggio chiaro | fatto: parametri fuori dall'addestramento (servizio e widget) e colonne mancanti nel modello; `test_un_parametro_fuori_dalladdestramento_e_incompatibile`, `test_feature_incompatibili_col_modello_si_spiegano_senza_crash` |
| nessun `joblib.load` nella pagina: passa da `services.py` | fatto; `test_nessun_import_proibito_dentro_app` |
