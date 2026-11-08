"""Home e pagine eseguite davvero con `streamlit.testing.v1.AppTest` (M6-T1).

Gli script girano nello stesso processo del test, con i servizi veri (`Servizi`) e repository
finti: nessun database, nessuna rete. Si verifica ciò che l'utente vedrebbe (numeri, messaggi,
stato) e le promesse di M6-T1 sulla cache: i servizi si creano una volta, il modello si carica
una volta sola attraverso più navigazioni, una lettura si ripete solo quando la cache scade o
viene svuotata.

Non prova l'aspetto grafico né il menu laterale (li costruisce Streamlit): vedi
`test_app_processo.py` per l'avvio reale.
"""

from __future__ import annotations

import logging

import pytest
from app_finta import (
    APP,
    PAGINE,
    RADICE,
    ApiariFinti,
    DashboardFinto,
    esegui,
    installa,
    servizi_finti,
    valori,
)
from streamlit.testing.v1 import AppTest

from beewatch.exceptions import ConfigError, DatabaseError, ModelError
from beewatch.ml.predictor import Predittore

MODELLO_COMMITTATO = RADICE / "models" / "produzione_v1.joblib"


# --------------------------------------------------------------------------- #
# Home
# --------------------------------------------------------------------------- #


def test_la_home_mostra_la_panoramica(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti())

    at = esegui(APP / "Home.py")

    assert not at.exception
    assert valori(at.title) == ["🐝 BeeWatch AI"]
    assert {m.label: m.value for m in at.metric} == {
        "Alveari attivi": "4",
        "Ispezioni (30 giorni)": "7",
        "Produzione stagione": "1 234,5 kg",
        "Da controllare": "2",
    }
    didascalie = " ".join(valori(at.caption))
    assert "Apiario attivo: **Collina** · 2 in tutto" in didascalie
    assert "v-stub" in didascalie and "RandomForestRegressor" in didascalie
    assert "±3.5 kg" in didascalie
    assert "llama3.1:8b via ollama" in didascalie


def test_lo_stato_della_sessione_nasce_con_lutente_demo_e_il_primo_apiario(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti())

    at = esegui(APP / "Home.py")

    assert at.session_state["utente_id"] == 1
    assert at.session_state["apiario_attivo_id"] == 10  # il primo, «Collina»


def test_lapiario_scelto_resta_scelto_se_esiste_ancora(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti())
    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=30)
    at.session_state["apiario_attivo_id"] = 11  # «Valle»

    at.run()

    assert at.session_state["apiario_attivo_id"] == 11
    assert "Apiario attivo: **Valle**" in " ".join(valori(at.caption))


def test_lapiario_scelto_che_non_esiste_piu_torna_al_primo(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti())
    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=30)
    at.session_state["apiario_attivo_id"] = 999

    at.run()

    assert at.session_state["apiario_attivo_id"] == 10


def test_senza_apiari_la_home_invita_a_crearne_uno(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti(apiari=ApiariFinti(())))

    at = esegui(APP / "Home.py")

    assert not at.exception
    assert any("Nessun apiario registrato" in t for t in valori(at.info))
    assert at.session_state["apiario_attivo_id"] is None


def test_se_il_database_non_risponde_la_home_lo_dice_senza_traceback(app_pronta, monkeypatch):
    errore = DatabaseError("Il server MySQL non risponde. Avvialo con docker compose up -d mysql.")
    installa(app_pronta, monkeypatch, servizi_finti(dashboard=DashboardFinto(errore)))

    at = esegui(APP / "Home.py")

    assert not at.exception
    [testo] = valori(at.error)  # tradotto da ui.mostra_errore: cosa è successo e cosa fare
    assert testo.startswith("**Non riesco a raggiungere il database.**")
    assert "Il server MySQL non risponde" in testo and "docker compose up -d mysql" in testo
    assert not at.code  # nessun dettaglio tecnico a schermo
    assert not at.metric  # niente numeri inventati


def test_se_la_configurazione_non_e_valida_lapp_si_ferma_con_il_motivo(app_pronta, monkeypatch):
    def rotta():
        raise ConfigError("Configurazione non valida: manca DB_NAME.")

    monkeypatch.setattr(app_pronta, "crea_servizi", rotta)

    at = esegui(APP / "Home.py")

    assert not at.exception
    assert "L'applicazione non può partire." in valori(at.markdown)
    [testo] = valori(at.error)
    assert testo.startswith("**La configurazione non è valida.**")
    assert "manca DB_NAME" in testo and "`.env`" in testo
    assert not at.metric
    assert not at.sidebar.selectbox  # la pagina si è fermata prima della sidebar


def test_senza_il_file_del_modello_la_home_funziona_e_avvisa(app_pronta, monkeypatch):
    def manca():
        raise ModelError("Il modello non è stato trovato: lancia scripts/train_model.py.")

    installa(app_pronta, monkeypatch, servizi_finti(crea_predittore=manca))

    at = esegui(APP / "Home.py")

    assert not at.exception
    assert len(at.metric) == 4  # il resto della Home c'è
    assert any("scripts/train_model.py" in t for t in valori(at.warning))


# --------------------------------------------------------------------------- #
# Le sei pagine
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("pagina", PAGINE, ids=lambda p: p.name)
def test_ogni_pagina_parte_con_lo_stato_pronto_e_dice_che_e_in_costruzione(
    app_pronta, monkeypatch, pagina
):
    installa(app_pronta, monkeypatch, servizi_finti())

    at = esegui(pagina)

    assert not at.exception
    assert len(at.title) == 1
    assert any("in costruzione" in t for t in valori(at.info))
    assert at.session_state["utente_id"] == 1  # lo stato è stato inizializzato anche qui


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #


def test_i_servizi_si_creano_una_volta_sola_per_piu_navigazioni(app_pronta, monkeypatch):
    create = installa(app_pronta, monkeypatch, servizi_finti())

    for file in [APP / "Home.py", *PAGINE, APP / "Home.py"]:
        assert not esegui(file).exception

    assert create == [1]


def test_il_modello_si_carica_una_volta_sola_e_un_log_lo_dimostra(app_pronta, monkeypatch, caplog):
    caricamenti: list[int] = []

    def crea_predittore():
        caricamenti.append(1)
        return Predittore(MODELLO_COMMITTATO)  # il modello vero, quello di produzione

    installa(app_pronta, monkeypatch, servizi_finti(crea_predittore=crea_predittore))

    with caplog.at_level(logging.INFO):
        # otto navigazioni: Home, le sei pagine, Home due volte (la Home chiede il modello)
        for file in [APP / "Home.py", *PAGINE, APP / "Home.py", APP / "Home.py"]:
            assert not esegui(file).exception

    righe = [r.getMessage() for r in caplog.records if "caricato da" in r.getMessage()]
    assert len(righe) == 1, righe  # il log: una riga «Modello vN caricato da …»
    creazioni = [r.getMessage() for r in caplog.records if "Servizi creati" in r.getMessage()]
    assert len(creazioni) == 1, creazioni  # e una sola creazione dei servizi
    assert righe[0].startswith("Modello ")
    assert caricamenti == [1]


def test_il_modello_mostrato_dalla_home_e_quello_vero(app_pronta, monkeypatch):
    installa(
        app_pronta,
        monkeypatch,
        servizi_finti(crea_predittore=lambda: Predittore(MODELLO_COMMITTATO)),
    )
    at = esegui(APP / "Home.py")
    didascalie = " ".join(valori(at.caption))
    assert "Modello di previsione **" in didascalie and "RandomForestRegressor" in didascalie


def test_una_lettura_in_cache_non_si_ripete_a_ogni_navigazione(app_pronta, monkeypatch):
    dashboard = DashboardFinto()
    installa(app_pronta, monkeypatch, servizi_finti(dashboard=dashboard))

    esegui(APP / "Home.py")
    esegui(APP / "Home.py")
    esegui(APP / "Home.py")

    assert dashboard.chiamate == 1


def test_dopo_una_scrittura_svuota_letture_fa_rileggere_il_dato(app_pronta, monkeypatch):
    dashboard = DashboardFinto()
    installa(app_pronta, monkeypatch, servizi_finti(dashboard=dashboard))

    esegui(APP / "Home.py")
    app_pronta.svuota_letture()
    esegui(APP / "Home.py")

    assert dashboard.chiamate == 2


def test_la_lettura_in_cache_ha_un_tempo_di_vita_dichiarato(app_pronta):
    assert app_pronta.TTL_LETTURE_SECONDI == 60
    assert app_pronta.panoramica.__wrapped__ is not None  # è una funzione decorata
