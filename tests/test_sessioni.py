"""«Ricordami»: la sessione del browser in un cookie, così ricaricare o cambiare tema non fa uscire.

Servizi con utenti e sessioni in memoria; l'app con AppTest (il cookie del browser si simula
sostituendo `avvio._cookie_sessione`); in fondo, il repository su MySQL vero.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta

import pytest
from accesso_finto import EMAIL_DEMO, GIRI_TEST, PASSWORD_DEMO, SessioniInMemoria, UtentiInMemoria
from anagrafica_finta import DATABASE_SPENTO, anagrafica_di_prova, ispezioni_di_prova
from app_finta import APP, DashboardFinto, PredittoreStub, installa
from preferenze_finte import PreferenzeInMemoria
from streamlit.testing.v1 import AppTest

from beewatch import sicurezza
from beewatch.database import Database
from beewatch.repositories_accesso import SessioniRepository
from beewatch.services import GIORNI_SESSIONE_RICORDATA, Servizi


@pytest.fixture(autouse=True)
def bcrypt_veloce(monkeypatch):
    monkeypatch.setattr(sicurezza, "GIRI", GIRI_TEST)


def servizi() -> tuple[Servizi, UtentiInMemoria, SessioniInMemoria]:
    utenti = UtentiInMemoria()
    sessioni = SessioniInMemoria(utenti)
    return Servizi(None, utenti=utenti, sessioni=sessioni), utenti, sessioni


# --------------------------------------------------------------------------- #
# Token e servizi
# --------------------------------------------------------------------------- #


def test_il_token_e_casuale_e_nel_database_va_solo_limpronta():
    a, b = sicurezza.nuovo_token(), sicurezza.nuovo_token()

    assert a != b and len(a) >= 43
    assert re.fullmatch(r"[0-9a-f]{64}", sicurezza.impronta_token(a))
    assert sicurezza.impronta_token(a) == sicurezza.impronta_token(a)


def test_una_sessione_aperta_si_riprende_e_si_chiude():
    s, _, sessioni = servizi()

    aperta = s.apri_sessione(1, ricorda=True)

    assert aperta.giorni_cookie == GIORNI_SESSIONE_RICORDATA
    assert aperta.token not in sessioni.righe  # salvata per impronta, mai il token
    assert s.riprendi_sessione(aperta.token).id == 1
    s.chiudi_sessione(aperta.token)
    assert s.riprendi_sessione(aperta.token) is None


def test_senza_ricordami_il_cookie_vale_finche_il_browser_e_aperto_e_al_massimo_un_giorno():
    s, _, sessioni = servizi()
    adesso = datetime(2026, 11, 14, 12, 0)

    aperta = s.apri_sessione(1, ricorda=False, adesso=adesso)

    assert aperta.giorni_cookie is None
    [riga] = sessioni.righe.values()
    assert riga["scade_il"] == adesso + timedelta(hours=24)


def test_una_sessione_scaduta_o_ignota_non_fa_entrare():
    s, _, _ = servizi()
    vecchia = s.apri_sessione(1, ricorda=True, adesso=datetime.now() - timedelta(days=31))

    assert s.riprendi_sessione(vecchia.token) is None
    assert s.riprendi_sessione("inventato") is None
    assert s.riprendi_sessione(None) is None and s.riprendi_sessione("") is None
    assert s.riprendi_sessione("x" * 500) is None


def test_un_account_disattivato_non_rientra_dal_cookie():
    s, utenti, _ = servizi()
    aperta = s.apri_sessione(1, ricorda=True)
    utenti.righe[1]["attivo"] = False

    assert s.riprendi_sessione(aperta.token) is None


def test_cambiare_la_password_chiude_le_sessioni_di_tutti_i_browser():
    s, _, _ = servizi()
    altro_browser = s.apri_sessione(1, ricorda=True)

    s.cambia_password(1, attuale=PASSWORD_DEMO, nuova="pappa-reale", conferma="pappa-reale")

    assert s.riprendi_sessione(altro_browser.token) is None


# --------------------------------------------------------------------------- #
# Nell'app
# --------------------------------------------------------------------------- #


class Ambiente:
    def __init__(self, utenti, sessioni, servizi):
        self.utenti, self.sessioni, self.servizi = utenti, sessioni, servizi


@pytest.fixture
def ambiente(app_pronta, monkeypatch) -> Ambiente:
    apiari, alveari = anagrafica_di_prova()
    utenti = UtentiInMemoria()
    sessioni = SessioniInMemoria(utenti)
    s = Servizi(None, utenti=utenti, sessioni=sessioni, apiari=apiari, alveari=alveari,
                ispezioni=ispezioni_di_prova(alveari), dashboard=DashboardFinto(),
                crea_predittore=PredittoreStub, preferenze=PreferenzeInMemoria())  # fmt: skip
    installa(app_pronta, monkeypatch, s)
    return Ambiente(utenti, sessioni, s)


def apri() -> AppTest:
    return AppTest.from_file(str(APP / "Home.py"), default_timeout=30).run()


def cookie_scritti(at: AppTest) -> list[str]:
    return [e.proto.body for e in at.get("html") if "document.cookie" in e.proto.body]


def accedi(at: AppTest, *, ricorda: bool) -> AppTest:
    at.text_input(key="accedi_email").input(EMAIL_DEMO)
    at.text_input(key="accedi_password").input(PASSWORD_DEMO)
    if ricorda:
        at.checkbox(key="accedi_ricorda").check()
    return at.button(key="accedi_invia").click().run()


def test_con_ricordami_il_cookie_vale_trenta_giorni(ambiente):
    at = accedi(apri(), ricorda=True)

    assert at.session_state["utente_id"] == 1
    [cookie] = cookie_scritti(at)
    token = at.session_state["sessione_browser"]
    assert f"bw_sessione={token}; path=/; SameSite=Strict; max-age={30 * 86400}" in cookie
    assert len(ambiente.sessioni.righe) == 1


def test_senza_ricordami_il_cookie_non_ha_durata(ambiente):
    at = accedi(apri(), ricorda=False)

    [cookie] = cookie_scritti(at)
    assert "max-age" not in cookie and "SameSite=Strict" in cookie


def test_il_cookie_si_scrive_una_volta_sola(ambiente):
    at = accedi(apri(), ricorda=True)

    at.run()

    assert not cookie_scritti(at)


def test_con_un_cookie_valido_si_entra_senza_password(ambiente, app_pronta, monkeypatch):
    aperta = ambiente.servizi.apri_sessione(1, ricorda=True)
    monkeypatch.setattr(app_pronta, "_cookie_sessione", lambda: aperta.token)

    at = apri()

    assert not at.exception
    assert at.session_state["utente_id"] == 1
    assert at.session_state["accesso"] == "Apicoltore Dimostrativo"
    assert "Bentornato" not in [s.value for s in at.subheader]


def test_un_cookie_scaduto_si_cancella_e_resta_la_pagina_accedi(ambiente, app_pronta, monkeypatch):
    monkeypatch.setattr(app_pronta, "_cookie_sessione", lambda: "token-che-non-esiste")

    at = apri()

    assert at.session_state["utente_id"] is None
    [cookie] = cookie_scritti(at)
    assert "bw_sessione=; path=/; SameSite=Strict; max-age=0" in cookie


def test_esci_chiude_la_sessione_e_cancella_il_cookie_senza_rientrare(
    ambiente, app_pronta, monkeypatch
):
    aperta = ambiente.servizi.apri_sessione(1, ricorda=True)
    monkeypatch.setattr(app_pronta, "_cookie_sessione", lambda: aperta.token)
    at = apri()

    at = at.sidebar.button(key="esci").click().run()

    assert at.session_state["utente_id"] is None
    assert ambiente.servizi.riprendi_sessione(aperta.token) is None
    assert any("max-age=0" in c for c in cookie_scritti(at))
    at.run()  # il cookie letto all'apertura c'è ancora: non deve far rientrare
    assert at.session_state["utente_id"] is None


def test_con_il_database_spento_il_cookie_non_blocca_lapp(ambiente, app_pronta, monkeypatch):
    ambiente.sessioni.errore = DATABASE_SPENTO
    monkeypatch.setattr(app_pronta, "_cookie_sessione", lambda: "qualcosa")

    at = apri()

    assert not at.exception
    assert at.session_state["utente_id"] is None


def test_se_la_sessione_non_si_salva_laccesso_vale_lo_stesso(ambiente):
    ambiente.sessioni.errore = DATABASE_SPENTO

    at = accedi(apri(), ricorda=True)

    assert not at.exception and at.session_state["utente_id"] == 1
    assert not cookie_scritti(at)


# --------------------------------------------------------------------------- #
# Con MySQL vero
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_integrazione_sessioni(database_test: Database):
    email = f"sessioni-{uuid.uuid4().hex}@beewatch.test"
    s = Servizi(database_test)
    utente = s.registra_utente(nome="Prova", email=email, password="favo-di-miele",
                               conferma="favo-di-miele")  # fmt: skip

    aperta = s.apri_sessione(utente.id, ricorda=True)
    scaduta = s.apri_sessione(utente.id, ricorda=False, adesso=datetime.now() - timedelta(days=2))

    assert s.riprendi_sessione(aperta.token).email == email
    assert s.riprendi_sessione(scaduta.token) is None
    s.chiudi_sessione(aperta.token)
    assert s.riprendi_sessione(aperta.token) is None

    ricordata = s.apri_sessione(utente.id, ricorda=True)  # cancellando l'utente, via a cascata
    s.elimina_account(utente.id, password="favo-di-miele")
    impronta = sicurezza.impronta_token(ricordata.token)
    assert SessioniRepository(database_test).utente_della_sessione(impronta) is None
