"""Password e servizi di registrazione e accesso (M6-T11).

Unitari con gli utenti in memoria (`accesso_finto.py`) e bcrypt vero, con pochi giri; in fondo,
su MySQL vero: registrazione, accesso e utente dimostrativo del seed con la sua password.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterator

import bcrypt
import pytest
from accesso_finto import EMAIL_DEMO, GIRI_TEST, PASSWORD_DEMO, UtentiInMemoria

from beewatch import sicurezza
from beewatch.database import Database
from beewatch.exceptions import ValidationError
from beewatch.services import ACCESSO_NEGATO, Servizi, UtenteAutenticato


@pytest.fixture(autouse=True)
def bcrypt_veloce(monkeypatch):
    monkeypatch.setattr(sicurezza, "GIRI", GIRI_TEST)


def servizi(utenti: UtentiInMemoria | None = None) -> tuple[Servizi, UtentiInMemoria]:
    utenti = utenti or UtentiInMemoria()
    return Servizi(None, utenti=utenti), utenti


DATI = {"nome": "Mario Rossi", "email": "Mario.Rossi@Esempio.it ", "password": "favo-di-miele"}


def registra(s: Servizi, **altri) -> UtenteAutenticato:
    campi = {**DATI, **altri}
    return s.registra_utente(conferma=campi["password"], **campi)


# --------------------------------------------------------------------------- #
# sicurezza.py
# --------------------------------------------------------------------------- #


def test_lhash_e_bcrypt_lungo_sessanta_e_verifica_solo_la_password_giusta():
    h = sicurezza.calcola_hash("favo-di-miele")

    assert len(h) == 60 and h.startswith("$2b$")  # la colonna è CHAR(60)
    assert "favo" not in h
    assert sicurezza.verifica("favo-di-miele", h)
    assert not sicurezza.verifica("favo-di-miel", h)
    assert sicurezza.calcola_hash("favo-di-miele") != h  # un sale nuovo ogni volta


@pytest.mark.parametrize("hash_salvato", [None, "", "non-un-hash", "$2b$12$troppo-corto"])
def test_un_hash_mancante_o_rovinato_e_un_no_senza_eccezioni(hash_salvato):
    assert not sicurezza.verifica("qualsiasi", hash_salvato)


def test_lhash_del_seed_verifica_la_password_dimostrativa_documentata():
    seed = "$2b$12$3UhRtFKUUOgVutfM3VnYbOeOjj5lL5asOvtgOVv/79WDjLjx3NX1W"  # sql/seed.sql

    assert sicurezza.verifica(PASSWORD_DEMO, seed)


@pytest.mark.parametrize(
    ("password", "frammento"),
    [
        ("corta", "almeno 8 caratteri"),
        ("è" * 40, "troppo lunga"),  # 80 byte in UTF-8: bcrypt ne guarda solo 72
        (" spazio-davanti", "spazio"),
    ],
)
def test_le_password_non_ammesse_lo_dicono(password, frammento):
    assert frammento in sicurezza.problema_password(password)


def test_una_password_oltre_72_byte_non_passa_mai_la_verifica():
    lunga = "a" * 80
    h = bcrypt.hashpw(lunga[:72].encode(), bcrypt.gensalt(GIRI_TEST)).decode()

    assert not sicurezza.verifica(lunga, h)  # bcrypt troncherebbe: qui no


# --------------------------------------------------------------------------- #
# Registrazione
# --------------------------------------------------------------------------- #


def test_registrare_salva_solo_lhash_e_lemail_in_minuscolo():
    s, utenti = servizi()

    utente = registra(s)

    assert utente == UtenteAutenticato(id=2, nome="Mario Rossi", email="mario.rossi@esempio.it")
    riga = utenti.righe[2]
    assert riga["hash_password"] != DATI["password"] and len(riga["hash_password"]) == 60
    assert sicurezza.verifica(DATI["password"], riga["hash_password"])


def test_la_registrazione_non_scrive_la_password_nei_log(caplog):
    s, _ = servizi()

    with caplog.at_level(logging.DEBUG):
        registra(s)
        s.accedi(DATI["email"], DATI["password"])

    testo = " ".join(r.getMessage() for r in caplog.records)
    assert "favo-di-miele" not in testo and "mario.rossi" not in testo


@pytest.mark.parametrize(
    ("campi", "campo"),
    [
        ({"nome": " "}, "nome"),
        ({"nome": "x" * 121}, "nome"),
        ({"email": "non-una-email"}, "email"),
        ({"email": "a@b"}, "email"),
        ({"password": "corta"}, "password"),
    ],
)
def test_i_dati_non_validi_si_rifiutano_con_il_campo(campi, campo):
    s, utenti = servizi()

    with pytest.raises(ValidationError) as errore:
        registra(s, **campi)
    assert errore.value.campo == campo
    assert len(utenti.righe) == 1  # solo il demo


def test_le_due_password_devono_coincidere():
    s, _ = servizi()

    with pytest.raises(ValidationError, match="non coincidono") as errore:
        s.registra_utente(conferma="altra-password", **DATI)
    assert errore.value.campo == "conferma"


def test_unemail_gia_usata_si_rifiuta_anche_con_maiuscole_diverse():
    s, _ = servizi()
    registra(s)

    with pytest.raises(ValidationError, match="Esiste già un account") as errore:
        registra(s, email="MARIO.ROSSI@esempio.it")
    assert errore.value.campo == "email"


# --------------------------------------------------------------------------- #
# Accesso
# --------------------------------------------------------------------------- #


def test_si_accede_con_email_e_password_giuste():
    s, _ = servizi()
    registra(s)

    assert s.accedi("  MARIO.rossi@esempio.it", DATI["password"]).id == 2


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("mario.rossi@esempio.it", "password-sbagliata"),  # password errata
        ("nessuno@esempio.it", "favo-di-miele"),  # email sconosciuta
        ("non-una-email", "favo-di-miele"),  # email malformata
        ("mario.rossi@esempio.it", ""),  # password vuota
    ],
)
def test_ogni_accesso_negato_ha_lo_stesso_messaggio(email, password):
    s, _ = servizi()
    registra(s)

    with pytest.raises(ValidationError) as errore:
        s.accedi(email, password)
    assert str(errore.value) == ACCESSO_NEGATO and errore.value.campo == "password"


def test_con_unemail_sconosciuta_la_password_si_verifica_lo_stesso(monkeypatch):
    s, _ = servizi()
    verificate: list[str | None] = []
    vera = sicurezza.verifica
    monkeypatch.setattr(
        "beewatch.services.verifica", lambda p, h: verificate.append(h) or vera(p, h)
    )

    with pytest.raises(ValidationError):
        s.accedi("nessuno@esempio.it", "qualcosa-di-lungo")
    assert verificate == [None]  # verificata contro l'hash fittizio: stesso tempo


def test_un_account_disattivato_non_entra():
    s, utenti = servizi()
    registra(s)
    utenti.righe[2]["attivo"] = False

    with pytest.raises(ValidationError) as errore:
        s.accedi(DATI["email"], DATI["password"])
    assert str(errore.value) == ACCESSO_NEGATO


def test_laccesso_dimostrativo_e_lutente_del_seed():
    s, _ = servizi()

    assert s.accesso_dimostrativo() == UtenteAutenticato(
        id=1, nome="Apicoltore Dimostrativo", email=EMAIL_DEMO
    )
    assert s.accedi(EMAIL_DEMO, PASSWORD_DEMO).id == 1  # anche con la sua password


def test_senza_utente_dimostrativo_lo_dice_con_il_rimedio():
    s, _ = servizi(UtentiInMemoria(con_demo=False))

    with pytest.raises(ValidationError, match="seed.sql"):
        s.accesso_dimostrativo()


# --------------------------------------------------------------------------- #
# Con MySQL vero
# --------------------------------------------------------------------------- #


@pytest.fixture
def email_di_prova(database_test: Database) -> Iterator[Callable[[], str]]:
    create: list[str] = []

    def nuova() -> str:
        create.append(f"accesso-{uuid.uuid4().hex}@beewatch.test")
        return create[-1]

    yield nuova
    with database_test.transazione() as cursore:
        for email in create:
            cursore.execute("DELETE FROM utenti WHERE email = %s", (email,))


@pytest.mark.integration
def test_integrazione_registrazione_e_accesso_su_mysql(
    database_test: Database, email_di_prova: Callable[[], str]
):
    s = Servizi(database_test)
    email = email_di_prova()

    utente = s.registra_utente(
        nome="Mario Rossi", email=email.upper(), password="favo-di-miele", conferma="favo-di-miele"
    )

    assert s.accedi(email, "favo-di-miele") == utente
    with pytest.raises(ValidationError, match="Esiste già un account"):
        s.registra_utente(nome="Altro", email=email, password="x" * 10, conferma="x" * 10)
    with pytest.raises(ValidationError):
        s.accedi(email, "sbagliata-di-sicuro")
    with database_test.transazione() as cursore:
        cursore.execute("SELECT hash_password FROM utenti WHERE id = %s", (utente.id,))
        salvato = cursore.fetchone()["hash_password"]
    assert len(salvato) == 60 and "favo" not in salvato


@pytest.mark.integration
def test_integrazione_lutente_dimostrativo_del_seed_entra_con_la_sua_password(
    database_test: Database,
):
    s = Servizi(database_test)

    assert s.accesso_dimostrativo().email == EMAIL_DEMO
    assert s.accedi(EMAIL_DEMO, PASSWORD_DEMO).id == s.accesso_dimostrativo().id
