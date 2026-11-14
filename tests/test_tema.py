"""Il tema chiaro e scuro del mockup, l'interruttore e lo stile (app/tema.py, beewatch.css)."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
from app_finta import APP, con_accesso, installa, servizi_finti
from streamlit.testing.v1 import AppTest
from test_app_struttura import carica_tema

tema = carica_tema()


def test_le_variabili_dei_due_temi_hanno_gli_stessi_nomi():
    assert set(tema.PALETTE["light"]) == set(tema.PALETTE["dark"])


@pytest.mark.parametrize("nome", ["light", "dark"])
def test_le_variabili_coprono_ogni_var_usata_dal_css(nome):
    css = tema.FILE_CSS.read_text(encoding="utf-8")
    usate = set(re.findall(r"var\(--bw-([a-z0-9-]+)\)", css))
    definite = set(re.findall(r"--bw-([a-z0-9-]+):", tema.variabili(nome)))
    assert usate <= definite, usate - definite


@pytest.mark.parametrize("nome", ["light", "dark"])
def test_lo_stile_non_contiene_il_carattere_che_streamlit_scarta(nome):
    # Un «<» dentro <style> e Streamlit butta via tutto lo stile (protezione dall'HTML)
    assert "<" not in tema.variabili(nome)
    assert "<" not in tema.FILE_CSS.read_text(encoding="utf-8")


def test_gli_indirizzi_ricordati_sono_quelli_delle_pagine_del_router():
    sorgente = (APP / "Home.py").read_text(encoding="utf-8")
    file = re.findall(r'st\.Page\(\s*"([^"]+)"', sorgente)
    attesi = {re.sub(r"^\d+_", "", Path(f).stem) for f in file} | {""}
    assert set(tema.PERCORSI_APP) == attesi


def test_il_formato_della_chiave_del_tema_e_quello_di_streamlit():
    """L'interruttore scrive la voce che Streamlit rilegge: se un aggiornamento la cambia, qui si
    vede (le versioni sono bloccate, ma il test lo dice prima di un utente)."""
    import streamlit

    cartella = Path(streamlit.__file__).parent / "static" / "static" / "js"
    trovati = set()
    for file in cartella.glob("*.js"):
        testo = file.read_text(encoding="utf-8", errors="ignore")
        trovati |= set(
            re.findall(r"var \w+=(\d+),\w+=`stActiveTheme-\$\{window\.location\.pathname\}`", testo)
        )
    assert trovati == {"2"}
    script = (APP / "tema.py").read_text(encoding="utf-8")
    assert '"stActiveTheme-" + p + "-v2"' in script
    assert "JSON.stringify(" in script  # Streamlit la rilegge con JSON.parse


def test_il_tema_attivo_fuori_dal_browser_e_il_chiaro():
    assert tema.tema_attivo() == "light"


def test_scrivere_il_tema_ricarica_con_il_valore_giusto(app_pronta):
    def corpo():
        import tema as t

        t.scrivi_tema("dark")

    at = AppTest.from_function(corpo, default_timeout=30).run()

    [script] = [e.proto.body for e in at.get("html")]
    assert 'JSON.stringify("Dark")' in script and "window.location.reload()" in script
    for percorso in tema.PERCORSI_APP:
        assert json.dumps(percorso) in script


def test_linterruttore_mostra_il_tema_attivo_e_non_ricarica_se_non_cambia(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti())

    at = con_accesso(AppTest.from_file(str(APP / "pages" / "8_Impostazioni.py"))).run()

    [interruttore] = at.get("button_group")
    assert [o.content for o in interruttore.proto.options] == ["Scuro", "Chiaro"]
    assert list(interruttore.proto.default) == [1]  # fuori dal browser il tema è il chiaro
    assert not [e for e in at.get("html") if "reload" in e.proto.body]


def test_lapp_applica_lo_stile_dal_router(app_pronta, monkeypatch):
    installa(app_pronta, monkeypatch, servizi_finti())

    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=30).run()

    stili = [e.proto.body for e in at.get("html") if "<style>" in e.proto.body]
    assert len(stili) == 1 and "--bw-accento: #F5B301;" in stili[0]  # fuori dal browser: chiaro
    assert '<span class="bw-stile"></span>' in stili[0]


def test_il_modulo_del_tema_non_importa_il_resto_dellapp():
    importati = {
        n.names[0].name if isinstance(n, ast.Import) else n.module
        for n in ast.walk(ast.parse((APP / "tema.py").read_text(encoding="utf-8")))
        if isinstance(n, ast.Import | ast.ImportFrom)
    }
    assert importati <= {"__future__", "json", "pathlib", "typing", "urllib.parse", "streamlit"}
