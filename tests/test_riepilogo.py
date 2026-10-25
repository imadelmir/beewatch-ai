"""Test del riepilogo strutturato (M5-T3): estrazione, validazione, un solo tentativo correttivo."""

from __future__ import annotations

import json
import logging

import pytest
from llm_fake import LLMFinto

from beewatch.ai.riepilogo import (
    MESSAGGIO_NON_DISPONIBILE,
    Azione,
    Criticita,
    Riepilogo,
    RiepilogoNonValido,
    estrai_json,
    genera_riepilogo,
    parsa_riepilogo,
    valida_riepilogo,
)
from beewatch.exceptions import BeeWatchError, LLMError

VALIDO = {
    "stato_salute": "attenzione",
    "elementi_rilevati": ["regina vista", "covata compatta"],
    "criticita": [{"descrizione": "scorte scarse", "gravita": "media"}],
    "azioni_suggerite": [
        {"azione": "controllare le scorte", "priorita": "alta", "entro_giorni": 7}
    ],
    "confidenza": "media",
    "campi_non_deducibili": ["presenza di varroa"],
}


def json_valido(**modifiche) -> str:
    return json.dumps({**VALIDO, **modifiche}, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# estrai_json
# --------------------------------------------------------------------------- #


def test_json_pulito():
    assert estrai_json(json_valido()) == VALIDO


def test_recinto_di_codice_con_e_senza_lingua():
    assert estrai_json(f"```json\n{json_valido()}\n```") == VALIDO
    assert estrai_json(f"```\n{json_valido()}\n```") == VALIDO


def test_testo_prima_e_dopo_il_json():
    risposta = f"Ecco il riepilogo richiesto:\n{json_valido()}\nSpero sia utile!"
    assert estrai_json(risposta) == VALIDO


def test_graffe_nel_testo_prima_dell_oggetto_non_lo_nascondono():
    risposta = f"Nota {{sciame}} e {{altro: x}}. Risultato: {json_valido()}"
    assert estrai_json(risposta) == VALIDO


def test_con_due_oggetti_vince_quello_con_lo_schema():
    risposta = f'{{"esempio": 1}} {json_valido()}'
    assert estrai_json(risposta)["stato_salute"] == "attenzione"


def test_senza_stato_salute_si_prende_il_primo_oggetto():
    assert estrai_json('testo {"a": 1} {"b": 2}') == {"a": 1}


def test_le_graffe_dentro_una_stringa_non_ingannano():
    dati = {**VALIDO, "elementi_rilevati": ["scritta {strana} sul telaino"]}
    assert estrai_json(json.dumps(dati, ensure_ascii=False)) == dati


@pytest.mark.parametrize("meta", [0.3, 0.5, 0.9])
def test_json_troncato_e_un_errore_chiaro(meta):
    testo = json_valido()
    with pytest.raises(RiepilogoNonValido) as errore:
        estrai_json(testo[: int(len(testo) * meta)])
    assert "troncato" in errore.value.problemi[0]


@pytest.mark.parametrize("testo", ["", "   \n", None, 42, "Non ho capito la richiesta."])
def test_risposte_senza_json(testo):
    with pytest.raises(RiepilogoNonValido):
        estrai_json(testo)


def test_un_elenco_json_non_e_un_oggetto():
    with pytest.raises(RiepilogoNonValido):
        estrai_json('["a", "b"]')


# --------------------------------------------------------------------------- #
# valida_riepilogo
# --------------------------------------------------------------------------- #


def test_riepilogo_valido_completo():
    r = valida_riepilogo(VALIDO)
    assert r == Riepilogo(
        stato_salute="attenzione",
        elementi_rilevati=("regina vista", "covata compatta"),
        criticita=(Criticita("scorte scarse", "media"),),
        azioni_suggerite=(Azione("controllare le scorte", "alta", 7),),
        confidenza="media",
        campi_non_deducibili=("presenza di varroa",),
    )


def test_elenchi_vuoti_sono_validi():
    r = valida_riepilogo(
        {
            **VALIDO,
            "elementi_rilevati": [],
            "criticita": [],
            "azioni_suggerite": [],
            "campi_non_deducibili": [],
        }
    )
    assert r.criticita == () and r.azioni_suggerite == ()


def test_entro_giorni_puo_mancare_o_essere_null():
    senza = {**VALIDO, "azioni_suggerite": [{"azione": "guardare", "priorita": "bassa"}]}
    con_null = {
        **VALIDO,
        "azioni_suggerite": [{"azione": "guardare", "priorita": "bassa", "entro_giorni": None}],
    }
    assert valida_riepilogo(senza).azioni_suggerite[0].entro_giorni is None
    assert valida_riepilogo(con_null).azioni_suggerite[0].entro_giorni is None


def test_maiuscole_e_spazi_negli_enum_si_normalizzano():
    r = valida_riepilogo({**VALIDO, "stato_salute": " Critico ", "confidenza": "ALTA"})
    assert (r.stato_salute, r.confidenza) == ("critico", "alta")


def test_campi_in_piu_sono_ignorati():
    assert valida_riepilogo({**VALIDO, "commento": "extra"}).stato_salute == "attenzione"


@pytest.mark.parametrize("campo", list(VALIDO))
def test_ogni_campo_mancante_e_nominato(campo):
    dati = {k: v for k, v in VALIDO.items() if k != campo}
    with pytest.raises(RiepilogoNonValido) as errore:
        valida_riepilogo(dati)
    assert campo in errore.value.problemi[0]


def test_tutti_i_problemi_sono_elencati_non_solo_il_primo():
    dati = {**VALIDO, "stato_salute": "ottimo", "confidenza": 3, "elementi_rilevati": "regina"}
    with pytest.raises(RiepilogoNonValido) as errore:
        valida_riepilogo(dati)
    testo = " | ".join(errore.value.problemi)
    assert "stato_salute" in testo and "confidenza" in testo and "elementi_rilevati" in testo
    assert len(errore.value.problemi) == 3


@pytest.mark.parametrize(
    "modifica, atteso",
    [
        ({"stato_salute": "ottimo"}, "stato_salute"),
        ({"stato_salute": None}, "stato_salute"),
        ({"confidenza": "certa"}, "confidenza"),
        ({"elementi_rilevati": "una stringa"}, "elementi_rilevati"),
        ({"elementi_rilevati": [1, 2]}, "elementi_rilevati[0]"),
        ({"elementi_rilevati": ["ok", "  "]}, "elementi_rilevati[1]"),
        ({"campi_non_deducibili": {"a": 1}}, "campi_non_deducibili"),
        ({"criticita": ["scorte"]}, "criticita[0]"),
        ({"criticita": [{"descrizione": "x", "gravita": "enorme"}]}, "criticita[0].gravita"),
        ({"criticita": [{"gravita": "alta"}]}, "criticita[0].descrizione"),
        (
            {"azioni_suggerite": [{"azione": "x", "priorita": "urgentissima"}]},
            "azioni_suggerite[0].priorita",
        ),
        ({"azioni_suggerite": [{"priorita": "alta"}]}, "azioni_suggerite[0].azione"),
        (
            {"azioni_suggerite": [{"azione": "x", "priorita": "alta", "entro_giorni": "7"}]},
            "entro_giorni",
        ),
        (
            {"azioni_suggerite": [{"azione": "x", "priorita": "alta", "entro_giorni": 7.5}]},
            "entro_giorni",
        ),
        (
            {"azioni_suggerite": [{"azione": "x", "priorita": "alta", "entro_giorni": True}]},
            "entro_giorni",
        ),
        (
            {"azioni_suggerite": [{"azione": "x", "priorita": "alta", "entro_giorni": 0}]},
            "entro_giorni",
        ),
        (
            {"azioni_suggerite": [{"azione": "x", "priorita": "alta", "entro_giorni": 366}]},
            "entro_giorni",
        ),
        ({"azioni_suggerite": "subito"}, "azioni_suggerite"),
        ({"azioni_suggerite": ["controllare"]}, "azioni_suggerite[0]"),
    ],
)
def test_valori_di_tipo_o_valore_sbagliato(modifica, atteso):
    with pytest.raises(RiepilogoNonValido) as errore:
        valida_riepilogo({**VALIDO, **modifica})
    assert any(atteso in p for p in errore.value.problemi), errore.value.problemi


@pytest.mark.parametrize("dati", [None, [], "testo", 5, [VALIDO]])
def test_non_un_oggetto(dati):
    with pytest.raises(RiepilogoNonValido):
        valida_riepilogo(dati)


def test_i_limiti_di_lunghezza_e_numero():
    troppo_lunga = "x" * 1001
    with pytest.raises(RiepilogoNonValido, match="oltre 1000"):
        valida_riepilogo({**VALIDO, "elementi_rilevati": [troppo_lunga]})
    with pytest.raises(RiepilogoNonValido, match="più di 20"):
        valida_riepilogo({**VALIDO, "elementi_rilevati": ["a"] * 21})
    assert (
        len(valida_riepilogo({**VALIDO, "elementi_rilevati": ["a"] * 20}).elementi_rilevati) == 20
    )
    assert valida_riepilogo({**VALIDO, "elementi_rilevati": ["x" * 1000]})


def test_gli_estremi_dei_giorni_sono_validi():
    for giorni in (1, 365):
        voce = {"azione": "x", "priorita": "alta", "entro_giorni": giorni}
        assert (
            valida_riepilogo({**VALIDO, "azioni_suggerite": [voce]})
            .azioni_suggerite[0]
            .entro_giorni
            == giorni
        )


def test_ogni_stato_e_ogni_confidenza_ammessi():
    for stato in ("buono", "attenzione", "critico", "non_determinabile"):
        for conf in ("alta", "media", "bassa"):
            assert valida_riepilogo({**VALIDO, "stato_salute": stato, "confidenza": conf})


def test_riepilogo_non_valido_e_un_llm_error_e_un_beewatch_error():
    with pytest.raises(LLMError):
        valida_riepilogo({})
    with pytest.raises(BeeWatchError):
        valida_riepilogo({})


def test_a_dict_e_a_json_ripercorrono_lo_schema():
    r = valida_riepilogo(VALIDO)
    assert r.a_dict() == VALIDO
    assert valida_riepilogo(json.loads(r.a_json())) == r
    accentato = valida_riepilogo({**VALIDO, "elementi_rilevati": ["è più forte"]})
    assert "è più forte" in accentato.a_json()  # niente \u00e8 nel database


def test_parsa_riepilogo_unisce_estrazione_e_validazione():
    assert parsa_riepilogo(f"```json\n{json_valido()}\n```").confidenza == "media"
    with pytest.raises(RiepilogoNonValido):
        parsa_riepilogo(json_valido()[:-10])


def test_il_fallback_e_onesto():
    r = Riepilogo.non_disponibile()
    assert r.stato_salute == "non_determinabile"
    assert r.confidenza == "bassa"
    assert r.criticita == () and r.azioni_suggerite == () and r.elementi_rilevati == ()
    assert r.campi_non_deducibili == (MESSAGGIO_NON_DISPONIBILE,)
    # è esso stesso conforme allo schema
    assert valida_riepilogo(json.loads(r.a_json())) == r


# --------------------------------------------------------------------------- #
# genera_riepilogo
# --------------------------------------------------------------------------- #


def test_risposta_valida_una_sola_chiamata():
    client = LLMFinto([json_valido()])
    esito = genera_riepilogo(client, "sistema", "utente")
    assert esito.valido and not esito.corretto_al_secondo_tentativo
    assert len(client.chiamate) == 1 and len(esito.risposte) == 1
    assert esito.riepilogo.stato_salute == "attenzione"
    assert esito.problemi == ()


def test_si_chiede_json_e_si_passano_i_parametri():
    client = LLMFinto([json_valido()])
    genera_riepilogo(client, "S", "U", temperatura=0.0, massimo_token=300)
    c = client.chiamate[0]
    assert (c.sistema, c.utente, c.temperatura, c.massimo_token, c.risposta_json) == (
        "S",
        "U",
        0.0,
        300,
        True,
    )


def test_json_troncato_poi_corretto_al_secondo_tentativo():
    troncato = json_valido()[:60]
    client = LLMFinto([troncato, json_valido()])
    esito = genera_riepilogo(client, "S", "nota dell'ispezione")
    assert esito.valido and esito.corretto_al_secondo_tentativo
    assert len(client.chiamate) == 2
    correttivo = client.chiamate[1]
    assert correttivo.sistema == "S"
    assert correttivo.utente.startswith("nota dell'ispezione")
    assert troncato in correttivo.utente  # il modello rivede la propria risposta
    assert "troncato" in correttivo.utente  # e cosa non andava
    assert "UN SOLO oggetto JSON" in correttivo.utente
    assert correttivo.risposta_json is True


def test_campi_mancanti_poi_corretto_nominando_i_campi():
    incompleto = json.dumps({"stato_salute": "buono"})
    client = LLMFinto([incompleto, json_valido()])
    esito = genera_riepilogo(client, "S", "U")
    assert esito.valido
    assert "confidenza" in client.chiamate[1].utente and "criticita" in client.chiamate[1].utente


def test_testo_attorno_al_json_non_richiede_il_secondo_tentativo():
    client = LLMFinto([f"Certo! {json_valido()} Fammi sapere."])
    assert genera_riepilogo(client, "S", "U").valido
    assert len(client.chiamate) == 1


def test_due_fallimenti_danno_il_fallback_senza_terza_chiamata():
    client = LLMFinto(["non json", '{"stato_salute": "ottimo"}', json_valido()])
    esito = genera_riepilogo(client, "S", "U")
    assert not esito.valido
    assert esito.riepilogo == Riepilogo.non_disponibile()
    assert len(client.chiamate) == 2  # mai una terza
    assert len(esito.risposte) == 2
    assert esito.problemi  # dell'ULTIMA risposta
    assert any("stato_salute" in p for p in esito.problemi)


def test_nessuna_eccezione_per_nessuna_risposta_malformata():
    strane = [
        "",
        "   ",
        "{",
        "}",
        "{{{{",
        "[]",
        "null",
        "42",
        "```json\n```",
        '{"stato_salute": ',
        "\x00\x01",
        "è" * 5000,
        json.dumps(VALIDO)[:-1],
        '{"a": ' * 100,
    ]
    for risposta in strane:
        esito = genera_riepilogo(LLMFinto([risposta]), "S", "U")
        assert esito.valido is False
        assert esito.riepilogo == Riepilogo.non_disponibile()


def test_un_errore_del_provider_non_e_un_problema_di_formato():
    client = LLMFinto([LLMError("Ollama non risponde")])
    with pytest.raises(LLMError, match="Ollama non risponde"):
        genera_riepilogo(client, "S", "U")
    assert len(client.chiamate) == 1


def test_errore_del_provider_durante_il_tentativo_correttivo_si_propaga():
    client = LLMFinto(["non json", LLMError("429")])
    with pytest.raises(LLMError, match="429") as errore:
        genera_riepilogo(client, "S", "U")
    assert not isinstance(errore.value, RiepilogoNonValido)


def test_durata_e_token_sono_la_somma_delle_chiamate():
    client = LLMFinto(["no", json_valido()], token=(100, 50))
    esito = genera_riepilogo(client, "S", "U")
    assert esito.token_prompt == 200 and esito.token_risposta == 100
    assert esito.durata_ms == sum(r.durata_ms for r in esito.risposte)


def test_token_sconosciuti_restano_sconosciuti():
    esito = genera_riepilogo(LLMFinto([json_valido()], token=None), "S", "U")
    assert esito.token_prompt is None and esito.token_risposta is None


def test_il_log_dice_perche_ma_non_riporta_la_risposta(caplog):
    segreto = "NOTA-RISERVATA-12345"
    client = LLMFinto([f'{{"stato_salute": "ottimo", "x": "{segreto}"}}', "{"])
    with caplog.at_level(logging.INFO):
        genera_riepilogo(client, "S", "U")
    testo = caplog.text
    assert "non valido al tentativo 1" in testo and "non valido al tentativo 2" in testo
    assert "stato_salute" in testo
    assert segreto not in testo


def test_il_correttivo_tronca_le_risposte_enormi():
    enorme = "x" * 10_000
    client = LLMFinto([enorme, json_valido()])
    genera_riepilogo(client, "S", "U")
    assert len(client.chiamate[1].utente) < 3000
