"""Test del client LLM, M5-T1: richieste, risposte, errori, factory.

Tutti locali: un server HTTP finto su socket veri (`llm_server.py`), nessuna rete e nessuna
chiave vera. **Non sostituiscono la verifica con un provider reale**, che la DoD di M5-T1 chiede
come passo manuale (`python scripts/verifica_llm.py`): qui si prova che il codice parla il
formato documentato, non che i provider rispondano oggi così.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest
from llm_server import ServerFinto, porta_chiusa

from beewatch.ai.llm import (
    ClientOllama,
    ClientOpenRouter,
    LLMClient,
    RispostaLLM,
    crea_client,
)
from beewatch.config import ConfigLLM, carica
from beewatch.exceptions import LLMError

CHIAVE = "sk-or-CHIAVE-SEGRETISSIMA-1234567890"
NOTA = "Nota riservata: la regina di Mario ha la covata a macchia di leopardo."
OLLAMA_OK = {
    "model": "llama3.1:8b",
    "message": {"role": "assistant", "content": "ciao dalla covata"},
    "done": True,
    "prompt_eval_count": 31,
    "eval_count": 7,
}
OPENROUTER_OK = {
    "id": "gen-1",
    "model": "meta-llama/llama-3.1-8b-instruct",
    "choices": [{"index": 0, "finish_reason": "stop",
                 "message": {"role": "assistant", "content": "ciao dalla covata"}}],
    "usage": {"prompt_tokens": 31, "completion_tokens": 7, "total_tokens": 38},
}  # fmt: skip


# In questo file i client non riprovano (`attese=()`): qui si prova UNA chiamata, errori compresi.
# I nuovi tentativi (backoff, Retry-After, tetto di tempo) sono in `test_llm_robustezza.py`.


def ollama(url: str, timeout: int = 5, **politica) -> ClientOllama:
    politica.setdefault("attese", ())
    return ClientOllama("llama3.1:8b", timeout, url, **politica)


def openrouter(url: str, timeout: int = 5, chiave: str = CHIAVE, **politica) -> ClientOpenRouter:
    politica.setdefault("attese", ())
    return ClientOpenRouter("meta-llama/llama-3.1-8b-instruct", timeout, chiave, url, **politica)


# --------------------------------------------------------------------------- #
# Ollama
# --------------------------------------------------------------------------- #


def test_ollama_riceve_la_richiesta_nel_formato_documentato() -> None:
    with ServerFinto() as server:
        server.rispondi(200, OLLAMA_OK)

        ollama(server.url).completa(
            "Sei un assistente.", NOTA, temperatura=0.1, massimo_token=300, risposta_json=True
        )

    richiesta = server.richieste[0]
    assert richiesta.percorso == "/api/chat"
    assert "authorization" not in richiesta.intestazioni  # Ollama in locale non vuole chiavi
    assert richiesta.json == {
        "model": "llama3.1:8b",
        "messages": [
            {"role": "system", "content": "Sei un assistente."},
            {"role": "user", "content": NOTA},
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 300},
        "format": "json",
    }


def test_ollama_senza_opzioni_facoltative_non_le_invia() -> None:
    with ServerFinto() as server:
        server.rispondi(200, OLLAMA_OK)
        ollama(server.url).completa("s", "u")

    corpo = server.richieste[0].json
    assert corpo["options"] == {"temperature": 0.2} and "format" not in corpo


def test_ollama_la_risposta_ha_i_campi_di_messaggi() -> None:
    with ServerFinto() as server:
        server.rispondi(200, OLLAMA_OK, ritardo=0.05)

        risposta = ollama(server.url).completa("s", "u")

    assert isinstance(risposta, RispostaLLM)
    assert (risposta.testo, risposta.provider, risposta.modello) == (
        "ciao dalla covata", "ollama", "llama3.1:8b"
    )  # fmt: skip
    assert (risposta.token_prompt, risposta.token_risposta) == (31, 7)
    assert isinstance(risposta.durata_ms, int) and risposta.durata_ms >= 50  # misurata dal client


def test_ollama_senza_conteggio_dei_token_li_lascia_vuoti() -> None:
    with ServerFinto() as server:
        server.rispondi(200, {"message": {"content": "ok"}})
        risposta = ollama(server.url).completa("s", "u")
    assert (risposta.token_prompt, risposta.token_risposta) == (None, None)
    assert risposta.modello == "llama3.1:8b"  # quello richiesto, se non lo dichiara


@pytest.mark.parametrize(
    "stato,corpo,atteso",
    [
        (404, {"error": "model 'llama3.1:8b' not found"}, "ollama pull llama3.1:8b"),
        (500, {"error": "boom"}, "errore interno"),
        (400, {"error": "bad option"}, "rifiutato la richiesta (stato 400) (bad option)"),
        (400, "non è json", "rifiutato la richiesta (stato 400)."),
    ],
    ids=["modello_assente", "errore_interno", "richiesta_rifiutata", "senza_dettaglio"],
)
def test_ollama_errori_http_con_un_messaggio_che_dice_cosa_fare(stato, corpo, atteso) -> None:
    with ServerFinto() as server:
        server.rispondi(stato, corpo)
        with pytest.raises(LLMError) as errore:
            ollama(server.url).completa("s", "u")
    assert atteso in str(errore.value)


@pytest.mark.parametrize(
    "corpo",
    [{"message": {"content": ""}}, {"message": {"content": "   "}}, {"message": None}, {}],
    ids=["vuota", "spazi", "senza_messaggio", "oggetto_vuoto"],
)
def test_ollama_risposta_senza_testo(corpo) -> None:
    with ServerFinto() as server:
        server.rispondi(200, corpo)
        with pytest.raises(LLMError, match="senza testo"):
            ollama(server.url).completa("s", "u")


@pytest.mark.parametrize(
    "corpo", ["<html>non sono Ollama</html>", [1, 2, 3]], ids=["testo", "lista"]
)
def test_ollama_risposta_che_non_e_un_oggetto_json(corpo) -> None:
    with ServerFinto() as server:
        server.rispondi(200, corpo)
        with pytest.raises(LLMError, match="non è JSON|formato inatteso"):
            ollama(server.url).completa("s", "u")


def test_ollama_spento_dice_come_accenderlo() -> None:
    with pytest.raises(LLMError, match="Ollama non risponde su http://127.0.0.1") as errore:
        ollama(porta_chiusa()).completa("s", "u")
    assert "ollama serve" in str(errore.value) and "OLLAMA_BASE_URL" in str(errore.value)


def test_ollama_timeout() -> None:
    with ServerFinto() as server:
        server.rispondi(200, OLLAMA_OK, ritardo=1.5)
        with pytest.raises(LLMError, match="non ha risposto entro 1 secondi") as errore:
            ollama(server.url, timeout=1).completa("s", "u")
    assert "LLM_TIMEOUT" in str(errore.value)


# --------------------------------------------------------------------------- #
# OpenRouter
# --------------------------------------------------------------------------- #


def test_openrouter_riceve_la_richiesta_nel_formato_documentato() -> None:
    with ServerFinto() as server:
        server.rispondi(200, OPENROUTER_OK)

        openrouter(server.url).completa(
            "Sei un assistente.", NOTA, temperatura=0.3, massimo_token=500, risposta_json=True
        )

    richiesta = server.richieste[0]
    assert richiesta.percorso == "/chat/completions"
    assert richiesta.intestazioni["authorization"] == f"Bearer {CHIAVE}"
    assert richiesta.json == {
        "model": "meta-llama/llama-3.1-8b-instruct",
        "messages": [
            {"role": "system", "content": "Sei un assistente."},
            {"role": "user", "content": NOTA},
        ],
        "temperature": 0.3,
        "stream": False,
        "max_tokens": 500,
        "response_format": {"type": "json_object"},
    }


def test_openrouter_la_risposta_ha_i_campi_di_messaggi() -> None:
    with ServerFinto() as server:
        server.rispondi(200, OPENROUTER_OK)
        risposta = openrouter(server.url).completa("s", "u")

    assert (risposta.testo, risposta.provider) == ("ciao dalla covata", "openrouter")
    assert risposta.modello == "meta-llama/llama-3.1-8b-instruct"  # il modello che ha risposto
    assert (risposta.token_prompt, risposta.token_risposta) == (31, 7)
    assert isinstance(risposta.durata_ms, int) and risposta.durata_ms >= 0


def test_openrouter_senza_uso_dichiarato_i_token_sono_vuoti() -> None:
    corpo = {"choices": [{"message": {"content": "ok"}}]}
    with ServerFinto() as server:
        server.rispondi(200, corpo)
        risposta = openrouter(server.url).completa("s", "u")
    assert (risposta.token_prompt, risposta.token_risposta) == (None, None)


@pytest.mark.parametrize(
    "stato,atteso",
    [
        (401, "controlla LLM_API_KEY"),
        (402, "credito OpenRouter è esaurito"),
        (403, "accesso negato"),
        (404, "non conosce il modello"),
        (408, "non ha risposto in tempo"),
        (429, "limite di richieste"),
        (500, "non è disponibile"),
        (503, "non è disponibile"),
        (418, "rifiutato la richiesta (stato 418) (sono una teiera)"),
    ],
)
def test_openrouter_errori_http_con_un_messaggio_che_dice_cosa_fare(stato, atteso) -> None:
    with ServerFinto() as server:
        server.rispondi(stato, {"error": {"code": stato, "message": "sono una teiera"}})
        with pytest.raises(LLMError) as errore:
            openrouter(server.url).completa("s", "u")
    assert atteso in str(errore.value)


@pytest.mark.parametrize(
    "corpo",
    [
        {"error": {"code": 502, "message": "il provider è caduto"}},  # 200 con un errore dentro
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": "  "}}]},
        {"choices": "no"},
    ],
    ids=[
        "errore_nel_200",
        "choices_vuote",
        "senza_messaggio",
        "contenuto_nullo",
        "spazi",
        "choices_non_lista",
    ],
)
def test_openrouter_risposte_ok_ma_inutilizzabili(corpo) -> None:
    with ServerFinto() as server:
        server.rispondi(200, corpo)
        with pytest.raises(LLMError, match="OpenRouter"):
            openrouter(server.url).completa("s", "u")


def test_openrouter_irraggiungibile_e_timeout() -> None:
    with pytest.raises(LLMError, match="Internet"):
        openrouter(porta_chiusa()).completa("s", "u")
    with ServerFinto() as server:
        server.rispondi(200, OPENROUTER_OK, ritardo=1.5)
        with pytest.raises(LLMError, match="non ha risposto entro 1 secondi"):
            openrouter(server.url, timeout=1).completa("s", "u")


def test_openrouter_senza_chiave_non_si_costruisce() -> None:
    for chiave in (None, ""):
        with pytest.raises(LLMError, match="LLM_API_KEY"):
            ClientOpenRouter("m", 5, chiave)


# --------------------------------------------------------------------------- #
# Segreti e dati dell'utente
# --------------------------------------------------------------------------- #


def scenari(url: str):
    """Chiamate che finiscono bene e male, con la chiave e la nota dentro."""
    return [
        (200, OPENROUTER_OK), (401, {"error": {"message": "bad"}}), (429, {"error": "x"}),
        (500, "esploso"), (200, "non json"),
    ]  # fmt: skip


def test_la_chiave_e_il_testo_dellutente_non_finiscono_ne_nei_messaggi_ne_nel_log(caplog) -> None:
    with ServerFinto() as server, caplog.at_level(logging.DEBUG):
        for stato, corpo in scenari(server.url):
            server.rispondi(stato, corpo)
            try:
                openrouter(server.url).completa("istruzioni di sistema", NOTA)
            except LLMError as errore:
                assert CHIAVE not in str(errore) and NOTA not in str(errore)

    assert CHIAVE not in caplog.text
    assert NOTA not in caplog.text and "istruzioni di sistema" not in caplog.text
    assert "richiesta di" in caplog.text  # del testo si registra la lunghezza


def test_il_log_di_una_chiamata_ha_provider_modello_durata_e_token(caplog) -> None:
    with ServerFinto() as server, caplog.at_level(logging.INFO, logger="beewatch.ai.llm"):
        server.rispondi(200, OLLAMA_OK)
        ollama(server.url).completa("s", "u")

    messaggio = next(r.getMessage() for r in caplog.records if r.name == "beewatch.ai.llm")
    assert re.fullmatch(
        r"LLM ollama/llama3.1:8b: \d+ ms, token 31→7, 1 tentativo, richiesta di 2 caratteri",
        messaggio,
    )


# --------------------------------------------------------------------------- #
# Factory e cambio di provider
# --------------------------------------------------------------------------- #


def configurazione(provider: str, **extra) -> ConfigLLM:
    base = {"provider": provider, "modello": "m", "api_key": None, "timeout": 30}
    return ConfigLLM(**{**base, **extra})


def test_la_factory_sceglie_ollama_con_il_suo_indirizzo() -> None:
    client = crea_client(configurazione("ollama", ollama_url="http://altro:1234"))

    assert isinstance(client, ClientOllama) and client.provider == "ollama"
    assert client._url == "http://altro:1234" and client._timeout == 30


def test_la_factory_sceglie_openrouter_con_la_chiave() -> None:
    client = crea_client(configurazione("openrouter", api_key=CHIAVE))
    assert isinstance(client, ClientOpenRouter) and client._api_key == CHIAVE


def test_la_factory_rifiuta_openrouter_senza_chiave_e_un_provider_sconosciuto() -> None:
    with pytest.raises(LLMError, match="LLM_API_KEY"):
        crea_client(configurazione("openrouter"))
    with pytest.raises(LLMError, match="sconosciuto"):
        crea_client(configurazione("chatgpt"))


def test_il_client_astratto_non_si_puo_istanziare() -> None:
    with pytest.raises(TypeError):
        LLMClient("m", 5)  # type: ignore[abstract]


def test_cambiare_provider_e_solo_una_modifica_a_env(tmp_path: Path, monkeypatch) -> None:
    """Due `.env` che differiscono per `LLM_PROVIDER` (e la chiave): stesso codice, altro client."""

    def client_da(env: str):
        percorso = tmp_path / "env"
        percorso.write_text("DB_NAME=x\nDB_USER=y\nDB_PASSWORD=z\n" + env, encoding="utf-8")
        for variabile in ("LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL"):
            monkeypatch.delenv(variabile, raising=False)
        return crea_client(carica(percorso).llm)

    locale = client_da("LLM_PROVIDER=ollama\n")
    cloud = client_da(f"LLM_PROVIDER=openrouter\nLLM_API_KEY={CHIAVE}\nLLM_MODEL=a/b\n")

    assert (type(locale), type(cloud)) == (ClientOllama, ClientOpenRouter)
    # Stessa interfaccia, stesso tipo di risposta: il chiamante non vede la differenza.
    with ServerFinto() as ol, ServerFinto() as orr:
        ol.rispondi(200, OLLAMA_OK)
        orr.rispondi(200, OPENROUTER_OK)
        locale._url, cloud._url = ol.url, orr.url
        a, b = locale.completa("s", "u"), cloud.completa("s", "u")
    assert (a.testo, a.token_prompt, a.token_risposta) == (
        b.testo,
        b.token_prompt,
        b.token_risposta,
    )
    assert (a.provider, b.provider) == ("ollama", "openrouter")


def test_i_campi_della_risposta_sono_le_colonne_di_messaggi() -> None:
    schema = (Path(__file__).resolve().parents[1] / "sql" / "schema.sql").read_text(
        encoding="utf-8"
    )
    tabella = schema[schema.index("CREATE TABLE IF NOT EXISTS messaggi") :]
    tabella = tabella[: tabella.index("ENGINE")]

    for campo in ("provider", "modello", "durata_ms", "token_prompt", "token_risposta"):
        assert re.search(rf"^\s+{campo}\s", tabella, re.MULTILINE), campo
        assert campo in RispostaLLM.__dataclass_fields__


def test_un_errore_di_rete_imprevisto_diventa_un_llm_error_senza_dettagli_dellutente(
    monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    import requests

    def cade(*argomenti, **opzioni):
        raise requests.exceptions.ChunkedEncodingError(f"connessione rotta mentre inviavo {NOTA}")

    monkeypatch.setattr(requests, "post", cade)

    with caplog.at_level(logging.DEBUG), pytest.raises(LLMError, match="non è riuscita") as errore:
        ollama("http://localhost:11434").completa("s", NOTA)

    assert NOTA not in str(errore.value) and NOTA not in caplog.text  # nemmeno il testo dell'errore
    assert "ChunkedEncodingError" in caplog.text  # del tipo sì: serve a capire cosa è successo
