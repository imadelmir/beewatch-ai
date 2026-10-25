"""La suite non può chiamare un provider vero né dipendere dal computer di chi la lancia (M5-T6).

La DoD di M5-T6 dice «la suite gira senza rete e senza chiave API». Qui non si spera: si verifica
che il blocco della rete (fixture `rete_bloccata` di `conftest.py`) funzioni, che l'ambiente di
ogni test sia privo di chiavi e che nessun test legga il `.env` vero dello sviluppatore.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest
import requests
from conftest import VARIABILI_BEEWATCH
from llm_server import ServerFinto

from beewatch import config
from beewatch.ai.llm import ClientOllama, ClientOpenRouter
from beewatch.exceptions import ConfigError, LLMError

RADICE_VERA = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "host", ["203.0.113.7", "8.8.8.8", "openrouter.ai", "host.docker.internal"]
)
def test_una_connessione_verso_unaltra_macchina_e_bloccata(host):
    with pytest.raises(RuntimeError, match="Test senza rete"):
        socket.create_connection((host, 80), timeout=1)


def test_anche_la_risoluzione_dei_nomi_e_bloccata():
    with pytest.raises(RuntimeError, match="Test senza rete"):
        socket.getaddrinfo("openrouter.ai", 443)


def test_connect_ex_verso_unaltra_macchina_e_bloccata():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        with pytest.raises(RuntimeError, match="Test senza rete"):
            s.connect_ex(("203.0.113.7", 80))


def test_requests_verso_un_provider_vero_non_parte():
    with pytest.raises(RuntimeError, match="openrouter.ai"):
        requests.post("https://openrouter.ai/api/v1/chat/completions", json={}, timeout=1)


def test_i_client_veri_non_arrivano_ai_provider_veri():
    # Non è un LLMError: un guasto di rete sarebbe stato nascosto da un messaggio gentile.
    # Qui il blocco scatta PRIMA, e un RuntimeError attraversa il client (che lo trasforma in
    # LLMError «imprevisto» con lo stack nel log): in nessun caso la richiesta esce dal computer.
    with pytest.raises(LLMError, match="imprevisto"):
        ClientOpenRouter("m", 5, api_key="chiave", attese=()).completa("s", "u")
    with pytest.raises(LLMError, match="imprevisto"):
        ClientOllama("m", 5, url="http://ollama.example.com:11434", attese=()).completa("s", "u")


def test_il_computer_stesso_resta_raggiungibile():
    with ServerFinto() as server:
        server.rispondi(200, {"message": {"content": "ciao"}})
        risposta = ClientOllama("m", 5, url=server.url, attese=()).completa("s", "u")
    assert risposta.testo == "ciao"


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_gli_indirizzi_locali_non_sono_bloccati(host):
    from conftest import _indirizzo_locale

    assert _indirizzo_locale(host)


def test_nessuna_variabile_di_beewatch_arriva_dal_computer_di_chi_lancia_i_test():
    presenti = [nome for nome in VARIABILI_BEEWATCH if nome in os.environ]
    assert presenti == []
    assert "LLM_API_KEY" not in os.environ


def test_il_env_vero_del_progetto_non_viene_letto():
    assert config.RADICE != RADICE_VERA
    assert not str(config.RADICE).startswith(str(RADICE_VERA))
    with pytest.raises(ConfigError):  # senza un .env di prova la configurazione non si carica
        config.ottieni()


def test_un_proxy_della_shell_non_instrada_le_richieste_al_server_locale():
    for nome in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        assert nome not in os.environ, nome
    assert "127.0.0.1" in os.environ["NO_PROXY"]
