# M4 - T8 · Servizio di previsione

> **Milestone** M4 · Machine Learning
> **Task** M4-T8
> **Stato** completata
> **Commit** `feat(m4): add the production forecast service`
> **Collegati** → [`model_card.md`](../../model_card.md) · [`M4-T7_modello_e_predittore.md`](M4-T7_modello_e_predittore.md) · [`dati.md`](../M2-dati/dati.md)

## Obiettivo

Fare da ponte fra i dati dell'utente e un modello addestrato su dati USDA, e rendere ogni
previsione tracciabile: sempre con il suo intervallo, mai come numero secco, con la versione del
modello e le feature con cui è nata. È anche il punto che l'interfaccia chiama: le pagine non
scrivono query e non conoscono il modello.

## Descrizione

`beewatch/services.py`:

```python
from beewatch.services import crea_servizi

servizi = crea_servizi()                                   # in app/: st.cache_resource
servizi.stati_prevedibili()                                # i 40 stati, con gli anni accettati
r = servizi.prevedi_produzione(utente_id=1, alveare_id=3, codice_stato="CA", anno=2013)
r.stima_kg, r.limite_inferiore_kg, r.limite_superiore_kg   # per esempio 30, 24, 36: chili interi
r.mostra_stima, r.messaggio, r.retrospettiva, r.versione_modello, r.feature
servizi.storico_previsioni(utente_id=1)                    # le ultime previsioni (Q9)
```

| Elemento | Cosa fa |
|---|---|
| `Servizi` | database, predittore e le operazioni dell'interfaccia; le dipendenze si passano al costruttore (i test mettono dei finti) |
| `prevedi_produzione` | valida, costruisce le feature, chiede la stima, arrotonda, applica la regola, salva |
| `RisultatoPrevisione` | stima ed estremi in chili interi, `livello`, `mostra_stima`, `messaggio`, `retrospettiva`, versione del modello, MAE del modello, feature |
| `stati_prevedibili`, `storico_previsioni` | per i selettori e per lo storico della pagina |
| `crea_servizi` | le dipendenze vere dalla configurazione; non apre connessioni e non carica il modello |

## Il flusso di `prevedi_produzione`

1. **Valida gli ingressi**, nell'ordine utente, alveare, stato, anno. Un errore è una
   `ValidationError` che nomina il campo (`utente_id`, `alveare_id`, `codice_stato`, `anno`) e dice
   cosa va bene («Per California si può prevedere dal 1999 al 2013»). Lo stato si normalizza
   (`" ca "` → `CA`); un anno decimale o testuale è rifiutato.
2. **Costruisce le feature con la sola storia fino all'anno prima.** Prende la serie dello stato
   da `produzione_usda`, tiene gli anni **precedenti** a quello da prevedere e aggiunge una riga
   vuota per l'anno richiesto; poi chiama la stessa `costruisci_feature_storiche` di M4-T2. La resa
   dell'anno richiesto non entra nemmeno se è già nei dati: un test la altera e controlla che
   le feature non cambino.
3. **Chiede la stima al predittore**, che aggiunge i limiti p10 e p90 dei residui (M4-T6).
4. **Arrotonda ai chili**: stima al più vicino, estremi **verso l'esterno** (inferiore per
   difetto, superiore per eccesso), così l'intervallo non si restringe. «Nessun arrotondamento
   sotto il chilo» (M2-T3).
5. **Applica la regola** «se l'intervallo è più largo della stima, la stima non si mostra»:
   `mostra_stima` è falso e `messaggio` dice perché. Il risultato ha comunque l'intervallo.
6. **Se la stima si mostra, la salva** in `previsioni` con `versione_modello` e `feature_json`.
   Se il modello non è ancora nella tabella `modelli` lo registra prima dai suoi metadati: la
   chiave esterna lo richiede, e con un clone pulito la tabella è vuota.

## Decisioni progettuali

**1. Una colonna nuova, `previsioni.feature_json`, per rispettare la DoD.** La DoD chiede
«persistita con modello_versione e feature_json», ma lo schema non aveva quella colonna (la nota
tecnica del backlog diceva che lo schema «lo supporta già»: non era vero per i valori). Senza i
valori una previsione vecchia non si può rifare né spiegare, perché `produzione_usda` può essere
ricaricata. La colonna è in un file a parte, `sql/schema_02_previsioni_feature_json.sql`, ripetibile
e applicabile a un database esistente. Il file si chiama così, e non `002_…` come suggeriva il
backlog, perché MySQL esegue gli script in ordine alfabetico: `002_…` verrebbe **prima** di
`schema.sql` e la tabella non esisterebbe ancora. `00_test_db.sh` applica ora anche le estensioni
`schema_*.sql` al database dei test.

**2. Chi ha già un volume deve applicarla a mano**, perché gli script di inizializzazione girano
solo a volume vuoto e l'utente applicativo non ha `ALTER`. Il comando è in testa al file e nel
README. Se il programma trova il database senza la colonna (o senza una tabella) lo dice con un
messaggio che rimanda a quel comando (errori MySQL 1054 e 1146, prima «operazione non riuscita»).

**3. Se la stima non si mostra, non si salva.** Lo storico (Q9) è l'elenco di ciò che l'utente ha
visto: una stima nascosta non ci deve comparire. Il risultato ha `id=None`.

**4. Gli anni accettati sono quelli per cui esiste la storia**: dal secondo anno dei dati
all'anno dopo l'ultimo (1999–2013). Il 2013 è la sola previsione davvero futura; gli anni
precedenti sono **prove a ritroso** (`retrospettiva=True`) e per il modello salvato sono «in
campione»: ha visto quell'anno in addestramento (M4-T7). L'interfaccia deve dirlo.

**5. Una classe `Servizi`, non funzioni di modulo.** Il backlog scrive `services.prevedi_produzione`.
Un metodo permette di iniettare database e predittore finti nei test e di tenere il servizio in
cache una volta sola in Streamlit. Il resto (assistente AI, M5) si aggiunge alla stessa classe.

**6. Il predittore si carica alla prima previsione**, una volta sola (anche con più thread) e senza
ricordare un fallimento: l'app parte anche senza il file del modello e lo dice solo quando serve.

**7. La stima porta con sé il MAE del modello** (`errore_medio_kg`, il 3,50 del 2010–2012) perché la
pagina possa scrivere «modello v1.0.0, errore medio 3,5 kg» come stabilito in M2-T3.

## File coinvolti

| File | Azione |
|---|---|
| `beewatch/services.py` | creato |
| `beewatch/models.py` | `Previsione.feature` (dizionario JSON finito, copiato) |
| `beewatch/repositories_riferimento.py` | `feature_json` in `salva_previsione` e Q9; `stati_del_pannello` |
| `beewatch/database.py` | messaggio per schema più vecchio del programma (1054, 1146) |
| `beewatch/ml/artefatto.py`, `addestramento.py` | `percorso_per_la_tabella` condiviso |
| `sql/schema_02_previsioni_feature_json.sql` | creato; `sql/00_test_db.sh` applica le estensioni |
| `docs/diagrams/er_diagram.dbml` | la colonna nuova |
| `tests/test_services.py`, `test_schema_estensioni.py` | creati; `test_models.py`, `test_repositories.py`, `test_database.py` estesi |
| `README.md`, `docs/README.md`, `docs/model_card.md` | comando di migrazione, indice, stato |

## Definition of Done

| Voce | Prova |
|---|---|
| servizio testato con un modello finto | `tests/test_services.py`: `PredittoreFinto`, repository finti, 46 test; in più il servizio vero con MySQL e il modello committato |
| input non validi gestiti con eccezione chiara | `ValidationError` con il campo, per utente, alveare, stato e anno; nessun caricamento del modello né salvataggio se l'ingresso è sbagliato |
| predizione persistita con modello_versione e feature_json | `test_la_previsione_si_salva_con_versione_del_modello_e_feature` e, da MySQL, `test_integrazione_prevedere_il_2013_salva_la_previsione_e_registra_il_modello` (feature rilette identiche dallo storico) |
| l'output include sempre l'incertezza, mai un numero secco | `RisultatoPrevisione` ha sempre `limite_inferiore_kg` e `limite_superiore_kg`; `test_il_risultato_ha_sempre_lintervallo_e_la_stima_dentro`, e la regola dell'intervallo più largo della stima |

## Miglioramenti futuri

- Un intervallo più stretto per le previsioni basse e più largo per le alte (la copertura per
  fasce è 87 % / 81 % / 72,5 %: vedi la model card).
- Quando ci sarà un login (DA-02), `utente_id` verrà dalla sessione e non da un parametro.
