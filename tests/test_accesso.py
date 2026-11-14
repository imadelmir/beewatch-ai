"""Il router, l'accesso, la registrazione e i primi passi, eseguiti con `AppTest` (M6-T11).

Si parte da `Home.py` senza accesso, come nel browser: il menu ha solo Accedi e Registrati.
Servizi veri con utenti e anagrafica in memoria (bcrypt vero, con pochi giri).
"""

from __future__ import annotations

import pytest
from accesso_finto import (
    EMAIL_DEMO,
    GIRI_TEST,
    PASSWORD_DEMO,
    SessioniInMemoria,
    UtentiInMemoria,
)
from anagrafica_finta import DATABASE_SPENTO, anagrafica_di_prova, ispezioni_di_prova
from app_finta import APP, DashboardFinto, PredittoreStub, installa, valori
from preferenze_finte import PreferenzeInMemoria
from streamlit.testing.v1 import AppTest

from beewatch import sicurezza
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
                sessioni=SessioniInMemoria(utenti),
                dashboard=DashboardFinto(), crea_predittore=PredittoreStub,
                preferenze=PreferenzeInMemoria(), ispezioni=ispezioni_di_prova(alveari)),
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
    dati = {"nome": "Mario", "cognome": "Rossi", "email": "mario@esempio.it",
            "password": "favo-di-miele", "apiario": ""}  # fmt: skip
    dati.update(campi)
    at.text_input(key="registrati_nome").input(dati["nome"])
    at.text_input(key="registrati_cognome").input(dati["cognome"])
    at.text_input(key="registrati_email").input(dati["email"])
    at.text_input(key="registrati_apiario").input(dati["apiario"])
    at.text_input(key="registrati_password").input(dati["password"])
    at.text_input(key="registrati_conferma").input(dati.get("conferma", dati["password"]))
    if consenso:
        at.checkbox(key="registrati_consenso").check()
    return at.button(key="registrati_invia").click().run()


def in_accedi(at: AppTest) -> bool:
    return "Bentornato" in valori(at.title)


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
    assert in_accedi(at)
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
    assert in_accedi(at) or any("accedi a BeeWatch AI" in i for i in valori(at.info))
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
    assert at.session_state["accesso"] == "Apicoltore Dimostrativo"


def test_con_la_password_sbagliata_lo_dice_e_resta_fuori(utenti):
    at = accedi(apri(), EMAIL_DEMO, "non-e-lei")

    [errore] = valori(at.error)
    assert ACCESSO_NEGATO in errore
    assert in_accedi(at) and at.session_state["accesso"] is None


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

    assert in_accedi(at)
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
    assert valori(at.title) == ["Aggiungi il tuo primo alveare"]
    assert at.session_state["utente_id"] == 3 and at.session_state["onboarding"] == 1
    assert at.session_state["accesso"] == "Mario Rossi"  # nome e cognome insieme
    assert utenti.righe[3]["hash_password"] != "favo-di-miele"
    assert "Passo 2 di 3" in valori(at.caption)  # il primo, il profilo, è la registrazione

    # senza apiario, il primo passo chiede anche il suo nome
    at.text_input(key="onboarding_codice").input("O1")
    at.text_input(key="onboarding_nome").input("Orto di casa")
    at = at.button(key="onboarding_alveare_invia").click().run()
    assert at.session_state["onboarding"] == 2
    [apiario] = [a for a in utenti.apiari.righe.values() if a.utente_id == 3]
    assert apiario.nome == "Orto di casa" and at.session_state["apiario_attivo_id"] == apiario.id
    assert [a.codice for a in utenti.alveari.righe.values() if a.apiario_id == apiario.id] == ["O1"]

    at.slider(key="onboarding_giorni").set_value(14)
    at = at.button(key="onboarding_fine").click().run()
    assert nella_home(at) and at.session_state["onboarding"] is None


def test_lapiario_scritto_alla_registrazione_nasce_subito(utenti):
    at = registrati(apri(), apiario="Colline Sud")

    [apiario] = [a for a in utenti.apiari.righe.values() if a.utente_id == 3]
    assert apiario.nome == "Colline Sud"
    assert at.selectbox(key="onboarding_apiario").options == ["Colline Sud"]
    assert not [t for t in at.text_input if t.key == "onboarding_nome"]

    at.text_input(key="onboarding_codice").input("A01")
    at.number_input(key="onboarding_regina").set_value(2025)
    at = at.button(key="onboarding_alveare_invia").click().run()

    [alveare] = [a for a in utenti.alveari.righe.values() if a.apiario_id == apiario.id]
    assert (alveare.codice, alveare.anno_regina) == ("A01", 2025)


def test_le_preferenze_dei_primi_passi_si_salvano_e_si_torna_indietro(utenti, app_pronta):
    at = registrati(apri(), apiario="Colline Sud")
    at.text_input(key="onboarding_codice").input("A01")
    at = at.button(key="onboarding_alveare_invia").click().run()

    at = at.button(key="onboarding_indietro").click().run()
    assert at.session_state["onboarding"] == 1  # di nuovo il primo alveare
    assert at.button(key="onboarding_indietro_1").disabled  # prima c'è il profilo, già fatto

    at.session_state["onboarding"] = 2
    at.run()
    at.slider(key="onboarding_giorni").set_value(21)
    at.toggle(key="onboarding_esterno").set_value(False)
    at = at.button(key="onboarding_fine").click().run()

    preferenze = app_pronta.servizi().preferenze(3)
    assert (preferenze.giorni_promemoria, preferenze.assistente_esterno) == (21, False)


def test_i_primi_passi_si_possono_saltare(utenti):
    at = registrati(apri())

    at = at.button(key="onboarding_salta").click().run()

    assert nella_home(at)
    assert not [a for a in utenti.apiari.righe.values() if a.utente_id == 3]


def test_i_primi_passi_controllano_i_campi_obbligatori(utenti):
    at = registrati(apri())

    at = at.button(key="onboarding_alveare_invia").click().run()
    [errore] = valori(at.error)
    assert "Il codice dell'alveare è obbligatorio." in errore

    at.text_input(key="onboarding_codice").input("A1")
    at = at.button(key="onboarding_alveare_invia").click().run()
    [errore] = valori(at.error)
    assert "Il nome dell'apiario è obbligatorio." in errore
    assert at.session_state["onboarding"] == 1


def test_senza_utente_dimostrativo_il_bottone_lo_spiega(app_pronta, monkeypatch):
    utenti = UtentiInMemoria(con_demo=False)
    apiari, alveari = anagrafica_di_prova()
    installa(
        app_pronta,
        monkeypatch,
        Servizi(
            None,
            utenti=utenti,
            apiari=apiari,
            alveari=alveari,
            preferenze=PreferenzeInMemoria(),
            sessioni=SessioniInMemoria(utenti),
        ),
    )

    at = apri().button(key="accedi_demo").click().run()

    assert not at.exception
    [errore] = valori(at.error)
    assert "seed.sql" in errore and at.session_state["accesso"] is None


def test_i_primi_passi_spiegano_gli_errori_dei_servizi(utenti):
    at = registrati(apri(), apiario="Orto")

    at.text_input(key="onboarding_codice").input("B1")
    utenti.alveari.errore = DATABASE_SPENTO
    at = at.button(key="onboarding_alveare_invia").click().run()
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")
    assert at.session_state["onboarding"] == 1


def test_senza_accesso_e_nei_primi_passi_non_ce_la_sidebar(utenti):
    at = apri()
    assert not at.sidebar.selectbox and not at.sidebar.button  # Accedi: schermo diviso

    at = registrati(at)
    assert at.session_state["onboarding"] == 1
    assert not at.sidebar.selectbox and not at.sidebar.button


def test_la_robustezza_della_password_si_vede_mentre_si_scrive(utenti):
    at = apri()
    at.switch_page("schermate/registrati.py").run()

    at.text_input(key="registrati_password").input("Favo-di-miele-2026").run()

    testo = " ".join(e.proto.body for e in at.get("html"))
    assert "Password robusta" in testo and "bw-forza-robusta" in testo
