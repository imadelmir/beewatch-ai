"""Test del controllo di salute del contenitore (B-12).

Niente rete e niente MySQL: `urlopen` e `mysql.connector.connect` sono sostituiti da
finti. Quello che si verifica è la *decisione* (sano / non sano, e perché) e che il
messaggio non contenga mai credenziali. La prova con Streamlit e MySQL veri sta in
`test_docker_stack.py`.
"""

from __future__ import annotations

import urllib.error

import mysql.connector
import pytest

from beewatch import healthcheck

PASSWORD = "PW-FINTA-hc-7Q"
UTENTE = "utente_finto_hc"
HOST = "host-finto-hc"


@pytest.fixture
def configurazione(monkeypatch) -> None:
    """La configurazione minima valida, con valori riconoscibili nei messaggi."""
    for nome, valore in {
        "DB_HOST": HOST,
        "DB_PORT": "3306",
        "DB_NAME": "beewatch_hc",
        "DB_USER": UTENTE,
        "DB_PASSWORD": PASSWORD,
    }.items():
        monkeypatch.setenv(nome, valore)


class RispostaFinta:
    def __init__(self, stato: int = 200) -> None:
        self.status = stato

    def __enter__(self) -> RispostaFinta:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class CursoreFinto:
    def __init__(self, errore: Exception | None = None) -> None:
        self.errore = errore
        self.query: list[str] = []

    def execute(self, sql: str) -> None:
        self.query.append(sql)
        if self.errore:
            raise self.errore

    def fetchall(self) -> list[tuple[int]]:
        return [(1,)]


class ConnessioneFinta:
    def __init__(self, errore_query: Exception | None = None) -> None:
        self.cursore = CursoreFinto(errore_query)
        self.chiusa = False

    def cursor(self) -> CursoreFinto:
        return self.cursore

    def close(self) -> None:
        self.chiusa = True


@pytest.fixture
def streamlit_su(monkeypatch):
    """Streamlit risponde 200."""
    chiamate: list[str] = []

    def _urlopen(url: str, timeout: float):
        chiamate.append(url)
        return RispostaFinta(200)

    monkeypatch.setattr(healthcheck.urllib.request, "urlopen", _urlopen)
    return chiamate


@pytest.fixture
def database_su(monkeypatch):
    """MySQL accetta la connessione. Restituisce (argomenti ricevuti, connessione)."""
    ricevuti: dict = {}
    connessione = ConnessioneFinta()

    def _connect(**argomenti):
        ricevuti.update(argomenti)
        return connessione

    monkeypatch.setattr(healthcheck.mysql.connector, "connect", _connect)
    return ricevuti, connessione


# --------------------------------------------------------------------------- #
# Sano
# --------------------------------------------------------------------------- #


def test_sano_se_config_streamlit_e_database_sono_a_posto(
    configurazione, streamlit_su, database_su, capsys
) -> None:
    ricevuti, connessione = database_su

    assert healthcheck.main() == 0

    assert capsys.readouterr().out.strip() == "OK"
    assert streamlit_su == [healthcheck.URL_STREAMLIT]
    assert connessione.cursore.query == ["SELECT 1"]  # legge soltanto
    assert connessione.chiusa


def test_si_connette_con_le_credenziali_dellapp_e_un_timeout(
    configurazione, streamlit_su, database_su
) -> None:
    ricevuti, _ = database_su

    healthcheck.main()

    assert ricevuti == {
        "host": HOST,
        "port": 3306,
        "user": UTENTE,
        "password": PASSWORD,
        "database": "beewatch_hc",
        "connection_timeout": healthcheck.TIMEOUT_SECONDI,
    }


# --------------------------------------------------------------------------- #
# Non sano: ogni causa ha il suo motivo
# --------------------------------------------------------------------------- #


def test_configurazione_errata_non_e_sana_e_non_tocca_ne_streamlit_ne_il_database(
    monkeypatch, streamlit_su, database_su, capsys
) -> None:
    """Senza DB_NAME/DB_USER/DB_PASSWORD (o con valori non validi) è inutile provare."""
    monkeypatch.setenv("DB_PORT", "non_un_numero")

    assert healthcheck.main() == 1

    assert "configurazione non valida" in capsys.readouterr().out
    assert streamlit_su == []
    assert database_su[0] == {}


def test_streamlit_che_non_risponde_non_e_sano(
    configurazione, monkeypatch, database_su, capsys
) -> None:
    def _rifiuta(url: str, timeout: float):
        raise urllib.error.URLError("connessione rifiutata")

    monkeypatch.setattr(healthcheck.urllib.request, "urlopen", _rifiuta)

    assert healthcheck.main() == 1

    assert "Streamlit non risponde" in capsys.readouterr().out
    assert database_su[0] == {}  # si ferma al primo problema


def test_streamlit_con_stato_diverso_da_200_non_e_sano(
    configurazione, monkeypatch, database_su, capsys
) -> None:
    monkeypatch.setattr(
        healthcheck.urllib.request, "urlopen", lambda url, timeout: RispostaFinta(503)
    )

    assert healthcheck.main() == 1

    assert "503" in capsys.readouterr().out


def test_streamlit_in_timeout_non_e_sano(configurazione, monkeypatch, database_su, capsys) -> None:
    def _lento(url: str, timeout: float):
        raise TimeoutError

    monkeypatch.setattr(healthcheck.urllib.request, "urlopen", _lento)

    assert healthcheck.main() == 1

    assert "Streamlit non risponde" in capsys.readouterr().out


@pytest.mark.parametrize(
    "errore,numero",
    [
        (mysql.connector.errors.InterfaceError("rifiutata", errno=2003), 2003),
        (mysql.connector.errors.ProgrammingError("access denied", errno=1045), 1045),
        (mysql.connector.errors.DatabaseError("db sconosciuto", errno=1049), 1049),
    ],
    ids=["db-spento", "password-errata", "database-inesistente"],
)
def test_database_non_raggiungibile_non_e_sano(
    configurazione, streamlit_su, monkeypatch, capsys, errore, numero
) -> None:
    def _fallisce(**_: object):
        raise errore

    monkeypatch.setattr(healthcheck.mysql.connector, "connect", _fallisce)

    assert healthcheck.main() == 1

    uscita = capsys.readouterr().out
    assert "database non raggiungibile" in uscita
    assert str(numero) in uscita


def test_database_che_non_esegue_query_non_e_sano_e_chiude_la_connessione(
    configurazione, streamlit_su, monkeypatch, capsys
) -> None:
    connessione = ConnessioneFinta(mysql.connector.errors.DatabaseError("x", errno=1142))
    monkeypatch.setattr(healthcheck.mysql.connector, "connect", lambda **_: connessione)

    assert healthcheck.main() == 1

    assert "non esegue query" in capsys.readouterr().out
    assert connessione.chiusa


def test_errore_del_driver_senza_numero_specifico_non_rompe_il_controllo(
    configurazione, streamlit_su, monkeypatch, capsys
) -> None:
    def _fallisce(**_: object):
        raise mysql.connector.Error("senza numero")

    monkeypatch.setattr(healthcheck.mysql.connector, "connect", _fallisce)

    assert healthcheck.main() == 1

    # Il driver mette -1 quando non c'è un numero: il controllo non deve rompersi.
    assert capsys.readouterr().out.startswith("KO: database non raggiungibile")


# --------------------------------------------------------------------------- #
# Sicurezza: nessuna credenziale nell'uscita
# --------------------------------------------------------------------------- #


def test_il_messaggio_non_contiene_mai_credenziali(configurazione, monkeypatch, capsys) -> None:
    """Il testo degli errori del driver cita utente, host e a volte la password.

    Ogni errore qui sotto le contiene tutte e tre: nessuna deve arrivare in uscita.
    """
    veleno = f"Access denied for user '{UTENTE}'@'{HOST}' (using password: {PASSWORD})"
    uscite: list[str] = []

    # 1. Streamlit giù, con un testo d'errore velenoso
    def _rifiuta(url: str, timeout: float):
        raise urllib.error.URLError(veleno)

    monkeypatch.setattr(healthcheck.urllib.request, "urlopen", _rifiuta)
    healthcheck.main()
    uscite.append(capsys.readouterr().out)

    # 2. Streamlit su, database che rifiuta con lo stesso testo
    monkeypatch.setattr(healthcheck.urllib.request, "urlopen", lambda url, timeout: RispostaFinta())

    def _nega(**_: object):
        raise mysql.connector.errors.ProgrammingError(veleno, errno=1045)

    monkeypatch.setattr(healthcheck.mysql.connector, "connect", _nega)
    healthcheck.main()
    uscite.append(capsys.readouterr().out)

    # 3. Connessione riuscita ma la query fallisce con lo stesso testo
    connessione = ConnessioneFinta(mysql.connector.errors.DatabaseError(veleno, errno=1142))
    monkeypatch.setattr(healthcheck.mysql.connector, "connect", lambda **_: connessione)
    healthcheck.main()
    uscite.append(capsys.readouterr().out)

    assert all(uscita.startswith("KO:") for uscita in uscite)
    for uscita in uscite:
        for segreto in (PASSWORD, UTENTE, HOST):
            assert segreto not in uscita


def test_il_modulo_si_lancia_come_comando(configurazione, monkeypatch, capsys) -> None:
    """`python -m beewatch.healthcheck` esce con il codice di main()."""
    import runpy
    import sys

    # Il modulo è già importato: lo si toglie per far eseguire runpy da zero, come fa
    # `python -m`, senza il RuntimeWarning «found in sys.modules».
    monkeypatch.delitem(sys.modules, "beewatch.healthcheck")
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda url, timeout: (_ for _ in ()).throw(OSError("giù"))
    )

    with pytest.raises(SystemExit) as uscita:
        runpy.run_module("beewatch.healthcheck", run_name="__main__")

    assert uscita.value.code == 1
    assert "Streamlit non risponde" in capsys.readouterr().out
