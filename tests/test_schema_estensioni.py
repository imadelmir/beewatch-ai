"""Test delle estensioni dello schema (`sql/schema_02_*.sql`), M4-T8.

Le estensioni sono modifiche arrivate dopo `schema.sql`. Devono essere ripetibili, applicarsi
a un database che esiste già senza perdere dati (è il caso di chi ha un volume vecchio) e
girare da sole alla creazione del database, sia quello principale sia quello dei test.

Tutti i test girano sullo stack Docker temporaneo, mai sul database di sviluppo.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from docker_support import DB_NAME, Stack

NOME_DB_TEST = f"{DB_NAME}_test"
RADICE = Path(__file__).resolve().parents[1]
ESTENSIONE = "schema_02_previsioni_feature_json.sql"

pytestmark = pytest.mark.integration


def come_root(stack: Stack, sql: str, database: str = NOME_DB_TEST) -> str:
    """Esegue `sql` come root dentro il contenitore MySQL (niente doppi apici nello SQL)."""
    comando = (
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B --raw '
        f'--database={database} -e "{sql}"'
    )
    esito = stack.nel_container("mysql", "sh", "-c", comando)
    assert esito.returncode == 0, stack.redigi(esito.stderr)
    return esito.stdout.strip()


def applica_estensione(stack: Stack, database: str = NOME_DB_TEST, file: str = ESTENSIONE) -> None:
    """Applica il file dell'estensione come l'operatore (il file è montato nel contenitore)."""
    comando = (
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot '
        f"--database={database} < /docker-entrypoint-initdb.d/{file}"
    )
    esito = stack.nel_container("mysql", "sh", "-c", comando)
    assert esito.returncode == 0, stack.redigi(esito.stderr + esito.stdout)


def colonna(stack: Stack, database: str) -> str:
    return come_root(
        stack,
        "SELECT CONCAT(column_name, ' ', column_type, ' ', is_nullable) "
        "FROM information_schema.columns "
        f"WHERE table_schema = '{database}' AND table_name = 'previsioni' "
        "AND column_name = 'feature_json'",
        database,
    )


@pytest.fixture
def stack(stack_mysql: Stack) -> Iterator[Stack]:
    """Lo stack; a fine test la colonna c'è di nuovo, qualunque cosa abbia fatto il test."""
    yield stack_mysql
    applica_estensione(stack_mysql)
    come_root(stack_mysql, "DELETE FROM previsioni; DELETE FROM modelli")


def test_la_colonna_c_e_nel_database_principale_e_in_quello_di_test(stack: Stack) -> None:
    for database in (DB_NAME, NOME_DB_TEST):
        assert colonna(stack, database) == "feature_json json YES", database


def test_lestensione_si_puo_riapplicare_senza_errori_e_senza_cambiare_nulla(stack: Stack) -> None:
    prima = come_root(stack, "SHOW CREATE TABLE previsioni")

    applica_estensione(stack)
    applica_estensione(stack)

    assert come_root(stack, "SHOW CREATE TABLE previsioni") == prima
    assert colonna(stack, NOME_DB_TEST) == "feature_json json YES"


def test_su_un_database_senza_la_colonna_lestensione_la_aggiunge_e_non_perde_dati(
    stack: Stack,
) -> None:
    come_root(
        stack,
        "DELETE FROM previsioni; DELETE FROM modelli; "
        "INSERT INTO modelli (versione, algoritmo, addestrato_il, righe_addestramento, "
        "variabili_usate, mae_kg, rmse_kg, r2, percorso_file) "
        "VALUES ('v-vecchio', 'x', NOW(), 1, '[]', 1, 1, 0.5, 'm'); "
        "INSERT INTO previsioni (utente_id, versione_modello, codice_stato_riferimento, "
        "anno_riferimento, stima_kg, limite_inferiore_kg, limite_superiore_kg, feature_json) "
        "VALUES (1, 'v-vecchio', 'CA', 2013, 30, 24, 36, '{}'); "
        "ALTER TABLE previsioni DROP COLUMN feature_json",  # il volume com'era prima di M4-T8
    )
    assert colonna(stack, NOME_DB_TEST) == ""  # davvero senza la colonna

    applica_estensione(stack)

    assert colonna(stack, NOME_DB_TEST) == "feature_json json YES"
    righe = come_root(
        stack, "SELECT versione_modello, stima_kg, feature_json IS NULL FROM previsioni"
    )
    assert righe.split() == ["v-vecchio", "30.00", "1"]  # la riga c'è, con feature NULL


def test_il_file_si_ordina_dopo_lo_schema_e_prima_del_seed() -> None:
    """MySQL esegue gli script di inizializzazione in ordine alfabetico."""
    nomi = sorted(p.name for p in (RADICE / "sql").glob("*.sql"))
    assert nomi.index("schema.sql") < nomi.index(ESTENSIONE) < nomi.index("seed.sql")


def test_lo_script_del_db_di_test_applica_anche_le_estensioni() -> None:
    codice = (RADICE / "sql" / "00_test_db.sh").read_text(encoding="utf-8")
    corpo = codice[codice.index("beewatch_crea_db_test()") :]
    assert "schema_*.sql" in corpo  # le estensioni, in ordine alfabetico
    # Prima lo schema, poi le estensioni, poi il seed.
    assert corpo.index("(schema.sql)") < corpo.index("schema_*.sql") < corpo.index("+=(seed.sql)")


# --------------------------------------------------------------------------- #
# schema_03: la tabella dei riepiloghi AI (M5-T5)
# --------------------------------------------------------------------------- #

ESTENSIONE_RIEPILOGHI = "schema_03_riepiloghi_ispezione.sql"


def tabella_riepiloghi(stack: Stack, database: str) -> str:
    return come_root(
        stack,
        "SELECT table_name FROM information_schema.tables "
        f"WHERE table_schema = '{database}' AND table_name = 'riepiloghi_ispezione'",
        database,
    )


@pytest.fixture
def stack_riepiloghi(stack_mysql: Stack) -> Iterator[Stack]:
    """Lo stack; a fine test la tabella c'è di nuovo, qualunque cosa abbia fatto il test."""
    yield stack_mysql
    applica_estensione(stack_mysql, file=ESTENSIONE_RIEPILOGHI)


def test_la_tabella_dei_riepiloghi_c_e_nel_database_principale_e_in_quello_di_test(
    stack_riepiloghi: Stack,
) -> None:
    for database in (DB_NAME, NOME_DB_TEST):
        assert tabella_riepiloghi(stack_riepiloghi, database) == "riepiloghi_ispezione", database


def test_riapplicare_la_tabella_dei_riepiloghi_non_cambia_nulla(stack_riepiloghi: Stack) -> None:
    prima = come_root(stack_riepiloghi, "SHOW CREATE TABLE riepiloghi_ispezione")

    applica_estensione(stack_riepiloghi, file=ESTENSIONE_RIEPILOGHI)
    applica_estensione(stack_riepiloghi, file=ESTENSIONE_RIEPILOGHI)

    assert come_root(stack_riepiloghi, "SHOW CREATE TABLE riepiloghi_ispezione") == prima


def test_su_un_database_senza_la_tabella_lestensione_la_crea_senza_toccare_il_resto(
    stack_riepiloghi: Stack,
) -> None:
    ispezioni = come_root(stack_riepiloghi, "SELECT COUNT(*) FROM ispezioni")
    come_root(
        stack_riepiloghi, "DROP TABLE riepiloghi_ispezione"
    )  # il volume com'era prima di M5-T5
    assert tabella_riepiloghi(stack_riepiloghi, NOME_DB_TEST) == ""

    applica_estensione(stack_riepiloghi, file=ESTENSIONE_RIEPILOGHI)

    assert tabella_riepiloghi(stack_riepiloghi, NOME_DB_TEST) == "riepiloghi_ispezione"
    assert come_root(stack_riepiloghi, "SELECT COUNT(*) FROM ispezioni") == ispezioni


def test_la_tabella_dei_riepiloghi_ha_cascate_e_vincoli_attesi(stack_riepiloghi: Stack) -> None:
    chiavi = come_root(
        stack_riepiloghi,
        "SELECT CONCAT(constraint_name, ' ', delete_rule) "
        "FROM information_schema.referential_constraints "
        f"WHERE constraint_schema = '{NOME_DB_TEST}' AND table_name = 'riepiloghi_ispezione' "
        "ORDER BY constraint_name",
    )
    assert chiavi.splitlines() == [
        "fk_riepiloghi_ispezioni CASCADE",
        "fk_riepiloghi_utenti CASCADE",
    ]


def test_il_file_dei_riepiloghi_si_ordina_dopo_lo_schema_e_prima_del_seed() -> None:
    nomi = sorted(p.name for p in (RADICE / "sql").glob("*.sql"))
    assert nomi.index("schema.sql") < nomi.index(ESTENSIONE_RIEPILOGHI) < nomi.index("seed.sql")
    assert nomi.index(ESTENSIONE) < nomi.index(ESTENSIONE_RIEPILOGHI)
