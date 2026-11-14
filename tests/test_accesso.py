"""Il router, l'accesso, la registrazione e i primi passi, eseguiti con `AppTest` (M6-T11).

Si parte da `Home.py` senza accesso, come nel browser: il menu ha solo Accedi e Registrati.
Servizi veri con utenti e anagrafica in memoria (bcrypt vero, con pochi giri).
"""

from __future__ import annotations

import pytest
from accesso_finto import EMAIL_DEMO, GIRI_TEST, PASSWORD_DEMO, UtentiInMemoria
from anagrafica_finta import DATABASE_SPENTO, anagrafica_di_prova
from app_finta import APP, DashboardFinto, PredittoreStub, installa, valori
from streamlit.testing.v1 import AppTest

from beewatch import sicurezza
from beewatch.models import Apiario
from beewatch.services import ACCESSO_NEGATO, Servizi


@pytest.fixture
def utenti(app_pronta, monkeypatch) -> UtentiInMemoria:
    monkeypatch.setattr(sicurezza, "GIRI", GIRI_TEST)
    utenti = UtentiInMemoria()
    utenti.crea("altrui@esempio.it", "Altro Apicoltore", "x" * 60)  # l'utente 2 dell'anagrafica
    apiari, alveari = anagrafica_di_prova()
    installa(
        app_pronta,
        monkeypatch,
        Servizi(None, utenti=utenti, apiari=apiari, alveari=alveari,
                dashboard=DashboardFinto(), crea_predittore=PredittoreStub),
    )  # fmt: skip
    utenti.apiari = apiari  # per guardare cosa crea l'onboarding
    utenti.alveari = alveari
    return utenti


def apri() -> AppTest:
    return AppTest.from_file(str(APP / "Home.py"), default_timeout=30).run()


def accedi(at: AppTest, email: str, password: str) -> AppTest:
    at.text_input(key="accedi_email").input(email)
    at.text_input(key="accedi_password").input(password)
    return at.button(key="accedi_invia").click().run()


def registrati(at: AppTest, *, consenso: bool = True, **campi) -> AppTest:
    at.switch_page("schermate/registrati.py").run()
    dati = {"nome": "Mario Rossi", "email": "mario@esempio.it", "password": "favo-di-miele"}
    dati.update(campi)
    at.text_input(key="registrati_nome").input(dati["nome"])
    at.text_input(key="registrati_email").input(dati["email"])
    at.text_input(key="registrati_password").input(dati["password"])
    at.text_input(key="registrati_conferma").input(dati.get("conferma", dati["password"]))
    if consenso:
        at.checkbox(key="registrati_consenso").check()
    return at.button(key="registrati_invia").click().run()


def nella_home(at: AppTest) -> bool:
    return valori(at.title) == ["🐝 BeeWatch AI"] and "Alveari attivi" in [
        m.label for m in at.metric
    ]


# --------------------------------------------------------------------------- #
# Senza accesso
# --------------------------------------------------------------------------- #


def test_senza_accesso_si_vede_solo_accedi(utenti):
    at = apri()

    assert not at.exception and not at.error
    assert "Bentornato" in valori(at.subheader)
    assert not at.metric  # niente dati dell'app
    assert at.session_state["accesso"] is None


@pytest.mark.parametrize("pagina", ["pages/1_Alveari.py", "schermate/home.py"])
def test_senza_accesso_le_pagine_dellapp_non_mostrano_nulla(utenti, pagina):
    at = apri()

    try:
        at.switch_page(pagina).run()  # come scriverne l'indirizzo: non è nel menu
    except ValueError as errore:
        # Streamlit 1.67: AppTest stesso rifiuta una pagina che il router non ha registrato,
        # e dice quali conosce: solo Accedi e Registrati.
        assert "Could not find a navigation page" in str(errore)
        assert "accedi.py" in str(errore) and "1_Alveari.py" not in str(errore).split("Known")[1]
        return

    assert not at.exception
    # O Streamlit ripiega su Accedi, o la pagina si ferma al secondo lucchetto di `avvia`:
    # in nessun caso compaiono i dati di qualcuno.
    assert not at.metric and not at.dataframe
    assert "Bentornato" in valori(at.subheader) or any(
        "accedi a BeeWatch AI" in i for i in valori(at.info)
    )
    assert at.session_state["utente_id"] is None


@pytest.mark.parametrize("pagina", sorted((APP / "pages").glob("*.py")), ids=lambda p: p.name)
def test_ogni_pagina_senza_accesso_si_ferma_al_lucchetto(utenti, pagina):
    at = AppTest.from_file(str(pagina), default_timeout=30).run()

    assert not at.exception
    assert valori(at.info) == ["Per vedere questa pagina accedi a BeeWatch AI."]
    assert not at.title and not at.metric and not at.dataframe


# --------------------------------------------------------------------------- #
# Accedi
# --------------------------------------------------------------------------- #


def test_con_la_password_giusta_si_entra_nella_home(utenti):
    at = accedi(apri(), EMAIL_DEMO, PASSWORD_DEMO)

    assert not at.exception and not at.error
    assert nella_home(at)
    assert at.session_state["utente_id"] == 1
    assert "**Accesso:** Apicoltore Dimostrativo" in valori(at.sidebar.caption)


def test_con_la_password_sbagliata_lo_dice_e_resta_fuori(utenti):
    at = accedi(apri(), EMAIL_DEMO, "non-e-lei")

    [errore] = valori(at.error)
    assert ACCESSO_NEGATO in errore
    assert "Bentornato" in valori(at.subheader) and at.session_state["accesso"] is None


def test_lutente_dimostrativo_entra_con_un_bottone(utenti):
    at = apri()

    at = at.button(key="accedi_demo").click().run()

    assert nella_home(at) and at.session_state["utente_id"] == 1


def test_dopo_laccesso_le_pagine_si_raggiungono(utenti):
    at = accedi(apri(), EMAIL_DEMO, PASSWORD_DEMO)

    at.switch_page("pages/1_Alveari.py").run()

    assert not at.exception and valori(at.title) == ["🏠 Alveari"]


def test_esci_riporta_ad_accedi(utenti):
    at = accedi(apri(), EMAIL_DEMO, PASSWORD_DEMO)

    at = at.sidebar.button(key="esci").click().run()

    assert "Bentornato" in valori(at.subheader)
    assert at.session_state["accesso"] is None and at.session_state["utente_id"] is None


def test_con_il_database_spento_laccesso_lo_dice(utenti):
    utenti.errore = DATABASE_SPENTO

    at = accedi(apri(), EMAIL_DEMO, PASSWORD_DEMO)

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")


# --------------------------------------------------------------------------- #
# Registrati e primi passi
# --------------------------------------------------------------------------- #


def test_senza_consenso_non_si_crea_laccount(utenti):
    at = registrati(apri(), consenso=False)

    [errore] = valori(at.error)
    assert "come vengono trattati i dati" in errore
    assert len(utenti.righe) == 2  # il demo e l'altro utente: nessuno nuovo


@pytest.mark.parametrize(
    ("campi", "frammento"),
    [
        ({"conferma": "un-altra-password"}, "non coincidono"),
        ({"email": EMAIL_DEMO}, "Esiste già un account"),
        ({"password": "corta"}, "almeno 8 caratteri"),
    ],
)
def test_la_registrazione_spiega_cosa_correggere(utenti, campi, frammento):
    at = registrati(apri(), **campi)

    assert not at.exception
    [errore] = valori(at.error)
    assert frammento in errore
    assert len(utenti.righe) == 2  # il demo e l'altro utente: nessuno nuovo


def test_registrarsi_porta_ai_primi_passi_e_poi_alla_home(utenti):
    at = registrati(apri())

    assert not at.exception and not at.error
    assert valori(at.title) == ["🧭 Benvenuto, Mario Rossi"]
    assert at.session_state["utente_id"] == 3 and at.session_state["onboarding"] == 1
    assert utenti.righe[3]["hash_password"] != "favo-di-miele"

    at.text_input(key="onboarding_nome").input("Orto di casa")
    at = at.button(key="onboarding_apiario_invia").click().run()
    assert at.session_state["onboarding"] == 2
    [apiario] = [a for a in utenti.apiari.righe.values() if a.utente_id == 3]
    assert apiario.nome == "Orto di casa" and at.session_state["apiario_attivo_id"] == apiario.id

    at.text_input(key="onboarding_codice").input("O1")
    at = at.button(key="onboarding_alveare_invia").click().run()
    assert at.session_state["onboarding"] == 3
    assert [a.codice for a in utenti.alveari.righe.values() if a.apiario_id == apiario.id] == ["O1"]

    at = at.button(key="onboarding_fine").click().run()
    assert nella_home(at) and at.session_state["onboarding"] is None


def test_i_primi_passi_si_possono_saltare(utenti):
    at = registrati(apri())

    at = at.button(key="onboarding_salta").click().run()

    assert nella_home(at)
    assert not [a for a in utenti.apiari.righe.values() if a.utente_id == 3]


def test_i_primi_passi_controllano_i_campi_obbligatori(utenti):
    at = registrati(apri())

    at = at.button(key="onboarding_apiario_invia").click().run()

    [errore] = valori(at.error)
    assert "Il nome dell'apiario è obbligatorio." in errore
    assert at.session_state["onboarding"] == 1


def test_senza_utente_dimostrativo_il_bottone_lo_spiega(app_pronta, monkeypatch):
    utenti = UtentiInMemoria(con_demo=False)
    apiari, alveari = anagrafica_di_prova()
    installa(app_pronta, monkeypatch, Servizi(None, utenti=utenti, apiari=apiari, alveari=alveari))

    at = apri().button(key="accedi_demo").click().run()

    assert not at.exception
    [errore] = valori(at.error)
    assert "seed.sql" in errore and at.session_state["accesso"] is None


def test_i_primi_passi_spiegano_gli_errori_dei_servizi(utenti):
    at = registrati(apri())
    utenti.apiari.crea(Apiario(utente_id=3, nome="Orto", id=None))  # nome già usato

    at.text_input(key="onboarding_nome").input("Orto")
    at = at.button(key="onboarding_apiario_invia").click().run()
    [errore] = valori(at.error)
    assert "Hai già un apiario con questo nome" in errore
    assert at.session_state["onboarding"] == 1

    at.text_input(key="onboarding_nome").input("Bosco")
    at = at.button(key="onboarding_apiario_invia").click().run()
    at = at.button(key="onboarding_alveare_invia").click().run()  # codice vuoto
    [errore] = valori(at.error)
    assert "Il codice dell'alveare è obbligatorio." in errore

    utenti.alveari.errore = DATABASE_SPENTO
    at.text_input(key="onboarding_codice").input("B1")
    at = at.button(key="onboarding_alveare_invia").click().run()
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")
    assert at.session_state["onboarding"] == 2
