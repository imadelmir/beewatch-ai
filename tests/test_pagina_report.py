"""La pagina Report eseguita con `AppTest` (M6-T12)."""

from __future__ import annotations

import pytest
from anagrafica_finta import (
    DATABASE_SPENTO,
    AlveariInMemoria,
    ApiariInMemoria,
    anagrafica_di_prova,
    ispezioni_di_prova,
    raccolti_di_prova,
)
from app_finta import APP, DashboardFinto, PredittoreStub, con_accesso, installa, valori
from report_finto import ReportInMemoria
from streamlit.testing.v1 import AppTest

from beewatch.services import Servizi

PAGINA = APP / "pages" / "7_Report.py"


def prepara(app_pronta, monkeypatch, *, apiari=None, alveari=None) -> ReportInMemoria:
    if apiari is None:
        apiari, alveari = anagrafica_di_prova()
    archivio = ReportInMemoria()
    installa(
        app_pronta,
        monkeypatch,
        Servizi(None, apiari=apiari, alveari=alveari, ispezioni=ispezioni_di_prova(alveari),
                raccolti=raccolti_di_prova(apiari), report=archivio, dashboard=DashboardFinto(),
                crea_predittore=PredittoreStub),
    )  # fmt: skip
    return archivio


@pytest.fixture
def archivio(app_pronta, monkeypatch) -> ReportInMemoria:
    return prepara(app_pronta, monkeypatch)


def apri() -> AppTest:
    return con_accesso(AppTest.from_file(str(PAGINA), default_timeout=30)).run()


def genera(at: AppTest, modello: str, **campi) -> AppTest:
    at.radio(key="report_modello").set_value(modello)
    if "mese" in campi:
        at.selectbox(key="report_mese").set_value(campi["mese"])
    if "anno" in campi:
        at.selectbox(key="report_anno").set_value(campi["anno"])
    return at.button(key="report_genera").click().run()


def scaricabili(at: AppTest) -> list:
    return at.get("download_button")


def test_senza_report_larchivio_invita_a_generarne_uno(archivio):
    at = apri()

    assert not at.exception and not at.error
    assert valori(at.title) == ["📄 Report"]
    assert at.radio(key="report_modello").options == [
        "Report mensile", "Analisi della produzione", "Stato sanitario",
    ]  # fmt: skip
    assert any(t.startswith("Nessun report nell'archivio.") for t in valori(at.info))
    assert {m.label: m.value for m in at.metric} == {"Report salvati": "0"}


def test_generare_un_report_lo_salva_lo_apre_e_lo_fa_scaricare(archivio):
    at = genera(apri(), "mensile", mese=10, anno=2026)

    assert not at.exception and not at.error
    assert valori(at.success) == [
        "Report «Report mensile · Collina · ottobre 2026» salvato nell'archivio."
    ]
    assert len(archivio.righe) == 1
    assert "#### Report mensile · Collina · ottobre 2026" in valori(at.markdown)
    sintesi = at.dataframe[0].value.to_dict("records")
    assert {"Voce": "Ispezioni", "Valore": "2"} in sintesi
    assert {"Voce": "Alveari ispezionati", "Valore": "2 di 2"} in sintesi
    bottoni = scaricabili(at)
    assert [b.proto.label for b in bottoni] == [
        "Scarica in CSV", "Scarica in Excel (XLSX)", "Scarica in PDF",
    ]  # fmt: skip


def test_ogni_modello_si_genera(archivio):
    at = apri()
    for modello, titolo in (
        ("produzione", "Analisi della produzione · Collina"),
        ("sanitario", "Stato sanitario · Collina"),
    ):
        at = genera(at, modello)
        assert f"#### {titolo}" in valori(at.markdown)
    assert {m.label: m.value for m in at.metric} == {"Report salvati": "2"}


def test_larchivio_apre_un_report_precedente(archivio):
    at = genera(apri(), "sanitario")
    at = genera(at, "produzione")
    [scelta] = [s for s in at.selectbox if s.key.startswith("report_scelto_")]

    scelta.select(1).run()  # il primo, lo stato sanitario

    assert "#### Stato sanitario · Collina" in valori(at.markdown)


def test_eliminare_chiede_una_conferma(archivio):
    at = genera(apri(), "sanitario")

    assert at.button(key="report_1_elimina").disabled
    at.checkbox(key="report_1_conferma").check().run()
    at = at.button(key="report_1_elimina").click().run()

    assert valori(at.success) == ["Report eliminato dall'archivio."]
    assert archivio.righe == {}


def test_senza_apiari_si_vede_solo_larchivio(app_pronta, monkeypatch):
    apiari = ApiariInMemoria()
    prepara(app_pronta, monkeypatch, apiari=apiari, alveari=AlveariInMemoria(apiari))

    at = apri()

    assert not at.exception and not at.error
    assert any(t.startswith("Nessun apiario registrato.") for t in valori(at.info))
    assert not [b for b in at.main.button if b.key == "report_genera"]


def test_con_il_database_spento_lo_dice_e_si_ferma(archivio):
    archivio.errore = DATABASE_SPENTO

    at = apri()

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")
    assert not scaricabili(at)


def test_se_il_salvataggio_fallisce_lo_dice(archivio):
    at = apri()
    archivio.errore = DATABASE_SPENTO

    at = genera(at, "sanitario")

    assert not at.exception and not at.success
    assert any(e.startswith("**Non riesco a raggiungere il database.**") for e in valori(at.error))


def test_se_un_report_non_si_riapre_lo_dice(app_pronta, archivio, monkeypatch):
    at = genera(apri(), "sanitario")

    def guasto(*_):
        raise DATABASE_SPENTO

    monkeypatch.setattr(archivio, "trova", guasto)
    app_pronta.svuota_letture()  # il report non è più in cache: va riletto
    at.run()

    assert not at.exception
    assert any(e.startswith("**Non riesco a raggiungere il database.**") for e in valori(at.error))
    assert not scaricabili(at)


def test_se_leliminazione_fallisce_lo_dice(archivio, monkeypatch):
    at = genera(apri(), "sanitario")

    def guasto(*_):
        raise DATABASE_SPENTO

    monkeypatch.setattr(archivio, "elimina", guasto)
    at.checkbox(key="report_1_conferma").check().run()
    at = at.button(key="report_1_elimina").click().run()

    assert not at.success
    assert any(e.startswith("**Non riesco a raggiungere il database.**") for e in valori(at.error))
    assert len(archivio.righe) == 1
