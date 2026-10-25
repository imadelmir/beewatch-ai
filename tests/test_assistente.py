"""Test dell'assistente e del servizio dei riepiloghi (M5-T5), tutti con un LLM finto.

Unitari: repository e modello di linguaggio finti, nessun database, nessuna rete, nessuna chiave
(e nessuna lettura del `.env`). Si verifica che il contesto sia quello giusto e solo quello,
che finisca nel log, che il riepilogo valido si salvi con tutta la tracciabilità e che ogni
guasto (provider, risposta malformata, database) abbia la sua conseguenza. La parte con MySQL è in
`test_riepiloghi_repository.py`.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal

import pytest
from llm_fake import LLMFinto

from beewatch.ai.assistant import (
    LUNGHEZZA_NOTA_PRECEDENTE,
    MAX_PRECEDENTI,
    MAX_RACCOLTI,
    AssistenteIspezioni,
    ContestoIspezione,
    sezioni_del_contesto,
)
from beewatch.ai.llm import ClientOllama, ClientOpenRouter
from beewatch.ai.prompt import versione_prompt
from beewatch.ai.riepilogo import MESSAGGIO_NON_DISPONIBILE
from beewatch.exceptions import ConfigError, DatabaseError, LLMError, ValidationError
from beewatch.models import (
    Alveare,
    Apiario,
    Ispezione,
    LivelloRischio,
    Raccolto,
    StatoAlveare,
    TipoMiele,
)
from beewatch.services import RiepilogoGenerato, Servizi

RISPOSTA = json.dumps(
    {
        "stato_salute": "attenzione",
        "elementi_rilevati": ["covata a macchie"],
        "criticita": [{"descrizione": "covata a macchie", "gravita": "media"}],
        "azioni_suggerite": [
            {"azione": "ricontrollare tra una settimana", "priorita": "media", "entro_giorni": 7}
        ],
        "confidenza": "media",
        "campi_non_deducibili": ["causa della covata a macchie"],
    },
    ensure_ascii=False,
)
NOTA = "Covata a macchie su due telaini, regina vista. NOTA-SEGRETA-777"


def ispezione(id_: int, giorno: date, note: str | None = "una nota", **extra) -> Ispezione:
    base = {
        "alveare_id": 5,
        "data_ispezione": giorno,
        "livello_rischio": LivelloRischio.MEDIO,
        "peso_kg": Decimal("23.70"),
        "telaini_covata": 4,
        "telaini_scorte": 3,
        "regina_vista": True,
        "sciamatura": False,
    }
    return Ispezione(id=id_, note=note, **{**base, **extra})


ALVEARE = Alveare(
    apiario_id=2,
    codice="A3",
    stato=StatoAlveare.IN_OSSERVAZIONE,
    data_installazione=date(2024, 3, 1),
    anno_regina=2024,
    id=5,
)
APIARIO = Apiario(
    utente_id=1,
    nome="Collina",
    localita="Frazione Segreta",
    latitudine=Decimal("45.123456"),
    longitudine=Decimal("9.654321"),
    id=2,
)


def raccolto(id_: int, giorno: date, kg: str = "10.0", alveare_id=None) -> Raccolto:
    return Raccolto(
        apiario_id=2,
        tipo_miele=TipoMiele.ACACIA,
        data_raccolto=giorno,
        quantita_kg=Decimal(kg),
        alveare_id=alveare_id,
        id=id_,
    )


def contesto(**extra) -> ContestoIspezione:
    base = {
        "apiario": "Collina",
        "alveare": ALVEARE,
        "ispezione": ispezione(12, date(2026, 5, 16), NOTA),
        "precedenti": (),
        "raccolti": (),
    }
    return ContestoIspezione(**{**base, **extra})


# --------------------------------------------------------------------------- #
# Il contesto
# --------------------------------------------------------------------------- #


def test_le_sezioni_descrivono_alveare_e_ispezione_in_italiano():
    s = sezioni_del_contesto(contesto())
    assert "Apiario: Collina" in s["alveare"] and "Codice: A3" in s["alveare"]
    assert "Stato registrato: in osservazione" in s["alveare"]
    assert "Anno della regina: 2024" in s["alveare"]
    assert "Data: 2026-05-16" in s["ispezione"]
    assert "Rischio valutato dall'apicoltore: medio" in s["ispezione"]
    assert "Peso: 23,70 kg" in s["ispezione"]
    assert "Regina vista: sì" in s["ispezione"] and "Sciamatura: no" in s["ispezione"]
    assert s["storico"] == "" and s["raccolti"] == ""  # il prompt li farà «(nessun dato)»


def test_i_valori_mancanti_si_dicono_mancanti_non_zero():
    spoglia = ispezione(
        1, date(2026, 5, 16), peso_kg=None, telaini_covata=None, telaini_scorte=None
    )
    alveare = Alveare(apiario_id=2, codice="B1", stato=StatoAlveare.IN_SALUTE, id=6)
    s = sezioni_del_contesto(contesto(alveare=alveare, ispezione=spoglia))
    assert "Peso: non registrato" in s["ispezione"]
    assert "Telaini di covata: non registrato" in s["ispezione"]
    assert "Installato il: non registrato" in s["alveare"]
    assert "Anno della regina: non registrato" in s["alveare"]


def test_coordinate_e_localita_non_entrano_nel_contesto_ne_nel_prompt():
    # Il `ContestoIspezione` riceve solo il nome dell'apiario: l'oggetto `Apiario` non passa di qui.
    richiesta_finta = LLMFinto([RISPOSTA])
    AssistenteIspezioni(richiesta_finta).riassumi(contesto())
    inviato = richiesta_finta.chiamate[0].sistema + richiesta_finta.chiamate[0].utente
    for vietato in ("45.123456", "9.654321", "Frazione Segreta", "latitudine", "longitudine"):
        assert vietato not in inviato
    assert "Collina" in inviato


def test_lo_storico_ha_al_massimo_tre_ispezioni_con_le_note_accorciate():
    lunga = "parola " * 100
    precedenti = tuple(ispezione(i, date(2026, 4, i), lunga) for i in range(1, 6))
    s = sezioni_del_contesto(contesto(precedenti=precedenti))
    righe = s["storico"].splitlines()
    assert len(righe) == MAX_PRECEDENTI == 3
    assert righe[0].startswith("- 2026-04-01")  # l'ordine è quello ricevuto (dal più recente)
    assert "…" in righe[0] and len(righe[0]) < 220 + LUNGHEZZA_NOTA_PRECEDENTE


def test_una_nota_precedente_assente_non_lascia_note_vuote():
    s = sezioni_del_contesto(contesto(precedenti=(ispezione(1, date(2026, 4, 1), None),)))
    assert "note:" not in s["storico"]


def test_i_raccolti_sono_al_massimo_cinque():
    raccolti = tuple(raccolto(i, date(2025, 1, i)) for i in range(1, 9))
    s = sezioni_del_contesto(contesto(raccolti=raccolti))
    assert len(s["raccolti"].splitlines()) == MAX_RACCOLTI == 5
    assert "- 2025-01-01: miele acacia, 10,0 kg" in s["raccolti"]


def test_le_previsioni_di_produzione_non_entrano_nel_prompt():
    inviato = json.dumps(sezioni_del_contesto(contesto()), ensure_ascii=False).lower()
    assert "previsione" not in inviato and "stima" not in inviato


# --------------------------------------------------------------------------- #
# AssistenteIspezioni
# --------------------------------------------------------------------------- #


def test_il_riepilogo_valido_arriva_con_le_risposte_del_modello():
    client = LLMFinto([RISPOSTA], modello="m-prova")
    esito = AssistenteIspezioni(client).riassumi(contesto())
    assert esito.valido and esito.riepilogo.stato_salute == "attenzione"
    assert esito.risposte[0].modello == "m-prova"
    assert client.chiamate[0].risposta_json is True


def test_la_richiesta_contiene_i_dati_e_la_nota_dentro_il_blocco():
    client = LLMFinto([RISPOSTA])
    AssistenteIspezioni(client).riassumi(
        contesto(
            precedenti=(ispezione(3, date(2026, 3, 28), "Invernamento riuscito"),),
            raccolti=(raccolto(1, date(2025, 5, 28), "34.5"),),
        )
    )
    richiesta = client.chiamate[0].utente
    assert "Codice: A3" in richiesta and "Data: 2026-05-16" in richiesta
    assert "2026-03-28" in richiesta and "Invernamento riuscito" in richiesta
    assert "34,5 kg" in richiesta
    assert f"<<<NOTE\n{NOTA}\nFINE NOTE>>>" in richiesta
    assert client.chiamate[0].sistema.startswith("# Ruolo")


def test_un_valore_assente_diventa_nessun_dato_nel_prompt():
    client = LLMFinto([RISPOSTA])
    AssistenteIspezioni(client).riassumi(contesto())
    assert client.chiamate[0].utente.count("(nessun dato)") == 2  # storico e raccolti


def test_il_contesto_e_visibile_nei_log_ma_la_nota_solo_in_debug(caplog):
    client = LLMFinto([RISPOSTA])
    with caplog.at_level(logging.INFO):
        AssistenteIspezioni(client).riassumi(
            contesto(precedenti=(ispezione(3, date(2026, 3, 28), "Invernamento riuscito"),))
        )
    info = caplog.text
    assert "ispezione 12" in info and "alveare A3" in info and f"prompt {versione_prompt()}" in info
    assert "provider finto" in info
    assert "[alveare]" in info and "Codice: A3" in info
    assert "[ispezione]" in info and "Peso: 23,70 kg" in info
    assert "[storico]" in info and "2026-03-28" in info
    assert "[raccolti]" in info
    assert f"nota di {len(NOTA)} caratteri" in info  # la lunghezza sì
    assert "NOTA-SEGRETA-777" not in info  # il testo no

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        AssistenteIspezioni(LLMFinto([RISPOSTA])).riassumi(contesto())
    assert "NOTA-SEGRETA-777" in caplog.text  # a DEBUG, la richiesta completa


def test_in_locale_dipende_dal_provider():
    assert AssistenteIspezioni(ClientOllama("m", 5)).in_locale is True
    assert AssistenteIspezioni(ClientOpenRouter("m", 5, api_key="k")).in_locale is False
    assert AssistenteIspezioni(LLMFinto([RISPOSTA])).in_locale is True


def test_un_errore_del_provider_si_propaga():
    with pytest.raises(LLMError, match="spento"):
        AssistenteIspezioni(LLMFinto([LLMError("Ollama spento")])).riassumi(contesto())


def test_una_risposta_malformata_da_il_fallback_e_non_unaltra_eccezione():
    esito = AssistenteIspezioni(LLMFinto(["boh", "{"])).riassumi(contesto())
    assert not esito.valido
    assert esito.riepilogo.campi_non_deducibili == (MESSAGGIO_NON_DISPONIBILE,)


# --------------------------------------------------------------------------- #
# Servizi.genera_riepilogo_ispezione (repository finti)
# --------------------------------------------------------------------------- #


class IspezioniFinte:
    def __init__(self, elenco: list[Ispezione]):
        self.elenco = elenco
        self.richieste: list[tuple] = []

    def trova(self, utente_id, ispezione_id):
        self.richieste.append(("trova", utente_id, ispezione_id))
        return next((i for i in self.elenco if i.id == ispezione_id), None)

    def ispezioni_per_alveare(self, utente_id, alveare_id):
        self.richieste.append(("per_alveare", utente_id, alveare_id))
        return sorted(
            (i for i in self.elenco if i.alveare_id == alveare_id),
            key=lambda i: (i.data_ispezione, i.id),
            reverse=True,
        )


class AlveariFinti:
    def __init__(self, alveare=ALVEARE):
        self.alveare = alveare

    def trova(self, utente_id, alveare_id):
        return self.alveare if self.alveare and self.alveare.id == alveare_id else None


class ApiariFinti:
    def __init__(self, apiario=APIARIO):
        self.apiario = apiario

    def trova(self, utente_id, apiario_id):
        return self.apiario


class RaccoltiFinti:
    def __init__(self, elenco: list[Raccolto]):
        self.elenco = elenco

    def per_apiario(self, utente_id, apiario_id):
        return sorted(self.elenco, key=lambda r: (r.data_raccolto, r.id), reverse=True)


class RiepiloghiFinti:
    def __init__(self, errore: Exception | None = None):
        self.salvati: list[dict] = []
        self.errore = errore

    def salva(self, utente_id, ispezione_id, **campi):
        if self.errore:
            raise self.errore
        self.salvati.append({"utente_id": utente_id, "ispezione_id": ispezione_id, **campi})
        return 100 + len(self.salvati)

    def ultimo(self, utente_id, ispezione_id):
        return {"id": 101, "chiesto": (utente_id, ispezione_id)}


STORIA = [
    ispezione(10, date(2026, 3, 28), "Invernamento riuscito"),
    ispezione(11, date(2026, 4, 20), "Ripresa regolare"),
    ispezione(12, date(2026, 5, 16), NOTA),
    ispezione(13, date(2026, 6, 20), "Dopo: non deve comparire"),  # successiva
]


def servizio(
    client: LLMFinto | None = None,
    *,
    elenco: list[Ispezione] | None = None,
    raccolti: list[Raccolto] | None = None,
    riepiloghi: RiepiloghiFinti | None = None,
    alveare=ALVEARE,
):
    client = client or LLMFinto([RISPOSTA], modello="m-prova")
    riepiloghi = riepiloghi or RiepiloghiFinti()
    s = Servizi(
        None,
        crea_llm=lambda: client,
        ispezioni=IspezioniFinte(STORIA if elenco is None else elenco),
        alveari=AlveariFinti(alveare),
        apiari=ApiariFinti(),
        raccolti=RaccoltiFinti(raccolti or []),
        riepiloghi=riepiloghi,
    )
    return s, client, riepiloghi


def test_il_riepilogo_si_genera_valida_e_salva_con_la_tracciabilita_completa():
    s, client, riepiloghi = servizio()

    r = s.genera_riepilogo_ispezione(1, 12)

    assert isinstance(r, RiepilogoGenerato)
    assert r.valido and r.salvato and r.id == 101 and r.messaggio is None
    assert r.riepilogo.stato_salute == "attenzione"
    assert (r.provider, r.modello, r.versione_prompt) == ("finto", "m-prova", versione_prompt())
    assert (r.durata_ms, r.token_prompt, r.token_risposta, r.tentativi) == (0, 100, 50, 1)
    assert r.in_locale is True
    [salvato] = riepiloghi.salvati
    assert salvato["utente_id"] == 1 and salvato["ispezione_id"] == 12
    assert salvato["riepilogo"] == json.loads(RISPOSTA)  # la copia fedele, come dizionario
    assert salvato["stato_salute"] == "attenzione" and salvato["confidenza"] == "media"
    assert (salvato["provider"], salvato["modello"]) == ("finto", "m-prova")
    assert salvato["versione_prompt"] == versione_prompt()
    assert (salvato["token_prompt"], salvato["token_risposta"], salvato["tentativi"]) == (
        100,
        50,
        1,
    )
    assert len(client.chiamate) == 1


def test_il_tentativo_correttivo_si_somma_in_durata_token_e_tentativi():
    client = LLMFinto(["non json", RISPOSTA], token=(100, 50))
    s, _, riepiloghi = servizio(client)

    r = s.genera_riepilogo_ispezione(1, 12)

    assert r.valido and r.tentativi == 2 and (r.token_prompt, r.token_risposta) == (200, 100)
    assert riepiloghi.salvati[0]["tentativi"] == 2


def test_i_token_sconosciuti_si_salvano_come_null():
    s, _, riepiloghi = servizio(LLMFinto([RISPOSTA], token=None))
    s.genera_riepilogo_ispezione(1, 12)
    assert riepiloghi.salvati[0]["token_prompt"] is None
    assert riepiloghi.salvati[0]["token_risposta"] is None


def test_il_contesto_ha_solo_le_ispezioni_precedenti_a_questa():
    s, client, _ = servizio()
    s.genera_riepilogo_ispezione(1, 12)
    richiesta = client.chiamate[0].utente
    assert "2026-04-20" in richiesta and "2026-03-28" in richiesta
    assert "non deve comparire" not in richiesta and "2026-06-20" not in richiesta
    assert richiesta.count("- 2026-") == 2  # l'ispezione stessa non è nello storico


def test_lo_storico_tiene_le_tre_piu_recenti():
    molte = [ispezione(i, date(2026, 1, i)) for i in range(1, 8)] + [
        ispezione(20, date(2026, 5, 16), NOTA)
    ]
    s, client, _ = servizio(elenco=molte)
    s.genera_riepilogo_ispezione(1, 20)
    assert client.chiamate[0].utente.count("- 2026-01-") == 3
    for presente in ("- 2026-01-07", "- 2026-01-06", "- 2026-01-05"):
        assert presente in client.chiamate[0].utente
    assert "- 2026-01-04" not in client.chiamate[0].utente


def test_i_raccolti_sono_quelli_fino_alla_data_dell_ispezione_e_di_questo_alveare_o_dellapiario():
    raccolti = [
        raccolto(1, date(2025, 5, 28), "34.5"),  # apiario intero
        raccolto(2, date(2025, 8, 30), "12.8", alveare_id=5),  # questo alveare
        raccolto(3, date(2025, 9, 1), "99.9", alveare_id=77),  # un altro alveare
        raccolto(4, date(2026, 5, 30), "29.2"),  # dopo l'ispezione
    ]
    s, client, _ = servizio(raccolti=raccolti)
    s.genera_riepilogo_ispezione(1, 12)
    richiesta = client.chiamate[0].utente
    assert "34,5 kg" in richiesta and "12,8 kg" in richiesta
    assert "99,9" not in richiesta and "29,2" not in richiesta


@pytest.mark.parametrize("utente", [0, -1, None, "1", True])
def test_un_utente_non_valido_e_un_errore_che_nomina_il_campo(utente):
    s, client, _ = servizio()
    with pytest.raises(ValidationError) as errore:
        s.genera_riepilogo_ispezione(utente, 12)
    assert errore.value.campo == "utente_id" and client.chiamate == []


@pytest.mark.parametrize("ispezione_id", [0, -1, None, "12", 1.5])
def test_una_ispezione_non_valida_e_un_errore_che_nomina_il_campo(ispezione_id):
    s, client, _ = servizio()
    with pytest.raises(ValidationError) as errore:
        s.genera_riepilogo_ispezione(1, ispezione_id)
    assert errore.value.campo == "ispezione_id" and client.chiamate == []


def test_una_ispezione_inesistente_o_non_dellutente_e_non_trovata_senza_chiamare_il_modello():
    s, client, riepiloghi = servizio()
    with pytest.raises(ValidationError, match="non trovata") as errore:
        s.genera_riepilogo_ispezione(1, 999)
    assert errore.value.campo == "ispezione_id"
    assert client.chiamate == [] and riepiloghi.salvati == []


def test_se_alveare_o_apiario_non_si_trovano_e_non_trovata():
    s, client, _ = servizio(alveare=None)
    with pytest.raises(ValidationError, match="non trovata"):
        s.genera_riepilogo_ispezione(1, 12)
    assert client.chiamate == []


@pytest.mark.parametrize("nota", [None, "", "   \n"])
def test_senza_note_non_si_chiama_il_modello(nota):
    s, client, riepiloghi = servizio(elenco=[ispezione(12, date(2026, 5, 16), nota)])
    with pytest.raises(ValidationError, match="non ha note") as errore:
        s.genera_riepilogo_ispezione(1, 12)
    assert errore.value.campo == "note"
    assert client.chiamate == [] and riepiloghi.salvati == []


def test_un_errore_del_provider_si_propaga_e_non_salva_nulla():
    s, _, riepiloghi = servizio(LLMFinto([LLMError("Ollama non risponde")]))
    with pytest.raises(LLMError, match="non risponde"):
        s.genera_riepilogo_ispezione(1, 12)
    assert riepiloghi.salvati == []


def test_una_risposta_non_valida_due_volte_non_si_salva_e_lo_dice():
    s, client, riepiloghi = servizio(LLMFinto(["boh", "ancora boh"]))

    r = s.genera_riepilogo_ispezione(1, 12)

    assert r.valido is False and r.salvato is False and r.id is None
    assert "non ha prodotto un riepilogo leggibile" in r.messaggio
    assert r.riepilogo.stato_salute == "non_determinabile" and r.tentativi == 2
    assert riepiloghi.salvati == [] and len(client.chiamate) == 2


def test_se_il_database_non_salva_il_riepilogo_si_restituisce_comunque(caplog):
    s, _, _ = servizio(riepiloghi=RiepiloghiFinti(DatabaseError("MySQL spento")))

    with caplog.at_level(logging.ERROR):
        r = s.genera_riepilogo_ispezione(1, 12)

    assert r.valido is True and r.salvato is False and r.id is None
    assert "non è stato salvato" in r.messaggio
    assert r.riepilogo.stato_salute == "attenzione"  # il lavoro del modello non si butta
    assert "generato ma non salvato" in caplog.text


def test_un_errore_imprevisto_nel_salvataggio_non_viene_nascosto():
    s, _, _ = servizio(riepiloghi=RiepiloghiFinti(RuntimeError("bug")))
    with pytest.raises(RuntimeError):
        s.genera_riepilogo_ispezione(1, 12)


def test_un_riepilogo_nuovo_non_cancella_i_vecchi():
    s, _, riepiloghi = servizio()
    s.genera_riepilogo_ispezione(1, 12)
    s.genera_riepilogo_ispezione(1, 12)
    assert len(riepiloghi.salvati) == 2


def test_il_client_si_crea_alla_prima_richiesta_e_una_volta_sola():
    creati: list[int] = []
    client = LLMFinto([RISPOSTA])
    s = Servizi(
        None,
        crea_llm=lambda: creati.append(1) or client,
        ispezioni=IspezioniFinte(STORIA),
        alveari=AlveariFinti(),
        apiari=ApiariFinti(),
        raccolti=RaccoltiFinti([]),
        riepiloghi=RiepiloghiFinti(),
    )
    assert creati == []  # costruire i servizi non crea il client
    s.genera_riepilogo_ispezione(1, 12)
    s.genera_riepilogo_ispezione(1, 12)
    assert creati == [1]


def test_senza_un_provider_configurato_lerrore_e_di_configurazione():
    s = Servizi(
        None,
        ispezioni=IspezioniFinte(STORIA),
        alveari=AlveariFinti(),
        apiari=ApiariFinti(),
        raccolti=RaccoltiFinti([]),
        riepiloghi=RiepiloghiFinti(),
    )
    with pytest.raises(ConfigError, match="non è configurato"):
        s.genera_riepilogo_ispezione(1, 12)


def test_se_la_creazione_del_client_fallisce_lerrore_arriva_e_il_tentativo_dopo_riprova():
    esiti: list = [LLMError("Manca la chiave OpenRouter"), LLMFinto([RISPOSTA])]

    def crea():
        esito = esiti.pop(0)
        if isinstance(esito, Exception):
            raise esito
        return esito

    s = Servizi(
        None,
        crea_llm=crea,
        ispezioni=IspezioniFinte(STORIA),
        alveari=AlveariFinti(),
        apiari=ApiariFinti(),
        raccolti=RaccoltiFinti([]),
        riepiloghi=RiepiloghiFinti(),
    )
    with pytest.raises(LLMError, match="chiave"):
        s.genera_riepilogo_ispezione(1, 12)
    assert s.genera_riepilogo_ispezione(1, 12).valido


def test_le_note_inviate_fuori_dal_computer_si_segnalano():
    client = ClientOpenRouter("m", 5, api_key="chiave")
    # il client vero non viene mai chiamato: si sostituisce solo il passo di rete
    client._completa = LLMFinto([RISPOSTA])._completa
    s, _, _ = servizio(client)  # type: ignore[arg-type]
    assert s.genera_riepilogo_ispezione(1, 12).in_locale is False


def test_il_riepilogo_salvato_chiede_al_repository_per_lutente():
    s, _, _ = servizio()
    assert s.riepilogo_salvato(1, 12)["chiesto"] == (1, 12)
    with pytest.raises(ValidationError):
        s.riepilogo_salvato(0, 12)
    with pytest.raises(ValidationError):
        s.riepilogo_salvato(1, None)


def test_il_testo_della_nota_non_finisce_nei_log_di_info_del_servizio(caplog):
    s, _, _ = servizio()
    with caplog.at_level(logging.INFO):
        s.genera_riepilogo_ispezione(1, 12)
    assert "NOTA-SEGRETA-777" not in caplog.text
    assert "Riepilogo 101 salvato per l'ispezione 12" in caplog.text
