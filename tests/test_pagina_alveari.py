"""La pagina Alveari eseguita con `AppTest` (M6-T3).

Servizi veri con l'anagrafica in memoria (`anagrafica_finta.py`, le stesse regole dei repository):
si compilano i form come farebbe l'utente e si controlla cosa vede (elenco, pastiglie, esiti,
errori) e cosa è cambiato nei dati. Le stesse operazioni sul database vero sono in
`test_servizi_anagrafica.py` (integration).
"""

from __future__ import annotations

from datetime import date

import pytest
from anagrafica_finta import DATABASE_SPENTO, anagrafica_di_prova
from app_finta import APP, DashboardFinto, PredittoreStub, installa, valori
from streamlit.testing.v1 import AppTest

from beewatch.models import StatoAlveare
from beewatch.services import Servizi

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
        dashboard=DashboardFinto(),
        descrizione_llm="llama3.1:8b via ollama (chiave: non richiesta)",
    )
    installa(app_pronta, monkeypatch, servizi)
    return apiari, alveari, servizi


def apri() -> AppTest:
    return AppTest.from_file(str(PAGINA), default_timeout=30).run()


def tutto_il_testo(at: AppTest) -> str:
    """Tutto il testo della pagina, per cercare ciò che NON deve comparire."""
    return " ".join(valori(at.markdown) + valori(at.caption) + valori(at.info) + valori(at.error))


def premi(at: AppTest, chiave: str) -> AppTest:
    return at.button(key=chiave).click().run()


# --------------------------------------------------------------------------- #
# Elenco
# --------------------------------------------------------------------------- #


def test_lelenco_mostra_gli_alveari_attivi_dellapiario_attivo(anagrafica):
    at = apri()

    assert not at.exception and not at.error
    assert valori(at.title) == ["🏠 Alveari"]
    assert [t.label for t in at.tabs] == ["Alveari", "Apiari"]
    assert "Alveari di Collina" in valori(at.subheader)
    codici = [m for m in valori(at.markdown) if m.startswith("**A")]
    assert codici == ["**A1**", "**A2**"]  # A9 è disattivato, X1 è di un altro utente
    assert {m.label: m.value for m in at.metric} == {"Alveari nell'apiario": "2", "In salute": "1"}


def test_lo_stato_e_una_pastiglia_mai_il_codice_grezzo(anagrafica):
    at = apri()

    pastiglie = [m for m in valori(at.markdown) if m.startswith("<span")]
    assert len(pastiglie) == 2
    assert "✔ In salute" in pastiglie[0] and "▼ Debole" in pastiglie[1]
    for codice in (s.value for s in StatoAlveare):
        assert codice not in tutto_il_testo(at)  # «in_salute» non compare mai


def test_ogni_alveare_mostra_dettagli_e_ultima_ispezione_allitaliana(anagrafica):
    didascalie = valori(apri().caption)

    assert "installato il 01/04/2025" in didascalie
    assert "Ultima ispezione: 30/10/2026 · 38,5 kg" in didascalie
    assert "regina del 2024" in didascalie and "Mai ispezionato" in didascalie
    assert "Regina marcata blu" in didascalie  # le note


def test_un_apiario_senza_alveari_mostra_lo_stato_vuoto(anagrafica):
    at = apri()
    at.sidebar.selectbox[0].select(11).run()  # «Valle»

    assert "Alveari di Valle" in valori(at.subheader)
    assert any(t.startswith("Nessun alveare in Valle.") for t in valori(at.info))
    assert {m.label: m.value for m in at.metric}["Alveari nell'apiario"] == "0"


def test_senza_apiari_entrambe_le_schede_invitano_a_crearne_uno(app_pronta, monkeypatch):
    from anagrafica_finta import AlveariInMemoria, ApiariInMemoria

    apiari = ApiariInMemoria()
    installa(
        app_pronta,
        monkeypatch,
        Servizi(None, apiari=apiari, alveari=AlveariInMemoria(apiari), dashboard=DashboardFinto()),
    )

    at = apri()

    assert not at.exception and not at.error
    vuoti = [t for t in valori(at.info) if t.startswith("Nessun apiario registrato.")]
    assert len(vuoti) == 2  # una per scheda, ognuna con la sua azione
    assert at.text_input(key="nuovo_apiario_nome")  # il modulo per crearlo c'è


def test_con_il_database_spento_la_pagina_lo_dice_e_si_ferma(app_pronta, monkeypatch):
    apiari, alveari = anagrafica_di_prova(errore=DATABASE_SPENTO)
    servizi = Servizi(None, apiari=apiari, alveari=alveari, dashboard=DashboardFinto())
    installa(app_pronta, monkeypatch, servizi)

    at = apri()

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")
    assert not at.tabs and not at.metric


# --------------------------------------------------------------------------- #
# Alveari: aggiungere, modificare, eliminare
# --------------------------------------------------------------------------- #


def test_aggiungere_un_alveare_lo_mette_in_elenco_e_lo_dice(anagrafica):
    _, alveari, _ = anagrafica
    at = apri()

    at.text_input(key="nuovo_alveare_codice").input("A3")
    at.selectbox(key="nuovo_alveare_stato").select(StatoAlveare.IN_OSSERVAZIONE)
    at.number_input(key="nuovo_alveare_regina").set_value(2025)
    at.text_area(key="nuovo_alveare_note").input("Sciame catturato a maggio")
    at = premi(at, "nuovo_alveare_invia")

    assert not at.exception and not at.error
    assert valori(at.success) == ["Alveare **A3** aggiunto a Collina."]
    nuovo = next(a for a in alveari.righe.values() if a.codice == "A3")
    assert (nuovo.apiario_id, nuovo.stato, nuovo.anno_regina) == (
        10,
        StatoAlveare.IN_OSSERVAZIONE,
        2025,
    )
    assert "**A3**" in valori(at.markdown)  # l'elenco è già aggiornato
    assert not at.run().success  # l'esito si mostra una volta sola


def test_un_codice_vuoto_si_ferma_nella_pagina_prima_del_servizio(anagrafica, monkeypatch):
    _, alveari, servizi = anagrafica
    chiamate: list[dict] = []
    monkeypatch.setattr(servizi, "crea_alveare", lambda *a, **k: chiamate.append(k))
    at = apri()

    at.text_input(key="nuovo_alveare_codice").input("   ")
    at = premi(at, "nuovo_alveare_invia")

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Un dato inserito non è valido.**")
    assert "Il codice dell'alveare è obbligatorio." in errore
    assert "(campo «codice»)" in errore
    assert chiamate == []  # il servizio non è stato chiamato
    assert not at.success


def test_un_codice_gia_usato_lo_rifiuta_il_servizio_con_un_messaggio_chiaro(anagrafica):
    _, alveari, _ = anagrafica
    prima = dict(alveari.righe)
    at = apri()

    at.text_input(key="nuovo_alveare_codice").input("A1")
    at = premi(at, "nuovo_alveare_invia")

    assert not at.exception
    [errore] = valori(at.error)
    assert "Nell'apiario c'è già un alveare con questo codice." in errore
    assert alveari.righe == prima and not at.success


def test_modificare_un_alveare_salva_i_campi_nuovi(anagrafica):
    _, alveari, _ = anagrafica
    at = apri()

    at.selectbox(key="alveare_da_modificare").select(2).run()  # A2
    at.text_input(key="alveare_2_codice").input("A2-bis")
    at.selectbox(key="alveare_2_stato").select(StatoAlveare.IN_SALUTE)
    at.date_input(key="alveare_2_installazione").set_value(date(2026, 4, 2))
    at = premi(at, "alveare_2_invia")

    assert not at.exception and not at.error
    assert valori(at.success) == ["Alveare **A2-bis** aggiornato."]
    a2 = alveari.righe[2]
    assert (a2.codice, a2.stato, a2.data_installazione) == (
        "A2-bis",
        StatoAlveare.IN_SALUTE,
        date(2026, 4, 2),
    )
    assert a2.anno_regina == 2024  # i campi non toccati restano


def test_un_alveare_si_puo_spostare_in_un_altro_apiario(anagrafica):
    _, alveari, _ = anagrafica
    at = apri()

    at.selectbox(key="alveare_da_modificare").select(2).run()
    at.selectbox(key="alveare_2_apiario").select(11)  # Valle
    at = premi(at, "alveare_2_invia")

    assert alveari.righe[2].apiario_id == 11
    assert [m for m in valori(at.markdown) if m.startswith("**A")] == ["**A1**"]


def test_eliminare_chiede_una_conferma_esplicita(anagrafica):
    _, alveari, _ = anagrafica
    at = apri()
    at.selectbox(key="alveare_da_modificare").select(2).run()

    assert at.button(key="alveare_2_elimina").disabled  # senza spunta non si preme
    at.button(key="alveare_2_elimina").click().run()
    assert alveari.righe[2].attivo  # e se anche arrivasse un clic, non succede nulla

    at.checkbox(key="alveare_2_conferma").check().run()
    assert not at.button(key="alveare_2_elimina").disabled
    at = premi(at, "alveare_2_elimina")

    assert not at.exception
    assert valori(at.success) == ["Alveare **A2** eliminato."]
    assert not alveari.righe[2].attivo  # cancellazione logica: la riga resta
    assert [m for m in valori(at.markdown) if m.startswith("**A")] == ["**A1**"]


# --------------------------------------------------------------------------- #
# Apiari
# --------------------------------------------------------------------------- #


def test_aggiungere_un_apiario_lo_rende_lapiario_attivo(anagrafica):
    apiari, _, _ = anagrafica
    at = apri()

    at.text_input(key="nuovo_apiario_nome").input("Bosco")
    at.text_input(key="nuovo_apiario_localita").input("Val Brembana")
    at.number_input(key="nuovo_apiario_latitudine").set_value(45.8)
    at.number_input(key="nuovo_apiario_longitudine").set_value(9.7)
    at = premi(at, "nuovo_apiario_invia")

    assert not at.exception and not at.error
    assert valori(at.success) == ["Apiario **Bosco** aggiunto: ora è l'apiario attivo."]
    bosco = next(a for a in apiari.righe.values() if a.nome == "Bosco")
    assert str(bosco.latitudine) == "45.8" and bosco.localita == "Val Brembana"
    assert at.session_state["apiario_attivo_id"] == bosco.id
    assert at.sidebar.selectbox[0].value == bosco.id
    assert "Alveari di Bosco" in valori(at.subheader)


@pytest.mark.parametrize(
    ("nome", "latitudine", "longitudine", "messaggio", "campo"),
    [
        ("", None, None, "Il nome dell'apiario è obbligatorio.", "nome"),
        ("Bosco", 45.8, None, "Le coordinate vanno date in coppia", "longitudine"),
        ("Bosco", None, 9.7, "Le coordinate vanno date in coppia", "latitudine"),
    ],
)
def test_i_controlli_della_pagina_sullapiario(
    anagrafica, monkeypatch, nome, latitudine, longitudine, messaggio, campo
):
    _, _, servizi = anagrafica
    chiamate: list[dict] = []
    monkeypatch.setattr(servizi, "crea_apiario", lambda *a, **k: chiamate.append(k))
    at = apri()

    at.text_input(key="nuovo_apiario_nome").input(nome)
    at.number_input(key="nuovo_apiario_latitudine").set_value(latitudine)
    at.number_input(key="nuovo_apiario_longitudine").set_value(longitudine)
    at = premi(at, "nuovo_apiario_invia")

    [errore] = valori(at.error)
    assert messaggio in errore and f"(campo «{campo}»)" in errore
    assert chiamate == []


def test_un_nome_gia_usato_lo_rifiuta_il_servizio(anagrafica):
    at = apri()

    at.text_input(key="nuovo_apiario_nome").input("Valle")
    at = premi(at, "nuovo_apiario_invia")

    [errore] = valori(at.error)
    assert "Hai già un apiario con questo nome." in errore


def test_modificare_un_apiario(anagrafica):
    apiari, _, _ = anagrafica
    at = apri()

    at.selectbox(key="apiario_da_modificare").select(11).run()
    at.text_input(key="apiario_11_nome").input("Valle bassa")
    at = premi(at, "apiario_11_invia")

    assert valori(at.success) == ["Apiario **Valle bassa** aggiornato."]
    assert apiari.righe[11].nome == "Valle bassa"
    assert "**Valle bassa**" in valori(at.markdown)


def test_eliminare_lapiario_attivo_passa_al_primo_rimasto(anagrafica):
    apiari, _, _ = anagrafica
    at = apri()
    assert at.session_state["apiario_attivo_id"] == 10  # Collina

    at.checkbox(key="apiario_10_conferma").check().run()
    at = premi(at, "apiario_10_elimina")

    assert not at.exception
    assert valori(at.success) == ["Apiario **Collina** eliminato."]
    assert not apiari.righe[10].attivo
    assert at.session_state["apiario_attivo_id"] == 11  # Valle
    assert at.sidebar.selectbox[0].options == ["Valle"]


# --------------------------------------------------------------------------- #
# Gli errori lungo la strada: mai un traceback, sempre il campo da correggere
# --------------------------------------------------------------------------- #


def test_se_gli_alveari_non_si_leggono_la_scheda_apiari_resta_usabile(app_pronta, monkeypatch):
    apiari, alveari = anagrafica_di_prova()
    alveari.errore = DATABASE_SPENTO  # gli apiari si leggono, gli alveari no
    servizi = Servizi(None, apiari=apiari, alveari=alveari, dashboard=DashboardFinto())
    installa(app_pronta, monkeypatch, servizi)

    at = apri()

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")
    assert at.text_input(key="nuovo_apiario_nome")  # l'altra scheda funziona


@pytest.mark.parametrize(
    ("codice", "messaggio"),
    [
        ("", "Il codice dell'alveare è obbligatorio."),
        ("A1", "Nell'apiario c'è già un alveare con questo codice."),
    ],
)
def test_modificare_un_alveare_con_un_codice_non_valido(anagrafica, codice, messaggio):
    _, alveari, _ = anagrafica
    at = apri()
    at.selectbox(key="alveare_da_modificare").select(2).run()

    at.text_input(key="alveare_2_codice").input(codice)
    at = premi(at, "alveare_2_invia")

    assert not at.exception and not at.success
    [errore] = valori(at.error)
    assert messaggio in errore and "(campo «codice»)" in errore
    assert alveari.righe[2].codice == "A2"


@pytest.mark.parametrize(
    ("nome", "messaggio"),
    [
        ("", "Il nome dell'apiario è obbligatorio."),
        ("Collina", "Hai già un apiario con questo nome."),
    ],
)
def test_modificare_un_apiario_con_un_nome_non_valido(anagrafica, nome, messaggio):
    apiari, _, _ = anagrafica
    at = apri()
    at.selectbox(key="apiario_da_modificare").select(11).run()

    at.text_input(key="apiario_11_nome").input(nome)
    at = premi(at, "apiario_11_invia")

    assert not at.exception and not at.success
    [errore] = valori(at.error)
    assert messaggio in errore
    assert apiari.righe[11].nome == "Valle"


@pytest.mark.parametrize(
    ("chiave", "metodo"), [("alveare_2", "elimina_alveare"), ("apiario_10", "elimina_apiario")]
)
def test_se_leliminazione_fallisce_lo_dice_senza_traceback(anagrafica, monkeypatch, chiave, metodo):
    from beewatch.exceptions import ValidationError

    _, _, servizi = anagrafica

    def sparito(*argomenti):
        raise ValidationError("Alveare non trovato.", campo="id")  # tolto da un'altra scheda

    monkeypatch.setattr(servizi, metodo, sparito)
    at = apri()
    if chiave == "alveare_2":
        at.selectbox(key="alveare_da_modificare").select(2).run()

    at.checkbox(key=f"{chiave}_conferma").check().run()
    at = premi(at, f"{chiave}_elimina")

    assert not at.exception and not at.success
    [errore] = valori(at.error)
    assert errore.startswith("**Un dato inserito non è valido.** Alveare non trovato.")


def test_le_note_dellapiario_compaiono_nellelenco(anagrafica):
    at = apri()

    at.text_input(key="nuovo_apiario_nome").input("Bosco")
    at.text_area(key="nuovo_apiario_note").input("Accesso dal sentiero 3")
    at = premi(at, "nuovo_apiario_invia")

    assert "Accesso dal sentiero 3" in valori(at.caption)
    assert "**Bosco** · apiario attivo" in valori(at.markdown)
