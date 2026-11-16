"""La pagina Ispezioni del mockup eseguita con `AppTest` (M6-T4; tavole 25–29).

Servizi veri con apiari, alveari e ispezioni in memoria (`anagrafica_finta.py`, le stesse regole
dei repository): si usano filtri, modulo e finestre come farebbe l'utente e si controlla cosa vede
e cosa finisce nei dati. Le stesse operazioni sul database vero sono in
`test_servizi_ispezioni.py` (integration).
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import pytest
from anagrafica_finta import (
    DATABASE_SPENTO,
    NOTA_LUNGA,
    IspezioniInMemoria,
    anagrafica_di_prova,
    ispezioni_di_prova,
)
from app_finta import APP, DashboardFinto, PredittoreStub, con_accesso, installa, valori
from streamlit.testing.v1 import AppTest

from beewatch.exceptions import ValidationError
from beewatch.models import LivelloRischio
from beewatch.services import Servizi

PAGINA = APP / "pages" / "2_Ispezioni.py"


def servizi_con(apiari, alveari, ispezioni) -> Servizi:
    return Servizi(None, crea_predittore=PredittoreStub, apiari=apiari, alveari=alveari,
                   ispezioni=ispezioni, dashboard=DashboardFinto())  # fmt: skip


@pytest.fixture
def registro(app_pronta, monkeypatch) -> IspezioniInMemoria:
    """L'anagrafica di prova con le sue ispezioni, installata nei servizi della pagina."""
    apiari, alveari = anagrafica_di_prova()
    ispezioni = ispezioni_di_prova(alveari)
    installa(app_pronta, monkeypatch, servizi_con(apiari, alveari, ispezioni))
    return ispezioni


def apri() -> AppTest:
    return con_accesso(AppTest.from_file(str(PAGINA), default_timeout=30)).run()


def premi(at: AppTest, chiave: str) -> AppTest:
    return at.button(key=chiave).click().run()


def html_di(at: AppTest) -> str:
    return " ".join(e.proto.body for e in at.get("html"))


def date_in_tabella(at: AppTest) -> list[str]:
    """Le date in grassetto delle righe, nell'ordine (gg/mm/aaaa)."""
    return [
        t.strip("*") for t in valori(at.markdown) if re.fullmatch(r"\*\*\d\d/\d\d/\d{4}\*\*", t)
    ]


def nuova(at: AppTest) -> AppTest:
    return premi(at, "apri_nuova_ispezione")


# --------------------------------------------------------------------------- #
# Servizi
# --------------------------------------------------------------------------- #


def test_lelenco_delle_ispezioni_e_di_tutti_gli_apiari_dalla_piu_recente(registro):
    apiari, alveari = anagrafica_di_prova()
    servizi = servizi_con(apiari, alveari, ispezioni_di_prova(alveari))

    elenco = servizi.elenco_ispezioni(1)

    # A9 è eliminato, X1 è di un altro utente: restano le quattro di A1 e A2
    assert [(i.data_ispezione, i.codice_alveare) for i in elenco] == [
        (date(2026, 10, 30), "A1"), (date(2026, 10, 5), "A2"),
        (date(2026, 9, 12), "A1"), (date(2026, 8, 20), "A2"),
    ]  # fmt: skip


def test_eliminare_unispezione_altrui_non_si_puo(registro):
    apiari, alveari = anagrafica_di_prova()
    servizi = servizi_con(apiari, alveari, registro)

    with pytest.raises(ValidationError):
        servizi.elimina_ispezione(1, 106)  # di X1, dell'utente 2
    assert 106 in registro.righe


# --------------------------------------------------------------------------- #
# Lo storico
# --------------------------------------------------------------------------- #


def test_la_tabella_del_mockup(registro):
    at = apri()

    assert not at.exception and not at.error
    assert valori(at.title) == ["Ispezioni"]
    testo = html_di(at)
    for intestazione in ("Data", "Alveare", "Stato", "Forza", "Scorte", "Regina", "Peso",
                         "Azioni"):  # fmt: skip
        assert f"<span>{intestazione}</span>" in testo
    assert date_in_tabella(at) == ["30/10/2026", "05/10/2026", "12/09/2026", "20/08/2026"]
    assert '<span class="bw-badge critico">Rischio alto</span>' in testo
    # 12/09 di A1: 6 telaini di covata e 4 di scorte, regina vista, 41,2 kg
    assert {"Alta", "Buone", "Sì", "41,2 kg"} <= set(valori(at.markdown))
    assert "Mostrando 4 di 4 ispezioni" in valori(at.caption)
    assert at.button(key="vedi_ispezione_101") and at.button(key="elimina_ispezione_101")
    assert "bw-pillola-data" in testo


def test_i_filtri_del_mockup(registro):
    at = apri()

    at.selectbox(key="ispezioni_filtro_alveare").select("A2").run()
    assert date_in_tabella(at) == ["05/10/2026", "20/08/2026"]

    at.selectbox(key="ispezioni_filtro_alveare").select("Tutti")
    at.selectbox(key="ispezioni_filtro_rischio").select(LivelloRischio.ALTO).run()
    assert date_in_tabella(at) == ["05/10/2026"]

    at.selectbox(key="ispezioni_filtro_rischio").select("Tutti")
    at.text_input(key="ispezioni_cerca").input("da programmare").run()  # cerca nelle note
    assert date_in_tabella(at) == ["05/10/2026"]

    at.text_input(key="ispezioni_cerca").input("niente del genere").run()
    assert "Nessuna ispezione corrisponde alla ricerca o ai filtri." in valori(at.caption)


def test_il_periodo_conta_i_giorni_da_oggi(app_pronta, monkeypatch):
    apiari, alveari = anagrafica_di_prova()
    ispezioni = ispezioni_di_prova(alveari)
    servizi = servizi_con(apiari, alveari, ispezioni)
    servizi.registra_ispezione(1, alveare_id=1, data_ispezione=date.today() - timedelta(days=3),
                               livello_rischio=LivelloRischio.NESSUNO)  # fmt: skip
    installa(app_pronta, monkeypatch, servizi)
    at = apri()

    at.selectbox(key="ispezioni_periodo").select("Ultimi 30 giorni").run()

    recente = (date.today() - timedelta(days=3)).strftime("%d/%m/%Y")
    attese = [d.strftime("%d/%m/%Y") for d in sorted(
        (i.data_ispezione for i in ispezioni.righe.values()
         if i.alveare_id in (1, 2) and i.data_ispezione >= date.today() - timedelta(days=30)),
        reverse=True)]  # fmt: skip
    assert date_in_tabella(at) == attese and attese[0] == recente
    assert "20/08/2026" not in date_in_tabella(at)


def test_esporta_e_lultimo_bottone_della_barra(registro):
    at = apri()

    [bottone] = at.get("download_button")

    assert bottone.proto.label == "Esporta"


def test_senza_alveari_e_senza_ispezioni_lo_dice(app_pronta, monkeypatch):
    apiari, alveari = anagrafica_di_prova()
    installa(app_pronta, monkeypatch,
             servizi_con(apiari, alveari, IspezioniInMemoria(alveari)))  # fmt: skip

    at = apri()

    assert any("Ancora nessuna ispezione registrata." in i for i in valori(at.info))


def test_con_il_database_spento_la_pagina_lo_dice_e_si_ferma(app_pronta, monkeypatch):
    apiari, alveari = anagrafica_di_prova(errore=DATABASE_SPENTO)
    installa(app_pronta, monkeypatch, servizi_con(apiari, alveari, ispezioni_di_prova(alveari)))

    at = apri()

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")
    assert not date_in_tabella(at)


# --------------------------------------------------------------------------- #
# Le finestre: leggere ed eliminare
# --------------------------------------------------------------------------- #


def test_leggere_unispezione_intera_e_in_sola_lettura(registro):
    at = premi(apri(), "vedi_ispezione_101")

    [note] = [t for t in at.text_area if t.key == "note_ispezione_101"]
    assert note.value == NOTA_LUNGA and note.disabled
    assert "**Alveare A1 · 12/09/2026**" in valori(at.markdown)
    assert "Telaini di covata: 6" in valori(at.caption)


def test_le_note_non_si_interpretano_come_formattazione(registro):
    at = premi(apri(), "vedi_ispezione_102")

    [note] = [t for t in at.text_area if t.key == "note_ispezione_102"]
    assert "*alta*" in note.value  # gli asterischi restano asterischi


def test_eliminare_chiede_conferma_e_cancella(registro):
    at = premi(apri(), "elimina_ispezione_104")
    assert 104 in registro.righe  # aprire la finestra non cancella nulla
    assert "**Eliminare l'ispezione del 20/08/2026 di A2?**" in valori(at.markdown)

    at = premi(at, "ispezione_104_elimina")

    assert 104 not in registro.righe
    assert valori(at.success) == ["Ispezione del 20/08/2026 di A2 eliminata."]


# --------------------------------------------------------------------------- #
# La nuova ispezione
# --------------------------------------------------------------------------- #


def test_nuova_ispezione_apre_il_modulo_a_tutta_pagina(registro):
    at = nuova(apri())

    assert valori(at.title) == ["Nuova ispezione"]
    assert "**Dati ispezione**" in valori(at.markdown)
    assert at.date_input(key="ispezione_data").value == date.today()
    assert at.selectbox(key="ispezione_alveare").options == ["A1", "A2"]


def test_registrare_unispezione_la_salva_e_torna_allo_storico(registro):
    at = nuova(apri())
    at.selectbox(key="ispezione_alveare").select(2)
    at.selectbox(key="ispezione_rischio").select(LivelloRischio.MEDIO)
    at.number_input(key="ispezione_covata").set_value(5)
    at.number_input(key="ispezione_scorte").set_value(1)
    at.selectbox(key="ispezione_regina").select("Sì")
    at.number_input(key="ispezione_peso").set_value(36.4)
    at.text_area(key="ispezione_note").input("Covata compatta, scorte quasi finite.")

    at = premi(at, "nuova_ispezione_invia")

    oggi = date.today().strftime("%d/%m/%Y")
    assert valori(at.success) == [f"Ispezione di **A2** del {oggi} registrata."]
    nuova_ispezione = max(registro.righe.values(), key=lambda i: i.id)
    assert (nuova_ispezione.alveare_id, nuova_ispezione.telaini_scorte,
            nuova_ispezione.regina_vista) == (2, 1, True)  # fmt: skip
    assert float(nuova_ispezione.peso_kg) == 36.4
    assert at.session_state["finestra_aperta"] is None
    assert valori(at.title) == ["Ispezioni"] and date_in_tabella(at)[0] == oggi


def test_un_rifiuto_del_modello_indica_il_campo(registro):
    at = nuova(apri())
    at.text_area(key="ispezione_note").input("x" * 70_000)

    at = premi(at, "nuova_ispezione_invia")

    assert any("note" in e for e in valori(at.error))
    assert valori(at.title) == ["Nuova ispezione"]  # si resta nel modulo


def test_annulla_riporta_allo_storico(registro):
    at = premi(nuova(apri()), "ispezione_annulla")

    assert at.session_state["finestra_aperta"] is None and valori(at.title) == ["Ispezioni"]


def test_torna_allo_storico(registro):
    at = premi(nuova(apri()), "ispezione_torna")

    assert at.session_state["finestra_aperta"] is None and valori(at.title) == ["Ispezioni"]


def test_dal_dettaglio_dellalveare_il_modulo_ha_gia_lalveare(registro):
    at = con_accesso(AppTest.from_file(str(PAGINA), default_timeout=30))
    at.session_state["finestra_aperta"] = ("nuova_ispezione", 2)

    at.run()

    assert at.selectbox(key="ispezione_alveare").value == 2


def test_se_il_salvataggio_fallisce_lo_dice_senza_traceback(registro):
    at = nuova(apri())
    registro.errore = DATABASE_SPENTO

    at = premi(at, "nuova_ispezione_invia")

    assert not at.exception
    assert any(e.startswith("**Non riesco a raggiungere il database.**") for e in valori(at.error))
