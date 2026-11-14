"""La pagina Ispezioni eseguita con `AppTest` (M6-T4).

Servizi veri con apiari, alveari e ispezioni in memoria (`anagrafica_finta.py`, le stesse regole
dei repository): si compilano filtri e form come farebbe l'utente e si controlla cosa vede e cosa
finisce nei dati. La pagina si apre passando dalla Home (`switch_page`), come nel browser: solo così
Streamlit conosce le pagine e `st.page_link` verso Alveari funziona. Le stesse operazioni sul
database vero sono in `test_servizi_ispezioni.py` (integration).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from anagrafica_finta import (
    DATABASE_SPENTO,
    NOTA_LUNGA,
    AlveariInMemoria,
    ApiariInMemoria,
    IspezioniInMemoria,
    anagrafica_di_prova,
    ispezioni_di_prova,
)
from app_finta import APP, DashboardFinto, PredittoreStub, con_accesso, installa, valori
from streamlit.testing.v1 import AppTest

from beewatch.exceptions import ValidationError
from beewatch.models import LivelloRischio
from beewatch.services import Servizi

PAGINA = "pages/2_Ispezioni.py"


def servizi_con(apiari, alveari, ispezioni) -> Servizi:
    return Servizi(
        None,
        crea_predittore=PredittoreStub,
        apiari=apiari,
        alveari=alveari,
        ispezioni=ispezioni,
        dashboard=DashboardFinto(),
    )


@pytest.fixture
def registro(app_pronta, monkeypatch) -> IspezioniInMemoria:
    """L'anagrafica di prova con le sue ispezioni, installata nei servizi della pagina."""
    apiari, alveari = anagrafica_di_prova()
    ispezioni = ispezioni_di_prova(alveari)
    installa(app_pronta, monkeypatch, servizi_con(apiari, alveari, ispezioni))
    return ispezioni


def apri() -> AppTest:
    at = con_accesso(AppTest.from_file(str(APP / "Home.py"), default_timeout=30)).run()
    return at.switch_page(PAGINA).run()


def righe(at: AppTest) -> list[dict]:
    return at.dataframe[0].value.to_dict("records")


def colonna(at: AppTest, nome: str) -> list[str]:
    return [r[nome] for r in righe(at)]


def metriche(at: AppTest) -> dict[str, str]:
    return {m.label: m.value for m in at.metric}


def selettore_alveare(at: AppTest):
    """Il selettore dell'alveare nel form (la chiave cambia con il filtro dello storico)."""
    [selettore] = [s for s in at.selectbox if s.key.startswith("ispezione_alveare_")]
    return selettore


def selettore_lettura(at: AppTest):
    """Il selettore «Leggi un'ispezione» (la chiave cambia con l'elenco mostrato)."""
    [selettore] = [s for s in at.selectbox if s.key.startswith("ispezione_da_leggere_")]
    return selettore


def registra(at: AppTest, **campi) -> AppTest:
    """Compila il form della nuova ispezione con `campi` (chiave del widget senza prefisso)."""
    for nome, valore in campi.items():
        chiave = f"ispezione_{nome}"
        if nome == "alveare":
            selettore_alveare(at).select(valore)
        elif nome == "rischio":
            at.selectbox(key=chiave).select(valore)
        elif nome == "data":
            at.date_input(key=chiave).set_value(valore)
        elif nome in ("peso", "covata", "scorte"):
            at.number_input(key=chiave).set_value(valore)
        elif nome == "regina":
            at.checkbox(key=chiave).check()
        else:
            at.text_area(key=chiave).input(valore)
    return at.button(key="nuova_ispezione_invia").click().run()


# --------------------------------------------------------------------------- #
# Storico
# --------------------------------------------------------------------------- #


def test_lo_storico_mostra_le_ispezioni_dellapiario_dalla_piu_recente(registro):
    at = apri()

    assert not at.exception and not at.error
    assert valori(at.title) == ["📋 Ispezioni"]
    assert valori(at.subheader) == ["Ispezioni di Collina"]
    assert colonna(at, "Data") == ["30/10/2026", "05/10/2026", "12/09/2026", "20/08/2026"]
    assert colonna(at, "Alveare") == ["A1", "A2", "A1", "A2"]  # né A9 eliminato né X1 altrui
    assert metriche(at) == {
        "Ispezioni mostrate": "4",
        "Con rischio medio o alto": "2",
        "Ultima ispezione": "30/10/2026",
    }


def test_la_tabella_parla_italiano_e_mai_con_i_codici_grezzi(registro):
    at = apri()

    [recente, varroa, lunga, _] = righe(at)
    assert recente["Rischio"] == "Rischio basso"
    assert recente["Peso (kg)"] == "38,5" and recente["Covata"] == "—"
    assert (recente["Regina vista"], recente["Sciamatura"]) == ("no", "sì")
    assert varroa["Rischio"] == "Rischio alto"
    assert lunga["Covata"] == "6" and lunga["Regina vista"] == "sì"
    assert len(lunga["Note"]) == 80 and lunga["Note"].endswith("…")  # solo l'anteprima
    codici = {livello.value for livello in LivelloRischio}
    assert not codici & set(colonna(at, "Rischio"))


def test_lo_storico_si_filtra_per_alveare(registro):
    at = apri()
    at.selectbox(key="filtro_alveare").select(2).run()

    assert colonna(at, "Alveare") == ["A2", "A2"]
    assert metriche(at)["Ispezioni mostrate"] == "2"
    assert selettore_alveare(at).value == 2  # il form propone lo stesso alveare
    at.selectbox(key="filtro_alveare").select(0).run()  # «Tutti gli alveari»
    assert selettore_alveare(at).value == 1


def test_lo_storico_si_filtra_per_intervallo_di_date(registro):
    at = apri()
    at.date_input(key="filtro_dal").set_value(date(2026, 9, 12))
    at.date_input(key="filtro_al").set_value(date(2026, 10, 5)).run()

    assert colonna(at, "Data") == ["05/10/2026", "12/09/2026"]  # estremi compresi
    assert metriche(at)["Ultima ispezione"] == "05/10/2026"


def test_un_intervallo_rovesciato_spiega_cosa_correggere(registro):
    at = apri()
    at.date_input(key="filtro_dal").set_value(date(2026, 10, 6))
    at.date_input(key="filtro_al").set_value(date(2026, 10, 5)).run()

    assert not at.exception
    [errore] = valori(at.error)
    assert "viene dopo" in errore and "«dal»" in errore
    assert not at.dataframe
    assert at.button(key="nuova_ispezione_invia")  # il form resta usabile


def test_filtri_senza_risultati_lo_dicono(registro):
    at = apri()
    at.date_input(key="filtro_dal").set_value(date(2026, 11, 1)).run()

    assert any(t.startswith("Nessuna ispezione con questi filtri.") for t in valori(at.info))
    assert not at.dataframe
    assert metriche(at) == {
        "Ispezioni mostrate": "0",
        "Con rischio medio o alto": "0",
        "Ultima ispezione": "—",
    }


# --------------------------------------------------------------------------- #
# Scheda di un'ispezione
# --------------------------------------------------------------------------- #


def test_cambiando_lelenco_il_selettore_riparte_dalla_piu_recente(registro):
    at = apri()
    selettore_lettura(at).select(104).run()
    assert "**Ispezione del 20/08/2026**" in valori(at.markdown)

    at.selectbox(key="filtro_alveare").select(1).run()  # 104 non c'è più

    assert selettore_lettura(at).value == 103
    assert "**Ispezione del 30/10/2026**" in valori(at.markdown)


def test_la_scheda_mostra_lalveare_con_il_suo_stato_e_il_collegamento(registro):
    at = apri()

    assert selettore_lettura(at).value == 103  # la più recente
    assert "**Alveare A1**" in valori(at.markdown)
    assert any("✔ In salute" in m for m in valori(at.markdown) if m.startswith("<span"))
    [collegamento] = at.get("page_link")
    assert collegamento.proto.label == "Vai all'alveare nella pagina Alveari"
    assert collegamento.proto.page == "Alveari"  # il file `pages/1_Alveari.py`
    assert (
        "Rischio basso · peso: 38,5 kg · telaini di covata: — · telaini di scorte: — · "
        "regina vista: no · sciamatura: sì"
    ) in valori(at.caption)
    assert "Nessuna nota per questa ispezione." in valori(at.caption)


def test_le_note_lunghe_si_leggono_intere_e_in_sola_lettura(registro):
    at = apri()
    selettore_lettura(at).select(101).run()

    note = at.text_area(key="note_ispezione_101")
    assert note.value == NOTA_LUNGA and len(note.value) > 2000
    assert note.disabled


def test_le_note_non_si_interpretano_come_formattazione(registro):
    at = apri()
    selettore_lettura(at).select(102).run()

    assert at.text_area(key="note_ispezione_102").value == (
        "Varroa *alta* sul vassoio: trattamento da programmare."
    )  # gli asterischi restano asterischi
    assert "**Alveare A2**" in valori(at.markdown)
    assert any("▼ Debole" in m for m in valori(at.markdown) if m.startswith("<span"))


# --------------------------------------------------------------------------- #
# Registrare un'ispezione
# --------------------------------------------------------------------------- #


def test_registrare_unispezione_la_salva_e_la_mette_in_cima(registro):
    at = apri()
    nota = NOTA_LUNGA + " Àncora: perché, città, così, più — «virgolette» e 🐝."

    at = registra(
        at, alveare=2, data=date(2026, 11, 3), rischio=LivelloRischio.MEDIO, peso=36.257,
        covata=5, scorte=3, regina=True, note=nota,
    )  # fmt: skip

    assert not at.exception and not at.error
    assert valori(at.success) == ["Ispezione di **A2** del 03/11/2026 registrata."]
    salvata = registro.righe[107]
    assert salvata.note == nota  # oltre 2000 caratteri, accenti ed emoji intatti
    assert (salvata.alveare_id, salvata.livello_rischio) == (2, LivelloRischio.MEDIO)
    assert str(salvata.peso_kg) == "36.26"  # arrotondato ai due decimali della colonna
    assert (salvata.telaini_covata, salvata.telaini_scorte, salvata.regina_vista) == (5, 3, True)
    assert righe(at)[0]["Data"] == "03/11/2026" and righe(at)[0]["Alveare"] == "A2"
    # selettore e scheda mostrano la stessa ispezione, la nuova (un bug visto nel browser)
    assert selettore_lettura(at).value == 107
    assert "**Ispezione del 03/11/2026**" in valori(at.markdown)
    assert metriche(at)["Ispezioni mostrate"] == "5"


def test_lesito_si_mostra_una_volta_sola(registro):
    at = registra(apri(), alveare=1)
    assert len(at.success) == 1

    at.selectbox(key="filtro_alveare").select(1).run()
    assert not at.success


def test_il_calendario_non_va_oltre_oggi(registro):
    """La data futura la ferma già il widget; il modello la rifiuta comunque (test dei servizi).

    Un valore oltre il massimo non arriva al servizio: Streamlit lo scarta e resta oggi.
    """
    at = apri()
    data = at.date_input(key="ispezione_data")
    assert data.max == date.today() and data.value == date.today()

    at = registra(at, alveare=1, data=date.today() + timedelta(days=1))

    assert all(i.data_ispezione <= date.today() for i in registro.righe.values())


def test_un_rifiuto_del_modello_indica_il_campo_da_correggere(registro, monkeypatch):
    at = apri()
    registro.errore = ValidationError(
        "La data «data_ispezione» non può essere nel futuro.", campo="data_ispezione"
    )

    at = registra(at, alveare=1)

    assert not at.exception and not at.success
    [errore] = valori(at.error)
    assert "data_ispezione" in errore and "futuro" in errore
    assert len(registro.righe) == 6


def test_senza_data_la_pagina_si_ferma_prima_del_servizio(registro, monkeypatch):
    at = apri()
    at.date_input(key="ispezione_data").set_value(None)

    at = at.button(key="nuova_ispezione_invia").click().run()

    [errore] = valori(at.error)
    assert "La data dell'ispezione è obbligatoria." in errore
    assert len(registro.righe) == 6


def test_se_il_salvataggio_fallisce_lo_dice_senza_traceback(registro):
    at = apri()
    registro.errore = DATABASE_SPENTO

    at = registra(at, alveare=1)

    assert not at.exception and not at.success
    assert any(e.startswith("**Non riesco a raggiungere il database.**") for e in valori(at.error))


# --------------------------------------------------------------------------- #
# Stati vuoti ed errori
# --------------------------------------------------------------------------- #


def test_senza_apiari_invita_a_crearne_uno(app_pronta, monkeypatch):
    apiari = ApiariInMemoria()
    alveari = AlveariInMemoria(apiari)
    installa(app_pronta, monkeypatch, servizi_con(apiari, alveari, IspezioniInMemoria(alveari)))

    at = apri()

    assert not at.exception and not at.error
    assert any(t.startswith("Nessun apiario registrato.") for t in valori(at.info))
    assert not at.main.button and not at.dataframe


def test_un_apiario_senza_alveari_rimanda_alla_pagina_alveari(registro):
    at = apri()
    at.sidebar.selectbox[0].select(11).run()  # «Valle»

    [vuoto] = [t for t in valori(at.info) if t.startswith("Nessun alveare in Valle.")]
    assert "Alveari" in vuoto
    assert not at.dataframe and not at.main.button  # niente form: non c'è un alveare da ispezionare


def test_un_apiario_senza_ispezioni_invita_a_registrare_la_prima(app_pronta, monkeypatch):
    apiari, alveari = anagrafica_di_prova()
    installa(app_pronta, monkeypatch, servizi_con(apiari, alveari, IspezioniInMemoria(alveari)))

    at = apri()

    assert any(t.startswith("Nessuna ispezione registrata in Collina.") for t in valori(at.info))
    assert at.button(key="nuova_ispezione_invia")
    assert metriche(at)["Ultima ispezione"] == "—"


def test_con_il_database_spento_la_pagina_lo_dice_e_si_ferma(app_pronta, monkeypatch):
    apiari, alveari = anagrafica_di_prova(errore=DATABASE_SPENTO)
    ispezioni = ispezioni_di_prova(alveari, errore=DATABASE_SPENTO)
    installa(app_pronta, monkeypatch, servizi_con(apiari, alveari, ispezioni))

    at = apri()

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")
    assert not any(t.startswith("Nessun apiario") for t in valori(at.info))  # non è vuoto: è giù
    assert not at.dataframe and not at.main.button


def test_se_solo_gli_alveari_non_si_leggono_la_pagina_lo_dice(app_pronta, monkeypatch):
    apiari, alveari = anagrafica_di_prova()
    installa(app_pronta, monkeypatch, servizi_con(apiari, alveari, ispezioni_di_prova(alveari)))
    alveari.errore = DATABASE_SPENTO

    at = apri()

    assert not at.exception
    assert any(e.startswith("**Non riesco a raggiungere il database.**") for e in valori(at.error))
    assert not at.dataframe and not at.main.button


def test_se_solo_le_ispezioni_non_si_leggono_il_form_resta(app_pronta, monkeypatch):
    apiari, alveari = anagrafica_di_prova()
    ispezioni = ispezioni_di_prova(alveari, errore=DATABASE_SPENTO)
    installa(app_pronta, monkeypatch, servizi_con(apiari, alveari, ispezioni))

    at = apri()

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")
    assert at.button(key="nuova_ispezione_invia") and not at.metric
