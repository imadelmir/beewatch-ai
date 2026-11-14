"""Profilo, password, cancellazione dell'account, preferenze, promemoria, configurazione (M6-T13).

Unitari con utenti, anagrafica, ispezioni e preferenze in memoria; in fondo, su MySQL vero:
preferenze (predefinite, salvate, sostituite), profilo, password, cancellazione a cascata.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pytest
from accesso_finto import GIRI_TEST, PASSWORD_DEMO, SessioniInMemoria, UtentiInMemoria
from anagrafica_finta import anagrafica_di_prova, ispezioni_di_prova
from dati_finti import RISPOSTA
from llm_fake import LLMFinto
from preferenze_finte import PreferenzeInMemoria

from beewatch import sicurezza
from beewatch.config import Config, ConfigDatabase, ConfigLLM
from beewatch.database import Database
from beewatch.exceptions import ValidationError
from beewatch.repositories_riferimento import PreferenzeRepository, UtentiRepository
from beewatch.services import Preferenze, Servizi


@pytest.fixture(autouse=True)
def bcrypt_veloce(monkeypatch):
    monkeypatch.setattr(sicurezza, "GIRI", GIRI_TEST)


def servizi(**argomenti) -> tuple[Servizi, UtentiInMemoria, PreferenzeInMemoria]:
    apiari, alveari = anagrafica_di_prova()
    utenti, preferenze = UtentiInMemoria(), PreferenzeInMemoria()
    s = Servizi(
        None,
        utenti=utenti,
        sessioni=SessioniInMemoria(utenti),
        preferenze=preferenze,
        apiari=apiari,
        alveari=alveari,
        ispezioni=ispezioni_di_prova(alveari),
        **argomenti,
    )
    return s, utenti, preferenze


# --------------------------------------------------------------------------- #
# Profilo e password
# --------------------------------------------------------------------------- #


def test_il_profilo_si_legge_e_si_aggiorna():
    s, utenti, _ = servizi()

    nuovo = s.aggiorna_profilo(1, nome="  Ape Regina ", email="Regina@Esempio.IT")

    assert (nuovo.nome, nuovo.email) == ("Ape Regina", "regina@esempio.it")
    assert s.profilo(1) == nuovo
    assert utenti.righe[1]["email"] == "regina@esempio.it"


def test_la_propria_email_si_puo_riscrivere_quella_di_un_altro_no():
    s, utenti, _ = servizi()
    utenti.crea("altro@esempio.it", "Altro", "x" * 60)

    s.aggiorna_profilo(1, nome="Apicoltore", email="demo@beewatch.local")  # la sua: va bene
    with pytest.raises(ValidationError, match="Esiste già un account") as errore:
        s.aggiorna_profilo(1, nome="Apicoltore", email="ALTRO@esempio.it")
    assert errore.value.campo == "email"


@pytest.mark.parametrize(("campi", "campo"), [({"nome": "x"}, "nome"), ({"email": "no"}, "email")])
def test_un_profilo_non_valido_dice_il_campo(campi, campo):
    s, _, _ = servizi()

    with pytest.raises(ValidationError) as errore:
        s.aggiorna_profilo(1, **{"nome": "Apicoltore", "email": "a@b.it", **campi})
    assert errore.value.campo == campo


def test_un_profilo_che_non_ce_e_un_errore_chiaro():
    s, _, _ = servizi()

    with pytest.raises(ValidationError, match="Utente non trovato"):
        s.profilo(999)


def test_cambiare_la_password_richiede_quella_attuale():
    s, utenti, _ = servizi()

    with pytest.raises(ValidationError, match="attuale non è corretta") as errore:
        s.cambia_password(1, attuale="sbagliata", nuova="nuova-password", conferma="nuova-password")
    assert errore.value.campo == "attuale"

    s.cambia_password(1, attuale=PASSWORD_DEMO, nuova="nuova-password", conferma="nuova-password")

    assert s.accedi("demo@beewatch.local", "nuova-password").id == 1
    with pytest.raises(ValidationError):
        s.accedi("demo@beewatch.local", PASSWORD_DEMO)
    assert "nuova-password" not in utenti.righe[1]["hash_password"]


@pytest.mark.parametrize(
    ("nuova", "conferma", "campo"),
    [("corta", "corta", "nuova"), ("lunga-abbastanza", "diversa!", "conferma")],
)
def test_la_password_nuova_segue_le_regole(nuova, conferma, campo):
    s, _, _ = servizi()

    with pytest.raises(ValidationError) as errore:
        s.cambia_password(1, attuale=PASSWORD_DEMO, nuova=nuova, conferma=conferma)
    assert errore.value.campo == campo


def test_cancellare_laccount_richiede_la_password_e_toglie_tutto():
    s, utenti, _ = servizi()

    with pytest.raises(ValidationError):
        s.elimina_account(1, password="sbagliata")
    assert 1 in utenti.righe

    s.elimina_account(1, password=PASSWORD_DEMO)

    assert 1 not in utenti.righe


# --------------------------------------------------------------------------- #
# Preferenze e promemoria
# --------------------------------------------------------------------------- #


def test_senza_preferenze_salvate_valgono_i_predefiniti():
    s, _, _ = servizi()

    assert s.preferenze(1) == Preferenze(
        giorni_promemoria=30, avvisi_rischio=True, assistente_esterno=True
    )


def test_le_preferenze_si_salvano_e_si_rileggono():
    s, _, preferenze = servizi()

    salvate = s.salva_preferenze(
        1, giorni_promemoria=14, avvisi_rischio=False, assistente_esterno=False
    )

    assert s.preferenze(1) == salvate == Preferenze(14, False, False)
    assert preferenze.righe[1]["giorni_promemoria"] == 14


@pytest.mark.parametrize(
    ("campi", "campo"),
    [
        ({"giorni_promemoria": 6}, "giorni_promemoria"),
        ({"giorni_promemoria": 91}, "giorni_promemoria"),
        ({"giorni_promemoria": True}, "giorni_promemoria"),
        ({"avvisi_rischio": "sì"}, "avvisi_rischio"),
        ({"assistente_esterno": 1}, "assistente_esterno"),
    ],
)
def test_le_preferenze_non_valide_dicono_il_campo(campi, campo):
    s, _, preferenze = servizi()
    valori = {"giorni_promemoria": 30, "avvisi_rischio": True, "assistente_esterno": True, **campi}

    with pytest.raises(ValidationError) as errore:
        s.salva_preferenze(1, **valori)
    assert errore.value.campo == campo
    assert preferenze.righe == {}


def test_i_promemoria_seguono_le_preferenze():
    s, _, _ = servizi()

    tutti = s.promemoria(1, oggi=date(2026, 11, 14))

    assert tutti.giorni == 30 and tutti.avvisi_rischio
    assert tutti.da_controllare == (("A2", None),)  # A1 ha un'ispezione nei dati di prova
    # Negli ultimi 60 giorni: l'alto di A2 del 05/10. Fuori: il medio del 20/08 (86 giorni) e
    # l'alto dell'alveare eliminato A9, che non ha bisogno di promemoria.
    assert tutti.a_rischio == (("A2", date(2026, 10, 5), "Rischio alto"),)

    s.salva_preferenze(1, giorni_promemoria=14, avvisi_rischio=False, assistente_esterno=True)
    senza_avvisi = s.promemoria(1, oggi=date(2026, 11, 14))

    assert senza_avvisi.giorni == 14 and senza_avvisi.a_rischio == ()


# --------------------------------------------------------------------------- #
# Assistente esterno e configurazione
# --------------------------------------------------------------------------- #


def test_senza_consenso_le_note_non_vanno_a_un_assistente_esterno():
    llm = LLMFinto([RISPOSTA])
    s, _, _ = servizi(crea_llm=lambda: llm, llm_in_locale=False)
    s.salva_preferenze(1, giorni_promemoria=30, avvisi_rischio=True, assistente_esterno=False)

    with pytest.raises(ValidationError, match="nessuna nota è stata inviata") as errore:
        s.genera_riepilogo_ispezione(1, 102)

    assert errore.value.campo == "assistente_esterno"
    assert llm.chiamate == []  # il modello non è stato nemmeno chiamato


def test_con_un_assistente_locale_il_consenso_non_serve():
    llm = LLMFinto([RISPOSTA])
    s, _, _ = servizi(crea_llm=lambda: llm, llm_in_locale=True, riepiloghi=_Riepiloghi())
    s.salva_preferenze(1, giorni_promemoria=30, avvisi_rischio=True, assistente_esterno=False)

    with pytest.raises(AttributeError):  # arriva fino ai raccolti: il consenso non l'ha fermato
        s.genera_riepilogo_ispezione(1, 102)
    assert llm.chiamate == []


class _Riepiloghi:
    def salva(self, *a, **k):
        return 1


def configurazione(provider: str, chiave: str | None) -> Config:
    return Config(
        database=ConfigDatabase("db.locale", 3306, "beewatch", "app", "PASSWORD-SEGRETA-123"),
        llm=ConfigLLM(provider=provider, modello="llama3.1:8b", api_key=chiave, timeout=60),
        percorso_modello=Path("models/produzione_v1.joblib"),
        livello_log="INFO",
    )


def test_la_configurazione_visibile_non_contiene_segreti():
    s, _, _ = servizi(configurazione=configurazione("openrouter", "sk-or-CHIAVE-SEGRETA"))

    voci = s.configurazione_visibile()
    testo = repr(voci)

    assert "PASSWORD-SEGRETA-123" not in testo and "CHIAVE-SEGRETA" not in testo
    assert ("Database", "Password", "impostata") in voci
    assert ("Assistente AI", "Chiave API", "impostata") in voci
    assert ("Assistente AI", "Dove gira", "esterno") in voci
    assert ("Database", "Server", "db.locale:3306") in voci
    assert ("Modello di previsione", "File", "produzione_v1.joblib") in voci


def test_con_ollama_si_mostra_lindirizzo_e_non_la_chiave():
    s, _, _ = servizi(configurazione=configurazione("ollama", None))

    voci = dict(((sez, voce), v) for sez, voce, v in s.configurazione_visibile())

    assert voci[("Assistente AI", "Dove gira")] == "su questo computer"
    assert ("Assistente AI", "Indirizzo di Ollama") in voci
    assert ("Assistente AI", "Chiave API") not in voci


def test_senza_configurazione_lelenco_e_vuoto():
    s, _, _ = servizi()

    assert s.configurazione_visibile() == ()


# --------------------------------------------------------------------------- #
# Con MySQL vero
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_integrazione_preferenze_profilo_password_e_cascata(database_test: Database):
    email = f"impostazioni-{uuid.uuid4().hex}@beewatch.test"
    s = Servizi(database_test)
    utente = s.registra_utente(
        nome="Prova", email=email, password="favo-di-miele", conferma="favo-di-miele"
    )

    assert s.preferenze(utente.id) == Preferenze()  # nessuna riga: i predefiniti
    s.salva_preferenze(
        utente.id, giorni_promemoria=21, avvisi_rischio=False, assistente_esterno=True
    )
    s.salva_preferenze(
        utente.id, giorni_promemoria=45, avvisi_rischio=False, assistente_esterno=False
    )
    assert s.preferenze(utente.id) == Preferenze(45, False, False)  # sostituite, non duplicate
    with pytest.raises(ValidationError, match="Esiste già un account"):
        s.aggiorna_profilo(utente.id, nome="Prova", email="demo@beewatch.local")
    s.aggiorna_profilo(utente.id, nome="Prova Due", email=email)
    s.cambia_password(
        utente.id, attuale="favo-di-miele", nuova="pappa-reale", conferma="pappa-reale"
    )
    assert s.accedi(email, "pappa-reale").nome == "Prova Due"

    s.elimina_account(utente.id, password="pappa-reale")

    assert UtentiRepository(database_test).trova(utente.id) is None
    assert PreferenzeRepository(database_test).leggi(utente.id) is None  # via con l'utente
