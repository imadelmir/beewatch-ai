"""La Home con MySQL vero e il seed (M6-T1), nello stack Docker isolato.

I repository sono quelli veri: si verifica che le query della panoramica girino davvero e che i
numeri arrivino alla pagina. I valori che dipendono dalla data di oggi (ispezioni recenti, alveari
da controllare) non si controllano: cambierebbero col calendario.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from beewatch.database import Database
from beewatch.ml.predictor import Predittore
from beewatch.services import Servizi

pytestmark = pytest.mark.integration

RADICE = Path(__file__).resolve().parents[1]
APP = RADICE / "app"


@pytest.fixture
def home_con_database(monkeypatch: pytest.MonkeyPatch, database_test: Database):
    monkeypatch.syspath_prepend(str(APP))
    sys.modules.pop("avvio", None)
    import avvio

    st.cache_resource.clear()
    st.cache_data.clear()
    monkeypatch.setattr(avvio, "configura", lambda: None)
    servizi = Servizi(
        database_test,
        crea_predittore=lambda: Predittore(RADICE / "models" / "produzione_v1.joblib"),
        descrizione_llm="prova",
    )
    monkeypatch.setattr(avvio, "crea_servizi", lambda: servizi)
    yield
    st.cache_resource.clear()
    st.cache_data.clear()
    sys.modules.pop("avvio", None)


def test_la_home_legge_il_seed_dal_database_vero(home_con_database) -> None:
    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=60).run()

    assert not at.exception
    numeri = {m.label: m.value for m in at.metric}
    assert numeri["Alveari attivi"] == "4"  # i quattro alveari del seed
    assert numeri["Produzione stagione"].endswith(" kg")
    assert int(numeri["Ispezioni (30 giorni)"]) >= 0 and int(numeri["Da controllare"]) <= 4
    assert at.session_state["utente_id"] == 1
    assert at.session_state["apiario_attivo_id"] is not None  # l'apiario del seed
    assert any("Apiario attivo:" in str(c.value) for c in at.caption)
    assert not at.error and not at.warning


def test_le_sei_pagine_partono_con_il_database_vero(home_con_database) -> None:
    for pagina in sorted((APP / "pages").glob("*.py")):
        at = AppTest.from_file(str(pagina), default_timeout=60).run()
        assert not at.exception, pagina.name
        assert not at.error, pagina.name
