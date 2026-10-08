"""Prova dell'ambiente Docker con i contenitori veri (B-02, B-03, B-12, B-14).

Si lancia a mano, perché costruisce l'immagine e avvia MySQL:

    pytest -m integration tests/test_docker_stack.py

Ogni stack è ISOLATO e TEMPORANEO (vedi `docker_support.Stack`): nome di progetto, volume
e immagine propri (`bwdockerfix-<sigla>`), credenziali casuali, `.env` finto passato con
`--env-file`. Il database di sviluppo (`beewatch-mysql`, `beewatch_dati_mysql`) e
l'immagine `beewatch-ai:dev` non vengono mai toccati: la pulizia ha una guardia che si
rifiuta di toccare risorse non proprie (provata in `test_docker_guardia.py`), e una
sentinella confronta lo stato delle risorse reali prima e dopo questo file.

Le prove stampano solo `allowed` / `denied`: mai password. Se un test fallisce, l'output
di Docker finisce nel messaggio con le credenziali sostituite da `***`.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Iterator
from pathlib import Path

import mysql.connector
import pytest
from docker_support import (
    DB_NAME,
    DB_USER,
    Stack,
    attendi,
    copia_sql_con_errore,
    docker_pronto,
    fotografia_risorse_reali,
    porta_libera,
    porta_occupata,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not docker_pronto(), reason="serve il demone Docker in esecuzione"),
]


@pytest.fixture(scope="module", autouse=True)
def _risorse_reali_intatte() -> Iterator[None]:
    """Sentinella: le risorse reali dello sviluppatore sono identiche prima e dopo."""
    prima = fotografia_risorse_reali()
    yield
    dopo = fotografia_risorse_reali()
    assert dopo == prima, f"le risorse reali sono cambiate durante i test: {prima} -> {dopo}"


@pytest.fixture(scope="module")
def cartella_stack(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("stack")


def _stack_avviato(stack: Stack, costruisci: bool = True) -> Iterator[Stack]:
    try:
        stack.avvia(costruisci=costruisci)
        yield stack
    finally:
        stack.smonta()


@pytest.fixture(scope="module")
def stack_standard(cartella_stack) -> Iterator[Stack]:
    """Caso 1: DB_PORT assente, quindi la porta 3306 anche sul computer."""
    if porta_occupata(3306):
        pytest.skip("la porta 3306 del computer è già occupata da un altro programma")
    yield from _stack_avviato(Stack(cartella_stack / "standard", None))


@pytest.fixture(scope="module")
def stack_custom(cartella_stack) -> Iterator[Stack]:
    """Caso 2: DB_PORT diverso da 3306. Parte con `docker compose up --wait` SEMPLICE.

    L'immagine dello stack non esiste ancora (clone pulito): il requisito del progetto è
    che `docker compose up` basti, quindi qui niente `--build`.
    """
    yield from _stack_avviato(Stack(cartella_stack / "custom", porta_libera()), costruisci=False)


def connetti_dal_computer(stack: Stack, porta: int):
    return mysql.connector.connect(
        host="127.0.0.1",
        port=porta,
        user=DB_USER,
        password=stack.password_app,
        database=DB_NAME,
        connection_timeout=5,
    )


# --------------------------------------------------------------------------- #
# B-02 · caso 1: porta standard
# --------------------------------------------------------------------------- #


def test_caso1_porta_standard_database_e_app_sani(stack_standard: Stack) -> None:
    for servizio in ("mysql", "app"):
        assert stack_standard.salute(stack_standard.container(servizio)) == "healthy", servizio


def test_caso1_il_computer_raggiunge_mysql_su_3306(stack_standard: Stack) -> None:
    connessione = connetti_dal_computer(stack_standard, 3306)
    cursore = connessione.cursor()
    cursore.execute("SELECT COUNT(*) FROM apiari")  # il seed è stato caricato
    assert cursore.fetchone()[0] > 0
    connessione.close()


def test_caso1_lapp_usa_mysql_3306(stack_standard: Stack) -> None:
    uscita = stack_standard.nel_container(
        "app", "python", "-c", "import os; print(os.environ['DB_HOST'], os.environ['DB_PORT'])"
    )
    assert uscita.stdout.split() == ["mysql", "3306"]  # anche se in .env c'è DB_HOST=localhost
    assert stack_standard.nel_container("app", "python", "-m", "beewatch.healthcheck").stdout == (
        "OK\n"
    )


# --------------------------------------------------------------------------- #
# B-02 · caso 2: porta del computer personalizzata
# --------------------------------------------------------------------------- #


def test_caso2_il_computer_usa_la_porta_scelta(stack_custom: Stack) -> None:
    assert stack_custom.porta_db != 3306
    connessione = connetti_dal_computer(stack_custom, stack_custom.porta_db)
    cursore = connessione.cursor()
    cursore.execute("SELECT 1")
    assert cursore.fetchone() == (1,)
    connessione.close()


def test_caso2_lapp_usa_comunque_mysql_3306(stack_custom: Stack) -> None:
    assert stack_custom.salute(stack_custom.container("app")) == "healthy"
    uscita = stack_custom.nel_container(
        "app", "python", "-c", "import os; print(os.environ['DB_HOST'], os.environ['DB_PORT'])"
    )
    assert uscita.stdout.split() == ["mysql", "3306"]


def test_caso2_la_vecchia_configurazione_non_avrebbe_funzionato(stack_custom: Stack) -> None:
    """Riproduce B-02: con `mysql:<porta del computer>` dentro la rete non risponde nessuno."""
    script = (
        "import mysql.connector as m, sys\n"
        "try:\n"
        f"    m.connect(host='mysql', port={stack_custom.porta_db}, user='x', password='x',"
        " connection_timeout=4)\n"
        "except m.Error as e:\n"
        "    print('errno', e.errno)\n"
    )
    uscita = stack_custom.nel_container("app", "python", "-c", script)
    assert uscita.stdout.split() == ["errno", "2003"]  # connessione rifiutata


# --------------------------------------------------------------------------- #
# B-14 · docker compose up avvia tutto
# --------------------------------------------------------------------------- #


def test_up_senza_profili_ha_avviato_mysql_e_app(stack_custom: Stack) -> None:
    servizi = stack_custom.compose("ps", "--services", "--status", "running").stdout.split()
    assert sorted(servizi) == ["app", "mysql"]


def test_lapp_e_raggiungibile_sulla_porta_pubblicata(stack_custom: Stack) -> None:
    import urllib.request

    url = f"http://127.0.0.1:{stack_custom.porta_app}/_stcore/health"
    with urllib.request.urlopen(url, timeout=10) as risposta:
        assert risposta.status == 200


# --------------------------------------------------------------------------- #
# B-03 · root e privilegi
# --------------------------------------------------------------------------- #

SCRIPT_PRIVILEGI = """
import os
import mysql.connector as m

c = m.connect(host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']),
              user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'],
              database=os.environ['DB_NAME'], connection_timeout=5, autocommit=False)
cur = c.cursor()
OPERAZIONI = [
    ('SELECT', 'SELECT COUNT(*) FROM tipi_miele'),
    ('INSERT', "INSERT INTO tipi_miele (id, codice, etichetta) VALUES (99, 'bw_prova', 'x')"),
    ('UPDATE', "UPDATE tipi_miele SET etichetta = 'y' WHERE id = 99"),
    ('DELETE', 'DELETE FROM tipi_miele WHERE id = 99'),
    ('CREATE TABLE', 'CREATE TABLE bw_prova_ddl (id INT)'),
    ('DROP TABLE', 'DROP TABLE tipi_miele'),
    ('ALTER TABLE', 'ALTER TABLE tipi_miele ADD COLUMN extra INT'),
    ('TRUNCATE', 'TRUNCATE TABLE tipi_miele'),
    ('CREATE TEMPORARY TABLE', 'CREATE TEMPORARY TABLE bw_prova_tmp (id INT)'),
    ('GRANT', 'GRANT SELECT ON *.* TO CURRENT_USER()'),
    ('CREATE USER', "CREATE USER 'bw_intruso'@'%' IDENTIFIED BY 'x'"),
]
for nome, sql in OPERAZIONI:
    try:
        cur.execute(sql)
        if cur.with_rows:
            cur.fetchall()
        esito = 'allowed'
    except m.Error as e:
        esito = 'denied' if e.errno in (1044, 1045, 1142, 1227) else f'errore-{e.errno}'
    print(f'{nome}|{esito}')
c.rollback()
"""

PRIVILEGI_ATTESI = {
    "SELECT": "allowed",
    "INSERT": "allowed",
    "UPDATE": "allowed",
    "DELETE": "allowed",
    "CREATE TABLE": "denied",
    "DROP TABLE": "denied",
    "ALTER TABLE": "denied",
    "TRUNCATE": "denied",
    "CREATE TEMPORARY TABLE": "denied",
    "GRANT": "denied",
    "CREATE USER": "denied",
}


def test_caso5_lutente_app_puo_solo_leggere_e_scrivere_i_dati(stack_custom: Stack) -> None:
    uscita = stack_custom.nel_container("app", "python", "-c", SCRIPT_PRIVILEGI)
    assert uscita.returncode == 0, stack_custom.redigi(uscita.stderr)

    esiti = dict(riga.split("|") for riga in uscita.stdout.splitlines())
    assert esiti == PRIVILEGI_ATTESI


def test_caso5_le_tabelle_sono_intatte_dopo_la_prova(stack_custom: Stack) -> None:
    connessione = connetti_dal_computer(stack_custom, stack_custom.porta_db)
    cursore = connessione.cursor()
    cursore.execute("SELECT COUNT(*) FROM tipi_miele WHERE id = 99")
    assert cursore.fetchone() == (0,)  # il rollback ha annullato la riga di prova
    cursore.execute("SHOW TABLES LIKE 'bw_prova%'")
    assert cursore.fetchall() == []
    cursore.execute("SELECT COUNT(*) FROM tipi_miele")
    assert cursore.fetchone()[0] > 0  # DROP e TRUNCATE non hanno avuto effetto
    connessione.close()


def test_i_privilegi_finali_sono_esattamente_quattro(stack_custom: Stack) -> None:
    comando = (
        'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N '
        f"-e \"SHOW GRANTS FOR '{DB_USER}'@'%'\" 2>/dev/null"
    )
    grants = stack_custom.nel_container("mysql", "sh", "-c", comando).stdout
    assert "ALL PRIVILEGES" not in grants
    assert "GRANT OPTION" not in grants
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON" in grants


def test_caso4_la_password_di_root_non_e_nellambiente_dellapp(stack_custom: Stack) -> None:
    app = stack_custom.container("app")
    ambiente = json.loads(stack_custom.esegui("inspect", "-f", "{{json .Config.Env}}", app).stdout)
    nomi = {voce.split("=", 1)[0] for voce in ambiente}
    assert "DB_ROOT_PASSWORD" not in nomi
    assert "MYSQL_ROOT_PASSWORD" not in nomi

    dentro = stack_custom.nel_container(
        "app", "python", "-c", "import os; print('\\n'.join(sorted(os.environ)))"
    ).stdout.split()
    assert "DB_ROOT_PASSWORD" not in dentro
    assert "MYSQL_ROOT_PASSWORD" not in dentro

    intero = stack_custom.esegui("inspect", app).stdout  # il valore non compare da nessuna parte
    assert stack_custom.password_root not in intero


def test_caso4_la_password_di_root_e_solo_nel_container_mysql(stack_custom: Stack) -> None:
    mysql_env = json.loads(
        stack_custom.esegui(
            "inspect", "-f", "{{json .Config.Env}}", stack_custom.container("mysql")
        ).stdout
    )
    assert any(v.startswith("MYSQL_ROOT_PASSWORD=") for v in mysql_env)


def test_root_non_si_collega_dallapp_nemmeno_con_la_password_vera(stack_custom: Stack) -> None:
    """La password vera viene data al processo di prova, non all'ambiente dell'app."""
    script = """
import os
import mysql.connector as m

for etichetta, pw in (('con-password-vera', os.environ['PROVA_PW']), ('senza-password', '')):
    try:
        m.connect(host='mysql', port=3306, user='root', password=pw, connection_timeout=5).close()
        print(etichetta + '|allowed')
    except m.Error as e:
        print(etichetta + '|denied-' + str(e.errno))
"""
    uscita = stack_custom.nel_container(
        "app", "python", "-c", script, ambiente={"PROVA_PW": stack_custom.password_root}
    )
    esiti = dict(riga.split("|") for riga in uscita.stdout.splitlines())
    assert esiti["con-password-vera"].startswith("denied")
    assert esiti["senza-password"].startswith("denied")
    assert stack_custom.password_root not in uscita.stdout + uscita.stderr


def test_root_funziona_dentro_il_container_mysql_per_lamministrazione(stack_custom: Stack) -> None:
    uscita = stack_custom.nel_container(
        "mysql", "sh", "-c", 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "SELECT 1" 2>/dev/null'
    )
    assert uscita.stdout.strip() == "1"


def test_lapp_non_gira_come_root(stack_custom: Stack) -> None:
    assert stack_custom.nel_container("app", "id", "-u").stdout.strip() == "1000"


def test_nei_log_non_ci_sono_password(stack_custom: Stack) -> None:
    log = stack_custom.compose("logs", "--no-color").stdout
    assert stack_custom.password_app not in log
    assert stack_custom.password_root not in log


def test_nellimmagine_non_ci_sono_password_ne_env(stack_custom: Stack) -> None:
    storia = stack_custom.esegui(
        "history", "--no-trunc", "--format", "{{.CreatedBy}}", stack_custom.immagine
    ).stdout
    config = stack_custom.esegui("image", "inspect", stack_custom.immagine).stdout
    for segreto in (stack_custom.password_app, stack_custom.password_root):
        assert segreto not in storia
        assert segreto not in config

    file_env = stack_custom.nel_container(
        "app", "sh", "-c", "ls -a /app | grep -x '.env' || echo assente"
    ).stdout.strip()
    assert file_env == "assente"


# --------------------------------------------------------------------------- #
# B-12 · healthcheck
# --------------------------------------------------------------------------- #


def _una_tantum(stack: Stack, nome: str, **ambiente: str) -> str:
    """Avvia un secondo contenitore dell'app (stessa immagine e rete), con variabili diverse.

    `--no-deps`: non tocca MySQL. Non pubblica porte. Restituisce il nome.
    """
    nome_completo = f"{stack.progetto}-{nome}"
    opzioni = [x for k, v in ambiente.items() for x in ("-e", f"{k}={v}")]
    stack.compose("run", "-d", "--no-deps", "--name", nome_completo, *opzioni, "app")
    return nome_completo


def _controllo(stack: Stack, contenitore: str, attesa_streamlit: bool = True) -> tuple[int, str]:
    """Esegue il controllo di salute nel contenitore, aspettando che Streamlit sia partito."""
    risultato: dict[str, tuple[int, str]] = {}

    def _pronto() -> bool:
        esito = stack.esegui(
            "exec", contenitore, "python", "-m", "beewatch.healthcheck", controlla=False
        )
        risultato["ultimo"] = (esito.returncode, esito.stdout.strip())
        return not attesa_streamlit or "Streamlit non risponde" not in esito.stdout

    attendi(_pronto, 60, f"{contenitore}: Streamlit non è partito")
    return risultato["ultimo"]


def test_caso3_database_disponibile_lapp_e_healthy(stack_custom: Stack) -> None:
    app = stack_custom.container("app")
    assert stack_custom.salute(app) == "healthy"
    esito = stack_custom.nel_container("app", "python", "-m", "beewatch.healthcheck")
    assert (esito.returncode, esito.stdout) == (0, "OK\n")


def test_configurazione_errata_lapp_e_unhealthy(stack_custom: Stack) -> None:
    contenitore = _una_tantum(stack_custom, "confnonvalida", DB_PORT="non_un_numero")
    codice, uscita = _controllo(stack_custom, contenitore, attesa_streamlit=False)
    assert codice == 1
    assert uscita.startswith("KO: configurazione non valida")


def test_password_errata_lapp_e_unhealthy_senza_stampare_password(stack_custom: Stack) -> None:
    sbagliata = "PW-SBAGLIATA-" + secrets.token_hex(4)
    contenitore = _una_tantum(stack_custom, "pwsbagliata", DB_PASSWORD=sbagliata)
    codice, uscita = _controllo(stack_custom, contenitore)
    assert codice == 1
    assert "database non raggiungibile (errore MySQL 1045)" in uscita
    for segreto in (sbagliata, stack_custom.password_app, DB_USER):
        assert segreto not in uscita


def test_host_inesistente_lapp_e_unhealthy(stack_custom: Stack) -> None:
    contenitore = _una_tantum(stack_custom, "hostassente", DB_HOST="host-che-non-esiste")
    codice, uscita = _controllo(stack_custom, contenitore)
    assert codice == 1
    assert uscita.startswith("KO: database non raggiungibile")


def test_caso3_database_non_disponibile_lapp_diventa_unhealthy_e_poi_si_riprende(
    stack_custom: Stack,
) -> None:
    app = stack_custom.container("app")
    try:
        stack_custom.compose("stop", "mysql")

        esito = stack_custom.nel_container("app", "python", "-m", "beewatch.healthcheck")
        assert esito.returncode == 1
        assert esito.stdout.startswith("KO: database non raggiungibile")

        # Anche per Docker: l'app non risulta più sana (2 controlli falliti, uno ogni 5 s).
        attendi(
            lambda: stack_custom.salute(app) == "unhealthy", 90, "l'app non è diventata unhealthy"
        )
    finally:
        stack_custom.compose("start", "mysql")

    attendi(lambda: stack_custom.salute(app) == "healthy", 120, "l'app non si è ripresa")


# --------------------------------------------------------------------------- #
# MySQL "sano" = server vero + utente app + schema presente
# --------------------------------------------------------------------------- #


def _comando_healthcheck_mysql(stack: Stack) -> str:
    esito = stack.esegui(
        "inspect", "-f", "{{json .Config.Healthcheck.Test}}", stack.container("mysql")
    )
    assert stack.password_app not in esito.stdout  # la password non è scritta nel controllo
    assert stack.password_root not in esito.stdout
    test = json.loads(esito.stdout)
    assert test[0] == "CMD-SHELL"
    return test[1]


def test_il_controllo_di_mysql_vuole_lo_schema(stack_custom: Stack) -> None:
    """Con il database dell'app il controllo riesce; con un database senza tabelle no."""
    comando = _comando_healthcheck_mysql(stack_custom)

    def esegui(nome_db: str) -> int:
        return stack_custom.nel_container(
            "mysql", "sh", "-c", comando, ambiente={"MYSQL_DATABASE": nome_db}
        ).returncode

    assert esegui(DB_NAME) == 0
    assert esegui("information_schema_non_esiste") == 1  # nessuna tabella
    assert (
        stack_custom.nel_container(
            "mysql", "sh", "-c", comando, ambiente={"MYSQL_PASSWORD": "sbagliata"}
        ).returncode
        == 1
    )  # l'utente dell'app non riesce a entrare


def test_mysql_non_si_riavvia_da_solo(stack_custom: Stack) -> None:
    mysql = stack_custom.container("mysql")
    politica = stack_custom.esegui("inspect", "-f", "{{.HostConfig.RestartPolicy.Name}}", mysql)
    assert politica.stdout.strip() in ("no", "")
    app = stack_custom.container("app")
    politica_app = stack_custom.esegui("inspect", "-f", "{{.HostConfig.RestartPolicy.Name}}", app)
    assert politica_app.stdout.strip() == "unless-stopped"  # la politica dell'app non è cambiata


# --------------------------------------------------------------------------- #
# Inizializzazione fallita: l'errore non deve essere silenzioso
# --------------------------------------------------------------------------- #


def _stack_con_init_rotto(cartella: Path, file_rotto: str, **opzioni) -> Iterator[Stack]:
    sql = copia_sql_con_errore(cartella / "sql", file_rotto)
    stack = Stack(cartella / "stack", porta_libera(), sql_dir=sql, **opzioni)
    try:
        yield stack
    finally:
        stack.smonta()


def _up(stack: Stack, attesa: int = 240, costruisci: bool = True):
    opzioni = ["--build"] if costruisci else []
    return stack.compose(
        "up", "-d", *opzioni, "--wait", "--wait-timeout", str(attesa), controlla=False, timeout=1500
    )


def _stato_mysql(stack: Stack) -> dict:
    mysql = stack.container("mysql", tutti=True)
    stato = json.loads(stack.esegui("inspect", "-f", "{{json .State}}", mysql).stdout)
    stato["RestartCount"] = int(stack.esegui("inspect", "-f", "{{.RestartCount}}", mysql).stdout)
    return stato


def _tabelle(stack: Stack) -> str:
    comando = (
        'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e '
        "\"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$MYSQL_DATABASE'\""
        " 2>/dev/null"
    )
    return stack.nel_container("mysql", "sh", "-c", comando).stdout.strip()


def test_init_rotto_non_e_silenzioso_ne_al_primo_ne_al_secondo_avvio(tmp_path) -> None:
    for stack in _stack_con_init_rotto(tmp_path, "privilegi.sql", mysql_controlli_rapidi=True):
        # 1) Primo avvio: lo script da' errore. `up` DEVE fallire, MySQL resta fermo.
        esito = _up(stack)
        uscita = stack.redigi(esito.stdout + esito.stderr)
        assert esito.returncode != 0, (
            "up --wait e' riuscito con uno script di init rotto:\n" + uscita
        )
        assert "exited" in uscita or "unhealthy" in uscita, uscita[-800:]
        stato = _stato_mysql(stack)
        assert stato["Status"] == "exited" and stato["ExitCode"] != 0, stato
        assert stato["RestartCount"] == 0, "Docker ha riavviato MySQL e nascosto l'errore"
        assert stack.nel_container("app", "true").returncode != 0  # l'app non e' partita

        # 2) Secondo avvio, SENZA `down -v`: il volume e' rimasto a meta' e MySQL salta
        #    l'inizializzazione. Non deve essere dichiarato pronto, perche' manca lo schema.
        secondo = _up(stack, attesa=90, costruisci=False)
        assert secondo.returncode != 0, "il database incompleto e' stato dichiarato pronto"
        assert "unhealthy" in stack.redigi(secondo.stdout + secondo.stderr)
        mysql = stack.container("mysql", tutti=True)
        assert stack.salute(mysql) != "healthy"
        assert _tabelle(stack) == "0"


def test_init_rotto_nel_seed_fa_fallire_up_e_non_riavvia(tmp_path) -> None:
    """Lo schema e' gia' stato creato, il seed no. Al primo `up` l'errore deve emergere.

    Limite noto: se poi si rilancia `up` senza `down -v`, il database ha le tabelle e il
    controllo di MySQL non puo' sapere che manca il seed. Dopo ogni errore di init: `down -v`.
    """
    for stack in _stack_con_init_rotto(tmp_path, "seed.sql"):
        esito = _up(stack)
        uscita = stack.redigi(esito.stdout + esito.stderr)
        assert esito.returncode != 0, uscita
        stato = _stato_mysql(stack)
        assert stato["Status"] == "exited" and stato["ExitCode"] != 0, stato
        assert stato["RestartCount"] == 0
