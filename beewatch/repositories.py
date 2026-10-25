"""Repository: l'unico posto del progetto che contiene SQL.

Ogni classe riceve un `Database` e offre metodi dal nome di dominio (`trova_alveari_attivi`,
`ispezioni_per_alveare`, `serie_storica_stato`...). Chi li usa (servizi, ETL, training) non scrive
query e non vede il driver.

Regole che valgono per tutte le query:

- **parametri sempre con `%s`**, mai testo concatenato: l'iniezione SQL non ha un punto d'ingresso;
- **ogni dato operativo è filtrato per `utente_id`** (decisione D2 di M2-T4): un utente non può
  leggere né modificare ciò che non è suo. Un id che non esiste e un id di un altro utente danno
  lo stesso errore, così non si scopre nemmeno che esiste;
- **apiari e alveari si disattivano, non si cancellano** (D7);
- **un metodo, una transazione**: i controlli e la scrittura che li segue stanno nella stessa
  transazione.

Le query Q1–Q11 sono quelle progettate e motivate in `docs/markdown/M2-dati/M2-T4_schema.md`. Il
passaggio fra il `codice` dei valori fissi (gli Enum di `models.py`) e l'`id` numerico del database
avviene qui, con una sottoquery sulla tabella di riferimento. Le entità tornano come oggetti di
`models.py`; i riepiloghi per le schermate come dizionari, una chiave per colonna.

Questo file ha i dati dell'apicoltore (apiari, alveari, ispezioni, raccolti); il resto è in
`repositories_riferimento.py`: il backlog fissa 400 righe per file.
"""

from __future__ import annotations

from typing import Any

from beewatch.database import Database
from beewatch.exceptions import ValidationError
from beewatch.models import Alveare, Apiario, Ispezione, Raccolto

Riga = dict[str, Any]


class _Repository:
    def __init__(self, database: Database) -> None:
        self._db = database

    def _righe(self, sql: str, parametri: tuple[Any, ...] = ()) -> list[Riga]:
        with self._db.transazione() as cursore:
            cursore.execute(sql, parametri)
            return cursore.fetchall()


def _non_trovato(cosa: str, campo: str, *, femminile: bool = False) -> ValidationError:
    return ValidationError(f"{cosa} non {'trovata' if femminile else 'trovato'}.", campo=campo)


def _richiedi(cursore: Any, sql: str, parametri: tuple[Any, ...], errore: ValidationError) -> None:
    """Solleva `errore` se la query non restituisce righe (controllo di appartenenza)."""
    cursore.execute(sql, parametri)
    if not cursore.fetchall():
        raise errore


def _vieta(cursore: Any, sql: str, parametri: tuple[Any, ...], errore: ValidationError) -> None:
    """Solleva `errore` se la query restituisce righe (controllo di unicità)."""
    cursore.execute(sql, parametri)
    if cursore.fetchall():
        raise errore


def _con_id(entita: Any) -> int:
    if entita.id is None:
        raise ValidationError("L'elemento da aggiornare non è ancora stato salvato.", campo="id")
    return entita.id


# Controlli di appartenenza riusati da più repository.
_ISPEZIONE_DELL_UTENTE = (
    "SELECT 1 FROM ispezioni i JOIN alveari al ON al.id = i.alveare_id "
    "JOIN apiari ap ON ap.id = al.apiario_id WHERE i.id = %s AND ap.utente_id = %s"
)
_APIARIO_DELL_UTENTE = "SELECT 1 FROM apiari WHERE id = %s AND utente_id = %s"
_ALVEARE_DELL_UTENTE = (
    "SELECT 1 FROM alveari al JOIN apiari ap ON ap.id = al.apiario_id "
    "WHERE al.id = %s AND ap.utente_id = %s"
)


# --------------------------------------------------------------------------- #
# Apiari
# --------------------------------------------------------------------------- #

_COLONNE_APIARIO = "id, utente_id, nome, localita, latitudine, longitudine, note, attivo"


def _apiario(riga: Riga) -> Apiario:
    return Apiario(**{**riga, "attivo": bool(riga["attivo"])})


class ApiariRepository(_Repository):
    def crea(self, apiario: Apiario) -> Apiario:
        with self._db.transazione() as cursore:
            self._nome_libero(cursore, apiario)
            cursore.execute(
                "INSERT INTO apiari (utente_id, nome, localita, latitudine, longitudine, note, "
                "attivo) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (apiario.utente_id, apiario.nome, apiario.localita, apiario.latitudine,
                 apiario.longitudine, apiario.note, apiario.attivo),
            )  # fmt: skip
            nuovo_id = cursore.lastrowid
        return Apiario(**{**apiario.__dict__, "id": nuovo_id})

    def trova(self, utente_id: int, apiario_id: int) -> Apiario | None:
        righe = self._righe(
            f"SELECT {_COLONNE_APIARIO} FROM apiari WHERE id = %s AND utente_id = %s",
            (apiario_id, utente_id),
        )
        return _apiario(righe[0]) if righe else None

    def elenca(self, utente_id: int, *, anche_disattivi: bool = False) -> list[Apiario]:
        filtro = "" if anche_disattivi else " AND attivo"
        righe = self._righe(
            f"SELECT {_COLONNE_APIARIO} FROM apiari WHERE utente_id = %s{filtro} ORDER BY nome",
            (utente_id,),
        )
        return [_apiario(r) for r in righe]

    def aggiorna(self, apiario: Apiario) -> None:
        apiario_id = _con_id(apiario)
        with self._db.transazione() as cursore:
            _richiedi(cursore, _APIARIO_DELL_UTENTE, (apiario_id, apiario.utente_id),
                      _non_trovato("Apiario", "id"))  # fmt: skip
            self._nome_libero(cursore, apiario)
            cursore.execute(
                "UPDATE apiari SET nome = %s, localita = %s, latitudine = %s, longitudine = %s, "
                "note = %s, attivo = %s WHERE id = %s AND utente_id = %s",
                (apiario.nome, apiario.localita, apiario.latitudine, apiario.longitudine,
                 apiario.note, apiario.attivo, apiario_id, apiario.utente_id),
            )  # fmt: skip

    def disattiva(self, utente_id: int, apiario_id: int) -> None:
        with self._db.transazione() as cursore:
            _richiedi(cursore, _APIARIO_DELL_UTENTE, (apiario_id, utente_id),
                      _non_trovato("Apiario", "id"))  # fmt: skip
            cursore.execute(
                "UPDATE apiari SET attivo = FALSE WHERE id = %s AND utente_id = %s",
                (apiario_id, utente_id),
            )

    @staticmethod
    def _nome_libero(cursore: Any, apiario: Apiario) -> None:
        _vieta(
            cursore,
            "SELECT 1 FROM apiari WHERE utente_id = %s AND nome = %s AND id <> %s",
            (apiario.utente_id, apiario.nome, apiario.id or 0),
            ValidationError("Hai già un apiario con questo nome.", campo="nome"),
        )


# --------------------------------------------------------------------------- #
# Alveari
# --------------------------------------------------------------------------- #

_SELECT_ALVEARE = (
    "SELECT al.id, al.apiario_id, al.codice, s.codice AS stato, al.data_installazione, "
    "al.anno_regina, al.note, al.attivo "
    "FROM alveari al JOIN apiari ap ON ap.id = al.apiario_id "
    "JOIN stati_alveare s ON s.id = al.stato_alveare_id "
)


def _alveare(riga: Riga) -> Alveare:
    return Alveare(**{**riga, "attivo": bool(riga["attivo"])})


class AlveariRepository(_Repository):
    def crea(self, utente_id: int, alveare: Alveare) -> Alveare:
        with self._db.transazione() as cursore:
            self._controlla(cursore, utente_id, alveare)
            cursore.execute(
                "INSERT INTO alveari (apiario_id, stato_alveare_id, codice, data_installazione, "
                "anno_regina, note, attivo) VALUES "
                "(%s, (SELECT id FROM stati_alveare WHERE codice = %s), %s, %s, %s, %s, %s)",
                (alveare.apiario_id, alveare.stato.value, alveare.codice,
                 alveare.data_installazione, alveare.anno_regina, alveare.note, alveare.attivo),
            )  # fmt: skip
            nuovo_id = cursore.lastrowid
        return Alveare(**{**alveare.__dict__, "id": nuovo_id})

    def trova(self, utente_id: int, alveare_id: int) -> Alveare | None:
        righe = self._righe(
            _SELECT_ALVEARE + "WHERE al.id = %s AND ap.utente_id = %s", (alveare_id, utente_id)
        )
        return _alveare(righe[0]) if righe else None

    def trova_alveari_attivi(self, utente_id: int) -> list[Alveare]:
        """Gli alveari attivi negli apiari attivi, per apiario e codice."""
        righe = self._righe(
            _SELECT_ALVEARE + "WHERE ap.utente_id = %s AND al.attivo AND ap.attivo "
            "ORDER BY ap.nome, al.codice",
            (utente_id,),
        )
        return [_alveare(r) for r in righe]

    def elenco_con_ultima_ispezione(self, utente_id: int) -> list[Riga]:
        """Q2 · pagina Alveari: ogni alveare con la data e il peso dell'ultima ispezione."""
        return self._righe(
            "SELECT al.id, al.codice, al.attivo, ap.nome AS apiario, s.etichetta AS stato, "
            "s.colore, ult.data_ispezione AS ultima_ispezione, ult.peso_kg "
            "FROM alveari al JOIN apiari ap ON ap.id = al.apiario_id "
            "JOIN stati_alveare s ON s.id = al.stato_alveare_id "
            "LEFT JOIN LATERAL (SELECT i.data_ispezione, i.peso_kg FROM ispezioni i "
            "  WHERE i.alveare_id = al.id ORDER BY i.data_ispezione DESC LIMIT 1) AS ult ON TRUE "
            "WHERE ap.utente_id = %s ORDER BY ap.nome, al.codice",
            (utente_id,),
        )

    def trascurati(self, utente_id: int, giorni: int = 30) -> list[Riga]:
        """Q3 · alveari attivi (in apiari attivi) mai ispezionati o non da oltre `giorni` giorni."""
        return self._righe(
            "SELECT al.id, al.codice, MAX(i.data_ispezione) AS ultima "
            "FROM alveari al JOIN apiari ap ON ap.id = al.apiario_id "
            "LEFT JOIN ispezioni i ON i.alveare_id = al.id "
            "WHERE ap.utente_id = %s AND al.attivo AND ap.attivo GROUP BY al.id, al.codice "
            "HAVING ultima IS NULL OR ultima < CURDATE() - INTERVAL %s DAY ORDER BY al.codice",
            (utente_id, giorni),
        )

    def aggiorna(self, utente_id: int, alveare: Alveare) -> None:
        alveare_id = _con_id(alveare)
        with self._db.transazione() as cursore:
            _richiedi(cursore, _ALVEARE_DELL_UTENTE, (alveare_id, utente_id),
                      _non_trovato("Alveare", "id"))  # fmt: skip
            self._controlla(cursore, utente_id, alveare)
            cursore.execute(
                "UPDATE alveari SET apiario_id = %s, "
                "stato_alveare_id = (SELECT id FROM stati_alveare WHERE codice = %s), "
                "codice = %s, data_installazione = %s, anno_regina = %s, note = %s, attivo = %s "
                "WHERE id = %s",
                (alveare.apiario_id, alveare.stato.value, alveare.codice,
                 alveare.data_installazione, alveare.anno_regina, alveare.note, alveare.attivo,
                 alveare_id),
            )  # fmt: skip

    def disattiva(self, utente_id: int, alveare_id: int) -> None:
        with self._db.transazione() as cursore:
            _richiedi(cursore, _ALVEARE_DELL_UTENTE, (alveare_id, utente_id),
                      _non_trovato("Alveare", "id"))  # fmt: skip
            cursore.execute("UPDATE alveari SET attivo = FALSE WHERE id = %s", (alveare_id,))

    @staticmethod
    def _controlla(cursore: Any, utente_id: int, alveare: Alveare) -> None:
        """L'apiario è dell'utente e il codice è libero dentro l'apiario."""
        _richiedi(cursore, _APIARIO_DELL_UTENTE, (alveare.apiario_id, utente_id),
                  _non_trovato("Apiario", "apiario_id"))  # fmt: skip
        _vieta(
            cursore,
            "SELECT 1 FROM alveari WHERE apiario_id = %s AND codice = %s AND id <> %s",
            (alveare.apiario_id, alveare.codice, alveare.id or 0),
            ValidationError("Nell'apiario c'è già un alveare con questo codice.", campo="codice"),
        )


# --------------------------------------------------------------------------- #
# Ispezioni
# --------------------------------------------------------------------------- #


def _ispezione(riga: Riga) -> Ispezione:
    booleani = {"regina_vista": bool(riga["regina_vista"]), "sciamatura": bool(riga["sciamatura"])}
    return Ispezione(**{**riga, **booleani})


_SELECT_ISPEZIONE = (
    "SELECT i.id, i.alveare_id, i.data_ispezione, lr.codice AS livello_rischio, "
    "i.peso_kg, i.telaini_covata, i.telaini_scorte, i.regina_vista, i.sciamatura, i.note "
    "FROM ispezioni i JOIN alveari al ON al.id = i.alveare_id "
    "JOIN apiari ap ON ap.id = al.apiario_id "
    "JOIN livelli_rischio lr ON lr.id = i.livello_rischio_id "
)


class IspezioniRepository(_Repository):
    def crea(self, utente_id: int, ispezione: Ispezione) -> Ispezione:
        with self._db.transazione() as cursore:
            _richiedi(cursore, _ALVEARE_DELL_UTENTE, (ispezione.alveare_id, utente_id),
                      _non_trovato("Alveare", "alveare_id"))  # fmt: skip
            cursore.execute(
                "INSERT INTO ispezioni (alveare_id, livello_rischio_id, data_ispezione, peso_kg, "
                "telaini_covata, telaini_scorte, regina_vista, sciamatura, note) VALUES "
                "(%s, (SELECT id FROM livelli_rischio WHERE codice = %s), "
                "%s, %s, %s, %s, %s, %s, %s)",
                (ispezione.alveare_id, ispezione.livello_rischio.value, ispezione.data_ispezione,
                 ispezione.peso_kg, ispezione.telaini_covata, ispezione.telaini_scorte,
                 ispezione.regina_vista, ispezione.sciamatura, ispezione.note),
            )  # fmt: skip
            nuovo_id = cursore.lastrowid
        return Ispezione(**{**ispezione.__dict__, "id": nuovo_id})

    def trova(self, utente_id: int, ispezione_id: int) -> Ispezione | None:
        """Un'ispezione dell'utente (un id altrui e uno inesistente danno lo stesso None)."""
        righe = self._righe(_SELECT_ISPEZIONE + "WHERE i.id = %s AND ap.utente_id = %s",
                            (ispezione_id, utente_id))  # fmt: skip
        return _ispezione(righe[0]) if righe else None

    def ispezioni_per_alveare(self, utente_id: int, alveare_id: int) -> list[Ispezione]:
        """Le ispezioni di un alveare, dalla più recente."""
        righe = self._righe(
            _SELECT_ISPEZIONE + "WHERE i.alveare_id = %s AND ap.utente_id = %s "
            "ORDER BY i.data_ispezione DESC, i.id DESC",
            (alveare_id, utente_id),
        )
        return [_ispezione(r) for r in righe]

    def andamento_peso(self, utente_id: int, alveare_id: int) -> list[Riga]:
        """Q4 · grafico della scheda alveare (con il filtro per utente che Q4 sottintende)."""
        return self._righe(
            "SELECT i.data_ispezione, i.peso_kg, i.telaini_covata, i.telaini_scorte "
            "FROM ispezioni i JOIN alveari al ON al.id = i.alveare_id "
            "JOIN apiari ap ON ap.id = al.apiario_id "
            "WHERE i.alveare_id = %s AND ap.utente_id = %s AND i.peso_kg IS NOT NULL "
            "ORDER BY i.data_ispezione",
            (alveare_id, utente_id),
        )

    def a_rischio_alto(self, utente_id: int, giorni: int = 60) -> list[Riga]:
        """Q6 · ispezioni di gravità almeno «medio» (3) negli ultimi `giorni` giorni."""
        return self._righe(
            "SELECT i.id, al.codice, i.data_ispezione, lr.etichetta AS rischio, i.note "
            "FROM ispezioni i JOIN alveari al ON al.id = i.alveare_id "
            "JOIN apiari ap ON ap.id = al.apiario_id "
            "JOIN livelli_rischio lr ON lr.id = i.livello_rischio_id "
            "WHERE ap.utente_id = %s AND lr.gravita >= 3 "
            "AND i.data_ispezione >= CURDATE() - INTERVAL %s DAY ORDER BY i.data_ispezione DESC",
            (utente_id, giorni),
        )

    def elimina(self, utente_id: int, ispezione_id: int) -> None:
        with self._db.transazione() as cursore:
            _richiedi(cursore, _ISPEZIONE_DELL_UTENTE, (ispezione_id, utente_id),
                      _non_trovato("Ispezione", "id", femminile=True))  # fmt: skip
            cursore.execute("DELETE FROM ispezioni WHERE id = %s", (ispezione_id,))


# --------------------------------------------------------------------------- #
# Raccolti
# --------------------------------------------------------------------------- #


class RaccoltiRepository(_Repository):
    def crea(self, utente_id: int, raccolto: Raccolto) -> Raccolto:
        with self._db.transazione() as cursore:
            _richiedi(cursore, _APIARIO_DELL_UTENTE, (raccolto.apiario_id, utente_id),
                      _non_trovato("Apiario", "apiario_id"))  # fmt: skip
            if raccolto.alveare_id is not None:
                # D8 di M2-T5: un CHECK non può leggere altre tabelle, lo si verifica qui.
                _richiedi(
                    cursore,
                    "SELECT 1 FROM alveari WHERE id = %s AND apiario_id = %s",
                    (raccolto.alveare_id, raccolto.apiario_id),
                    ValidationError("L'alveare non è in questo apiario.", campo="alveare_id"),
                )
            cursore.execute(
                "INSERT INTO raccolti (apiario_id, alveare_id, tipo_miele_id, data_raccolto, "
                "quantita_kg, note) VALUES "
                "(%s, %s, (SELECT id FROM tipi_miele WHERE codice = %s), %s, %s, %s)",
                (raccolto.apiario_id, raccolto.alveare_id, raccolto.tipo_miele.value,
                 raccolto.data_raccolto, raccolto.quantita_kg, raccolto.note),
            )  # fmt: skip
            nuovo_id = cursore.lastrowid
        return Raccolto(**{**raccolto.__dict__, "id": nuovo_id})

    def per_apiario(self, utente_id: int, apiario_id: int) -> list[Raccolto]:
        righe = self._righe(
            "SELECT r.id, r.apiario_id, r.alveare_id, tm.codice AS tipo_miele, r.data_raccolto, "
            "r.quantita_kg, r.note FROM raccolti r JOIN apiari ap ON ap.id = r.apiario_id "
            "JOIN tipi_miele tm ON tm.id = r.tipo_miele_id "
            "WHERE r.apiario_id = %s AND ap.utente_id = %s "
            "ORDER BY r.data_raccolto DESC, r.id DESC",
            (apiario_id, utente_id),
        )
        return [Raccolto(**r) for r in righe]

    def produzione_per_stagione(self, utente_id: int) -> list[Riga]:
        """Q5 · pagina Report: chili raccolti per anno e tipo di miele."""
        return self._righe(
            "SELECT YEAR(r.data_raccolto) AS anno, tm.etichetta AS tipo, "
            "SUM(r.quantita_kg) AS totale_kg FROM raccolti r "
            "JOIN apiari ap ON ap.id = r.apiario_id JOIN tipi_miele tm ON tm.id = r.tipo_miele_id "
            "WHERE ap.utente_id = %s GROUP BY anno, tm.etichetta ORDER BY anno DESC, tipo",
            (utente_id,),
        )

    def elimina(self, utente_id: int, raccolto_id: int) -> None:
        with self._db.transazione() as cursore:
            _richiedi(
                cursore,
                "SELECT 1 FROM raccolti r JOIN apiari ap ON ap.id = r.apiario_id "
                "WHERE r.id = %s AND ap.utente_id = %s",
                (raccolto_id, utente_id),
                _non_trovato("Raccolto", "id"),
            )
            cursore.execute("DELETE FROM raccolti WHERE id = %s", (raccolto_id,))
