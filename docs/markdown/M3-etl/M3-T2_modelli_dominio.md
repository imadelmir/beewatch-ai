# M3 - T2 · Modelli di dominio

> **Milestone** M3 · Accesso ai dati ed ETL
> **Task** M3-T2
> **Stato** completata
> **Commit** `feat(m3): add domain models with validation`
> **Collegati** → [`M2-T4_schema.md`](../M2-dati/M2-T4_schema.md) · [`M3-T1_connessione_database.md`](M3-T1_connessione_database.md)

## Obiettivo

Dare al dominio oggetti che **non possono esistere con valori sbagliati**. Un
apiario senza nome, un'ispezione nel futuro, un raccolto di zero chili vengono
rifiutati nel momento in cui si prova a crearli, con un `ValidationError` che
indica il campo: il form dell'interfaccia (M6) potrà evidenziare la casella
giusta, e repository e servizi non dovranno ricontrollare nulla.

## Descrizione

`beewatch/models.py` contiene cinque dataclass congelate e tre `Enum`.

```python
from datetime import date
from beewatch.models import Ispezione, LivelloRischio

ispezione = Ispezione(
    alveare_id=3,
    data_ispezione=date(2026, 5, 2),
    livello_rischio=LivelloRischio.BASSO,
    peso_kg="38,5",          # diventa Decimal("38.5")
    telaini_covata=6,
)
```

| Entità | Campi (nomi delle colonne dello schema) |
|---|---|
| `Apiario` | `utente_id`, `nome`, `localita`, `latitudine`, `longitudine`, `note`, `attivo`, `id` |
| `Alveare` | `apiario_id`, `codice`, `stato`, `data_installazione`, `anno_regina`, `note`, `attivo`, `id` |
| `Ispezione` | `alveare_id`, `data_ispezione`, `livello_rischio`, `peso_kg`, `telaini_covata`, `telaini_scorte`, `regina_vista`, `sciamatura`, `note`, `id` |
| `Raccolto` | `apiario_id`, `tipo_miele`, `data_raccolto`, `quantita_kg`, `alveare_id`, `note`, `id` |
| `Previsione` | `utente_id`, `versione_modello`, `codice_stato_riferimento`, `anno_riferimento`, `stima_kg`, `limite_inferiore_kg`, `limite_superiore_kg`, `alveare_id`, `id` |

`id` vale `None` finché l'oggetto non è salvato: lo assegna il database.

| Enum | Valori (= colonna `codice` della tabella di riferimento) |
|---|---|
| `StatoAlveare` | `in_salute`, `in_osservazione`, `debole`, `sciamato`, `morto` |
| `LivelloRischio` | `nessuno`, `basso`, `medio`, `alto` |
| `TipoMiele` | `acacia`, `millefiori`, `castagno`, `tiglio`, `melata`, `girasole`, `eucalipto`, `non_definito` |

### Regole verificate alla creazione

| Regola | Da dove viene |
|---|---|
| testi obbligatori non vuoti, lunghezze massime (`nome` 120, `localita` 160, `codice` 20, `versione_modello` 40) | NOT NULL e VARCHAR dello schema |
| note entro i 65 535 byte di una colonna TEXT, rifiutate e mai troncate | TEXT dello schema; M2-T4 («mai troncata») |
| latitudine −90…90, longitudine −180…180, al massimo 6 decimali | CHECK e DECIMAL(9,6) |
| `peso_kg` ≥ 0, `quantita_kg` > 0, entrambi ≤ 9999,99 con al massimo 2 decimali | CHECK e DECIMAL(6,2) |
| `telaini_covata`, `telaini_scorte` interi fra 0 e 30 | CHECK e TINYINT UNSIGNED |
| `anno_regina` fra 2000 e l'anno corrente | CHECK (2000–2100) + backlog: «non futuro» |
| `data_ispezione` non nel futuro | backlog M3-T2 |
| `anno_riferimento` fra 1990 e 2100, `codice_stato_riferimento` di due lettere maiuscole | CHECK e CHAR(2) |
| `limite_inferiore_kg ≤ stima_kg ≤ limite_superiore_kg` | CHECK `chk_previsioni_intervallo` (M2-T3: mai un numero secco) |
| stato, rischio e tipo di miele solo fra i valori dell'Enum | tabelle di riferimento del seed |
| riferimenti (`*_id`) interi positivi; booleani veri booleani; date `date` (non `datetime`) | tipi dello schema |

I numeri diventano `Decimal` (decisione D5 di M2-T4: mai `FLOAT`); un `float`
passa dalla sua forma testuale, così `0.1` resta `0.1`. Si accetta anche la
virgola come separatore decimale. Le cifre decimali in più rispetto alla colonna
vengono **rifiutate**: MySQL le arrotonderebbe senza dirlo.

## File coinvolti

| File | Azione |
|---|---|
| `beewatch/models.py` | creato |
| `tests/test_models.py` | creato |
| `sql/00_test_db.sh` | modificato: applica anche `seed.sql` al database di test |
| `tests/test_database.py` | modificato: il database di test ora ha il seed |
| `docs/markdown/M3-etl/M3-T1_connessione_database.md` | modificato: idem |
| `docs/README.md` | modificato: indice |

## Decisioni progettuali

**1. La validazione sta nel costruttore.** `__post_init__` controlla e
normalizza; un oggetto che esiste è valido. L'alternativa (un metodo
`valida()` da ricordarsi di chiamare) lascia passare oggetti a metà.

**2. Le regole vengono dallo schema, non da un'invenzione.** Ogni limite ha la
sua origine nella tabella sopra. Il database resta l'ultima difesa; il modello è
la prima, e l'unica che sa dire *quale* campo è sbagliato.

**3. Enum con valore uguale al codice.** `StrEnum`: `StatoAlveare.SCIAMATO ==
"sciamato"`. Il codice non contiene stringhe magiche, e un repository può
costruire l'Enum dal codice letto dal database. La conversione codice ↔ `id`
numerico è compito dei repository (M3-T3). Un test di integrazione verifica che
gli Enum coincidano con il seed.

**4. Il database di test riceve anche il seed.** Senza le tabelle di
riferimento non si può salvare un alveare (serve `stati_alveare`) né caricare
l'ETL (serve `stati_usa`). `sql/00_test_db.sh` applica ora `seed.sql` dopo
`schema.sql`, senza copiarne il contenuto.

**5. Note e coordinate fuori dalla `repr`.** Sono dati personali (M2-T4):
un oggetto stampato per sbaglio in un log non li deve portare con sé.

**6. Niente `Utente` e niente `Trattamento`.** `Trattamento` non esiste nello
schema approvato. Un modello `Utente` non serve finché non si decide il login
(**DA-02**, aperta): repository e servizi ricevono solo `utente_id`, che è ciò
che serve all'isolamento fra utenti in entrambe le opzioni di DA-02.

## Definition of Done

| Voce | Prova |
|---|---|
| ogni entità rifiuta valori non validi con `ValidationError` | `test_un_valore_non_valido_e_rifiutato_indicando_il_campo` (57 casi), `test_la_stima_deve_stare_dentro_il_suo_intervallo` |
| test unitari su tutti gli invarianti | `tests/test_models.py`; copertura di `models.py` 100% righe e rami |
| nessuna stringa magica: si usano gli enum | `StatoAlveare`, `LivelloRischio`, `TipoMiele`; `test_integrazione_i_codici_degli_enum_sono_quelli_del_seed` |

## Miglioramenti futuri

- Un modello `Utente` se DA-02 sceglierà il login.
- Altre regole di dominio (es. data del raccolto non futura) solo se richieste:
  oggi né lo schema né il backlog le prevedono.
