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
import sys
from decimal import Decimal
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from beewatch.exceptions import ConfigError, DatabaseError, ModelError
from beewatch.ml.predictor import Predittore
from beewatch.models import Apiario
from beewatch.services import Servizi

RADICE = Path(__file__).resolve().parents[1]
APP = RADICE / "app"
MODELLO_COMMITTATO = RADICE / "models" / "produzione_v1.joblib"
PAGINE = sorted((APP / "pages").glob("*.py"))


class DashboardFinto:
    def __init__(self, errore: Exception | None = None):
        self.chiamate = 0
        self.errore = errore

    def riepilogo(self, utente_id: int) -> dict:
        self.chiamate += 1
        if self.errore:
            raise self.errore
        return {
            "alveari_attivi": 4,
            "ispezioni_30_giorni": 7,
            "produzione_stagione_kg": Decimal("1234.50"),
        }


class ApiariFinti:
    def __init__(self, nomi: tuple[str, ...] = ("Collina", "Valle")):
        self.nomi = nomi

    def elenca(self, utente_id: int) -> list[Apiario]:
        return [Apiario(utente_id=utente_id, nome=n, id=10 + i) for i, n in enumerate(self.nomi)]


class AlveariFinti:
    def trascurati(self, utente_id: int) -> list[dict]:
        return [{"id": 3, "codice": "A3"}, {"id": 5, "codice": "B1"}]


class PredittoreStub:
    versione = "v-stub"
    metadati = {
        "algoritmo": "RandomForestRegressor",
        "metriche": {"hold_out_2010_2012": {"mae_kg": 3.499}},
        "addestrato_il": "2026-10-23T12:00:00+00:00",
        "addestramento": {"righe": 600},
    }


@pytest.fixture
def app_pronta(monkeypatch: pytest.MonkeyPatch):
    """`app/` nel percorso degli import (lo fa `streamlit run`, non AppTest) e cache pulite."""
    monkeypatch.syspath_prepend(str(APP))
    sys.modules.pop("avvio", None)
    import avvio

    st.cache_resource.clear()
    st.cache_data.clear()
    monkeypatch.setattr(avvio, "configura", lambda: None)  # il logging vero legge il .env
    yield avvio
    st.cache_resource.clear()
    st.cache_data.clear()
    sys.modules.pop("avvio", None)


def servizi_finti(
    dashboard: DashboardFinto | None = None,
    apiari: ApiariFinti | None = None,
    crea_predittore=PredittoreStub,
) -> Servizi:
    return Servizi(
        None,
        crea_predittore=crea_predittore,
        dashboard=dashboard or DashboardFinto(),
        apiari=apiari or ApiariFinti(),
        alveari=AlveariFinti(),
        descrizione_llm="llama3.1:8b via ollama (chiave: non richiesta)",
    )


def installa(avvio, monkeypatch, servizi: Servizi) -> list[int]:
    """Fa creare ad `avvio` questi servizi; restituisce un contatore delle creazioni."""
    create: list[int] = []
    monkeypatch.setattr(avvio, "crea_servizi", lambda: create.append(1) or servizi)
    return create


def esegui(file: Path) -> AppTest:
    return AppTest.from_file(str(file), default_timeout=30).run()


def valori(elementi) -> list[str]:
    return [str(e.value) for e in elementi]


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
    assert valori(at.error) == ["Non riesco a leggere i dati."]
    assert "docker compose up -d mysql" in valori(at.code)[0]
    assert not at.metric  # niente numeri inventati


def test_se_la_configurazione_non_e_valida_lapp_si_ferma_con_il_motivo(app_pronta, monkeypatch):
    def rotta():
        raise ConfigError("Configurazione non valida: manca DB_NAME.")

    monkeypatch.setattr(app_pronta, "crea_servizi", rotta)

    at = esegui(APP / "Home.py")

    assert not at.exception
    assert valori(at.error) == ["L'applicazione non può partire."]
    assert "manca DB_NAME" in valori(at.code)[0]
    assert not at.metric


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
