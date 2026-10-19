# M3 - T1 · Connessione al database e transazioni

> **Milestone** M3 · Accesso ai dati ed ETL
> **Task** M3-T1
> **Stato** implementata, pronta per review e merge
> **Commit** `feat(m3): implement MySQL database layer`
> **Collegati** → [`M2-T5_schema_sql.md`](../M2-dati/M2-T5_schema_sql.md) · [`M1-T4_eccezioni_logging.md`](../M1-fondamenta/M1-T4_eccezioni_logging.md) · [`M1-T3_configurazione.md`](../M1-fondamenta/M1-T3_configurazione.md)

## Obiettivo

Avere un solo punto del progetto che sa come si parla con MySQL. Repository,
ETL e servizi (le prossime task) ricevono un `Database`, aprono una transazione
e lavorano con un cursore: non importano `mysql.connector` e non ne vedono le
eccezioni.

## Descrizione

`beewatch/database.py` contiene la classe `Database`, con due metodi pubblici.

```python
from beewatch.config import ottieni
from beewatch.database import Database

db = Database(ottieni().database)

with db.transazione() as cursore:
    cursore.execute(
        "SELECT id, codice FROM alveari WHERE apiario_id = %s AND attivo = TRUE",
        (apiario_id,),
    )
    righe = cursore.fetchall()      # list[dict]: riga["codice"]

if not db.verifica_connessione():   # True / False, non solleva
    ...
```

| Metodo | Cosa fa |
|---|---|
| `Database(config)` | riceve una `ConfigDatabase`. Non apre connessioni |
| `transazione()` | context manager: apre una connessione, restituisce un cursore a dizionari, all'uscita fa `commit` o `rollback` e chiude tutto |
| `verifica_connessione()` | `SELECT 1` con un solo tentativo e timeout breve; `True`/`False` |

### Transazioni

| Come termina il blocco `with` | Cosa succede |
|---|---|
| senza errori | `commit` |
| eccezione del driver (query sbagliata, vincolo violato, connessione caduta) | `rollback`, poi `DatabaseError` con l'eccezione originale in `__cause__` |
| qualunque altra eccezione (`ValidationError`, un bug, Ctrl+C) | `rollback`, poi **la stessa** eccezione, non tradotta |
| il `commit` fallisce | `rollback`, poi `DatabaseError` |

In tutti i casi cursore e connessione vengono chiusi. Se il `rollback` o la
chiusura falliscono a loro volta (tipicamente perché la connessione è caduta),
l'errore va nel log come avviso e **non sostituisce** quello originale.

Il cursore è *buffered*: le righe di una `SELECT` vengono lette tutte subito.
Senza, un risultato non letto fino in fondo farebbe fallire il `commit`.

### Retry e timeout

| Costante | Valore | Significato |
|---|---|---|
| `TIMEOUT_CONNESSIONE` | 5 s | tempo concesso a ogni tentativo di connessione |
| `ATTESE_RETRY` | 0,5 s · 1 s | attese fra i tentativi: tre tentativi, al massimo 1,5 s di attesa |
| `TIMEOUT_VERIFICA` | 2 s | timeout di `verifica_connessione()`, che fa un tentativo solo |

Si ritenta **solo l'apertura della connessione**, e solo per gli errori che
possono passare da soli: server non raggiungibile o ancora in avvio (2002,
2003, 2006, 2013, 2055) e troppe connessioni (1040). Non si ritentano
credenziali rifiutate, database inesistente, host sconosciuto. Una query non si
riesegue mai.

### Errori

Ogni errore del driver diventa `DatabaseError` (già definita in M1-T4), con un
messaggio in italiano per chi usa l'app.

| Caso | Errore MySQL | Messaggio (inizio) |
|---|---|---|
| server spento o irraggiungibile | 2002, 2003, 2005, 2006, 2013, 2055 | «Impossibile connettersi al database. Verifica che MySQL sia avviato…» |
| credenziali rifiutate | 1045 | «Il database ha rifiutato le credenziali…» |
| database inesistente / non accessibile | 1049 / 1044 | «Il database «nome» non esiste…» / «…non ha accesso al database «nome»» |
| troppe connessioni | 1040 | «Il database ha troppe connessioni aperte…» |
| operazione non permessa | 1142 | «L'utente del database non ha il permesso…» |
| connessione caduta a metà transazione | 2006, 2013, 2055 | «La connessione al database si è interrotta…» |
| tutto il resto | — | messaggio generico che rimanda al log |

Nel log: a livello `ERROR` il numero d'errore, lo SQLSTATE e
`ConfigDatabase.descrizione()` (che maschera la password); a `WARNING` i
tentativi di connessione falliti; a `DEBUG` apertura e chiusura delle
transazioni e il testo originale del driver.

### Database di test e privilegi

`sql/00_test_db.sh` viene eseguito da root all'inizializzazione di MySQL e
prepara `<DB_NAME>_test`:

1. crea il database in `utf8mb4`;
2. vi applica `sql/schema.sql`, lo stesso file del database principale;
3. concede all'utente applicativo `SELECT, INSERT, UPDATE, DELETE` e basta.

Il database principale non viene letto né modificato. Lo script è ripetibile.

**Su un volume che esiste già lo script non parte da solo**: Docker esegue gli
script di inizializzazione solo a volume vuoto. Per avere il database di test
senza ricreare il volume lo si lancia a mano:

```bash
docker compose exec mysql bash /docker-entrypoint-initdb.d/00_test_db.sh
```

## File coinvolti

| File | Azione |
|---|---|
| `beewatch/database.py` | creato |
| `sql/00_test_db.sh` | creato |
| `tests/test_database.py` | creato |
| `tests/conftest.py` | modificato: fixture `stack_mysql`, `config_db_test`, `database_test` |
| `tests/docker_support.py` | modificato: `Stack.avvia()` può avviare solo alcuni servizi |
| `tests/test_docker_guardia.py` | modificato: un test per il nuovo parametro |
| `docs/README.md` | modificato: indice |

Nessuna nuova dipendenza e nessuna nuova variabile d'ambiente.

## Decisioni progettuali

**1. La configurazione si passa al costruttore.** `Database` non chiama
`ottieni()`. I test usano un altro database costruendo un'altra
`ConfigDatabase`, e nessun codice può finire sul database vero perché si è
dimenticato un parametro.

**2. Una connessione per transazione, nessun pool.** La Definition of Done non
chiede un pool, e quello del driver apre subito tutte le connessioni e non ha un
metodo pubblico per chiuderle. Senza pool non c'è stato condiviso: niente da
proteggere fra i thread di Streamlit, niente connessioni rimaste aperte da ore,
niente metodo `chiudi()`. Il costo è una stretta di mano con MySQL per
transazione. Un pool si può aggiungere in seguito senza cambiare chi usa
`transazione()`.

**3. Retry solo sulla connessione e solo sugli errori transitori.** Rieseguire
una scrittura può duplicarla; ritentare una password sbagliata fa solo aspettare.

**4. `verifica_connessione()` non ritenta.** La chiamerà l'interfaccia a ogni
ricaricamento: con i retry e il timeout normale, a database spento la pagina
resterebbe ferma una quindicina di secondi.

**5. Il testo del driver va nel log solo a `DEBUG`.** Può citare un pezzo della
query o un valore (`Duplicate entry '…'`). A livello normale restano numero
d'errore e SQLSTATE; l'eccezione originale resta comunque in `__cause__`.

**6. Privilegi minimi anche sul database di test.** La bozza della task
prevedeva `GRANT ALL` sul database di test: avrebbe contraddetto il Blocco 2
(e fatto fallire il test sui privilegi). Lo schema lo crea root; i test fanno
solo DML e puliscono con `DELETE`, perché `TRUNCATE` richiede il privilegio
`DROP`.

**7. Uno script di shell, non SQL.** Il nome del database arriva da una
variabile d'ambiente, e solo dalla shell si può applicare `schema.sql` a un
database dal nome non fisso senza copiarne il contenuto. Lo script funziona sia
eseguito sia incluso con `source` (l'immagine MySQL fa l'una o l'altra cosa
secondo i permessi del file), e i fine riga LF sono garantiti da
`.gitattributes`.

**8. I test di integrazione usano uno stack Docker temporaneo.** Non il MySQL
di sviluppo: progetto, contenitore e volume propri, creati e distrutti dai test
con le protezioni di `tests/docker_support.py`. Se Docker non è in esecuzione
i test **falliscono** con un messaggio chiaro, non vengono saltati.

## Test

| Gruppo | Dove | Cosa serve |
|---|---|---|
| unitari, driver simulato | `tests/test_database.py` | niente: `pytest -m "not integration"` |
| integrazione, MySQL vero | `tests/test_database.py` (`@pytest.mark.integration`) | Docker in esecuzione: `pytest -m integration tests/test_database.py` |

I test di integrazione scrivono in `stati_usa` del database di test (che nasce
vuoto) con i codici riservati `Z1` e `Z2`, e tolgono solo quelle righe.

### Come si lanciano

Suite rapida, senza i test di integrazione (è quella della CI):

```bash
pytest -m "not integration" --strict-markers
```

Suite di integrazione: richiede Docker in esecuzione, perché crea, usa e
distrugge uno stack MySQL temporaneo. Se Docker non risponde, i test del
database **falliscono** con un messaggio chiaro invece di essere saltati:

```bash
pytest -m integration
```

`pytest` senza marker raccoglie **anche** i test di integrazione: senza Docker
va quindi in errore. Per il ciclo di lavoro quotidiano si usa la suite rapida.

## Definition of Done

| Voce | Prova |
|---|---|
| connessione verificata da un test di integrazione | `test_integrazione_ci_si_collega_al_database_di_test_non_a_quello_principale` |
| rollback automatico in caso di eccezione | `test_se_il_blocco_solleva_rollback_e_la_stessa_eccezione_riemerge`, `test_integrazione_uneccezione_nel_blocco_annulla_tutte_le_scritture` |
| credenziali lette solo da config | `test_la_connessione_usa_la_configurazione_ricevuta`; nessun valore letterale nel modulo |
| errore del driver → `DatabaseError` comprensibile | `test_messaggio_per_un_errore_di_connessione`, `test_integrazione_password_sbagliata_errore_chiaro_subito_e_senza_segreti` |

## Limiti conosciuti

- I test di integrazione non girano ancora su GitHub: la CI esegue solo
  `pytest -m "not integration"`. Il job con MySQL è previsto in M3-T6.
- `DatabaseError` non espone il numero d'errore di MySQL: chi deve distinguere,
  per esempio, una chiave duplicata oggi può solo guardare `__cause__`. Si
  decide in M3-T3, quando i repository ne avranno bisogno.
- `beewatch/healthcheck.py` continua a collegarsi a MySQL per conto proprio: è
  un controllo di salute, non deve ritentare né scrivere nei log dell'app.
- Lo script del database di test presume che l'utente applicativo sia
  `'<DB_USER>'@'%'`, come lo crea l'immagine di MySQL.
- Se il `commit` fallisce perché la connessione cade in quel momento, non si
  può sapere se il server l'aveva già registrato: l'app segnala comunque
  l'operazione come non completata.

## Miglioramenti futuri

- Pool di connessioni, solo se le misure mostreranno che serve.
- Job CI con MySQL per i test `integration` (M3-T6).
- Aggiornare `docs/diagrams/architecture.drawio` con il livello dati.
