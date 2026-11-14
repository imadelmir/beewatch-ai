"""La pagina Trasparenza e il documento etico (M6-T8).

Due gruppi di controlli:

- **coerenza**: ogni paragrafo della pagina sta in `docs/etica.md` parola per parola, e i punti
  obbligatori (dati, AI generativa, limiti, GDPR, AI Act, veterinario) ci sono; niente gergo non
  spiegato;
- **la pagina** con `AppTest`: l'avvertenza in cima, l'assistente locale o esterno detto in base
  alla configurazione, il modello con i suoi numeri, le sezioni, gli errori.
"""

from __future__ import annotations

import ast
import re

import pytest
from app_finta import APP, PAGINE, RADICE, con_accesso, installa, servizi_finti, valori
from streamlit.testing.v1 import AppTest

from beewatch.exceptions import ModelError

PAGINA = APP / "pages" / "6_Trasparenza.py"
ETICA = RADICE / "docs" / "etica.md"


def sezioni() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """`SEZIONI` della pagina, lette senza eseguirla."""
    for nodo in ast.parse(PAGINA.read_text(encoding="utf-8")).body:
        if isinstance(nodo, ast.AnnAssign) and getattr(nodo.target, "id", "") == "SEZIONI":
            return ast.literal_eval(nodo.value)
    raise AssertionError("SEZIONI non trovata nella pagina")


def paragrafi() -> list[str]:
    return [p for _, elenco in sezioni() for p in elenco]


def normalizza(testo: str) -> str:
    return re.sub(r"\s+", " ", testo).strip()


def tutta_la_pagina() -> str:
    return " ".join(titolo + " " + " ".join(elenco) for titolo, elenco in sezioni())


# --------------------------------------------------------------------------- #
# Coerenza con docs/etica.md e contenuti obbligatori
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("paragrafo", paragrafi(), ids=lambda p: p[:40])
def test_ogni_paragrafo_della_pagina_sta_nel_documento_etico_parola_per_parola(paragrafo):
    assert normalizza(paragrafo) in normalizza(ETICA.read_text(encoding="utf-8"))


def test_il_documento_etico_tratta_i_cinque_punti_obbligatori():
    documento = ETICA.read_text(encoding="utf-8")

    for titolo in ("Bias", "Privacy e GDPR", "Trasparenza", "EU AI Act", "Limiti e usi impropri"):
        assert re.search(rf"^## \d\. {titolo}", documento, flags=re.M), titolo


@pytest.mark.parametrize(
    ("argomento", "parole"),
    [
        ("dati e dove sono", ("database MySQL", "sul computer", "note di campo", "coordinate")),
        ("AI generativa", ("intelligenza artificiale generativa", "modello di linguaggio")),
        ("note fuori dal PC", ("escono dal PC", "servizio esterno")),
        ("limiti del modello", ("USDA", "1998", "2012", "stati USA", "clima italiano")),
        ("GDPR", ("GDPR", "Art. 5", "Art. 6", "Art. 17")),
        ("AI Act", ("AI Act", "art. 50", "rischio minimo")),
        ("veterinario", ("Non sostituisce un veterinario né un tecnico apistico",)),
    ],
)
def test_la_pagina_dice_cio_che_la_dod_chiede(argomento, parole):
    testo = tutta_la_pagina()
    for parola in parole:
        assert parola in testo, (argomento, parola)


@pytest.mark.parametrize(
    "gergo", ["LLM", "MAE", "RMSE", "R²", "token", "embedding", "dataset di training", "API"]
)
def test_nessun_gergo_non_spiegato(gergo):
    assert gergo not in tutta_la_pagina()


def test_i_termini_tecnici_che_restano_sono_spiegati():
    testo = tutta_la_pagina()
    assert "le istruzioni che ha ricevuto (il prompt)" in testo
    assert "quanto il modello si fida di sé (la confidenza)" in testo
    assert "I file di registro (log)" in testo
    assert "un programma che ha imparato a produrre testo" in testo


def test_la_pagina_e_nel_menu_principale():
    assert PAGINA in PAGINE  # ogni file di `pages/` è una voce del menu, in ordine di prefisso


# --------------------------------------------------------------------------- #
# La pagina con AppTest
# --------------------------------------------------------------------------- #


def apri() -> AppTest:
    return con_accesso(AppTest.from_file(str(PAGINA), default_timeout=30)).run()


def test_lavvertenza_sul_veterinario_e_in_cima(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti())

    at = apri()

    assert not at.exception and not at.error
    assert valori(at.title) == ["🔍 Trasparenza"]
    prima = at.warning[0]
    assert prima.value.startswith("BeeWatch AI non è uno strumento diagnostico.")
    assert not at.expander  # niente di nascosto


def test_ogni_sezione_ha_il_suo_titolo_e_i_suoi_paragrafi(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti())

    at = apri()

    titoli = valori(at.subheader)
    for titolo, elenco in sezioni():
        assert titolo in titoli
        for paragrafo in elenco:
            assert paragrafo in valori(at.markdown)


def test_con_lassistente_locale_le_note_restano_sul_pc(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti(llm_in_locale=True))

    at = apri()

    [locale] = valori(at.success)
    assert "gira su questo computer" in locale and "non escono dal PC" in locale


def test_con_un_assistente_esterno_lo_dice_chiaramente(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti(llm_in_locale=False))

    at = apri()

    assert not at.success
    assert any("servizio esterno" in w and "escono dal PC" in w for w in valori(at.warning))


def test_senza_assistente_configurato_lo_dice(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti(llm_in_locale=None))

    at = apri()

    assert any("non è configurato" in i for i in valori(at.info))


def test_il_modello_in_uso_con_i_suoi_numeri(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti())

    at = apri()

    assert {m.label: m.value for m in at.metric} == {
        "Errore medio": "3,5 kg",
        "Righe di addestramento": "600",
    }
    assert any("Modello v-stub (RandomForestRegressor)" in c for c in valori(at.caption))


def test_senza_modello_la_pagina_resta_leggibile(app_pronta, monkeypatch):
    def manca():
        raise ModelError("Il modello non è stato trovato: lancia scripts/train_model.py.")

    installa(app_pronta, monkeypatch, servizi_finti(crea_predittore=manca))

    at = apri()

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Il modello di previsione non è disponibile.**")
    assert len(valori(at.subheader)) == 2 + len(sezioni())  # tutto il resto c'è
