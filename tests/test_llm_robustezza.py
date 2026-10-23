"""Test della robustezza delle chiamate al modello, M5-T2.

Un server HTTP finto su socket veri (`llm_server.py`) per gli stati e le intestazioni; una pausa e
un orologio **finti**, così nessun test aspetta secondi veri e si vede esattamente quanto il
client avrebbe aspettato. Dove serve un errore di rete immediato si sostituisce `requests.post`.

Cosa si prova (DoD): il comportamento con un provider irraggiungibile, che nessuna eccezione
diversa da `LLMError` raggiunga l'interfaccia, e che latenza, token e tentativi vengano loggati.
"""

from __future__ import annotations

import logging
import time
from email.utils import formatdate

import pytest
import requests
from llm_server import ServerFinto

from beewatch.ai.llm import (
    ATTESE_RETRY,
    ClientOllama,
    ClientOpenRouter,
    LLMClient,
    crea_client,
)
from beewatch.config import ConfigLLM
from beewatch.exceptions import LLMError

CHIAVE = "sk-or-CHIAVE-SEGRETISSIMA-1234567890"
NOTA = "Nota riservata: la regina di Mario ha la covata a macchia di leopardo."
OLLAMA_OK = {"message": {"content": "ok"}, "prompt_eval_count": 3, "eval_count": 1}
OPENROUTER_OK = {
    "choices": [{"message": {"content": "ok"}}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 1},
}


class Tempo:
    """Pausa e orologio finti: la pausa registra l'attesa e fa avanzare l'orologio."""

    def __init__(self) -> None:
        self.attese: list[float] = []
        self.ora = 0.0

    def pausa(self, secondi: float) -> None:
        self.attese.append(secondi)
        self.ora += secondi

    def orologio(self) -> float:
        return self.ora


def clienti(url: str, tempo: Tempo, timeout: int = 5) -> list[LLMClient]:
    politica = {"pausa": tempo.pausa, "orologio": tempo.orologio}
    return [
        ClientOllama("llama3.1:8b", timeout, url, **politica),
        ClientOpenRouter("a/b", timeout, CHIAVE, url, **politica),
    ]


def ok_per(client: LLMClient) -> dict:
    return OLLAMA_OK if client.provider == "ollama" else OPENROUTER_OK


@pytest.fixture(params=["ollama", "openrouter"])
def provider(request) -> str:
    return request.param


def client_di(provider: str, url: str, tempo: Tempo, timeout: int = 5) -> LLMClient:
    return clienti(url, tempo, timeout)[0 if provider == "ollama" else 1]


def chiama(client: LLMClient):
    return client.completa("sistema", NOTA)


# --------------------------------------------------------------------------- #
# Quando si riprova, e quante volte
# --------------------------------------------------------------------------- #


def test_il_backoff_predefinito_e_1_2_e_4_secondi() -> None:
    assert ATTESE_RETRY == (1.0, 2.0, 4.0)


def test_un_429_e_poi_un_200_riesce_al_secondo_tentativo(provider: str) -> None:
    tempo = Tempo()
    with ServerFinto() as server:
        client = client_di(provider, server.url, tempo)
        server.rispondi(429, {"error": "troppe richieste"}).rispondi(200, ok_per(client))

        risposta = chiama(client)

    assert risposta.testo == "ok" and risposta.tentativi == 2
    assert tempo.attese == [1.0] and len(server.richieste) == 2


@pytest.mark.parametrize("stato", [408, 500, 502, 503, 504])
def test_gli_stati_transitori_si_ritentano(provider: str, stato: int) -> None:
    tempo = Tempo()
    with ServerFinto() as server:
        client = client_di(provider, server.url, tempo)
        server.rispondi(stato, {"error": "giù"}).rispondi(200, ok_per(client))

        assert chiama(client).tentativi == 2


def test_le_attese_sono_1_2_e_4_e_il_quarto_tentativo_puo_riuscire(provider: str) -> None:
    tempo = Tempo()
    with ServerFinto() as server:
        client = client_di(provider, server.url, tempo)
        for _ in range(3):
            server.rispondi(500, {"error": "giù"})
        server.rispondi(200, ok_per(client))

        risposta = chiama(client)

    assert risposta.tentativi == 4 and tempo.attese == [1.0, 2.0, 4.0]


def test_se_il_provider_resta_giu_si_rinuncia_dopo_quattro_tentativi(provider: str) -> None:
    tempo = Tempo()
    with ServerFinto() as server:
        client = client_di(provider, server.url, tempo)
        server.rispondi(503, {"error": "giù"})

        with pytest.raises(LLMError, match=r"\(dopo 4 tentativi\)"):
            chiama(client)

    assert len(server.richieste) == 4 and tempo.attese == [
        1.0,
        2.0,
        4.0,
    ]  # tre nuovi tentativi, non di più


@pytest.mark.parametrize("stato", [400, 401, 402, 403, 404, 418])
def test_gli_errori_che_riprovando_non_cambiano_non_si_ritentano(provider: str, stato: int) -> None:
    tempo = Tempo()
    with ServerFinto() as server:
        client = client_di(provider, server.url, tempo)
        server.rispondi(stato, {"error": "no"})

        with pytest.raises(LLMError) as errore:
            chiama(client)

    assert len(server.richieste) == 1 and tempo.attese == []
    assert "tentativi" not in str(errore.value)


@pytest.mark.parametrize(
    "corpo",
    ["non json", [1, 2], {"message": {"content": ""}}, {"choices": []}],
    ids=["testo", "lista", "vuota", "senza_scelte"],
)
def test_una_risposta_arrivata_ma_inutilizzabile_non_si_ritenta(provider: str, corpo) -> None:
    tempo = Tempo()
    with ServerFinto() as server:
        client = client_di(provider, server.url, tempo)
        server.rispondi(200, corpo)

        with pytest.raises(LLMError):
            chiama(client)

    assert len(server.richieste) == 1 and tempo.attese == []


def test_un_timeout_si_ritenta_e_un_modello_che_si_sta_caricando_puo_rispondere_alla_seconda() -> (
    None
):
    tempo = Tempo()
    with ServerFinto() as server:
        client = clienti(server.url, tempo, timeout=1)[0]
        server.rispondi(200, OLLAMA_OK, ritardo=1.6).rispondi(200, OLLAMA_OK)  # la prima scade

        risposta = chiama(client)

    assert risposta.tentativi == 2 and tempo.attese == [1.0]


# --------------------------------------------------------------------------- #
# Retry-After
# --------------------------------------------------------------------------- #


def prova_retry_after(valore: str, provider: str = "openrouter") -> tuple[Tempo, int]:
    tempo = Tempo()
    with ServerFinto() as server:
        client = client_di(provider, server.url, tempo)
        server.rispondi(429, {"error": "limite"}, intestazioni={"Retry-After": valore})
        server.rispondi(200, ok_per(client))
        risposta = chiama(client)
    return tempo, risposta.tentativi


def test_retry_after_in_secondi_vale_piu_del_backoff_se_e_piu_lungo() -> None:
    tempo, tentativi = prova_retry_after("7")
    assert tempo.attese == [7.0] and tentativi == 2


def test_retry_after_piu_corto_del_backoff_non_lo_accorcia() -> None:
    tempo, _ = prova_retry_after("0")
    assert tempo.attese == [1.0]


def test_retry_after_come_data_http_si_converte_in_secondi() -> None:
    tempo, _ = prova_retry_after(formatdate(time.time() + 10, usegmt=True))
    assert 8.0 <= tempo.attese[0] <= 10.0


@pytest.mark.parametrize(
    "valore",
    ["domani", formatdate(time.time() - 3600, usegmt=True), ""],
    ids=["testo_senza_senso", "data_passata", "vuoto"],
)
def test_retry_after_illeggibile_o_nel_passato_si_ignora(valore: str) -> None:
    tempo, _ = prova_retry_after(valore)
    assert tempo.attese == [1.0]


def test_se_il_provider_chiede_piu_di_30_secondi_non_si_aspetta_e_lo_si_dice() -> None:
    tempo = Tempo()
    with ServerFinto() as server:
        client = client_di("openrouter", server.url, tempo)
        server.rispondi(429, {"error": "limite"}, intestazioni={"Retry-After": "120"})

        with pytest.raises(LLMError, match="limite di richieste") as errore:
            chiama(client)

    assert "attendere 120 secondi" in str(errore.value)
    assert len(server.richieste) == 1 and tempo.attese == []  # non si è bloccata l'interfaccia


# --------------------------------------------------------------------------- #
# Errori di rete e tetto di tempo
# --------------------------------------------------------------------------- #


def con_post(
    monkeypatch: pytest.MonkeyPatch, tempo: Tempo, errore: Exception, secondi: float = 0.0
):
    chiamate: list[int] = []

    def post(*argomenti, **opzioni):
        chiamate.append(1)
        tempo.ora += secondi  # quanto «dura» il tentativo
        raise errore

    monkeypatch.setattr(requests, "post", post)
    return chiamate


def test_un_provider_irraggiungibile_da_un_errore_chiaro_dopo_quattro_tentativi(
    monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    """Il caso della DoD: provider spento. L'interfaccia riceve un LLMError, non si pianta."""
    tempo = Tempo()
    chiamate = con_post(monkeypatch, tempo, requests.exceptions.ConnectionError("rifiutata"))
    client = clienti("http://localhost:11434", tempo)[0]

    with caplog.at_level(logging.WARNING), pytest.raises(LLMError) as errore:
        chiama(client)

    assert "Ollama non risponde su http://localhost:11434" in str(errore.value)
    assert "(dopo 4 tentativi)" in str(errore.value)
    assert len(chiamate) == 4 and tempo.attese == [1.0, 2.0, 4.0]
    avvisi = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert avvisi == [
        "LLM ollama: tentativo 1 non riuscito (connessione), riprovo fra 1.0 s",
        "LLM ollama: tentativo 2 non riuscito (connessione), riprovo fra 2.0 s",
        "LLM ollama: tentativo 3 non riuscito (connessione), riprovo fra 4.0 s",
    ]


def test_il_tetto_di_tempo_ferma_i_tentativi_dopo_due_timeout_da_60_secondi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Senza tetto sarebbero quattro timeout da un minuto: quattro minuti di interfaccia ferma."""
    tempo = Tempo()
    chiamate = con_post(monkeypatch, tempo, requests.exceptions.Timeout(), secondi=60)
    client = clienti("http://localhost:11434", tempo, timeout=60)[0]

    with pytest.raises(LLMError, match=r"non ha risposto entro 60 secondi.*\(dopo 2 tentativi\)"):
        chiama(client)

    assert len(chiamate) == 2 and tempo.attese == [1.0]
    assert tempo.ora == 121.0  # 60 + 1 + 60: meno di tre volte il timeout


def test_con_errori_veloci_il_tetto_non_toglie_nessun_tentativo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tempo = Tempo()
    chiamate = con_post(monkeypatch, tempo, requests.exceptions.ConnectionError("x"), secondi=0.01)
    client = clienti("http://localhost:11434", tempo, timeout=60)[0]

    with pytest.raises(LLMError):
        chiama(client)

    assert len(chiamate) == 4


def test_un_errore_di_rete_imprevisto_non_si_ritenta(monkeypatch: pytest.MonkeyPatch) -> None:
    tempo = Tempo()
    chiamate = con_post(monkeypatch, tempo, requests.exceptions.ChunkedEncodingError("x"))
    client = clienti("http://localhost:11434", tempo)[0]

    with pytest.raises(LLMError, match="non è riuscita"):
        chiama(client)

    assert len(chiamate) == 1 and tempo.attese == []


# --------------------------------------------------------------------------- #
# Log: latenza, token, tentativi; mai la chiave né il testo
# --------------------------------------------------------------------------- #


def test_il_log_finale_ha_modello_durata_token_e_tentativi(caplog) -> None:
    tempo = Tempo()
    with ServerFinto() as server, caplog.at_level(logging.INFO, logger="beewatch.ai.llm"):
        client = clienti(server.url, tempo)[1]
        server.rispondi(429, {"error": "x"}).rispondi(200, {**OPENROUTER_OK, "model": "a/b"})

        chiama(client)

    righe = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert len(righe) == 1
    assert righe[0].startswith("LLM openrouter/a/b: ") and "token 3→1, 2 tentativi" in righe[0]


def test_ne_la_chiave_ne_il_testo_finiscono_nel_log_dei_tentativi(caplog) -> None:
    tempo = Tempo()
    with ServerFinto() as server, caplog.at_level(logging.DEBUG):
        client = clienti(server.url, tempo)[1]
        server.rispondi(503, {"error": f"{CHIAVE} {NOTA}"})
        with pytest.raises(LLMError) as errore:
            chiama(client)

    assert CHIAVE not in caplog.text and NOTA not in caplog.text
    assert CHIAVE not in str(errore.value) and NOTA not in str(errore.value)


# --------------------------------------------------------------------------- #
# Nessuna eccezione diversa da LLMError
# --------------------------------------------------------------------------- #

CORPI_STRANI = [
    None, [], 123, "x", {}, {"choices": 5}, {"choices": [5]}, {"choices": [{"message": []}]},
    {"choices": [{"message": {"content": 5}}]}, {"message": []}, {"message": {"content": 5}},
    {"message": {"content": ["a"]}}, {"error": {"message": 5}}, {"choices": [None]},
]  # fmt: skip


@pytest.mark.parametrize("corpo", CORPI_STRANI, ids=[repr(c)[:30] for c in CORPI_STRANI])
def test_risposte_strane_diventano_llm_error_e_mai_un_altro_errore(provider: str, corpo) -> None:
    tempo = Tempo()
    with ServerFinto() as server:
        client = client_di(provider, server.url, tempo)
        server.rispondi(200, corpo)

        with pytest.raises(LLMError):
            chiama(client)


def test_un_errore_imprevisto_diventa_llm_error_con_lo_stack_nel_log(
    monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    def bug(*argomenti, **opzioni):
        raise KeyError("un bug mio")

    client = clienti("http://localhost:11434", Tempo())[0]
    monkeypatch.setattr(client, "_invia", bug)

    with (
        caplog.at_level(logging.ERROR),
        pytest.raises(LLMError, match="Errore imprevisto") as errore,
    ):
        chiama(client)

    assert isinstance(errore.value.__cause__, KeyError)
    registrazione = next(r for r in caplog.records if "imprevisto" in r.getMessage())
    assert registrazione.exc_info is not None  # lo stack c'è, nel log


def test_la_factory_passa_la_politica_di_tentativi_al_client() -> None:
    tempo = Tempo()
    configurazione = ConfigLLM(provider="ollama", modello="m", api_key=None, timeout=30)

    client = crea_client(configurazione, attese=(0.5,), pausa=tempo.pausa, orologio=tempo.orologio)

    assert client._attese == (0.5,) and client._pausa == tempo.pausa
