"""La pagina Previsione eseguita con `AppTest` (M6-T5).

Servizi veri con dati USDA, predittore e previsioni finti (`previsione_finta.py`) e l'anagrafica in
memoria (`anagrafica_finta.py`): si sceglie il modo, si compila il modulo e si controlla cosa vede
l'utente (stima con la banda, modello, avvisi, storico) e cosa finisce nello storico.
"""

from __future__ import annotations

import pytest
from anagrafica_finta import DATABASE_SPENTO, AlveariInMemoria, ApiariInMemoria, anagrafica_di_prova
from app_finta import APP, DashboardFinto, con_accesso, installa, valori
from previsione_finta import (
    FEATURE_INCOMPATIBILI,
    ModelliFinti,
    PredittoreFinto,
    PrevisioniInMemoria,
    ProduzioneFinta,
)
from streamlit.testing.v1 import AppTest

from beewatch.exceptions import ModelError
from beewatch.services import Servizi

PAGINA = APP / "pages" / "3_Previsione.py"
A_MANO = "Con parametri scritti a mano"


class Ambiente:
    """Ciò che i test vogliono guardare dopo aver usato la pagina."""

    def __init__(self, predittore, previsioni, produzione):
        self.predittore, self.previsioni, self.produzione = predittore, previsioni, produzione


def prepara(
    app_pronta,
    monkeypatch,
    *,
    predittore=None,
    crea_predittore=None,
    produzione=None,
    apiari=None,
    alveari=None,
) -> Ambiente:
    if apiari is None:
        apiari, alveari = anagrafica_di_prova()
    predittore = predittore or PredittoreFinto()
    produzione = produzione or ProduzioneFinta()
    previsioni = PrevisioniInMemoria({1: "A1", 2: "A2"})
    servizi = Servizi(
        None,
        crea_predittore=crea_predittore or (lambda: predittore),
        apiari=apiari,
        alveari=alveari,
        produzione=produzione,
        previsioni=previsioni,
        modelli=ModelliFinti(),
        dashboard=DashboardFinto(),
        descrizione_llm="llama3.1:8b via ollama (chiave: non richiesta)",
    )
    installa(app_pronta, monkeypatch, servizi)
    return Ambiente(predittore, previsioni, produzione)


@pytest.fixture
def ambiente(app_pronta, monkeypatch) -> Ambiente:
    return prepara(app_pronta, monkeypatch)


def apri() -> AppTest:
    return con_accesso(AppTest.from_file(str(PAGINA), default_timeout=30)).run()


def calcola(at: AppTest, stato: str = "ND", anno: int = 2012, **parametri) -> AppTest:
    at.selectbox(key="previsione_stato").select(stato)
    at.number_input(key="previsione_anno").set_value(anno)
    for campo, valore in parametri.items():
        at.number_input(key=f"parametro_{campo}").set_value(valore)
    return at.button(key="previsione_invia").click().run()


def collegato(at: AppTest):
    [selettore] = [s for s in at.selectbox if s.key.startswith("previsione_alveare_")]
    return selettore


def storico(at: AppTest) -> list[dict]:
    return at.dataframe[-1].value.to_dict("records") if at.dataframe else []


# --------------------------------------------------------------------------- #
# Prima del calcolo
# --------------------------------------------------------------------------- #


def test_la_pagina_mostra_limiti_modello_e_modulo(ambiente):
    at = apri()

    assert not at.exception and not at.error
    assert valori(at.title) == ["📈 Previsione"]
    [limiti] = valori(at.warning)
    assert limiti.startswith("**Limiti di trasferibilità.**")
    assert (
        not at.expander
    )  # il disclaimer non sta in un espansore (e prima del calcolo non ce ne sono)
    assert {m.label: m.value for m in at.metric} == {"Errore medio del modello": "3,5 kg"}
    assert any(
        "Modello in uso: **v-finto** (RandomForestRegressor)" in c for c in valori(at.caption)
    )
    assert at.selectbox(key="previsione_stato").options == ["California", "North Dakota"]
    anno = at.number_input(key="previsione_anno")
    assert (anno.min, anno.max, anno.value) == (1999, 2013, 2013)
    assert collegato(at).options == ["Nessun alveare", "A1", "A2"]


def test_senza_previsioni_lo_storico_lo_dice(ambiente):
    at = apri()

    assert "Storico delle previsioni" in valori(at.subheader)
    assert any(t.startswith("Nessuna previsione salvata.") for t in valori(at.info))


# --------------------------------------------------------------------------- #
# Dai dati storici
# --------------------------------------------------------------------------- #


def test_prevedere_dai_dati_mostra_stima_banda_modello_e_la_salva(ambiente):
    at = calcola(apri(), "ND", 2012)

    assert not at.exception and not at.error
    assert "North Dakota, 2012" in valori(at.subheader)
    stima = next(m for m in at.metric if m.label == "Resa per colonia stimata")
    assert stima.value == "52 kg"  # la media dei tre anni prima, mai un numero senza banda
    didascalie = valori(at.caption)
    assert "Banda di incertezza: da 49 a 56 kg (intervallo al 80%)." in didascalie
    assert any("Stimata dal modello **v-finto**" in c for c in didascalie)
    assert any("prova a ritroso" in c for c in didascalie)  # il 2012 è già nei dati
    assert at.get("plotly_chart")  # la barra orizzontale con la banda d'errore
    [salvata] = ambiente.previsioni.salvate
    assert (salvata.codice_stato_riferimento, salvata.anno_riferimento, salvata.alveare_id) == (
        "ND", 2012, None,
    )  # fmt: skip
    [riga] = storico(at)
    assert riga["Stato"] == "North Dakota" and riga["Stima (kg)"] == "52"
    assert riga["Banda (kg)"] == "da 49 a 56" and riga["Modello"] == "v-finto"


def test_i_valori_usati_dal_modello_si_possono_vedere(ambiente):
    at = calcola(apri(), "CA", 2013)

    [espansore] = at.expander
    assert espansore.label == "I valori con cui il modello ha stimato"
    valori_usati = {r["Valore"]: r["Dato"] for r in at.dataframe[0].value.to_dict("records")}
    assert valori_usati["Stato"] == "CA" and valori_usati["Anno da prevedere"] == "2013"
    assert "prova a ritroso" not in " ".join(valori(at.caption))  # il 2013 è davvero futuro


def test_collegare_un_alveare_la_mette_nel_suo_storico(ambiente):
    at = apri()
    collegato(at).select(2)

    at = calcola(at, "CA", 2010)

    assert ambiente.previsioni.salvate[0].alveare_id == 2
    at.selectbox(key="storico_alveare").select(2).run()
    assert "Storico delle previsioni dell'alveare A2" in valori(at.subheader)
    assert [r["Alveare"] for r in storico(at)] == ["A2"]
    at.selectbox(key="storico_alveare").select(1).run()
    assert any(
        t.startswith("Nessuna previsione collegata all'alveare A1.") for t in valori(at.info)
    )


def test_lo_storico_scelto_propone_lo_stesso_alveare_nel_modulo(ambiente):
    at = apri()
    at.selectbox(key="storico_alveare").select(1).run()

    assert collegato(at).value == 1


def test_una_banda_piu_larga_della_stima_non_mostra_il_valore(app_pronta, monkeypatch):
    ambiente = prepara(
        app_pronta, monkeypatch, predittore=PredittoreFinto(inferiore=-40.0, superiore=40.0)
    )

    at = calcola(apri(), "CA", 2010)

    assert not at.exception
    assert any("più largo della stima" in w for w in valori(at.warning))
    stima = next(m for m in at.metric if m.label == "Resa per colonia stimata")
    assert stima.value.startswith("da ") and stima.value.endswith(" kg")  # solo la banda
    assert ambiente.previsioni.salvate == []


# --------------------------------------------------------------------------- #
# Con parametri a mano
# --------------------------------------------------------------------------- #


def test_i_parametri_a_mano_hanno_come_limiti_lintervallo_delladdestramento(ambiente):
    at = apri()
    at.radio(key="modo").set_value(A_MANO).run()

    resa = at.number_input(key="parametro_resa_anno_prima")
    assert (resa.min, resa.max, resa.value) == (30.0, 53.0, None)
    colonie = at.number_input(key="parametro_colonie_anno_prima")
    assert (colonie.min, colonie.max) == (401_998, 452_012)
    assert "da 30 a 53 kg" in resa.help
    assert not [s for s in at.selectbox if s.key.startswith("previsione_alveare_")]


def test_una_simulazione_mostra_la_stima_e_non_si_salva(ambiente):
    at = apri()
    at.radio(key="modo").set_value(A_MANO).run()

    at = calcola(
        at, "CA", 2005, resa_anno_prima=40.0, resa_media_3_anni_prima=42.0,
        colonie_anno_prima=420_000,
    )  # fmt: skip

    assert not at.exception and not at.error
    assert "California, 2005 · simulazione con parametri a mano" in valori(at.subheader)
    assert next(m for m in at.metric if m.label == "Resa per colonia stimata").value == "42 kg"
    assert any("Le simulazioni non si salvano" in c for c in valori(at.caption))
    assert ambiente.predittore.ricevute[0]["colonie_anno_prima"] == 420_000
    assert ambiente.previsioni.salvate == []


def test_un_parametro_mancante_si_ferma_nella_pagina(ambiente):
    at = apri()
    at.radio(key="modo").set_value(A_MANO).run()

    at = calcola(at, "CA", 2005, resa_anno_prima=40.0)

    errori = valori(at.error)
    assert len(errori) == 2
    assert "Scrivi «Resa media dei 3 anni prima»." in errori[0]
    assert "Scrivi «Colonie dell'anno prima»." in errori[1]
    assert ambiente.predittore.ricevute == []  # il modello non è stato interrogato


# --------------------------------------------------------------------------- #
# Errori: modello, feature, database
# --------------------------------------------------------------------------- #


def test_senza_modello_la_pagina_lo_dice_e_mostra_lo_storico(app_pronta, monkeypatch):
    def manca():
        raise ModelError("Il modello non è stato trovato: lancia scripts/train_model.py.")

    prepara(app_pronta, monkeypatch, crea_predittore=manca)

    at = apri()

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Il modello di previsione non è disponibile.**")
    assert not at.main.button  # niente modulo: non c'è con cosa calcolare
    assert "Storico delle previsioni" in valori(at.subheader)
    assert valori(at.warning)[0].startswith("**Limiti di trasferibilità.**")


def test_feature_incompatibili_col_modello_si_spiegano_senza_crash(app_pronta, monkeypatch):
    incompatibile = PredittoreFinto(errore=FEATURE_INCOMPATIBILI)
    ambiente = prepara(app_pronta, monkeypatch, predittore=incompatibile)

    at = calcola(apri(), "CA", 2010)

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Il modello di previsione non è disponibile.**")
    assert "mancano le colonne: temperatura_media" in errore
    assert ambiente.previsioni.salvate == []


def test_senza_dati_usda_rimanda_alletl(app_pronta, monkeypatch):
    prepara(app_pronta, monkeypatch, produzione=ProduzioneFinta(vuota=True))

    at = apri()

    assert not at.exception and not at.error
    assert any("run_etl.py" in t for t in valori(at.info))
    assert not at.main.button


def test_senza_pannello_i_parametri_a_mano_spiegano_il_rimedio(app_pronta, monkeypatch):
    prepara(app_pronta, monkeypatch, produzione=ProduzioneFinta(senza_pannello=True))
    at = apri()

    at.radio(key="modo").set_value(A_MANO).run()

    assert not at.exception
    [errore] = valori(at.error)
    assert "run_etl.py" in errore
    assert not at.main.button  # niente modulo senza gli intervalli
    at.radio(key="modo").set_value("Dai dati storici di uno stato").run()
    assert at.button(key="previsione_invia")  # l'altro modo funziona


def test_con_il_database_spento_lo_dice_e_si_ferma(app_pronta, monkeypatch):
    prepara(app_pronta, monkeypatch, produzione=ProduzioneFinta(errore=DATABASE_SPENTO))

    at = apri()

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")
    assert not at.main.button and not at.dataframe


def test_se_lo_storico_non_si_legge_il_modulo_resta(ambiente):
    ambiente.previsioni.errore = DATABASE_SPENTO

    at = apri()

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")
    assert at.button(key="previsione_invia")


def test_senza_alveari_si_prevede_lo_stesso(app_pronta, monkeypatch):
    apiari = ApiariInMemoria()
    prepara(app_pronta, monkeypatch, apiari=apiari, alveari=AlveariInMemoria(apiari))

    at = calcola(apri(), "CA", 2010)

    assert not at.exception and not at.error
    assert any("Nessun alveare nell'apiario attivo" in c for c in valori(at.caption))
    assert next(m for m in at.metric if m.label == "Resa per colonia stimata").value == "31 kg"
