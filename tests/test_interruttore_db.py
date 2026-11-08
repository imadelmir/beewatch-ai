"""L'interruttore del database in `app/avvio.py` (M6-T9).

Con il server spento, la sidebar e il corpo della pagina leggevano ciascuno per conto suo e
ognuno ritentava la connessione: circa 30 secondi prima dell'errore. Dopo il primo errore *di
connessione* le altre letture devono fallire subito, con lo stesso messaggio; un errore di una
sola query no, e dopo la pausa si riprova davvero.
"""

from __future__ import annotations

from app_finta import APP, ApiariFinti, DashboardFinto, esegui, installa, servizi_finti, valori

from beewatch.exceptions import DatabaseError

SPENTO = "Il server MySQL non risponde."


class ApiariContati(ApiariFinti):
    def __init__(self, errore: Exception | None) -> None:
        super().__init__(errore=errore)
        self.letture = 0

    def elenca(self, utente_id: int):
        self.letture += 1
        return super().elenca(utente_id)


def prepara(app_pronta, monkeypatch, errore: Exception | None):
    apiari, dashboard = ApiariContati(errore), DashboardFinto(errore)
    installa(app_pronta, monkeypatch, servizi_finti(dashboard=dashboard, apiari=apiari))
    return apiari, dashboard


def test_con_il_server_spento_la_connessione_si_tenta_una_volta_sola(app_pronta, monkeypatch):
    apiari, dashboard = prepara(app_pronta, monkeypatch, DatabaseError(SPENTO, connessione=True))

    at = esegui(APP / "Home.py")

    assert not at.exception
    # la sidebar ci ha provato; la panoramica del corpo ha fallito subito, senza ritentare
    assert apiari.letture == 1 and dashboard.chiamate == 0
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**") and SPENTO in errore
    assert "**Database:** non raggiungibile" in valori(at.sidebar.caption)


def test_lerrore_di_una_sola_query_non_blocca_le_altre_letture(app_pronta, monkeypatch):
    apiari, dashboard = prepara(app_pronta, monkeypatch, DatabaseError("Query fallita."))

    esegui(APP / "Home.py")

    assert apiari.letture == 1 and dashboard.chiamate == 1  # ognuna ha provato davvero


def test_passata_la_pausa_si_riprova_davvero(app_pronta, monkeypatch):
    apiari, dashboard = prepara(app_pronta, monkeypatch, DatabaseError(SPENTO, connessione=True))
    esegui(APP / "Home.py")
    monkeypatch.setattr(app_pronta, "PAUSA_DOPO_ERRORE_DB_SECONDI", 0)

    esegui(APP / "Home.py")

    assert apiari.letture == 2 and dashboard.chiamate == 1


def test_una_lettura_riuscita_richiude_linterruttore(app_pronta, monkeypatch):
    apiari, dashboard = prepara(app_pronta, monkeypatch, DatabaseError(SPENTO, connessione=True))
    esegui(APP / "Home.py")
    monkeypatch.setattr(app_pronta, "PAUSA_DOPO_ERRORE_DB_SECONDI", 0)
    apiari.errore = dashboard.errore = None  # il server è tornato

    at = esegui(APP / "Home.py")

    assert not at.error
    assert app_pronta._ultimo_errore_db["errore"] is None
    monkeypatch.setattr(app_pronta, "PAUSA_DOPO_ERRORE_DB_SECONDI", 10)
    assert not esegui(APP / "Home.py").error  # nessun errore vecchio che torna


def test_svuotare_le_letture_richiude_linterruttore(app_pronta, monkeypatch):
    prepara(app_pronta, monkeypatch, DatabaseError(SPENTO, connessione=True))
    esegui(APP / "Home.py")
    assert app_pronta._ultimo_errore_db["errore"] is not None

    app_pronta.svuota_letture()

    assert app_pronta._ultimo_errore_db["errore"] is None
