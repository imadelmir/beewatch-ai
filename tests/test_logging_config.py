"""Test della configurazione del logging (M1-T4).

Il test più importante è quello sull'idempotenza: Streamlit riesegue lo script
a ogni interazione, e un `configura()` non protetto moltiplicherebbe gli
handler — quindi le righe di log — a ogni click dell'utente.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from beewatch import logging_config
from beewatch.exceptions import ConfigError
from beewatch.logging_config import NOME_LOGGER, azzera, configura, ottieni_logger

pytestmark = pytest.mark.usefixtures("logging_azzerato")


def nostri(logger: logging.Logger) -> list[logging.Handler]:
    """Solo gli handler installati da BeeWatch.

    pytest e Streamlit aggiungono i propri handler allo stesso logger: contarli
    tutti renderebbe i test dipendenti da strumenti esterni.
    """
    return logging_config._nostri_handler(logger)


def test_configura_installa_terminale_e_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(logging_config, "CARTELLA_LOG", tmp_path / "logs")
    monkeypatch.setattr(logging_config, "FILE_LOG", tmp_path / "logs" / "beewatch.log")

    radice = configura(livello="INFO")

    assert len(nostri(radice)) == 2
    assert (tmp_path / "logs" / "beewatch.log").exists()


def test_senza_file_resta_solo_il_terminale() -> None:
    radice = configura(livello="INFO", su_file=False)
    assert len(nostri(radice)) == 1
    assert isinstance(nostri(radice)[0], logging.StreamHandler)


def test_configura_e_idempotente() -> None:
    """Dieci riesecuzioni di Streamlit non devono produrre dieci handler."""
    radice = configura(livello="INFO", su_file=False)
    for _ in range(10):
        configura(livello="INFO", su_file=False)
    assert len(nostri(radice)) == 1


def test_il_livello_richiesto_viene_applicato() -> None:
    radice = configura(livello="WARNING", su_file=False)
    assert radice.level == logging.WARNING
    assert radice.isEnabledFor(logging.WARNING)
    assert not radice.isEnabledFor(logging.INFO)


def test_il_livello_arriva_dalla_configurazione(monkeypatch) -> None:
    """Senza argomento, il livello è quello di LOG_LEVEL nel file `.env`."""
    finta = type("FintaConfig", (), {"livello_log": "ERROR"})()
    monkeypatch.setattr(logging_config, "ottieni", lambda: finta)

    assert configura(su_file=False).level == logging.ERROR


def test_non_propaga_al_logger_root() -> None:
    """Streamlit configura il root: propagando, ogni riga uscirebbe due volte."""
    assert configura(livello="INFO", su_file=False).propagate is False


def test_ottieni_logger_restituisce_un_figlio() -> None:
    configura(livello="INFO", su_file=False)
    figlio = ottieni_logger("beewatch.database.repository")

    assert figlio.name.startswith(NOME_LOGGER)
    assert figlio.getEffectiveLevel() == logging.INFO


def test_il_messaggio_finisce_nel_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(logging_config, "CARTELLA_LOG", tmp_path / "logs")
    monkeypatch.setattr(logging_config, "FILE_LOG", tmp_path / "logs" / "beewatch.log")
    configura(livello="INFO")

    ottieni_logger("beewatch.ml.previsione").warning("modello assente")
    for handler in nostri(logging.getLogger(NOME_LOGGER)):
        handler.flush()

    contenuto = (tmp_path / "logs" / "beewatch.log").read_text(encoding="utf-8")
    assert "modello assente" in contenuto
    assert "WARNING" in contenuto
    assert "beewatch.ml.previsione" in contenuto


def test_le_librerie_rumorose_sono_silenziate() -> None:
    configura(livello="DEBUG", su_file=False)
    for nome in logging_config.LIBRERIE_SILENZIATE:
        assert logging.getLogger(nome).level == logging.WARNING


# --------------------------------------------------------------------------- #
# B-21 · Livello di log passato a configura()
# --------------------------------------------------------------------------- #


def stato_iniziale(logger: logging.Logger) -> tuple[int, bool, list[logging.Handler]]:
    return logger.level, logger.propagate, nostri(logger)


@pytest.mark.parametrize(
    "scritto,atteso",
    [
        ("DEBUG", logging.DEBUG),
        ("INFO", logging.INFO),
        ("WARNING", logging.WARNING),
        ("ERROR", logging.ERROR),
        ("CRITICAL", logging.CRITICAL),
        ("info", logging.INFO),
        ("Warning", logging.WARNING),
        ("  error  ", logging.ERROR),
    ],
)
def test_livello_valido_in_qualsiasi_scrittura(scritto: str, atteso: int) -> None:
    """Stesse regole di LOG_LEVEL in `.env`: maiuscole e spazi non contano."""
    assert configura(livello=scritto, su_file=False).level == atteso


@pytest.mark.parametrize("scritto", ["VERBOSE", "TRACE", "20", "inf0", "NOTSET", "WARN"])
def test_livello_non_valido_da_config_error(scritto: str) -> None:
    """Prima: `ValueError: Unknown level` dal modulo logging, senza spiegazioni."""
    radice = logging.getLogger(NOME_LOGGER)
    prima = stato_iniziale(radice)

    with pytest.raises(ConfigError) as info:
        configura(livello=scritto, su_file=False)

    messaggio = str(info.value)
    assert scritto in messaggio
    assert "DEBUG" in messaggio  # elenca i valori ammessi
    assert not isinstance(info.value, ValueError)
    assert stato_iniziale(radice) == prima  # nessuna configurazione a metà


@pytest.mark.parametrize("vuoto", ["", "   "])
def test_livello_vuoto_equivale_a_non_indicato(monkeypatch, vuoto: str) -> None:
    """Come `LOG_LEVEL=` vuoto in `.env`: si usa il livello della configurazione."""
    finta = type("FintaConfig", (), {"livello_log": "ERROR"})()
    monkeypatch.setattr(logging_config, "ottieni", lambda: finta)

    assert configura(livello=vuoto, su_file=False).level == logging.ERROR


def test_livello_non_valido_e_segnalato_anche_a_logging_gia_configurato() -> None:
    """Un errore di battitura non deve passare inosservato alla seconda chiamata."""
    configura(livello="INFO", su_file=False)
    with pytest.raises(ConfigError):
        configura(livello="VERBOSE", su_file=False)


# --------------------------------------------------------------------------- #
# B-22 · Cartella e file di log non utilizzabili
# --------------------------------------------------------------------------- #


def punta_i_log_su(monkeypatch, cartella: Path, file: Path | None = None) -> Path:
    file = file or cartella / "beewatch.log"
    monkeypatch.setattr(logging_config, "CARTELLA_LOG", cartella)
    monkeypatch.setattr(logging_config, "FILE_LOG", file)
    return file


def test_cartella_annidata_inesistente_viene_creata(tmp_path: Path, monkeypatch) -> None:
    file = punta_i_log_su(monkeypatch, tmp_path / "a" / "b" / "logs")

    radice = configura(livello="INFO")
    radice.warning("scritto")
    for handler in nostri(radice):
        handler.flush()

    assert "scritto" in file.read_text(encoding="utf-8")


def test_cartella_gia_esistente_va_bene(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "logs").mkdir()
    punta_i_log_su(monkeypatch, tmp_path / "logs")

    assert len(nostri(configura(livello="INFO"))) == 2


def _prova_errore_di_log(monkeypatch, cartella: Path, file: Path | None = None) -> ConfigError:
    """Configura con un percorso inutilizzabile e controlla che non resti nulla a metà."""
    punta_i_log_su(monkeypatch, cartella, file)
    radice = logging.getLogger(NOME_LOGGER)
    prima = stato_iniziale(radice)

    with pytest.raises(ConfigError) as info:
        configura(livello="INFO")

    assert not isinstance(info.value, OSError)
    assert isinstance(info.value.__cause__, OSError)  # il dettaglio tecnico resta nella catena
    assert stato_iniziale(radice) == prima  # niente console installata «a metà»
    return info.value


def test_cartella_sotto_un_file_da_config_error(tmp_path: Path, monkeypatch) -> None:
    """`mkdir` fallisce perché un pezzo del percorso è un file, non una cartella."""
    (tmp_path / "ostacolo").write_text("sono un file")
    cartella = tmp_path / "ostacolo" / "logs"

    errore = _prova_errore_di_log(monkeypatch, cartella)

    assert str(cartella / "beewatch.log") in str(errore)
    assert "log" in str(errore).lower()


def test_cartella_dei_log_che_e_un_file_da_config_error(tmp_path: Path, monkeypatch) -> None:
    ostacolo = tmp_path / "logs"
    ostacolo.write_text("sono un file")

    errore = _prova_errore_di_log(monkeypatch, ostacolo)

    assert str(ostacolo) in str(errore)


def test_file_di_log_che_e_una_cartella_da_config_error(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "logs").mkdir()
    file = tmp_path / "logs" / "beewatch.log"
    file.mkdir()  # al posto del file c'è una cartella

    errore = _prova_errore_di_log(monkeypatch, tmp_path / "logs", file)

    assert str(file) in str(errore)


def test_dopo_un_errore_di_log_si_puo_riprovare(tmp_path: Path, monkeypatch) -> None:
    """Lo stato non resta sporco: sistemato il problema, `configura()` funziona."""
    (tmp_path / "ostacolo").write_text("sono un file")
    punta_i_log_su(monkeypatch, tmp_path / "ostacolo" / "logs")
    with pytest.raises(ConfigError):
        configura(livello="INFO")

    punta_i_log_su(monkeypatch, tmp_path / "logs")

    assert len(nostri(configura(livello="INFO"))) == 2


def test_senza_file_il_percorso_dei_log_non_viene_toccato(tmp_path: Path, monkeypatch) -> None:
    """`su_file=False` non deve nemmeno guardare la cartella, anche se è inutilizzabile."""
    (tmp_path / "ostacolo").write_text("sono un file")
    punta_i_log_su(monkeypatch, tmp_path / "ostacolo" / "logs")

    assert len(nostri(configura(livello="INFO", su_file=False))) == 1


# --------------------------------------------------------------------------- #
# B-04 · azzera() ripristina lo stato, non solo gli handler
# --------------------------------------------------------------------------- #


def test_azzera_ripristina_handler_livello_e_propagate() -> None:
    radice = logging.getLogger(NOME_LOGGER)
    prima = stato_iniziale(radice)

    configura(livello="DEBUG", su_file=False)
    assert stato_iniziale(radice) != prima  # la configurazione ha davvero cambiato qualcosa
    azzera()

    assert nostri(radice) == []
    assert radice.level == logging.NOTSET
    assert radice.propagate is True
    assert stato_iniziale(radice) == prima


def test_azzera_ripristina_i_livelli_delle_librerie_silenziate() -> None:
    libreria = logging.getLogger("urllib3")
    originale = libreria.level
    try:
        libreria.setLevel(logging.ERROR)
        configura(livello="DEBUG", su_file=False)
        assert libreria.level == logging.WARNING

        azzera()

        assert libreria.level == logging.ERROR  # com'era prima di configura()
    finally:
        libreria.setLevel(originale)


def test_azzera_non_riapplica_livelli_vecchi_alla_chiamata_successiva() -> None:
    """Dopo il ripristino la memoria è vuota: un secondo `azzera()` non tocca più le librerie."""
    libreria = logging.getLogger("urllib3")
    originale = libreria.level
    try:
        configura(livello="DEBUG", su_file=False)
        azzera()
        libreria.setLevel(logging.INFO)  # lo cambia qualcun altro, dopo di noi

        azzera()

        assert libreria.level == logging.INFO
    finally:
        libreria.setLevel(originale)


def test_azzera_chiude_il_file_di_log(tmp_path: Path, monkeypatch) -> None:
    """Un file di log rimasto aperto blocca la pulizia delle cartelle temporanee su Windows."""
    file = tmp_path / "logs" / "beewatch.log"
    monkeypatch.setattr(logging_config, "CARTELLA_LOG", file.parent)
    monkeypatch.setattr(logging_config, "FILE_LOG", file)
    radice = configura(livello="INFO")
    su_disco = next(h for h in nostri(radice) if isinstance(h, logging.FileHandler))
    assert su_disco.stream is not None  # aperto

    azzera()

    assert su_disco.stream is None  # chiuso
    file.unlink()  # su Windows fallirebbe con il file ancora aperto


def test_azzera_non_tocca_gli_handler_altrui() -> None:
    radice = logging.getLogger(NOME_LOGGER)
    altrui = logging.NullHandler()
    radice.addHandler(altrui)
    try:
        configura(livello="INFO", su_file=False)
        azzera()
        assert altrui in radice.handlers
    finally:
        radice.removeHandler(altrui)


def test_azzera_senza_configura_e_innocua() -> None:
    radice = logging.getLogger(NOME_LOGGER)
    prima = stato_iniziale(radice)
    azzera()
    azzera()
    assert stato_iniziale(radice) == prima


def test_configura_azzera_configura_il_log_e_catturabile(caplog, capsys) -> None:
    """La sequenza che rompeva i test: dopo `azzera()` `caplog` non vedeva più nulla.

    Prima: `propagate` restava False, quindi i messaggi di `beewatch.*` non
    arrivavano al root, dove `caplog` ascolta. Ogni passaggio qui sotto
    verifica un messaggio realmente emesso e catturato.
    """
    figlio = ottieni_logger("beewatch.prova.reset")

    # 1. configura → azzera: il logger è tornato «normale» e caplog lo cattura.
    configura(livello="INFO", su_file=False)
    azzera()
    figlio.warning("dopo il primo azzera")
    assert "dopo il primo azzera" in caplog.text
    caplog.clear()

    # 2. configura di nuovo: gli handler tornano uno solo (nessun doppione)
    #    e il messaggio esce davvero sul terminale.
    radice = configura(livello="INFO", su_file=False)
    assert len(nostri(radice)) == 1
    capsys.readouterr()  # scarta l'output precedente
    figlio.warning("dopo la riconfigurazione")
    assert "dopo la riconfigurazione" in capsys.readouterr().out

    # 3. Con propagate=False (voluto) il root non riceve nulla: caplog va
    #    collegato al logger di pacchetto, e allora cattura di nuovo.
    assert caplog.text == ""
    radice.addHandler(caplog.handler)
    try:
        figlio.warning("catturato da caplog")
    finally:
        radice.removeHandler(caplog.handler)
    assert "catturato da caplog" in caplog.text

    # 4. azzera di nuovo: caplog torna a funzionare sul root, come all'inizio.
    azzera()
    caplog.clear()
    figlio.warning("dopo il secondo azzera")
    assert "dopo il secondo azzera" in caplog.text
