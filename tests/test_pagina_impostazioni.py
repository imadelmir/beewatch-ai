"""La pagina Impostazioni, i promemoria della Home e il consenso nell'Assistente (M6-T13)."""

from __future__ import annotations

from pathlib import Path

import pytest
from accesso_finto import GIRI_TEST, PASSWORD_DEMO, SessioniInMemoria, UtentiInMemoria
from anagrafica_finta import DATABASE_SPENTO, anagrafica_di_prova, ispezioni_di_prova
from app_finta import APP, DashboardFinto, PredittoreStub, con_accesso, installa, valori
from assistente_finto import RaccoltiVuoti, RiepiloghiInMemoria
from preferenze_finte import PreferenzeInMemoria
from streamlit.testing.v1 import AppTest

from beewatch import sicurezza
from beewatch.config import Config, ConfigDatabase, ConfigLLM
from beewatch.services import Servizi

PAGINA = APP / "pages" / "8_Impostazioni.py"


class Ambiente:
    def __init__(self, utenti, preferenze):
        self.utenti, self.preferenze = utenti, preferenze


def configurazione() -> Config:
    return Config(
        database=ConfigDatabase("127.0.0.1", 3306, "beewatch", "app", "PASSWORD-SEGRETA-123"),
        llm=ConfigLLM(provider="ollama", modello="llama3.1:8b", api_key=None, timeout=60),
        percorso_modello=Path("models/produzione_v1.joblib"),
        livello_log="INFO",
    )


def prepara(app_pronta, monkeypatch, *, llm_in_locale=True, cfg=None) -> Ambiente:
    monkeypatch.setattr(sicurezza, "GIRI", GIRI_TEST)
    apiari, alveari = anagrafica_di_prova()
    utenti, preferenze = UtentiInMemoria(), PreferenzeInMemoria()
    installa(
        app_pronta,
        monkeypatch,
        Servizi(None, apiari=apiari, alveari=alveari, ispezioni=ispezioni_di_prova(alveari),
                utenti=utenti, preferenze=preferenze, dashboard=DashboardFinto(),
                sessioni=SessioniInMemoria(utenti),
                crea_predittore=PredittoreStub, raccolti=RaccoltiVuoti(),
                riepiloghi=RiepiloghiInMemoria(), llm_in_locale=llm_in_locale,
                descrizione_llm="un-modello via openrouter (chiave: impostata)"
                if llm_in_locale is False else "llama3.1:8b via ollama (chiave: non richiesta)",
                configurazione=cfg),
    )  # fmt: skip
    return Ambiente(utenti, preferenze)


@pytest.fixture
def ambiente(app_pronta, monkeypatch) -> Ambiente:
    return prepara(app_pronta, monkeypatch, cfg=configurazione())


def apri(pagina=PAGINA) -> AppTest:
    return con_accesso(AppTest.from_file(str(pagina), default_timeout=30)).run()


def scheda(at: AppTest, nome: str):
    return next(t for t in at.tabs if t.label == nome)


# --------------------------------------------------------------------------- #
# La pagina
# --------------------------------------------------------------------------- #


def test_quattro_schede_con_il_profilo_compilato(ambiente):
    at = apri()

    assert not at.exception and not at.error
    assert valori(at.title) == ["⚙️ Impostazioni"]
    assert [t.label for t in at.tabs] == ["Profilo", "Notifiche", "AI e Modelli", "Database"]
    assert at.text_input(key="profilo_nome").value == "Apicoltore Dimostrativo"
    assert at.text_input(key="profilo_email").value == "demo@beewatch.local"


def test_aggiornare_il_profilo_cambia_anche_il_nome_nella_sidebar(ambiente):
    at = apri()
    at.text_input(key="profilo_nome").input("Ape Regina")

    at = at.button(key="profilo_invia").click().run()

    assert valori(at.success) == ["Profilo aggiornato."]
    assert ambiente.utenti.righe[1]["nome_completo"] == "Ape Regina"
    assert any("Ape Regina" in e.proto.body for e in at.sidebar.get("html"))


def test_unemail_gia_usata_lo_dice(ambiente):
    ambiente.utenti.crea("altro@esempio.it", "Altro", "x" * 60)
    at = apri()
    at.text_input(key="profilo_email").input("altro@esempio.it")

    at = at.button(key="profilo_invia").click().run()

    [errore] = valori(at.error)
    assert "Esiste già un account con questa email." in errore


def test_cambiare_la_password(ambiente):
    at = apri()
    at.text_input(key="password_attuale").input(PASSWORD_DEMO)
    at.text_input(key="password_nuova").input("pappa-reale")
    at.text_input(key="password_conferma").input("pappa-reale")

    at = at.button(key="password_invia").click().run()

    assert valori(at.success) == ["Password cambiata."]
    assert sicurezza.verifica("pappa-reale", ambiente.utenti.righe[1]["hash_password"])


def test_con_la_password_attuale_sbagliata_non_cambia(ambiente):
    vecchio = ambiente.utenti.righe[1]["hash_password"]
    at = apri()
    at.text_input(key="password_attuale").input("sbagliata")
    at.text_input(key="password_nuova").input("pappa-reale")
    at.text_input(key="password_conferma").input("pappa-reale")

    at = at.button(key="password_invia").click().run()

    [errore] = valori(at.error)
    assert "La password attuale non è corretta." in errore
    assert ambiente.utenti.righe[1]["hash_password"] == vecchio


def test_cancellare_laccount_chiede_spunta_e_password(ambiente):
    at = apri()
    assert at.button(key="cancella_invia").disabled

    at.text_input(key="cancella_password").input("sbagliata")
    at = at.checkbox(key="cancella_conferma").check().run()  # come nel browser: si abilita
    assert not at.button(key="cancella_invia").disabled
    at = at.button(key="cancella_invia").click().run()
    assert any("La password attuale non è corretta." in e for e in valori(at.error))
    assert 1 in ambiente.utenti.righe

    at.text_input(key="cancella_password").input(PASSWORD_DEMO)
    at = at.button(key="cancella_invia").click().run()

    assert 1 not in ambiente.utenti.righe
    assert at.session_state["accesso"] is None and at.session_state["utente_id"] is None
    assert valori(at.info) == ["Per vedere questa pagina accedi a BeeWatch AI."]


def test_le_notifiche_si_salvano(ambiente):
    at = apri()
    at.slider(key="notifiche_giorni").set_value(14)
    at.checkbox(key="notifiche_avvisi").uncheck()

    at = at.button(key="notifiche_invia").click().run()

    assert valori(at.success) == ["Notifiche salvate."]
    assert ambiente.preferenze.righe[1] == {
        "giorni_promemoria": 14, "avvisi_rischio": False, "assistente_esterno": True,
    }  # fmt: skip
    assert at.slider(key="notifiche_giorni").value == 14
    assert "Ispezioni a rischio (60 giorni)" not in [m.label for m in at.metric]


def test_il_consenso_allassistente_esterno_si_salva(ambiente):
    at = apri()
    at.checkbox(key="ai_esterno").uncheck()

    at = at.button(key="ai_invia").click().run()

    assert valori(at.success) == ["Preferenze dell'assistente salvate."]
    assert ambiente.preferenze.righe[1]["assistente_esterno"] is False
    assert any("Ora l'assistente è locale" in c for c in valori(at.caption))


def test_la_scheda_database_mostra_la_configurazione_senza_segreti(ambiente):
    at = apri()

    righe = at.dataframe[0].value.to_dict("records")
    testo = repr(righe)
    assert "PASSWORD-SEGRETA-123" not in testo
    assert {"Sezione": "Database", "Voce": "Password", "Valore": "impostata"} in righe
    assert {"Sezione": "Database", "Voce": "Server", "Valore": "127.0.0.1:3306"} in righe


def test_senza_configurazione_la_scheda_database_lo_dice(app_pronta, monkeypatch):
    prepara(app_pronta, monkeypatch, cfg=None)

    at = apri()

    assert any("non è disponibile" in c for c in valori(at.caption))


def test_con_il_database_spento_lo_dice_e_si_ferma(ambiente):
    ambiente.utenti.errore = DATABASE_SPENTO

    at = apri()

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")
    assert not at.tabs


# --------------------------------------------------------------------------- #
# Dove le impostazioni si vedono: Home e Assistente
# --------------------------------------------------------------------------- #


def test_la_home_mostra_i_promemoria(ambiente):
    at = apri(APP / "schermate" / "home.py")

    assert "Promemoria" in valori(at.subheader)
    testo = " ".join(valori(at.markdown))
    assert (
        "Da ricontrollare (nessuna ispezione da oltre 30 giorni): **A2** (mai ispezionato)."
        in testo
    )


def test_senza_consenso_lassistente_esterno_non_propone_il_bottone(app_pronta, monkeypatch):
    ambiente = prepara(app_pronta, monkeypatch, llm_in_locale=False)
    ambiente.preferenze.salva(1, 30, True, False)

    at = apri(APP / "pages" / "4_Assistente_AI.py")

    assert not at.exception
    assert any("hai scelto di non inviare" in w for w in valori(at.warning))
    assert not [b for b in at.main.button if b.key == "genera_riepilogo"]


def test_con_consenso_lassistente_esterno_resta_disponibile(app_pronta, monkeypatch):
    prepara(app_pronta, monkeypatch, llm_in_locale=False)

    at = apri(APP / "pages" / "4_Assistente_AI.py")

    assert at.button(key="genera_riepilogo")
