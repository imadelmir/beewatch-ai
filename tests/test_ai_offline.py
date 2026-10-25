"""La componente AI intera, senza rete e senza chiave API (M5-T6).

Ogni test usa il client VERO (`ClientOllama`, `ClientOpenRouter`) contro un server HTTP locale che
risponde con le risposte di `tests/fixtures/llm/` (scritte a mano nel formato documentato dei
provider: vedi il README di quella cartella). Quindi si attraversa tutto: richiesta HTTP, nuovi
tentativi, lettura della risposta, parser, servizio. Il blocco della rete (`conftest.py`) garantisce
che niente esca dal computer.

Cosa NON prova: che Ollama o OpenRouter rispondano davvero così. Lo prova `scripts/verifica_llm.py`
con un provider vero (issue di M5-T1).
"""

from __future__ import annotations

import json
import logging
import re

import pytest
from dati_finti import (
    ALVEARE,
    STORIA,
    AlveariFinti,
    ApiariFinti,
    IspezioniFinte,
    RaccoltiFinti,
    RiepiloghiFinti,
)
from llm_registrate import CARTELLA, accoda, carica, contenuto, tutti
from llm_server import ServerFinto, porta_chiusa

from beewatch.ai.llm import ClientOllama, ClientOpenRouter
from beewatch.ai.riepilogo import Riepilogo, RiepilogoNonValido, genera_riepilogo, parsa_riepilogo
from beewatch.exceptions import LLMError
from beewatch.services import Servizi

CHIAVE = "sk-or-v1-CHIAVE-SEGRETA-DI-PROVA"
SEGRETO_NOTA = "NOTA-SEGRETA-777"


def ollama(server: ServerFinto, **politica) -> ClientOllama:
    politica.setdefault("attese", ())
    return ClientOllama("llama3.1:8b", 5, server.url, **politica)


def openrouter(server: ServerFinto, **politica) -> ClientOpenRouter:
    politica.setdefault("attese", ())
    return ClientOpenRouter("meta-llama/llama-3.1-8b-instruct", 5, CHIAVE, server.url, **politica)


@pytest.fixture
def server():
    with ServerFinto() as s:
        yield s


# --------------------------------------------------------------------------- #
# Le fixture stesse
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("nome", tutti())
def test_ogni_fixture_ha_la_forma_attesa(nome):
    voce = carica(nome)
    assert set(voce) == {"descrizione", "stato", "intestazioni", "corpo"}
    assert voce["descrizione"].strip()
    assert isinstance(voce["stato"], int) and 100 <= voce["stato"] <= 599
    assert isinstance(voce["intestazioni"], dict)
    assert nome.split("_")[0] in {"ollama", "openrouter"}


def test_il_readme_elenca_tutti_i_file_e_dice_che_non_sono_registrazioni_vere():
    readme = (CARTELLA / "README.md").read_text(encoding="utf-8")
    for nome in tutti():
        assert f"`{nome}`" in readme, nome
    assert "Non sono registrazioni di chiamate vere" in readme


# --------------------------------------------------------------------------- #
# Risposte buone
# --------------------------------------------------------------------------- #


def test_ollama_valido_dalla_richiesta_al_riepilogo(server):
    accoda(server, "ollama_valido")
    esito = genera_riepilogo(ollama(server), "sistema", "utente")

    assert esito.valido and isinstance(esito.riepilogo, Riepilogo)
    assert esito.riepilogo.stato_salute == "attenzione" and esito.riepilogo.confidenza == "media"
    assert (esito.token_prompt, esito.token_risposta) == (812, 164)
    assert esito.risposte[0].provider == "ollama" and esito.risposte[0].modello == "llama3.1:8b"
    richiesta = server.richieste[0]
    assert richiesta.percorso == "/api/chat"
    assert richiesta.json["format"] == "json" and richiesta.json["stream"] is False


def test_openrouter_valido_dalla_richiesta_al_riepilogo(server):
    accoda(server, "openrouter_valido")
    esito = genera_riepilogo(openrouter(server), "sistema", "utente")

    assert esito.valido
    assert (esito.token_prompt, esito.token_risposta) == (815, 170)
    assert esito.risposte[0].provider == "openrouter"
    richiesta = server.richieste[0]
    assert richiesta.percorso == "/chat/completions"
    assert richiesta.intestazioni["authorization"] == f"Bearer {CHIAVE}"
    assert richiesta.json["response_format"] == {"type": "json_object"}


def test_il_riepilogo_valido_dei_due_provider_e_lo_stesso():
    assert parsa_riepilogo(contenuto("ollama_valido")) == parsa_riepilogo(
        contenuto("openrouter_valido")
    )


def test_testo_e_recinto_attorno_al_json_non_servono_di_un_secondo_tentativo(server):
    accoda(server, "ollama_con_testo_e_recinto")
    esito = genera_riepilogo(ollama(server), "sistema", "utente")
    assert esito.valido and len(server.richieste) == 1 and not esito.corretto_al_secondo_tentativo


# --------------------------------------------------------------------------- #
# JSON rotto: un solo tentativo correttivo, poi il fallback onesto
# --------------------------------------------------------------------------- #


def test_json_troncato_poi_corretto_nel_secondo_tentativo(server):
    accoda(server, "ollama_json_troncato", "ollama_valido")
    esito = genera_riepilogo(ollama(server), "sistema", "nota dell'apicoltore")

    assert esito.valido and esito.corretto_al_secondo_tentativo
    assert len(server.richieste) == 2
    secondo = server.richieste[1].json["messages"][1]["content"]
    assert secondo.startswith("nota dell'apicoltore") and "troncato" in secondo
    assert (esito.token_prompt, esito.token_risposta) == (1624, 328)  # le due chiamate sommate


@pytest.mark.parametrize(
    "scenario",
    [
        "ollama_json_troncato",
        "ollama_campi_mancanti",
        "ollama_stato_non_ammesso",
        "ollama_solo_testo",
    ],
)
def test_risposta_inutilizzabile_due_volte_da_il_fallback_e_non_un_crash(server, scenario):
    accoda(server, scenario, scenario, "ollama_valido")  # il terzo non deve mai essere chiesto
    esito = genera_riepilogo(ollama(server), "sistema", "utente")

    assert not esito.valido and esito.riepilogo == Riepilogo.non_disponibile()
    assert len(server.richieste) == 2
    assert esito.problemi


def test_i_campi_mancanti_sono_nominati_nel_messaggio_correttivo(server):
    accoda(server, "ollama_campi_mancanti", "ollama_valido")
    genera_riepilogo(ollama(server), "sistema", "utente")
    correttivo = server.richieste[1].json["messages"][1]["content"]
    for campo in ("elementi_rilevati", "criticita", "azioni_suggerite", "campi_non_deducibili"):
        assert campo in correttivo


def test_un_riepilogo_non_valido_non_si_scambia_per_un_errore_del_provider():
    with pytest.raises(RiepilogoNonValido):
        parsa_riepilogo(contenuto("ollama_stato_non_ammesso"))


# --------------------------------------------------------------------------- #
# Errori del provider (HTTP): 429, 5xx, 401, 404, formato
# --------------------------------------------------------------------------- #


def test_429_con_retry_after_si_aspetta_e_poi_riesce(server):
    accoda(server, "openrouter_429", "openrouter_valido")
    attese: list[float] = []
    client = openrouter(server, attese=(1.0, 2.0, 4.0), pausa=attese.append)

    esito = genera_riepilogo(client, "sistema", "utente")

    assert esito.valido and esito.risposte[0].tentativi == 2
    assert attese == [2.0]  # il Retry-After (2 s) è più lungo del primo backoff (1 s)
    assert len(server.richieste) == 2


def test_429_sempre_finisce_in_un_llm_error_chiaro_dopo_quattro_tentativi(server):
    accoda(server, "openrouter_429")  # l'ultima risposta si ripete
    attese: list[float] = []
    client = openrouter(server, attese=(1.0, 2.0, 4.0), pausa=attese.append)

    with pytest.raises(LLMError, match=r"limite di richieste.*dopo 4 tentativi"):
        genera_riepilogo(client, "sistema", "utente")

    assert len(server.richieste) == 4
    assert attese == [2.0, 2.0, 4.0]


def test_503_poi_successo(server):
    accoda(server, "openrouter_503", "openrouter_valido")
    attese: list[float] = []
    esito = genera_riepilogo(
        openrouter(server, attese=(1.0, 2.0, 4.0), pausa=attese.append), "sistema", "utente"
    )
    assert esito.valido and attese == [1.0]


def test_ollama_500_sempre_e_un_errore_dopo_i_tentativi(server):
    accoda(server, "ollama_errore_500")
    client = ollama(server, attese=(1.0, 2.0, 4.0), pausa=lambda s: None)
    with pytest.raises(LLMError, match=r"errore interno.*dopo 4 tentativi"):
        genera_riepilogo(client, "sistema", "utente")
    assert len(server.richieste) == 4


def test_401_e_permanente_un_solo_tentativo_e_si_dice_di_controllare_la_chiave(server):
    accoda(server, "openrouter_401")
    attese: list[float] = []
    client = openrouter(server, attese=(1.0, 2.0, 4.0), pausa=attese.append)

    with pytest.raises(LLMError, match="LLM_API_KEY") as errore:
        genera_riepilogo(client, "sistema", "utente")

    assert len(server.richieste) == 1 and attese == []
    assert CHIAVE not in str(errore.value)


def test_ollama_senza_il_modello_dice_come_scaricarlo_e_non_riprova(server):
    accoda(server, "ollama_modello_non_trovato")
    with pytest.raises(LLMError, match="ollama pull llama3.1:8b"):
        genera_riepilogo(ollama(server, attese=(1.0, 2.0, 4.0), pausa=lambda s: None), "s", "u")
    assert len(server.richieste) == 1


@pytest.mark.parametrize(
    "scenario, atteso",
    [
        ("openrouter_200_con_errore", "Upstream timeout"),
        ("openrouter_formato_inatteso", "formato inatteso"),
    ],
)
def test_risposte_200_inutilizzabili_sono_llm_error_senza_nuovi_tentativi(server, scenario, atteso):
    accoda(server, scenario)
    with pytest.raises(LLMError, match=atteso):
        genera_riepilogo(openrouter(server, attese=(1.0,), pausa=lambda s: None), "s", "u")
    assert len(server.richieste) == 1


def test_ollama_con_contenuto_vuoto_e_un_errore_del_provider_non_un_problema_di_formato(server):
    accoda(server, "ollama_senza_testo")
    with pytest.raises(LLMError, match="senza testo") as errore:
        genera_riepilogo(ollama(server), "sistema", "utente")
    assert not isinstance(errore.value, RiepilogoNonValido)
    assert len(server.richieste) == 1  # il correttivo è per il formato, non per il provider


def test_timeout_e_un_llm_error_che_dice_quanto_si_e_aspettato(server):
    server.rispondi(200, {"message": {"content": "tardi"}}, ritardo=1.6)
    client = ClientOllama("llama3.1:8b", 1, server.url, attese=())
    with pytest.raises(LLMError, match="non ha risposto entro 1 secondi"):
        genera_riepilogo(client, "sistema", "utente")


def test_provider_spento_e_un_llm_error_con_il_rimedio():
    client = ClientOllama("llama3.1:8b", 5, porta_chiusa(), attese=())
    with pytest.raises(LLMError, match="ollama serve"):
        genera_riepilogo(client, "sistema", "utente")


def test_corpo_non_json_con_stato_200_e_un_llm_error(server):
    server.rispondi(200, "<html>Bad gateway</html>")
    with pytest.raises(LLMError, match="non è JSON"):
        genera_riepilogo(ollama(server), "sistema", "utente")


# --------------------------------------------------------------------------- #
# Dati sensibili
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "scenari",
    [
        ("openrouter_401",),
        ("openrouter_429",),
        ("openrouter_503",),
        ("openrouter_200_con_errore",),
        ("openrouter_valido",),
    ],
)
def test_ne_la_chiave_ne_il_testo_dellutente_finiscono_nei_log_o_negli_errori(
    server, caplog, scenari
):
    accoda(server, *scenari)
    client = openrouter(server, attese=(1.0, 2.0, 4.0), pausa=lambda s: None)
    messaggio = ""
    with caplog.at_level(logging.DEBUG):
        try:
            genera_riepilogo(client, "sistema", f"nota con {SEGRETO_NOTA}")
        except LLMError as errore:
            messaggio = str(errore)
    assert CHIAVE not in caplog.text and CHIAVE not in messaggio
    assert SEGRETO_NOTA not in caplog.text and SEGRETO_NOTA not in messaggio


# --------------------------------------------------------------------------- #
# Il servizio, con il client vero e il server locale
# --------------------------------------------------------------------------- #


def servizio(client, riepiloghi: RiepiloghiFinti | None = None):
    riepiloghi = riepiloghi or RiepiloghiFinti()
    return (
        Servizi(
            None,
            crea_llm=lambda: client,
            ispezioni=IspezioniFinte(STORIA),
            alveari=AlveariFinti(ALVEARE),
            apiari=ApiariFinti(),
            raccolti=RaccoltiFinti([]),
            riepiloghi=riepiloghi,
        ),
        riepiloghi,
    )


def test_servizio_con_ollama_salva_il_riepilogo_con_la_tracciabilita(server):
    accoda(server, "ollama_valido")
    s, riepiloghi = servizio(ollama(server))

    r = s.genera_riepilogo_ispezione(1, 12)

    assert r.valido and r.salvato and r.in_locale is True
    [salvato] = riepiloghi.salvati
    assert (salvato["provider"], salvato["modello"]) == ("ollama", "llama3.1:8b")
    assert (salvato["token_prompt"], salvato["token_risposta"], salvato["tentativi"]) == (
        812,
        164,
        1,
    )
    assert salvato["riepilogo"]["stato_salute"] == "attenzione"
    inviata = server.richieste[0].json["messages"][1]["content"]
    assert "Codice: A3" in inviata and SEGRETO_NOTA in inviata  # la nota arriva al modello


def test_servizio_con_openrouter_segnala_che_le_note_escono_dal_computer(server):
    accoda(server, "openrouter_valido")
    s, _ = servizio(openrouter(server))
    assert s.genera_riepilogo_ispezione(1, 12).in_locale is False


def test_servizio_json_troncato_poi_corretto_somma_i_token_e_conta_due_tentativi(server):
    accoda(server, "ollama_json_troncato", "ollama_valido")
    s, riepiloghi = servizio(ollama(server))

    r = s.genera_riepilogo_ispezione(1, 12)

    assert r.valido and r.tentativi == 2 and (r.token_prompt, r.token_risposta) == (1624, 328)
    assert riepiloghi.salvati[0]["tentativi"] == 2


def test_servizio_json_rotto_due_volte_non_salva_e_non_solleva(server):
    accoda(server, "ollama_json_troncato")
    s, riepiloghi = servizio(ollama(server))

    r = s.genera_riepilogo_ispezione(1, 12)

    assert not r.valido and not r.salvato and "non ha prodotto" in r.messaggio
    assert riepiloghi.salvati == []


@pytest.mark.parametrize(
    "scenario, costruisci",
    [
        ("openrouter_429", openrouter),
        ("openrouter_401", openrouter),
        ("ollama_errore_500", ollama),
        ("ollama_modello_non_trovato", ollama),
    ],
)
def test_servizio_con_un_provider_che_fallisce_propaga_llm_error_e_non_salva(
    server, scenario, costruisci
):
    accoda(server, scenario)
    s, riepiloghi = servizio(costruisci(server, attese=(1.0, 2.0, 4.0), pausa=lambda s: None))

    with pytest.raises(LLMError):
        s.genera_riepilogo_ispezione(1, 12)
    assert riepiloghi.salvati == []


def test_servizio_con_provider_spento_dice_come_avviarlo():
    client = ClientOllama("llama3.1:8b", 5, porta_chiusa(), attese=())
    s, riepiloghi = servizio(client)
    with pytest.raises(LLMError, match="ollama serve"):
        s.genera_riepilogo_ispezione(1, 12)
    assert riepiloghi.salvati == []


def test_il_riepilogo_salvato_e_json_pulito_e_senza_il_testo_grezzo_del_modello(server):
    accoda(server, "ollama_con_testo_e_recinto")
    s, riepiloghi = servizio(ollama(server))
    s.genera_riepilogo_ispezione(1, 12)
    salvato = riepiloghi.salvati[0]["riepilogo"]
    json.dumps(salvato)  # serializzabile
    assert "Ecco il riepilogo" not in json.dumps(salvato)  # le frasi attorno non si salvano
    assert re.fullmatch(r"[a-z_]+", salvato["stato_salute"])
