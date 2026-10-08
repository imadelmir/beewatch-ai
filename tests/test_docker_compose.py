"""Test della configurazione Docker (B-02, B-03, B-14), senza avviare nessun contenitore.

Si fa renderizzare il compose a `docker compose config` con un file di variabili
finto (`--env-file`): il `.env` vero dello sviluppatore non viene mai letto, e non serve
il demone Docker. Se la CLI `docker compose` non c'è, vengono saltati solo i test che la usano.

La prova con i contenitori veri (porte, privilegi, healthcheck) sta in
`test_docker_stack.py`, marcato `integration`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RADICE_PROGETTO = Path(__file__).resolve().parents[1]
COMPOSE = RADICE_PROGETTO / "docker-compose.yml"

PASSWORD_ROOT = "ROOT-SEGRETA-compose-5d"
VARIABILI_BASE = {
    "DB_NAME": "beewatch_t",
    "DB_USER": "app_t",
    "DB_PASSWORD": "APP-SEGRETA-compose-9f",
    "DB_ROOT_PASSWORD": PASSWORD_ROOT,
}

# Le variabili che l'applicazione può ricevere: quelle che legge `beewatch/config.py`.
# Aggiungerne una qui è una scelta consapevole, non un effetto collaterale.
VARIABILI_DELLAPP = {
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_API_KEY",
    "LLM_TIMEOUT",
    "MODEL_PATH",
    "LOG_LEVEL",
    "TZ",
}


def _docker_compose_disponibile() -> bool:
    if shutil.which("docker") is None:
        return False
    esito = subprocess.run(["docker", "compose", "version"], capture_output=True, check=False)
    return esito.returncode == 0


def renderizza(tmp_path: Path, **variabili: str) -> dict:
    """La configurazione di compose, già risolta, come dizionario.

    Salta il test se manca la CLI `docker compose`: i controlli che leggono solo file di
    testo (Dockerfile, .dockerignore, privilegi.sql) non la usano e girano sempre.
    """
    if not _docker_compose_disponibile():
        pytest.skip("serve la CLI `docker compose`")
    valori = {**VARIABILI_BASE, **variabili}
    env = tmp_path / "prova.env"
    env.write_text("".join(f"{k}={v}\n" for k, v in valori.items()), encoding="utf-8")
    esito = subprocess.run(
        [
            "docker", "compose", "-f", str(COMPOSE), "--env-file", str(env),
            "config", "--format", "json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )  # fmt: skip
    assert esito.returncode == 0, esito.stderr
    return json.loads(esito.stdout)


# --------------------------------------------------------------------------- #
# B-02 · La porta del computer non è la porta della rete di Docker
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "variabili,porta_sul_computer",
    [
        pytest.param({}, 3306, id="DB_PORT-assente-3306"),
        pytest.param({"DB_PORT": "3306"}, 3306, id="DB_PORT-3306"),
        pytest.param({"DB_PORT": "3397"}, 3397, id="DB_PORT-personalizzata-3397"),
    ],
)
def test_la_porta_del_computer_cambia_ma_quella_dellapp_resta_3306(
    tmp_path, variabili, porta_sul_computer
) -> None:
    servizi = renderizza(tmp_path, **variabili)["services"]

    # MySQL: pubblicata su 127.0.0.1 alla porta scelta, ma dentro il contenitore è 3306.
    (pubblicata,) = servizi["mysql"]["ports"]
    assert pubblicata["host_ip"] == "127.0.0.1"
    assert int(pubblicata["published"]) == porta_sul_computer
    assert pubblicata["target"] == 3306

    # App: raggiunge sempre `mysql:3306`, indipendentemente da DB_PORT.
    ambiente = servizi["app"]["environment"]
    assert ambiente["DB_HOST"] == "mysql"
    assert ambiente["DB_PORT"] == "3306"


def test_db_host_e_db_port_del_env_non_arrivano_allapp(tmp_path) -> None:
    """`DB_HOST=localhost` e `DB_PORT=3397` in .env sono per chi sta fuori da Docker."""
    ambiente = renderizza(tmp_path, DB_HOST="localhost", DB_PORT="3397")["services"]["app"][
        "environment"
    ]
    assert (ambiente["DB_HOST"], ambiente["DB_PORT"]) == ("mysql", "3306")


# --------------------------------------------------------------------------- #
# B-03 · root solo per MySQL, e all'app solo ciò che serve
# --------------------------------------------------------------------------- #


def test_lapp_non_riceve_la_password_di_root(tmp_path) -> None:
    app = renderizza(tmp_path)["services"]["app"]

    assert "DB_ROOT_PASSWORD" not in app["environment"]
    assert PASSWORD_ROOT not in json.dumps(app)  # né sotto altro nome, né altrove


def test_lapp_riceve_solo_le_variabili_che_legge(tmp_path) -> None:
    """Un elenco chiuso: un `env_file: .env` farebbe passare tutto il file."""
    app = renderizza(tmp_path, EXTRA_NON_ELENCATA="x")["services"]["app"]

    assert set(app["environment"]) <= VARIABILI_DELLAPP
    assert "EXTRA_NON_ELENCATA" not in app["environment"]
    assert "env_file" not in app


def test_le_variabili_mancanti_dellapp_sono_vuote_non_inventate(tmp_path) -> None:
    """Se in .env mancano, `config.py` usa i suoi predefiniti: compose passa stringhe vuote."""
    ambiente = renderizza(tmp_path)["services"]["app"]["environment"]
    for nome in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_TIMEOUT", "MODEL_PATH"):
        assert ambiente[nome] == ""


def test_root_si_collega_solo_dallinterno_di_mysql(tmp_path) -> None:
    """Senza questo l'immagine crea `root@%`, raggiungibile da ogni contenitore della rete."""
    mysql = renderizza(tmp_path)["services"]["mysql"]
    assert mysql["environment"]["MYSQL_ROOT_HOST"] == "localhost"


def test_la_password_di_root_arriva_solo_a_mysql(tmp_path) -> None:
    servizi = renderizza(tmp_path)["services"]
    assert servizi["mysql"]["environment"]["MYSQL_ROOT_PASSWORD"] == PASSWORD_ROOT


def test_lo_script_dei_privilegi_concede_solo_dml() -> None:
    sql = (RADICE_PROGETTO / "sql" / "privilegi.sql").read_text(encoding="utf-8")
    codice = "\n".join(riga for riga in sql.splitlines() if not riga.lstrip().startswith("--"))

    concessioni = re.findall(r"GRANT\s+([A-Z, ]+?)\s+ON", codice)
    assert concessioni == ["SELECT, INSERT, UPDATE, DELETE"]
    assert "WITH GRANT OPTION" not in codice


# --------------------------------------------------------------------------- #
# B-14 · `docker compose up` avvia tutto
# --------------------------------------------------------------------------- #


def test_senza_profili_compose_avvia_database_e_applicazione(tmp_path) -> None:
    servizi = renderizza(tmp_path)["services"]

    assert set(servizi) == {"mysql", "app"}
    assert "profiles" not in servizi["app"]


def test_lapp_parte_solo_quando_mysql_e_sano(tmp_path) -> None:
    app = renderizza(tmp_path)["services"]["app"]
    assert app["depends_on"]["mysql"]["condition"] == "service_healthy"


def test_compose_non_forza_la_build_a_ogni_up(tmp_path) -> None:
    """`docker compose up` riusa l'immagine che c'è; per ricostruirla si usa `--build`.

    Con `pull_policy: build` ogni `up` costa circa 10 secondi e ricrea il contenitore
    dell'app anche a codice invariato.
    """
    app = renderizza(tmp_path)["services"]["app"]
    assert "pull_policy" not in app
    assert "build" in app  # ma l'immagine si costruisce da sola se non esiste


# --------------------------------------------------------------------------- #
# Inizializzazione fallita: l'errore non deve essere nascosto
# --------------------------------------------------------------------------- #


def test_mysql_non_si_riavvia_da_solo_e_lapp_mantiene_la_sua_politica(tmp_path) -> None:
    """Con `unless-stopped` un init fallito diventa un MySQL su volume a metà, "sano"."""
    servizi = renderizza(tmp_path)["services"]
    assert servizi["mysql"]["restart"] == "no"
    assert servizi["app"]["restart"] == "unless-stopped"


def test_il_controllo_di_mysql_vuole_utente_app_e_schema_senza_segreti(tmp_path) -> None:
    mysql = renderizza(tmp_path)["services"]["mysql"]
    test = mysql["healthcheck"]["test"]

    assert test[0] == "CMD-SHELL"
    comando = test[1]
    assert "information_schema.tables" in comando  # lo schema deve esserci
    assert "$$MYSQL_USER" in comando and "-u root" not in comando  # entra come utente dell'app
    assert "MYSQL_PWD" in comando  # la password non sta nella riga di comando
    assert VARIABILI_BASE["DB_PASSWORD"] not in json.dumps(mysql["healthcheck"])
    assert PASSWORD_ROOT not in json.dumps(mysql["healthcheck"])


# --------------------------------------------------------------------------- #
# Invarianti da non perdere
# --------------------------------------------------------------------------- #


def test_mysql_resta_sulla_porta_interna_3306_e_con_dati_persistenti(tmp_path) -> None:
    mysql = renderizza(tmp_path)["services"]["mysql"]
    assert mysql["ports"][0]["target"] == 3306
    assert any(v["type"] == "volume" and v["target"] == "/var/lib/mysql" for v in mysql["volumes"])


def test_il_dockerfile_gira_come_utente_non_root() -> None:
    righe = (RADICE_PROGETTO / "Dockerfile").read_text(encoding="utf-8").splitlines()
    utenti = [r.split()[1] for r in righe if r.strip().upper().startswith("USER ")]
    assert utenti and utenti[-1] not in ("root", "0")


def test_il_dockerfile_non_copia_il_env_e_il_dockerignore_lo_esclude() -> None:
    dockerfile = (RADICE_PROGETTO / "Dockerfile").read_text(encoding="utf-8")
    copie = [r for r in dockerfile.splitlines() if r.strip().upper().startswith(("COPY", "ADD"))]
    assert not any(re.search(r"(^|\s)\.env(\s|$)", r) for r in copie)

    ignorati = (RADICE_PROGETTO / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in [riga.strip() for riga in ignorati]


def test_lhealthcheck_dellimmagine_e_quello_che_controlla_il_database() -> None:
    righe = (RADICE_PROGETTO / "Dockerfile").read_text(encoding="utf-8").splitlines()
    istruzioni = "\n".join(r for r in righe if not r.lstrip().startswith("#"))  # senza commenti

    assert "beewatch.healthcheck" in istruzioni
    assert "_stcore/health" not in istruzioni  # il solo controllo di Streamlit non basta


def test_il_timeout_dockerfile_basta_ai_due_controlli_di_rete() -> None:
    """Streamlit (3 s) + MySQL (3 s) devono stare sotto il `--timeout` di HEALTHCHECK.

    Se lo superano Docker uccide il controllo e segna `unhealthy` anche con tutto a posto.
    """
    from beewatch.healthcheck import TIMEOUT_SECONDI

    dockerfile = (RADICE_PROGETTO / "Dockerfile").read_text(encoding="utf-8")
    trovato = re.search(r"HEALTHCHECK[^\n]*--timeout=(\d+)s", dockerfile)

    assert trovato, "HEALTHCHECK senza --timeout"
    assert int(trovato.group(1)) > 2 * TIMEOUT_SECONDI
