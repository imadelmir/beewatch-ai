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
from app_finta import con_accesso
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
    at = con_accesso(AppTest.from_file(str(APP / "Home.py"), default_timeout=60)).run()

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
    """Ogni pagina aperta dalla Home, come nel browser: solo così `st.page_link` funziona.

    Con i dati del seed la pagina Ispezioni arriva alla scheda di un'ispezione, che ha il
    collegamento alla pagina Alveari: aperta da sola, AppTest non conosce le altre pagine.
    """
    for pagina in sorted((APP / "pages").glob("*.py")):
        at = con_accesso(AppTest.from_file(str(APP / "Home.py"), default_timeout=60)).run()
        at.switch_page(str(pagina.relative_to(APP))).run()
        assert not at.exception, pagina.name
        assert not at.error, pagina.name
        if pagina.name == "2_Ispezioni.py":  # lo storico del seed arriva davvero alla pagina
            assert at.dataframe and len(at.dataframe[0].value) > 0


def test_con_un_utente_senza_dati_ogni_pagina_resta_usabile(
    home_con_database, database_test: Database
) -> None:
    """M6-T9: database vuoto per l'utente (nessun apiario, nessuna stima, nessun riepilogo)."""
    with database_test.transazione() as cursore:
        cursore.execute(
            "INSERT INTO utenti (email, nome_completo, hash_password) VALUES (%s, %s, %s)",
            ("vuoto-m6t9@beewatch.test", "Utente vuoto", "x" * 60),
        )
        utente = cursore.lastrowid
    try:
        for pagina in [APP / "Home.py", *sorted((APP / "pages").glob("*.py"))]:
            at = con_accesso(AppTest.from_file(str(APP / "Home.py"), default_timeout=60))
            at.session_state["utente_id"] = utente  # `inizializza_stato` non lo sovrascrive
            at.run()
            if pagina.name != "Home.py":
                at.switch_page(str(pagina.relative_to(APP))).run()
            assert not at.exception, pagina.name
            assert not at.error, (pagina.name, [e.value for e in at.error])
            assert at.session_state["utente_id"] == utente
    finally:
        with database_test.transazione() as cursore:
            cursore.execute("DELETE FROM utenti WHERE id = %s", (utente,))
