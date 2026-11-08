"""Finti e scorciatoie per eseguire l'interfaccia con `AppTest` (M6-T1, M6-T2, M6-T4).

Servizi veri (`Servizi`) con repository finti: nessun database, nessuna rete. La fixture
`app_pronta` (in `conftest.py`) mette `app/` nel percorso degli import e pulisce le cache; qui ci
sono i pezzi che i test dell'interfaccia condividono.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from beewatch.models import Alveare, Apiario, Ispezione, LivelloRischio, StatoAlveare
from beewatch.services import Servizi

RADICE = Path(__file__).resolve().parents[1]
APP = RADICE / "app"
PAGINE = sorted((APP / "pages").glob("*.py"))
MODULI_DI_APP = ("avvio", "ui")  # `ui` tiene un riferimento ad `avvio`: si ricaricano insieme


def prepara_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """`app/` nel percorso degli import (lo fa `streamlit run`, non AppTest) e cache pulite."""
    monkeypatch.syspath_prepend(str(APP))
    for nome in MODULI_DI_APP:
        sys.modules.pop(nome, None)
    import avvio

    st.cache_resource.clear()
    st.cache_data.clear()
    monkeypatch.setattr(avvio, "configura", lambda: None)  # il logging vero legge il .env
    yield avvio
    st.cache_resource.clear()
    st.cache_data.clear()
    for nome in MODULI_DI_APP:
        sys.modules.pop(nome, None)


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
    def __init__(
        self, nomi: tuple[str, ...] = ("Collina", "Valle"), errore: Exception | None = None
    ):
        self.nomi = nomi
        self.errore = errore

    def elenca(self, utente_id: int) -> list[Apiario]:
        if self.errore:
            raise self.errore
        return [Apiario(utente_id=utente_id, nome=n, id=10 + i) for i, n in enumerate(self.nomi)]


class AlveariFinti:
    def trascurati(self, utente_id: int) -> list[dict]:
        return [{"id": 3, "codice": "A3"}, {"id": 5, "codice": "B1"}]

    # La pagina Alveari (M6-T3) chiede anche questi: qui nessun alveare da elencare. I test
    # della pagina usano l'anagrafica in memoria di `anagrafica_finta.py`.
    def trova_alveari_attivi(self, utente_id: int) -> list:
        return []

    def elenco_con_ultima_ispezione(self, utente_id: int) -> list[dict]:
        return []


class AlveariConUnaIspezione(AlveariFinti):
    """L'alveare A3 di Collina, ispezionato il 30/10/2026: per le pagine «con dati»."""

    def trova_alveari_attivi(self, utente_id: int) -> list[Alveare]:
        return [Alveare(apiario_id=10, codice="A3", stato=StatoAlveare.IN_SALUTE, id=3)]

    def elenco_con_ultima_ispezione(self, utente_id: int) -> list[dict]:
        return [
            {"id": 3, "codice": "A3", "ultima_ispezione": date(2026, 10, 30),
             "peso_kg": Decimal("38.50")}
        ]  # fmt: skip


class IspezioniFinte:
    """Una sola ispezione, dell'alveare A3 (`AlveariConUnaIspezione`)."""

    def ispezioni_per_alveare(self, utente_id: int, alveare_id: int) -> list[Ispezione]:
        if alveare_id != 3:
            return []
        return [
            Ispezione(alveare_id=3, data_ispezione=date(2026, 10, 30), id=1,
                      livello_rischio=LivelloRischio.BASSO, peso_kg=Decimal("38.50"))
        ]  # fmt: skip


class PredittoreStub:
    versione = "v-stub"
    metadati = {
        "algoritmo": "RandomForestRegressor",
        "metriche": {"hold_out_2010_2012": {"mae_kg": 3.499}},
        "addestrato_il": "2026-10-23T12:00:00+00:00",
        "addestramento": {"righe": 600},
    }


def servizi_finti(
    dashboard: DashboardFinto | None = None,
    apiari: ApiariFinti | None = None,
    crea_predittore=PredittoreStub,
    alveari: AlveariFinti | None = None,
    ispezioni: IspezioniFinte | None = None,
) -> Servizi:
    return Servizi(
        None,
        crea_predittore=crea_predittore,
        dashboard=dashboard or DashboardFinto(),
        apiari=apiari or ApiariFinti(),
        alveari=alveari or AlveariFinti(),
        ispezioni=ispezioni or IspezioniFinte(),
        descrizione_llm="llama3.1:8b via ollama (chiave: non richiesta)",
    )


def installa(avvio, monkeypatch, servizi: Servizi) -> list[int]:
    """Fa creare ad `avvio` questi servizi; restituisce un contatore delle creazioni."""
    create: list[int] = []
    monkeypatch.setattr(avvio, "crea_servizi", lambda: create.append(1) or servizi)
    return create


def esegui(file: Path) -> AppTest:
    return AppTest.from_file(str(file), default_timeout=30).run()


def naviga(file: Path) -> AppTest:
    """Apre la Home e poi la pagina, come nel browser: così Streamlit conosce tutte le pagine.

    Serve alle pagine con `st.page_link` (Ispezioni): aperte da sole, il collegamento fallisce.
    """
    at = esegui(APP / "Home.py")
    return at if file.name == "Home.py" else at.switch_page(str(file.relative_to(APP))).run()


def valori(elementi) -> list[str]:
    return [str(e.value) for e in elementi]
