"""Il modello e i raccolti nella pagina Previsioni (M6-T7, prima pagina Dashboard; mockup).

Servizi veri con anagrafica, raccolti, dati USDA e predittore finti: si controllano i grafici
(assi con unità, palette, fonte), la card «Affidabilità modello» con le metriche dei metadati e
gli stati della pagina, anche con un solo alveare e una sola ispezione.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from anagrafica_finta import (
    DATABASE_SPENTO,
    AlveariInMemoria,
    ApiariInMemoria,
    RaccoltiInMemoria,
    anagrafica_di_prova,
    raccolti_di_prova,
)
from app_finta import APP, DashboardFinto, con_accesso, installa, valori
from previsione_finta import (
    ModelliFinti,
    PredittoreFinto,
    PrevisioniInMemoria,
    ProduzioneFinta,
)
from streamlit.testing.v1 import AppTest

from beewatch.exceptions import ModelError
from beewatch.models import Alveare, Apiario, Raccolto, StatoAlveare, TipoMiele
from beewatch.services import Servizi

PAGINA = APP / "pages" / "3_Previsione.py"
PRIMARIO = "#F5B301"  # l'Accent del mockup (specifica §3)


def prepara(app_pronta, monkeypatch, *, apiari=None, alveari=None, raccolti=None,
            produzione=None, crea_predittore=None) -> None:  # fmt: skip
    if apiari is None:
        apiari, alveari = anagrafica_di_prova()
        raccolti = raccolti_di_prova(apiari)
    servizi = Servizi(
        None,
        apiari=apiari,
        alveari=alveari,
        raccolti=raccolti or RaccoltiInMemoria(apiari),
        produzione=produzione or ProduzioneFinta(),
        crea_predittore=crea_predittore or PredittoreFinto,
        dashboard=DashboardFinto(),
        previsioni=PrevisioniInMemoria({1: "A1", 2: "A2"}),
        modelli=ModelliFinti(),
    )
    installa(app_pronta, monkeypatch, servizi)


@pytest.fixture
def pronta(app_pronta, monkeypatch) -> None:
    prepara(app_pronta, monkeypatch)


def apri() -> AppTest:
    return con_accesso(AppTest.from_file(str(PAGINA), default_timeout=30)).run()


def metriche(at: AppTest) -> dict[str, str]:
    return {m.label: m.value for m in at.metric}


def figure(at: AppTest) -> list[dict]:
    return [json.loads(g.proto.spec) for g in at.get("plotly_chart")]


def fonti(at: AppTest) -> list[str]:
    return [c for c in valori(at.caption) if c.startswith("Fonte: ")]


# --------------------------------------------------------------------------- #
# Con dati
# --------------------------------------------------------------------------- #


def affidabilita(at: AppTest) -> str:
    """Il testo della card «Affidabilità modello» (un elenco HTML, non delle metriche)."""
    return " ".join(e.proto.body for e in at.get("html"))


def test_la_pagina_ha_le_card_del_modello_e_dei_raccolti(pronta):
    at = apri()

    assert not at.exception and not at.error
    assert valori(at.title) == ["Previsioni"]
    for titolo in ("Storico vs previsto", "Affidabilità modello", "Storico delle previsioni",
                   "I tuoi raccolti · Collina"):  # fmt: skip
        assert titolo in valori(at.subheader), titolo
    assert any("102,5 kg in tutto, 51,2 kg in media" in c for c in valori(at.caption))
    assert not at.metric  # prima del calcolo nessuna stima: niente numeri senza banda


def test_tre_grafici_con_assi_in_unita_palette_e_fonte(pronta):
    at = apri()

    confronto, serie, distribuzione = figure(at)
    assert serie["layout"]["yaxis"]["title"]["text"] == "Miele raccolto (kg)"
    assert serie["layout"]["xaxis"]["title"]["text"] == "Anno"
    assert distribuzione["layout"]["yaxis"]["title"]["text"] == "Miele raccolto in tutto (kg)"
    assert confronto["layout"]["yaxis"]["title"]["text"] == "Resa per colonia (kg)"
    for figura in (serie, distribuzione, confronto):
        colori = {
            colore
            for t in figura["data"]
            for colore in (t.get("marker", {}).get("color"), t.get("line", {}).get("color"))
        }
        assert PRIMARIO in colori  # la palette del §3, non il default di Plotly
    assert len(fonti(at)) >= 3  # ogni grafico ha la sua fonte


def test_la_serie_e_la_distribuzione_tengono_separato_lintero_apiario(pronta):
    at = apri()

    _, serie, distribuzione = figure(at)
    assert {t["name"] for t in serie["data"]} == {"A1", "Intero apiario", "Alveare eliminato"}
    assert list(distribuzione["data"][0]["x"]) == [
        "A1",
        "A2",
        "Alveare eliminato",  # dopo gli alveari attivi, le altre voci in ordine alfabetico
        "Intero apiario",
    ]
    assert any("dividerle fra gli alveari sarebbe inventare" in c for c in valori(at.caption))


def test_il_confronto_ha_barre_raggruppate_con_la_banda_sul_previsto(pronta):
    at = apri()

    confronto = figure(at)[0]
    assert confronto["layout"]["barmode"] == "group"
    previsto, reale = confronto["data"]
    assert (previsto["name"], reale["name"]) == ("Previsto dal modello", "Reale (USDA)")
    assert previsto["error_y"]["array"] and len(previsto["x"]) == 6
    assert confronto["layout"]["title"]["text"] == "Previsto e reale in California"


def test_si_puo_cambiare_lo_stato_del_confronto(pronta):
    at = apri()
    at.selectbox(key="dashboard_stato").select("ND").run()

    assert figure(at)[0]["layout"]["title"]["text"] == "Previsto e reale in North Dakota"


def test_le_metriche_del_modello_vengono_dai_metadati(pronta):
    at = apri()

    testo = affidabilita(at)
    for voce, valore in (("R²", "0,62"), ("Errore medio (MAE)", "3,5 kg"), ("RMSE", "4,5 kg"),
                         ("Errore in validazione", "4,1 kg"), ("Modello", "v-finto")):  # fmt: skip
        assert voce in testo and valore in testo, voce
    didascalia = next(c for c in valori(at.caption) if c.startswith("Il riferimento più forte"))
    assert "«persistenza (resa dell'anno prima)»" in didascalia


# --------------------------------------------------------------------------- #
# Un solo alveare, nessun dato, errori
# --------------------------------------------------------------------------- #


def test_con_un_solo_alveare_e_una_sola_ispezione_resta_leggibile(app_pronta, monkeypatch):
    apiari = ApiariInMemoria(Apiario(utente_id=1, nome="Orto", id=10))
    alveari = AlveariInMemoria(
        apiari,
        Alveare(apiario_id=10, codice="U1", stato=StatoAlveare.IN_SALUTE, id=1),
        ispezioni={1: (date(2026, 9, 1), Decimal("30.00"))},
    )
    raccolti = RaccoltiInMemoria(
        apiari,
        Raccolto(apiario_id=10, alveare_id=1, tipo_miele=TipoMiele.ACACIA,
                 data_raccolto=date(2026, 6, 1), quantita_kg=Decimal("8.50"), id=1),
    )  # fmt: skip
    prepara(app_pronta, monkeypatch, apiari=apiari, alveari=alveari, raccolti=raccolti)

    at = apri()

    assert not at.exception and not at.error
    assert any("8,5 kg in tutto, 8,5 kg in media" in c for c in valori(at.caption))
    _, serie, distribuzione = figure(at)
    assert [t["name"] for t in serie["data"]] == ["U1"]
    assert list(distribuzione["data"][0]["x"]) == ["U1"]


def test_un_apiario_senza_raccolti_mostra_solo_il_modello(pronta):
    at = apri()
    at.sidebar.selectbox[0].select(11).run()  # «Valle»: niente alveari, niente raccolti

    assert not any(s.startswith("I tuoi raccolti") for s in valori(at.subheader))
    assert len(figure(at)) == 1  # resta il confronto del modello


def test_senza_apiari_il_modello_resta(app_pronta, monkeypatch):
    apiari = ApiariInMemoria()
    prepara(app_pronta, monkeypatch, apiari=apiari, alveari=AlveariInMemoria(apiari))

    at = apri()

    assert not at.exception and not at.error
    assert "Errore medio (MAE)" in affidabilita(at)


def test_senza_modello_lo_dice_e_i_raccolti_si_vedono(app_pronta, monkeypatch):
    def manca():
        raise ModelError("Il modello non è stato trovato: lancia scripts/train_model.py.")

    prepara(app_pronta, monkeypatch, crea_predittore=manca)

    at = apri()

    assert not at.exception
    assert any(e.startswith("**Il modello di previsione non è disponibile.**")
               for e in valori(at.error))  # fmt: skip
    assert any("102,5 kg in tutto" in c for c in valori(at.caption))


def test_senza_dati_usda_rimanda_alletl(app_pronta, monkeypatch):
    prepara(app_pronta, monkeypatch, produzione=ProduzioneFinta(vuota=True))

    at = apri()

    assert not at.exception and not at.error
    assert any("run_etl.py" in t for t in valori(at.info))


def test_con_il_database_spento_lo_dice_e_si_ferma(app_pronta, monkeypatch):
    apiari, alveari = anagrafica_di_prova(errore=DATABASE_SPENTO)
    prepara(app_pronta, monkeypatch, apiari=apiari, alveari=alveari)

    at = apri()

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")
    assert not at.metric


def test_se_il_confronto_fallisce_il_resto_della_pagina_resta(app_pronta, monkeypatch):
    from previsione_finta import FEATURE_INCOMPATIBILI

    prepara(
        app_pronta,
        monkeypatch,
        crea_predittore=lambda: PredittoreFinto(errore=FEATURE_INCOMPATIBILI),
    )

    at = apri()

    assert not at.exception
    assert any("mancano le colonne" in e for e in valori(at.error))
    assert "3,5 kg" in affidabilita(at)  # le metriche si leggono lo stesso
    assert len(figure(at)) == 2  # i due grafici dei raccolti
