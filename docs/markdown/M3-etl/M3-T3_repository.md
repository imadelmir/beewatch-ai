# M3 - T3 · Repository

> **Milestone** M3 · Accesso ai dati ed ETL
> **Task** M3-T3
> **Stato** completata
> **Commit** `feat(m3): add repositories with parameterized queries`
> **Collegati** → [`M2-T4_schema.md`](../M2-dati/M2-T4_schema.md) (query Q1–Q11) · [`M3-T1_connessione_database.md`](M3-T1_connessione_database.md) · [`M3-T2_modelli_dominio.md`](M3-T2_modelli_dominio.md)

## Obiettivo

Isolare l'accesso ai dati: tutto l'SQL del progetto sta nei repository, con
metodi dal nome di dominio. Servizi, ETL e training chiedono
`trova_alveari_attivi(utente_id)` e ricevono oggetti del dominio; non scrivono
query e non conoscono il driver.

## Descrizione

Ogni repository riceve un `Database` (M3-T1) e ogni metodo apre la propria
transazione.

```python
db = Database(ottieni().database)
alveari = AlveariRepository(db)

nuovo = alveari.crea(utente_id, Alveare(apiario_id=1, codice="A5", stato=StatoAlveare.IN_SALUTE))
for alveare in alveari.trova_alveari_attivi(utente_id):
    ...
```

| Repository | File | Metodi |
|---|---|---|
| `ApiariRepository` | `repositories.py` | `crea`, `trova`, `elenca`, `aggiorna`, `disattiva` |
| `AlveariRepository` | `repositories.py` | `crea`, `trova`, `trova_alveari_attivi`, `elenco_con_ultima_ispezione` (Q2), `trascurati` (Q3), `aggiorna`, `disattiva` |
| `IspezioniRepository` | `repositories.py` | `crea`, `ispezioni_per_alveare`, `andamento_peso` (Q4), `a_rischio_alto` (Q6), `elimina` |
| `RaccoltiRepository` | `repositories.py` | `crea`, `per_apiario`, `produzione_per_stagione` (Q5), `elimina` |
| `DashboardRepository` | `repositories_riferimento.py` | `riepilogo` (Q1) |
| `UtentiRepository` | `repositories_riferimento.py` | `elimina` (Q11, cancellazione GDPR) |
| `ProduzioneUsdaRepository` | `repositories_riferimento.py` | `serie_storica_stato` (Q7), `dati_addestramento` (Q8), `codici_stati` |
| `PrevisioniRepository` | `repositories_riferimento.py` | `salva_previsione`, `ultime_previsioni` (Q9) |
| `ConversazioniRepository` | `repositories_riferimento.py` | `messaggi` (Q10) |

Le entità tornano come oggetti di `models.py` (validati alla costruzione); le
query per le schermate (Q1–Q10) come dizionari, una chiave per colonna.

### Regole applicate in tutti i metodi

| Regola | Come |
|---|---|
| Query parametrizzate | sempre `%s`; nessun valore concatenato. Le uniche parti composte sono costanti del modulo (elenco di colonne, un filtro fisso) |
| Isolamento fra utenti (D2) | ogni lettura e scrittura di dati operativi è filtrata per `utente_id`. Un id inesistente e un id di un altro utente danno lo stesso `ValidationError` («… non trovato»): non si scopre che esiste |
| Disattivare, non cancellare (D7) | apiari e alveari hanno `disattiva`; ispezioni e raccolti, che non hanno `attivo`, hanno `elimina` |
| Coerenza raccolto/apiario (D8 di M2-T5) | se un raccolto indica l'alveare, l'alveare deve essere di quell'apiario: controllato prima dell'`INSERT`, nella stessa transazione |
| Unicità con messaggio chiaro | nome dell'apiario unico per utente, codice dell'alveare unico nell'apiario: controllati prima della scrittura, così l'utente riceve `ValidationError(campo=...)` e non un errore del database |
| Codici ↔ id | lo stato, il rischio e il tipo di miele arrivano come Enum; l'`id` si ricava con una sottoquery sulla tabella di riferimento |

### Scostamenti dalle query di M2-T4

- **Q4** in M2-T4 filtra solo per alveare: qui c'è anche il filtro per utente
  (D2 lo richiede, Q4 lo sottintendeva).
- **Q2** restituisce anche `id` e `attivo`, perché la pagina possa aprire la
  scheda e distinguere gli alveari dismessi.
- **Q3, Q6** hanno la finestra in giorni come parametro (predefiniti 30 e 60,
  i valori di M2-T4).
- **Q6** si chiama «rischio alto» ma, come approvata, prende `gravita >= 3`,
  cioè *medio* e *alto*. È mantenuta così; il nome del metodo
  (`a_rischio_alto`) segue la query.
- Gli ordinamenti hanno un criterio secondario (`id`) per essere stabili a
  parità di data.

## File coinvolti

| File | Azione |
|---|---|
| `beewatch/repositories.py` | creato (395 righe) |
| `beewatch/repositories_riferimento.py` | creato (122 righe) |
| `tests/test_repositories.py` | creato |
| `docs/README.md` | modificato: indice |

## Decisioni progettuali

**1. Due file invece di uno.** Il backlog fissa 400 righe per file e dice di
dividere se si superano: un file unico ne avrebbe avute circa 500.
`repositories.py` gestisce i dati dell'apicoltore; `repositories_riferimento.py`
riepiloghi, riferimento USDA, previsioni, conversazioni e cancellazione
dell'utente. Il secondo riusa la base e i controlli del primo. Un test verifica
che nessuno dei due superi il limite.

**2. Un metodo, una transazione.** Il controllo di appartenenza e la scrittura
che lo segue stanno insieme: non c'è un momento in cui il controllo è vero e la
scrittura parte su dati cambiati nel frattempo. Operazioni composte da più metodi
(se serviranno) andranno nei servizi.

**3. Controlli prima della scrittura, non interpretazione degli errori.** Per
nome e codice duplicati si controlla con una `SELECT` invece di leggere il numero
d'errore di MySQL: `DatabaseError` resta come è (M3-T1) e il messaggio parla
all'utente. Il vincolo `UNIQUE` dello schema resta la garanzia finale.

**4. Nessun `crea` per utenti, conversazioni e modelli.** Il login è una
decisione aperta (**DA-02**); conversazioni e salvataggio dei riepiloghi AI
dipendono da **DA-03** (M5); i modelli li registrerà il training (M4-T7). Per
questo `salva_report`, citato nella descrizione del backlog, **non esiste
ancora**: dove salvarlo è proprio DA-03.

## Definition of Done

| Voce | Prova |
|---|---|
| nessun SQL fuori dai repository | `test_nessun_sql_fuori_dai_repository` (analizza le stringhe di ogni modulo di `beewatch/`, escluse le docstring; unica eccezione dichiarata il `SELECT 1` di `database.py` e `healthcheck.py`) |
| query parametrizzate (`%s`) | revisione del codice; `test_il_testo_dellutente_resta_testo_anche_se_sembra_sql` |
| test di integrazione su CRUD e query principali | `tests/test_repositories.py`: 26 test su MySQL vero (CRUD di apiari, alveari, ispezioni, raccolti; Q1–Q11; isolamento fra utenti; D8) |
| file sotto le 400 righe | `test_i_file_dei_repository_restano_sotto_le_400_righe` |

I test di integrazione creano utenti propri e li cancellano con `elimina` (Q11):
le cascate portano via tutto ciò che hanno scritto.

## Limiti conosciuti

- La suite rapida (senza MySQL) copre i repository solo in parte (35% e 50%):
  le query si provano sul database vero. Con i test di integrazione la
  copertura è 100% righe e rami su entrambi i file, anche nel job CI
  `integrazione` (M3-T6).
- Le date di Q1, Q3 e Q6 vengono da `CURDATE()` di MySQL, quelle dei modelli da
  `date.today()` del computer: a cavallo della mezzanotte, con fusi diversi,
  possono differire di un giorno.

## Miglioramenti futuri

- `salva_report` quando DA-03 avrà deciso dove si salvano i riepiloghi AI.
- Creazione di utenti e conversazioni con M5/M6, se DA-02 lo prevede.
