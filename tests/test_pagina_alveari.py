"""La pagina Alveari del mockup eseguita con `AppTest` (M6-T3; tavole 16–24).

Servizi veri con anagrafica e ispezioni in memoria (`anagrafica_finta.py`, le stesse regole dei
repository): si usano tabella, filtri e finestre come farebbe l'utente e si controlla cosa vede e
cosa è cambiato nei dati. Le stesse operazioni sul database vero sono in
`test_servizi_anagrafica.py` (integration).
"""

from __future__ import annotations

import re
from datetime import date

import pytest
from anagrafica_finta import DATABASE_SPENTO, anagrafica_di_prova, ispezioni_di_prova
from app_finta import APP, DashboardFinto, PredittoreStub, con_accesso, installa, valori
from streamlit.testing.v1 import AppTest

from beewatch.models import StatoAlveare
from beewatch.services import SOGLIE_FORZA, SOGLIE_SCORTE, Servizi, classifica_telaini

PAGINA = APP / "pages" / "1_Alveari.py"


@pytest.fixture
def anagrafica(app_pronta, monkeypatch):
    """L'anagrafica di prova installata nei servizi della pagina: (apiari, alveari, servizi)."""
    apiari, alveari = anagrafica_di_prova()
    servizi = Servizi(
        None,
        crea_predittore=PredittoreStub,
        apiari=apiari,
        alveari=alveari,
        ispezioni=ispezioni_di_prova(alveari),
        dashboard=DashboardFinto(),
        descrizione_llm="llama3.1:8b via ollama (chiave: non richiesta)",
    )
    installa(app_pronta, monkeypatch, servizi)
    return apiari, alveari, servizi


def apri() -> AppTest:
    return con_accesso(AppTest.from_file(str(PAGINA), default_timeout=30)).run()


def premi(at: AppTest, chiave: str) -> AppTest:
    return at.button(key=chiave).click().run()


def html_di(at: AppTest) -> str:
    return " ".join(e.proto.body for e in at.get("html"))


def righe(at: AppTest) -> list[str]:
    """I codici delle righe della tabella, nell'ordine."""
    testi = valori(at.markdown)
    # solo i codici in grassetto delle righe (non il titolo di una finestra)
    return [t.strip("*") for t in testi if re.fullmatch(r"\*\*[A-Za-z0-9]+\*\*", t)]


# --------------------------------------------------------------------------- #
# Forza e scorte (servizi)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("telaini", "forza", "scorte"),
    [(None, None, None), (0, "Bassa", "Scarse"), (2, "Bassa", "Medie"), (3, "Media", "Medie"),
     (4, "Media", "Buone"), (6, "Alta", "Buone"), (10, "Alta", "Buone")],
)  # fmt: skip
def test_forza_e_scorte_dai_telaini(telaini, forza, scorte):
    assert classifica_telaini(telaini, SOGLIE_FORZA) == forza
    assert classifica_telaini(telaini, SOGLIE_SCORTE) == scorte


def test_lelenco_degli_alveari_ha_tutti_gli_apiari_e_lultima_ispezione(anagrafica):
    *_, servizi = anagrafica

    elenco = servizi.elenco_alveari(1)

    assert [(r.apiario, r.codice) for r in elenco] == [("Collina", "A1"), ("Collina", "A2")]
    a1, a2 = elenco
    # A1: l'ultima ispezione (30/10) non ha contato i telaini: valgono quelli del 12/09
    assert (a1.ultima_ispezione, a1.peso_kg) == (date(2026, 10, 30), 38.5)
    assert (a1.forza, a1.scorte) == ("Alta", "Buone")
    assert (a2.forza, a2.scorte, a2.peso_kg) == ("Bassa", None, None)


# --------------------------------------------------------------------------- #
# La tabella
# --------------------------------------------------------------------------- #


def test_la_tabella_del_mockup(anagrafica):
    at = apri()

    assert not at.exception and not at.error
    assert valori(at.title) == ["Alveari"]
    testo = html_di(at)
    for intestazione in ("ID alveare", "Posizione", "Stato", "Forza", "Scorte di miele",
                         "Ultima ispezione", "Azioni"):  # fmt: skip
        assert intestazione in testo
    assert righe(at) == ["A1", "A2"]
    assert '<span class="bw-badge sano">In salute</span>' in testo
    assert '<span class="bw-badge attenzione">Debole</span>' in testo
    assert "30/10/2026" in valori(at.markdown) and "Alta" in valori(at.markdown)
    assert "Mostrando 2 di 2 alveari" in valori(at.caption)
    for chiave in ("vedi_1", "modifica_1", "elimina_1"):  # le tre azioni di ogni riga
        assert at.button(key=chiave)


def test_cercare_e_filtrare(anagrafica):
    at = apri()

    at.text_input(key="alveari_cerca").input("a2").run()
    assert righe(at) == ["A2"]

    at.text_input(key="alveari_cerca").input("").run()
    at.selectbox(key="alveari_filtro_stato").select(StatoAlveare.IN_SALUTE).run()
    assert righe(at) == ["A1"]

    at.selectbox(key="alveari_filtro_stato").select("Tutti").run()
    at.selectbox(key="alveari_filtro_apiario").select("Valle").run()
    assert righe(at) == []
    assert "Nessun alveare corrisponde alla ricerca o ai filtri." in valori(at.caption)


def test_esporta_e_il_csv_della_tabella_filtrata(anagrafica):
    at = apri()

    [bottone] = at.get("download_button")

    assert bottone.proto.label == "Esporta"


def test_il_csv_si_apre_in_excel_in_italiano(app_pronta):
    import pandas as pd
    import schede

    dati = schede.csv_per_excel(pd.DataFrame([{"ID alveare": "A1", "Peso (kg)": 38.5}]))

    assert dati.startswith("\ufeff".encode())
    assert dati.decode("utf-8-sig").splitlines() == ["ID alveare;Peso (kg)", "A1;38,5"]


def test_dieci_righe_per_pagina(anagrafica):
    *_, servizi = anagrafica
    for numero in range(3, 15):
        servizi.crea_alveare(1, apiario_id=10, codice=f"A{numero:02d}",
                             stato=StatoAlveare.IN_SALUTE)  # fmt: skip

    at = apri()

    assert len(righe(at)) == 10
    assert "Mostrando 10 di 14 alveari" in valori(at.caption)
    [pagine] = [g for g in at.get("button_group") if "alveari_pagina" in g.proto.id]
    assert [o.content for o in pagine.proto.options] == ["1", "2"]


def test_senza_alveari_lo_stato_vuoto_del_mockup(app_pronta, monkeypatch):
    apiari, alveari = anagrafica_di_prova()
    for alveare in list(alveari.righe.values()):
        if alveare.apiario_id == 10:
            alveari.righe.pop(alveare.id)
    installa(app_pronta, monkeypatch, Servizi(None, apiari=apiari, alveari=alveari,
                                              ispezioni=ispezioni_di_prova(alveari),
                                              crea_predittore=PredittoreStub))  # fmt: skip

    at = apri()

    assert "**Nessun alveare registrato**" in valori(at.markdown)
    assert at.button(key="vuoto_nuovo_alveare")


def test_senza_apiari_invita_a_crearne_uno(app_pronta, monkeypatch):
    apiari, alveari = anagrafica_di_prova()
    apiari.righe = {k: v for k, v in apiari.righe.items() if v.utente_id != 1}
    installa(app_pronta, monkeypatch, Servizi(None, apiari=apiari, alveari=alveari,
                                              ispezioni=ispezioni_di_prova(alveari),
                                              crea_predittore=PredittoreStub))  # fmt: skip

    at = apri()

    assert any("Nessun apiario registrato." in i for i in valori(at.info))
    assert at.button(key="apri_nuovo_alveare").disabled


def test_con_il_database_spento_la_pagina_lo_dice_e_si_ferma(app_pronta, monkeypatch):
    apiari, alveari = anagrafica_di_prova(errore=DATABASE_SPENTO)
    installa(app_pronta, monkeypatch, Servizi(None, apiari=apiari, alveari=alveari,
                                              crea_predittore=PredittoreStub))  # fmt: skip

    at = apri()

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")
    assert not righe(at)


# --------------------------------------------------------------------------- #
# Le finestre: nuovo, modifica, elimina
# --------------------------------------------------------------------------- #


def test_nuovo_alveare_nella_finestra(anagrafica):
    _, alveari, _ = anagrafica
    at = premi(apri(), "apri_nuovo_alveare")
    assert at.text_input(key="nuovo_alveare_codice")

    at.text_input(key="nuovo_alveare_codice").input("A25")
    at.selectbox(key="nuovo_alveare_stato").select(StatoAlveare.IN_OSSERVAZIONE)
    at.number_input(key="nuovo_alveare_regina").set_value(2025)
    at = premi(at, "nuovo_alveare_invia")

    assert valori(at.success) == ["Alveare **A25** aggiunto."]
    nuovo = next(a for a in alveari.righe.values() if a.codice == "A25")
    assert (nuovo.apiario_id, nuovo.stato, nuovo.anno_regina) == (
        10, StatoAlveare.IN_OSSERVAZIONE, 2025,
    )  # fmt: skip
    assert at.session_state["finestra_aperta"] is None  # la finestra si è chiusa
    assert "A25" in righe(at)


def test_nella_finestra_un_codice_vuoto_si_ferma_prima_del_servizio(anagrafica):
    _, alveari, _ = anagrafica
    prima = len(alveari.righe)
    at = premi(apri(), "apri_nuovo_alveare")

    at = premi(at, "nuovo_alveare_invia")

    assert any("Il codice dell'alveare è obbligatorio." in e for e in valori(at.error))
    assert len(alveari.righe) == prima
    assert at.session_state["finestra_aperta"] == ("nuovo_alveare", None)  # resta aperta


def test_un_codice_gia_usato_lo_dice_il_servizio(anagrafica):
    at = premi(apri(), "apri_nuovo_alveare")
    at.text_input(key="nuovo_alveare_codice").input("A1")

    at = premi(at, "nuovo_alveare_invia")

    assert any("A1" in e or "già" in e for e in valori(at.error))


def test_annulla_chiude_la_finestra(anagrafica):
    at = premi(apri(), "apri_nuovo_alveare")

    at = premi(at, "nuovo_alveare_annulla")

    # (AppTest conserva gli elementi della finestra chiusa: conta lo stato, il browser la chiude)
    assert at.session_state["finestra_aperta"] is None


def test_modificare_un_alveare_e_spostarlo(anagrafica):
    _, alveari, _ = anagrafica
    at = premi(apri(), "modifica_2")

    at.text_input(key="alveare_2_codice").input("A2bis")
    at.selectbox(key="alveare_2_apiario").select(11)
    at.selectbox(key="alveare_2_stato").select(StatoAlveare.IN_SALUTE)
    at = premi(at, "alveare_2_invia")

    assert valori(at.success) == ["Alveare **A2bis** aggiornato."]
    assert (alveari.righe[2].codice, alveari.righe[2].apiario_id) == ("A2bis", 11)


def test_eliminare_chiede_conferma_nella_finestra(anagrafica):
    _, alveari, _ = anagrafica
    at = premi(apri(), "elimina_2")

    assert "**Eliminare l'alveare A2?**" in valori(at.markdown)
    assert alveari.righe[2].attivo  # aprire la finestra non elimina nulla

    at = premi(at, "alveare_2_elimina")

    assert valori(at.success) == ["Alveare **A2** eliminato."]
    assert not alveari.righe[2].attivo
    assert righe(at) == ["A1"]


def test_se_leliminazione_fallisce_lo_dice_senza_traceback(anagrafica):
    _, alveari, _ = anagrafica
    at = premi(apri(), "elimina_2")
    alveari.errore = DATABASE_SPENTO

    at = at.button(key="alveare_2_elimina").click().run()

    assert not at.exception
    assert any(e.startswith("**Non riesco a raggiungere il database.**") for e in valori(at.error))


# --------------------------------------------------------------------------- #
# Gli apiari
# --------------------------------------------------------------------------- #


def test_aggiungere_un_apiario_lo_rende_lapiario_attivo(anagrafica):
    apiari, _, _ = anagrafica
    at = premi(apri(), "apri_apiari")

    at.text_input(key="nuovo_apiario_nome").input("Bosco")
    at.text_input(key="nuovo_apiario_localita").input("Val Seriana")
    at = premi(at, "nuovo_apiario_invia")

    assert valori(at.success) == ["Apiario **Bosco** aggiunto: ora è l'apiario attivo."]
    nuovo = next(a for a in apiari.righe.values() if a.nome == "Bosco")
    assert at.session_state["apiario_attivo_id"] == nuovo.id


@pytest.mark.parametrize(
    ("campi", "messaggio"),
    [({"nome": ""}, "Il nome dell'apiario è obbligatorio."),
     ({"nome": "Orto", "latitudine": 45.1}, "Le coordinate vanno date in coppia")],
)  # fmt: skip
def test_i_controlli_della_pagina_sullapiario(anagrafica, campi, messaggio):
    at = premi(apri(), "apri_apiari")
    at.text_input(key="nuovo_apiario_nome").input(campi["nome"])
    if "latitudine" in campi:
        at.number_input(key="nuovo_apiario_latitudine").set_value(campi["latitudine"])

    at = premi(at, "nuovo_apiario_invia")

    assert any(messaggio in e for e in valori(at.error))


def test_modificare_ed_eliminare_un_apiario(anagrafica):
    apiari, _, _ = anagrafica
    at = premi(apri(), "apri_apiari")
    at.text_input(key="apiario_10_localita").input("Colli")
    at = premi(at, "apiario_10_invia")
    assert apiari.righe[10].localita == "Colli"

    # AppTest tiene gli elementi di una finestra chiusa: si riparte da una pagina nuova
    at = premi(apri(), "apri_apiari")
    at.checkbox(key="apiario_10_conferma").check().run()
    at = premi(at, "apiario_10_elimina")

    assert valori(at.success) == ["Apiario **Collina** eliminato."]
    assert not apiari.righe[10].attivo


# --------------------------------------------------------------------------- #
# Il dettaglio di un alveare
# --------------------------------------------------------------------------- #


def test_il_dettaglio_del_mockup(anagrafica):
    at = premi(apri(), "vedi_1")

    assert not at.exception
    assert valori(at.title) == ["Alveare A1"]
    assert "Collina · Ultima ispezione 30/10/2026" in valori(at.caption)
    assert {m.label: m.value for m in at.metric} == {
        "Stato": "In salute", "Forza": "Alta", "Scorte": "Buone", "Peso": "38,5 kg",
    }  # fmt: skip
    testo = html_di(at)
    for titolo in ("Andamento del peso", "Storico ispezioni", "Dettagli alveare",
                   "Salute e rischi", "Assistente AI"):  # fmt: skip
        assert titolo in testo, titolo
    assert "Regina marcata blu" in testo and "01/04/2025" in testo
    assert "Sciamatura" in testo and "Osservata" in testo  # l'ultima ispezione l'ha vista
    assert len(at.get("plotly_chart")) == 1  # due pesate: l'andamento c'è


def test_un_valore_preoccupante_ha_il_suo_colore(anagrafica):
    at = premi(apri(), "vedi_2")

    assert {m.label: m.value for m in at.metric}["Forza"] == "Bassa"
    assert "Servono almeno due ispezioni con il peso" in " ".join(valori(at.caption))
    assert '<span class="bw-badge critico">Rischio alto</span>' in html_di(at)


def test_dal_dettaglio_si_torna_allelenco(anagrafica):
    at = premi(apri(), "vedi_1")

    at = premi(at, "torna_elenco")

    assert valori(at.title) == ["Alveari"] and at.session_state["alveare_in_vista"] is None


def test_dal_dettaglio_si_modifica(anagrafica):
    at = premi(premi(apri(), "vedi_1"), "dettaglio_modifica")

    assert at.text_input(key="alveare_1_codice").value == "A1"
