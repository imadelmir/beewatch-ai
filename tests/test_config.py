"""Test della configurazione centralizzata (M1-T3).

Sono le stesse verifiche fatte a mano quando il modulo è nato, trasformate in
codice: ogni volta che qualcuno tocca `config.py`, girano da sole.

La fixture `ambiente_pulito` (autouse, in conftest.py) toglie le variabili
BeeWatch da `os.environ` e sposta la radice del progetto in una cartella
temporanea. Senza, il `.env` dello sviluppatore renderebbe i risultati diversi
da quelli della CI.
"""

from __future__ import annotations

import codecs
import dataclasses
import logging
from pathlib import Path

import pytest

from beewatch import config as modulo_config
from beewatch.config import (
    Config,
    ConfigDatabase,
    ConfigLLM,
    carica,
    forma_canonica,
    ottieni,
)
from beewatch.exceptions import ConfigError

# Il minimo indispensabile perché la configurazione sia valida: le tre
# variabili che non hanno un valore predefinito.
MINIMI = {
    "DB_NAME": "beewatch_test",
    "DB_USER": "tester",
    "DB_PASSWORD": "segreta",
}


# --------------------------------------------------------------------------- #
# Caso felice
# --------------------------------------------------------------------------- #


def test_configurazione_completa(scrivi_env) -> None:
    percorso = scrivi_env(
        DB_HOST="db.example.com",
        DB_PORT=3307,
        DB_NAME="apiario",
        DB_USER="mario",
        DB_PASSWORD="segreta",
        LLM_PROVIDER="ollama",
        LLM_MODEL="llama3.1:8b",
        LLM_TIMEOUT=90,
        LOG_LEVEL="DEBUG",
    )
    config = carica(percorso)

    assert config.database.host == "db.example.com"
    assert config.database.porta == 3307
    assert config.database.nome == "apiario"
    assert config.llm.provider == "ollama"
    assert config.llm.timeout == 90
    assert config.livello_log == "DEBUG"


def test_valori_predefiniti(scrivi_env) -> None:
    """Chi compila solo le tre variabili obbligatorie deve ottenere un avvio valido."""
    config = carica(scrivi_env(**MINIMI))

    assert config.database.host == "localhost"
    assert config.database.porta == 3306
    assert config.llm.provider == "ollama"
    assert config.llm.timeout == 60
    assert config.livello_log == "INFO"
    assert config.percorso_modello.name == "produzione_v1.joblib"


# --------------------------------------------------------------------------- #
# Validazione: tutti gli errori insieme, non uno alla volta
# --------------------------------------------------------------------------- #


def test_variabili_obbligatorie_mancanti(scrivi_env) -> None:
    """L'eccezione elenca *tutti* i problemi: si correggono in un passaggio."""
    with pytest.raises(ConfigError) as info:
        carica(scrivi_env(DB_HOST="localhost"))

    messaggio = str(info.value)
    assert "DB_NAME" in messaggio
    assert "DB_USER" in messaggio
    assert "DB_PASSWORD" in messaggio
    assert "3 problema/i" in messaggio


def test_il_messaggio_dice_cosa_fare(scrivi_env) -> None:
    """Chi installa il progetto deve capire la soluzione senza leggere il codice."""
    with pytest.raises(ConfigError) as info:
        carica(scrivi_env())
    assert ".env.example" in str(info.value)


def test_gli_errori_seguono_l_ordine_di_lettura(scrivi_env) -> None:
    """L'elenco segue l'ordine in cui `carica()` legge le variabili.

    Le correzioni sui segreti non devono spostare nessuna voce: DB_PASSWORD sta
    fra DB_USER e LLM_API_KEY, non in cima.
    """
    percorso = scrivi_env(
        DB_PORT="abc", LLM_PROVIDER="openrouter", LLM_TIMEOUT=1, LOG_LEVEL="VERBOSE"
    )
    with pytest.raises(ConfigError) as info:
        carica(percorso)

    righe = [riga for riga in str(info.value).splitlines() if riga.startswith("  · ")]
    assert [riga.split()[1] for riga in righe] == [
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "LLM_API_KEY",
        "LLM_TIMEOUT",
        "LOG_LEVEL",
    ]


def test_porta_non_numerica(scrivi_env) -> None:
    with pytest.raises(ConfigError, match="DB_PORT"):
        carica(scrivi_env(**MINIMI, DB_PORT="tremilatrecentosei"))


def test_porta_fuori_intervallo(scrivi_env) -> None:
    with pytest.raises(ConfigError, match="65535"):
        carica(scrivi_env(**MINIMI, DB_PORT=70000))


def test_timeout_fuori_intervallo(scrivi_env) -> None:
    with pytest.raises(ConfigError, match="LLM_TIMEOUT"):
        carica(scrivi_env(**MINIMI, LLM_TIMEOUT=1))


def test_provider_non_ammesso(scrivi_env) -> None:
    with pytest.raises(ConfigError, match="LLM_PROVIDER"):
        carica(scrivi_env(**MINIMI, LLM_PROVIDER="chatgpt"))


def test_livello_log_non_ammesso(scrivi_env) -> None:
    with pytest.raises(ConfigError, match="LOG_LEVEL"):
        carica(scrivi_env(**MINIMI, LOG_LEVEL="VERBOSE"))


@pytest.mark.parametrize("scritto,atteso", [("info", "INFO"), ("Warning", "WARNING")])
def test_livello_log_insensibile_alle_maiuscole(scrivi_env, scritto: str, atteso: str) -> None:
    """Chi scrive `info` non deve essere punito: si restituisce la forma canonica."""
    assert carica(scrivi_env(**MINIMI, LOG_LEVEL=scritto)).livello_log == atteso


# --------------------------------------------------------------------------- #
# Regola specifica del provider LLM
# --------------------------------------------------------------------------- #


def test_openrouter_senza_chiave_fallisce_allavvio(scrivi_env) -> None:
    """Meglio fallire subito che alla prima domanda dell'utente in demo."""
    with pytest.raises(ConfigError, match="LLM_API_KEY"):
        carica(scrivi_env(**MINIMI, LLM_PROVIDER="openrouter"))


def test_openrouter_con_chiave(scrivi_env) -> None:
    config = carica(scrivi_env(**MINIMI, LLM_PROVIDER="openrouter", LLM_API_KEY="sk-finta"))
    assert config.llm.api_key == "sk-finta"
    assert config.llm.in_locale is False


def test_ollama_non_richiede_chiave(scrivi_env) -> None:
    config = carica(scrivi_env(**MINIMI))
    assert config.llm.api_key is None
    assert config.llm.in_locale is True


# --------------------------------------------------------------------------- #
# Segreti e immutabilità
# --------------------------------------------------------------------------- #


def test_la_password_non_compare_mai_nel_riepilogo(scrivi_env) -> None:
    """Il riepilogo finisce nel log d'avvio: deve essere sicuro da condividere."""
    config = carica(scrivi_env(**{**MINIMI, "DB_PASSWORD": "password_segretissima"}))
    riepilogo = config.riepilogo()

    assert "password_segretissima" not in riepilogo
    assert "***" in riepilogo


def test_la_chiave_api_non_compare_nel_riepilogo(scrivi_env) -> None:
    config = carica(scrivi_env(**MINIMI, LLM_PROVIDER="openrouter", LLM_API_KEY="sk-vera"))
    assert "sk-vera" not in config.riepilogo()


def test_la_configurazione_e_immutabile(scrivi_env) -> None:
    """Una sola verità: se serve cambiarla si modifica `.env` e si riavvia."""
    config = carica(scrivi_env(**MINIMI))
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.database.host = "altro"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Precedenza e cache
# --------------------------------------------------------------------------- #


def test_lambiente_ha_la_precedenza_sul_file(scrivi_env, monkeypatch) -> None:
    """In Docker e in CI le variabili arrivano dall'ambiente, non da `.env`."""
    monkeypatch.setenv("DB_NAME", "da_ambiente")
    config = carica(scrivi_env(**{**MINIMI, "DB_NAME": "da_file"}))
    assert config.database.nome == "da_ambiente"


def test_ottieni_legge_una_volta_sola(monkeypatch) -> None:
    """`ottieni()` si può chiamare ovunque senza costo: la cache lo garantisce."""
    for chiave, valore in MINIMI.items():
        monkeypatch.setenv(chiave, valore)
    ottieni.cache_clear()

    primo = ottieni()
    secondo = ottieni()

    assert isinstance(primo, Config)
    assert primo is secondo


# --------------------------------------------------------------------------- #
# B-01 · I segreti non compaiono nelle rappresentazioni automatiche
# --------------------------------------------------------------------------- #

PASSWORD_DB = "P@ss-DB-SEGRETA-9f3"
PASSWORD_ROOT = "ROOT-SEGRETA-5d2"
CHIAVE_API = "sk-API-SEGRETA-7c1"
SEGRETI = (PASSWORD_DB, PASSWORD_ROOT, CHIAVE_API)


@pytest.fixture
def config_con_segreti(scrivi_env) -> Config:
    return carica(
        scrivi_env(
            DB_NAME="beewatch_test",
            DB_USER="tester",
            DB_PASSWORD=PASSWORD_DB,
            DB_ROOT_PASSWORD=PASSWORD_ROOT,
            LLM_PROVIDER="openrouter",
            LLM_API_KEY=CHIAVE_API,
        )
    )


def _rappresentazioni(c: Config) -> dict[str, str]:
    """Tutti i modi in cui un oggetto di configurazione può finire in un testo."""
    return {
        "repr(Config)": repr(c),
        "str(Config)": str(c),
        "f-string Config": f"{c}",
        "%s Config": "%s" % (c,),  # noqa: UP031
        "repr(lista)": repr([c]),
        "repr(database)": repr(c.database),
        "str(database)": str(c.database),
        "repr(llm)": repr(c.llm),
        "str(llm)": str(c.llm),
        "riepilogo": c.riepilogo(),
        "descrizione database": c.database.descrizione(),
        "descrizione llm": c.llm.descrizione(),
    }


@pytest.mark.parametrize("segreto", SEGRETI, ids=["password_db", "password_root", "api_key"])
def test_nessun_segreto_in_nessuna_rappresentazione(config_con_segreti, segreto: str) -> None:
    for dove, testo in _rappresentazioni(config_con_segreti).items():
        assert segreto not in testo, f"«{segreto}» compare in: {dove}"


def test_la_rappresentazione_resta_utile(config_con_segreti) -> None:
    """Nascondere i segreti non deve svuotare il repr: il resto si vede ancora."""
    testo = repr(config_con_segreti)
    assert "beewatch_test" in testo
    assert "tester" in testo
    assert "openrouter" in testo


def test_i_segreti_restano_leggibili_dal_codice(config_con_segreti) -> None:
    """`repr=False` nasconde, non cancella: la connessione deve poter usare la password."""
    assert config_con_segreti.database.password == PASSWORD_DB
    assert config_con_segreti.llm.api_key == CHIAVE_API


def test_loggare_la_configurazione_non_espone_i_segreti(config_con_segreti, caplog) -> None:
    """Lo sbaglio più comune: `logger.info("cfg=%s", cfg)` durante il debug."""
    logger = logging.getLogger("prova_segreti")
    with caplog.at_level(logging.DEBUG, logger="prova_segreti"):
        logger.info("cfg=%s", config_con_segreti)
        logger.debug("cfg=%r", config_con_segreti.database)
        logger.warning("llm=%r", config_con_segreti.llm)

    assert "cfg=" in caplog.text  # il log è stato davvero scritto
    for segreto in SEGRETI:
        assert segreto not in caplog.text


def test_il_nome_di_un_futuro_campo_segreto_non_resta_visibile() -> None:
    """Guardia per chi aggiunge un segreto in futuro e dimentica `repr=False`.

    Controlla per nome: ogni campo che suona come un segreto deve avere
    `repr=False`. Il controllo sui campi trovati evita che il test diventi
    vuoto se qualcuno rinomina i campi.
    """
    parole_sensibili = ("password", "api_key", "apikey", "token", "secret", "chiave")
    sensibili = [
        (classe.__name__, campo)
        for classe in (ConfigDatabase, ConfigLLM, Config)
        for campo in dataclasses.fields(classe)
        if any(parola in campo.name.lower() for parola in parole_sensibili)
    ]

    assert {campo.name for _, campo in sensibili} >= {"password", "api_key"}
    visibili = [f"{classe}.{campo.name}" for classe, campo in sensibili if campo.repr]
    assert visibili == [], f"campi sensibili con repr attivo: {visibili}"


def test_i_segreti_non_compaiono_nel_messaggio_di_errore(scrivi_env) -> None:
    """Un errore di configurazione finisce a video: niente segreti, anche con altri errori."""
    percorso = scrivi_env(
        DB_NAME="x",
        DB_USER="y",
        DB_PASSWORD=PASSWORD_DB,
        DB_ROOT_PASSWORD=PASSWORD_ROOT,
        DB_PORT="non_un_numero",
        LLM_PROVIDER="openrouter",
        LLM_API_KEY=CHIAVE_API,
        LLM_TIMEOUT=1,
        LOG_LEVEL="VERBOSE",
    )
    with pytest.raises(ConfigError) as info:
        carica(percorso)

    assert "3 problema/i" in str(info.value)  # gli errori ci sono davvero
    for segreto in SEGRETI:
        assert segreto not in str(info.value)
        assert segreto not in repr(info.value)


def test_segreti_mancanti_sono_segnalati_per_nome(scrivi_env) -> None:
    """Il messaggio nomina la variabile, mai il valore (qui: password di soli spazi)."""
    with pytest.raises(ConfigError) as info:
        carica(scrivi_env(DB_NAME="x", DB_USER="y", DB_PASSWORD="   ", LLM_PROVIDER="openrouter"))
    messaggio = str(info.value)
    assert "DB_PASSWORD" in messaggio
    assert "LLM_API_KEY" in messaggio


# --------------------------------------------------------------------------- #
# B-25 · Whitespace: si pulisce il testo semplice, non i segreti
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "variabile,leggi",
    [
        ("DB_HOST", lambda c: c.database.host),
        ("DB_NAME", lambda c: c.database.nome),
        ("DB_USER", lambda c: c.database.utente),
        ("LLM_MODEL", lambda c: c.llm.modello),
    ],
)
def test_i_valori_semplici_perdono_gli_spazi_attorno(
    monkeypatch, scrivi_env, variabile: str, leggi
) -> None:
    """Uno spazio finale copiato per sbaglio non deve diventare parte del nome host."""
    monkeypatch.setenv(variabile, "  valore  ")
    config = carica(scrivi_env(**{k: v for k, v in MINIMI.items() if k != variabile}))
    assert leggi(config) == "valore"


@pytest.mark.parametrize(
    "password",
    [
        "  con spazi attorno  ",
        "finale ",
        " iniziale",
        "interno con spazi",
        'a#b"c\\',
        "password\n",
        "password\r\n",
    ],
)
def test_la_password_non_viene_modificata(monkeypatch, scrivi_env, password: str) -> None:
    """Dall'ambiente il valore arriva esattamente com'è, a-capo finale compreso.

    È la politica scelta: nessun `strip()` sui segreti. Un `\\n` in fondo a una
    variabile d'ambiente è quindi parte della password.
    """
    monkeypatch.setenv("DB_PASSWORD", password)
    config = carica(scrivi_env(DB_NAME="x", DB_USER="y"))
    assert config.database.password == password


def test_la_chiave_api_non_viene_modificata(monkeypatch, scrivi_env) -> None:
    monkeypatch.setenv("LLM_API_KEY", " sk-con-spazi ")
    config = carica(scrivi_env(**MINIMI, LLM_PROVIDER="openrouter"))
    assert config.llm.api_key == " sk-con-spazi "


def test_nel_file_env_le_virgolette_conservano_gli_spazi(tmp_path) -> None:
    """La sintassi di `.env` decide cosa è spazio «di sintassi» e cosa è valore."""
    percorso = tmp_path / "virgolette.env"
    percorso.write_text(
        'DB_NAME=x\nDB_USER=y\nDB_PASSWORD="  fra virgolette  "\n', encoding="utf-8"
    )
    assert carica(percorso).database.password == "  fra virgolette  "


def test_nel_file_env_senza_virgolette_gli_spazi_sono_sintassi(tmp_path) -> None:
    percorso = tmp_path / "semplice.env"
    percorso.write_text("DB_NAME=x\nDB_USER=y\nDB_PASSWORD=   pw   \n", encoding="utf-8")
    assert carica(percorso).database.password == "pw"


@pytest.mark.parametrize(
    "contenuto,atteso",
    [
        pytest.param(b"DB_PASSWORD=password\n", "password", id="senza-virgolette-lf"),
        pytest.param(b"DB_PASSWORD=password\r\n", "password", id="senza-virgolette-crlf"),
        pytest.param(b'DB_PASSWORD="password\\n"\n', "password\n", id="virgolette-escape-n"),
        pytest.param(b'DB_PASSWORD="password\\r\\n"\n', "password\r\n", id="virgolette-escape-rn"),
        pytest.param(b'DB_PASSWORD="password\n"\n', "password\n", id="virgolette-a-capo-reale"),
    ],
)
def test_nel_file_env_il_newline_segue_la_sintassi(tmp_path, contenuto: bytes, atteso: str) -> None:
    """Il terminatore di riga non è parte della password; un `\\n` fra virgolette sì."""
    percorso = tmp_path / "newline.env"
    percorso.write_bytes(b"DB_NAME=n\nDB_USER=u\n" + contenuto)

    assert carica(percorso).database.password == atteso


@pytest.mark.parametrize("valore", ["", " ", "   ", "\t"])
def test_password_vuota_o_di_soli_spazi_e_mancante(monkeypatch, scrivi_env, valore: str) -> None:
    monkeypatch.setenv("DB_PASSWORD", valore)
    with pytest.raises(ConfigError, match="DB_PASSWORD"):
        carica(scrivi_env(DB_NAME="x", DB_USER="y"))


@pytest.mark.parametrize("valore", ["", "   "])
def test_chiave_vuota_o_di_soli_spazi_con_ollama_vale_nessuna_chiave(
    monkeypatch, scrivi_env, valore: str
) -> None:
    monkeypatch.setenv("LLM_API_KEY", valore)
    assert carica(scrivi_env(**MINIMI)).llm.api_key is None


def test_chiave_di_soli_spazi_con_openrouter_e_mancante(monkeypatch, scrivi_env) -> None:
    monkeypatch.setenv("LLM_API_KEY", "   ")
    with pytest.raises(ConfigError, match="LLM_API_KEY"):
        carica(scrivi_env(**MINIMI, LLM_PROVIDER="openrouter"))


# --------------------------------------------------------------------------- #
# B-09 · MODEL_PATH
# --------------------------------------------------------------------------- #

PREDEFINITO = ("models", "produzione_v1.joblib")


@pytest.mark.parametrize(
    "scritto,atteso",
    [
        pytest.param(None, lambda r: r.joinpath(*PREDEFINITO), id="assente"),
        pytest.param("", lambda r: r.joinpath(*PREDEFINITO), id="vuota"),
        pytest.param("   ", lambda r: r.joinpath(*PREDEFINITO), id="solo-spazi"),
        pytest.param("models/v2.joblib", lambda r: r / "models" / "v2.joblib", id="relativo"),
        pytest.param("  models/v2.joblib  ", lambda r: r / "models" / "v2.joblib", id="spazi"),
        pytest.param("./models/v2.joblib", lambda r: r / "models" / "v2.joblib", id="punto"),
        pytest.param("models/../altro/v2.joblib", lambda r: r / "altro" / "v2.joblib", id="dotdot"),
        pytest.param(
            "../fuori/v2.joblib", lambda r: r.parent / "fuori" / "v2.joblib", id="dotdot-esterno"
        ),
    ],
)
def test_model_path_relativo(monkeypatch, scrivi_env, ambiente_pulito, scritto, atteso) -> None:
    """Un percorso relativo parte dalla radice del progetto ed esce già normalizzato."""
    if scritto is not None:
        monkeypatch.setenv("MODEL_PATH", scritto)

    percorso = carica(scrivi_env(**MINIMI)).percorso_modello

    assert percorso == atteso(ambiente_pulito)
    assert percorso.is_absolute()
    assert ".." not in percorso.parts


def test_model_path_assoluto_resta_com_e(monkeypatch, scrivi_env, tmp_path) -> None:
    assoluto = tmp_path / "esterno" / "modello.joblib"
    monkeypatch.setenv("MODEL_PATH", str(assoluto))
    assert carica(scrivi_env(**MINIMI)).percorso_modello == assoluto


def test_model_path_assoluto_con_dotdot_viene_normalizzato(
    monkeypatch, scrivi_env, tmp_path
) -> None:
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "a" / ".." / "b" / "modello.joblib"))
    assert carica(scrivi_env(**MINIMI)).percorso_modello == tmp_path / "b" / "modello.joblib"


def test_model_path_vuoto_nel_file_env_usa_il_predefinito(scrivi_env, ambiente_pulito) -> None:
    """`MODEL_PATH=` lasciato vuoto in `.env` non deve puntare alla cartella del progetto."""
    config = carica(scrivi_env(**MINIMI, MODEL_PATH=""))
    assert config.percorso_modello == ambiente_pulito.joinpath(*PREDEFINITO)
    assert config.percorso_modello != ambiente_pulito


def test_model_path_non_richiede_che_il_file_esista(monkeypatch, scrivi_env, tmp_path) -> None:
    """Il modello nasce in M4-T7: la configurazione deve reggere anche senza il file."""
    inesistente = tmp_path / "ancora" / "da_creare.joblib"
    monkeypatch.setenv("MODEL_PATH", str(inesistente))

    assert carica(scrivi_env(**MINIMI)).percorso_modello == inesistente
    assert not inesistente.parent.exists()


# --------------------------------------------------------------------------- #
# B-23 / B-24 · Codifica del file .env
# --------------------------------------------------------------------------- #

TESTO_ENV = f"DB_NAME=apiàrio\nDB_USER=mario\nDB_PASSWORD={PASSWORD_DB}\n"


def _scrivi_byte(tmp_path: Path, contenuto: bytes) -> Path:
    percorso = tmp_path / "codifica.env"
    percorso.write_bytes(contenuto)
    return percorso


def test_env_utf8_con_accenti(tmp_path) -> None:
    config = carica(_scrivi_byte(tmp_path, TESTO_ENV.encode("utf-8")))
    assert config.database.nome == "apiàrio"
    assert config.database.password == PASSWORD_DB


@pytest.mark.parametrize("a_capo", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_env_utf8_con_bom_non_perde_la_prima_variabile(tmp_path, a_capo: str) -> None:
    """Blocco note di Windows salva con BOM e CRLF: DB_NAME, la prima riga, deve contare."""
    testo = TESTO_ENV.replace("\n", a_capo)
    config = carica(_scrivi_byte(tmp_path, codecs.BOM_UTF8 + testo.encode("utf-8")))

    assert config.database.nome == "apiàrio"
    assert config.database.utente == "mario"
    assert config.database.password == PASSWORD_DB


def test_env_con_bom_e_prima_variabile_facoltativa(tmp_path) -> None:
    """Il caso peggiore: la prima riga è DB_HOST, che ha un predefinito e non avvisa."""
    contenuto = codecs.BOM_UTF8 + b"DB_HOST=db.example.com\nDB_NAME=x\nDB_USER=y\nDB_PASSWORD=z\n"
    assert carica(_scrivi_byte(tmp_path, contenuto)).database.host == "db.example.com"


@pytest.mark.parametrize(
    "contenuto",
    [
        pytest.param(codecs.BOM_UTF16_LE + TESTO_ENV.encode("utf-16-le"), id="utf16-le-bom"),
        pytest.param(codecs.BOM_UTF16_BE + TESTO_ENV.encode("utf-16-be"), id="utf16-be-bom"),
        pytest.param(TESTO_ENV.encode("utf-16-le"), id="utf16-le-senza-bom"),
        pytest.param(TESTO_ENV.encode("utf-16-be"), id="utf16-be-senza-bom"),
        pytest.param(codecs.BOM_UTF32_LE + TESTO_ENV.encode("utf-32-le"), id="utf32-le-bom"),
        # Lettere senza byte NUL (U+0141): qui il riconoscimento spetta solo al BOM.
        pytest.param(codecs.BOM_UTF16_LE + "ŁŁŁ".encode("utf-16-le"), id="utf16-le-bom-senza-nul"),
        pytest.param(codecs.BOM_UTF16_BE + "ŁŁŁ".encode("utf-16-be"), id="utf16-be-bom-senza-nul"),
    ],
)
def test_env_utf16_da_errore_chiaro(tmp_path, contenuto: bytes) -> None:
    """PowerShell `>` produce UTF-16: l'utente deve capire cosa fare, senza traceback."""
    percorso = _scrivi_byte(tmp_path, contenuto)

    with pytest.raises(ConfigError) as info:
        carica(percorso)

    messaggio = str(info.value)
    assert "UTF-16" in messaggio
    assert "UTF-8" in messaggio
    assert str(percorso) in messaggio
    assert PASSWORD_DB not in messaggio
    assert info.value.__cause__ is None  # nessuna eccezione di sistema concatenata
    assert info.value.__context__ is None


def test_env_non_utf8_da_errore_chiaro_senza_contenuto(tmp_path) -> None:
    """Latin-1 salvato per errore: il messaggio non deve riportare byte del file."""
    contenuto = f"DB_NAME=apiàrio\nDB_PASSWORD={PASSWORD_DB}\n".encode("latin-1")
    percorso = _scrivi_byte(tmp_path, contenuto)

    with pytest.raises(ConfigError) as info:
        carica(percorso)

    messaggio = str(info.value)
    assert "UTF-8" in messaggio
    assert str(percorso) in messaggio
    assert PASSWORD_DB not in messaggio
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__


def test_env_assente_non_e_un_errore(monkeypatch, tmp_path) -> None:
    """In Docker e in CI non c'è `.env`: le variabili arrivano dall'ambiente."""
    for chiave, valore in MINIMI.items():
        monkeypatch.setenv(chiave, valore)
    assert carica(tmp_path / "non_esiste.env").database.nome == "beewatch_test"


def test_env_vuoto_elenca_le_variabili_mancanti(tmp_path) -> None:
    with pytest.raises(ConfigError, match="3 problema/i"):
        carica(_scrivi_byte(tmp_path, b""))


def test_env_illeggibile_da_errore_applicativo(tmp_path) -> None:
    """Una cartella al posto del file: l'errore di sistema diventa un ConfigError."""
    cartella = tmp_path / "finta.env"
    cartella.mkdir()

    with pytest.raises(ConfigError, match="Impossibile leggere") as info:
        carica(cartella)

    assert str(cartella) in str(info.value)
    assert not isinstance(info.value, OSError)


@pytest.mark.parametrize(
    "errore,atteso",
    [
        (OSError(5, "Errore di I/O"), "Errore di I/O"),
        (OSError("senza codice di sistema"), "OSError"),
    ],
    ids=["con-strerror", "senza-strerror"],
)
def test_env_errore_di_io_qualsiasi_da_errore_applicativo(
    monkeypatch, tmp_path, errore: OSError, atteso: str
) -> None:
    """Non solo i permessi: qualunque OSError in lettura diventa un ConfigError."""

    def _fallisce(self: Path) -> bytes:
        raise errore

    monkeypatch.setattr(Path, "read_bytes", _fallisce)

    with pytest.raises(ConfigError, match="Impossibile leggere") as info:
        carica(tmp_path / "qualunque.env")

    assert atteso in str(info.value)
    assert info.value.__cause__ is None


# --------------------------------------------------------------------------- #
# B-05 · I test non dipendono dal `.env` né dall'ambiente del computer
# --------------------------------------------------------------------------- #


def test_la_radice_dei_test_non_e_quella_del_progetto(ambiente_pulito) -> None:
    radice_vera = Path(__file__).resolve().parents[1]
    assert modulo_config.RADICE == ambiente_pulito
    assert modulo_config.RADICE != radice_vera


def test_senza_env_e_senza_variabili_la_configurazione_fallisce() -> None:
    """Anche sul computer di chi ha un `.env` completo: la radice dei test è vuota."""
    with pytest.raises(ConfigError, match="3 problema/i"):
        carica()


def test_il_percorso_predefinito_e_il_env_della_radice(ambiente_pulito) -> None:
    (ambiente_pulito / ".env").write_text(
        "DB_NAME=dalla_radice\nDB_USER=u\nDB_PASSWORD=p\n", encoding="utf-8"
    )
    assert carica().database.nome == "dalla_radice"


# --------------------------------------------------------------------------- #
# Funzione condivisa con logging_config
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "grezzo,atteso",
    [("info", "INFO"), (" Warning ", "WARNING"), ("DEBUG", "DEBUG"), ("verbose", None), ("", None)],
)
def test_forma_canonica(grezzo: str, atteso: str | None) -> None:
    assert forma_canonica(grezzo, modulo_config.LIVELLI_LOG) == atteso
