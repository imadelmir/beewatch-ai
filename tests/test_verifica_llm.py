"""Test di `scripts/verifica_llm.py` (M5-T1): lo script che prova una chiamata vera.

Qui si prova lo script, non il provider: contro un server finto. La chiamata vera la fa l'utente
(vedi la Definition of Done di M5-T1).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from llm_server import ServerFinto, porta_chiusa

from beewatch.config import ConfigLLM

CHIAVE = "sk-or-CHIAVE-DELLO-SCRIPT"
OLLAMA_OK = {"model": "m", "message": {"content": "OK"}, "prompt_eval_count": 12, "eval_count": 2}
OLLAMA_JSON = {"model": "m", "message": {"content": '{"ok": true}'}}


def carica_script() -> ModuleType:
    percorso = Path(__file__).resolve().parents[1] / "scripts" / "verifica_llm.py"
    specifica = importlib.util.spec_from_file_location("verifica_llm", percorso)
    modulo = importlib.util.module_from_spec(specifica)
    specifica.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    modulo = carica_script()
    monkeypatch.setattr(modulo, "configura", lambda: None)
    # Senza nuovi tentativi: un errore deve arrivare subito, non dopo 1 + 2 + 4 secondi veri.
    crea_vero = modulo.crea_client
    monkeypatch.setattr(modulo, "crea_client", lambda cfg: crea_vero(cfg, attese=()))
    return modulo


def con_configurazione(script: ModuleType, monkeypatch, url: str, **extra) -> None:
    base = {"provider": "ollama", "modello": "llama3.1:8b", "api_key": None, "timeout": 5,
            "ollama_url": url}  # fmt: skip
    configurazione = SimpleNamespace(llm=ConfigLLM(**{**base, **extra}))
    monkeypatch.setattr(script.config, "ottieni", lambda: configurazione)


def test_una_chiamata_riuscita_stampa_il_riepilogo_ed_esce_con_0(
    script, monkeypatch, capsys
) -> None:
    with ServerFinto() as server:
        server.rispondi(200, OLLAMA_OK).rispondi(200, OLLAMA_JSON)
        con_configurazione(script, monkeypatch, server.url)

        esito = script.main([])

    uscita = capsys.readouterr().out
    assert esito == 0
    assert "Provider ollama, modello llama3.1:8b, timeout 5 s" in uscita
    assert "risposta:    'OK'" in uscita and "token:       12 → 2" in uscita
    assert "formato JSON: rispettato" in uscita and "Chiamata riuscita." in uscita
    assert [r.json["format"] if "format" in r.json else None for r in server.richieste] == [
        None,
        "json",
    ]


def test_se_il_modello_non_rispetta_il_json_lo_dice_ma_non_fallisce(
    script, monkeypatch, capsys
) -> None:
    with ServerFinto() as server:
        server.rispondi(200, OLLAMA_OK).rispondi(200, {"message": {"content": "ecco: {ok}"}})
        con_configurazione(script, monkeypatch, server.url)

        esito = script.main([])

    assert esito == 0
    assert "formato JSON: NON rispettato" in capsys.readouterr().out


def test_se_il_provider_non_risponde_esce_con_1_e_dice_perche(script, monkeypatch, capsys) -> None:
    con_configurazione(script, monkeypatch, porta_chiusa())

    esito = script.main([])

    errore = capsys.readouterr().err
    assert esito == 1 and "Chiamata NON riuscita: Ollama non risponde" in errore


def test_provider_e_modello_si_possono_sostituire_solo_per_la_prova(
    script, monkeypatch, capsys
) -> None:
    with ServerFinto() as server:
        server.rispondi(200, {"choices": [{"message": {"content": "OK"}}], "model": "x/y"})
        con_configurazione(script, monkeypatch, server.url, api_key=CHIAVE)
        monkeypatch.setattr(
            script,
            "crea_client",
            lambda cfg: script_crea(cfg, server.url),  # stesso client, ma verso il server finto
        )

        esito = script.main(["--provider", "openrouter", "--modello", "x/y"])

    uscita = capsys.readouterr()
    assert esito == 0 and "Provider openrouter, modello x/y" in uscita.out
    assert CHIAVE not in uscita.out + uscita.err  # la chiave non si stampa mai
    assert server.richieste[0].intestazioni["authorization"] == f"Bearer {CHIAVE}"


def script_crea(cfg: ConfigLLM, url: str):
    from beewatch.ai.llm import ClientOpenRouter

    assert cfg.provider == "openrouter" and cfg.modello == "x/y"
    return ClientOpenRouter(cfg.modello, cfg.timeout, cfg.api_key, url)


def test_openrouter_senza_chiave_esce_con_1(script, monkeypatch, capsys) -> None:
    con_configurazione(script, monkeypatch, "http://localhost:1", provider="openrouter")

    esito = script.main([])

    assert esito == 1 and "LLM_API_KEY" in capsys.readouterr().err
