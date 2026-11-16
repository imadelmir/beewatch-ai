"""La pagina Report del mockup eseguita con `AppTest` (M6-T12; tavole 35–39).

Le finestre si aprono e si chiudono come nel browser; dopo ogni scrittura il test riparte da
una pagina nuova (AppTest conserva gli elementi di una finestra chiusa), con i dati nei finti.
"""

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


def premi(at: AppTest, chiave: str) -> AppTest:
    return at.button(key=chiave).click().run()


def genera(modello: str, **campi) -> AppTest:
    """Dalla card del modello: «Genera», poi mese e anno nella finestra, poi «Genera report»."""
    at = premi(apri(), f"genera_{modello}")
    if "mese" in campi:
        at.selectbox(key="report_mese").set_value(campi["mese"])
    if "anno" in campi:
        at.selectbox(key="report_anno").set_value(campi["anno"])
    return premi(at, "report_genera")


def scaricabili(at: AppTest) -> list:
    return at.get("download_button")


def html_di(at: AppTest) -> str:
    return " ".join(e.proto.body for e in at.get("html"))


def test_le_tre_card_e_larchivio_vuoto(archivio):
    at = apri()

    assert not at.exception and not at.error
    assert valori(at.title) == ["Report"]
    testo = html_di(at)
    for titolo in ("Report mensile", "Analisi della produzione", "Stato sanitario"):
        assert titolo in testo
    assert [b.key for b in at.main.button if b.key.startswith("genera_")] == [
        "genera_mensile", "genera_produzione", "genera_sanitario",
    ]  # fmt: skip
    assert "Report generati" in valori(at.subheader)
    assert any(t.startswith("Nessun report nell'archivio.") for t in valori(at.info))


def test_la_card_apre_la_finestra_con_il_suo_modello(archivio):
    at = premi(apri(), "genera_sanitario")

    assert at.selectbox(key="report_modello").value == "sanitario"
    assert at.selectbox(key="report_modello").options == [
        "Report mensile", "Analisi della produzione", "Stato sanitario",
    ]  # fmt: skip


def test_generare_un_report_lo_salva_e_lo_mette_in_archivio(archivio):
    at = genera("mensile", mese=10, anno=2026)

    assert not at.exception and not at.error
    assert valori(at.success) == [
        "Report «Report mensile · Collina · ottobre 2026» salvato nell'archivio."
    ]
    assert len(archivio.righe) == 1
    assert "**Report mensile · Collina · ottobre 2026**" in valori(at.markdown)
    assert "Mostrando 1 di 1 report" in valori(at.caption)
    assert "CSV · Excel (XLSX) · PDF" in valori(at.markdown)


def test_aprire_un_report_mostra_sintesi_e_i_tre_download(archivio):
    genera("mensile", mese=10, anno=2026)
    [ident] = archivio.righe

    at = premi(apri(), f"apri_report_{ident}")

    assert "#### Report mensile · Collina · ottobre 2026" in valori(at.markdown)
    sintesi = at.dataframe[0].value.to_dict("records")
    assert {"Voce": "Ispezioni", "Valore": "2"} in sintesi
    assert {"Voce": "Alveari ispezionati", "Valore": "2 di 2"} in sintesi
    assert [b.proto.label for b in scaricabili(at)] == [
        "Scarica in CSV", "Scarica in Excel (XLSX)", "Scarica in PDF",
    ]  # fmt: skip


def test_ogni_modello_si_genera(archivio):
    for modello, titolo in (
        ("produzione", "Analisi della produzione · Collina"),
        ("sanitario", "Stato sanitario · Collina"),
    ):
        at = genera(modello)
        assert f"**{titolo}**" in valori(at.markdown)
    assert "Mostrando 2 di 2 report" in valori(apri().caption)


def test_cercare_nellarchivio(archivio):
    genera("sanitario")
    genera("produzione")

    at = apri()
    at.text_input(key="report_cerca").input("sanitario").run()

    assert "Mostrando 1 di 1 report" in valori(at.caption)
    assert "**Stato sanitario · Collina**" in valori(at.markdown)


def test_eliminare_chiede_una_conferma(archivio):
    genera("sanitario")
    [ident] = archivio.righe

    at = premi(apri(), f"elimina_report_{ident}")
    assert ident in archivio.righe  # aprire la finestra non elimina nulla
    at = premi(at, f"report_{ident}_elimina")

    assert valori(at.success) == ["Report eliminato dall'archivio."]
    assert archivio.righe == {}


def test_senza_apiari_si_vede_solo_larchivio(app_pronta, monkeypatch):
    apiari = ApiariInMemoria()
    prepara(app_pronta, monkeypatch, apiari=apiari, alveari=AlveariInMemoria(apiari))

    at = apri()

    assert not at.exception and not at.error
    assert any(t.startswith("Nessun apiario registrato.") for t in valori(at.info))
    assert not [b for b in at.main.button if b.key.startswith("genera_")]
    assert at.button(key="apri_genera_report").disabled


def test_con_il_database_spento_lo_dice_e_si_ferma(archivio):
    archivio.errore = DATABASE_SPENTO

    at = apri()

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")
    assert not scaricabili(at)


def test_se_il_salvataggio_fallisce_lo_dice(archivio):
    at = premi(apri(), "genera_sanitario")
    archivio.errore = DATABASE_SPENTO

    at = premi(at, "report_genera")

    assert not at.exception and not at.success
    assert any(e.startswith("**Non riesco a raggiungere il database.**") for e in valori(at.error))


def test_se_un_report_non_si_riapre_lo_dice(app_pronta, archivio, monkeypatch):
    genera("sanitario")
    [ident] = archivio.righe

    def guasto(*_):
        raise DATABASE_SPENTO

    monkeypatch.setattr(archivio, "trova", guasto)
    app_pronta.svuota_letture()  # il report non è più in cache: va riletto
    at = premi(apri(), f"apri_report_{ident}")

    assert not at.exception
    assert any(e.startswith("**Non riesco a raggiungere il database.**") for e in valori(at.error))
    assert not scaricabili(at)


def test_se_leliminazione_fallisce_lo_dice(archivio, monkeypatch):
    genera("sanitario")
    [ident] = archivio.righe

    def guasto(*_):
        raise DATABASE_SPENTO

    monkeypatch.setattr(archivio, "elimina", guasto)
    at = premi(premi(apri(), f"elimina_report_{ident}"), f"report_{ident}_elimina")

    assert not at.success
    assert any(e.startswith("**Non riesco a raggiungere il database.**") for e in valori(at.error))
    assert len(archivio.righe) == 1
