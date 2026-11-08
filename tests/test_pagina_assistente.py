"""La pagina Assistente AI eseguita con `AppTest` (M6-T6).

Servizi veri (`genera_riepilogo_ispezione` compreso: contesto, validazione, tentativo correttivo,
salvataggio) con anagrafica, ispezioni e riepiloghi in memoria e il client di `llm_fake.py`:
nessuna rete, nessun database. Si sceglie l'ispezione, si preme il bottone e si guarda cosa vede
l'utente: banner, riepilogo strutturato, confidenza, lacune, provenienza, errori, storico.
"""

from __future__ import annotations

import pytest
from anagrafica_finta import (
    DATABASE_SPENTO,
    NOTA_LUNGA,
    AlveariInMemoria,
    ApiariInMemoria,
    IspezioniInMemoria,
    anagrafica_di_prova,
    ispezioni_di_prova,
)
from app_finta import APP, DashboardFinto, installa, valori
from assistente_finto import (
    RISPOSTA_CON_MARKDOWN,
    RISPOSTA_SENZA_ELENCHI,
    RaccoltiVuoti,
    RiepiloghiInMemoria,
)
from dati_finti import RISPOSTA
from llm_fake import LLMFinto
from streamlit.testing.v1 import AppTest

from beewatch.ai.prompt import versione_prompt
from beewatch.exceptions import DatabaseError, LLMError
from beewatch.services import Servizi

PAGINA = APP / "pages" / "4_Assistente_AI.py"
DESCRIZIONE = "llama3.1:8b via ollama (chiave: non richiesta)"


class LLMEsterno(LLMFinto):
    provider = "openrouter"
    in_locale = False


class Ambiente:
    def __init__(self, llm, riepiloghi, ispezioni):
        self.llm, self.riepiloghi, self.ispezioni = llm, riepiloghi, ispezioni


def prepara(app_pronta, monkeypatch, *, risposte=(RISPOSTA,), llm=None, senza_llm=False,
            apiari=None, alveari=None, ispezioni=None) -> Ambiente:  # fmt: skip
    if apiari is None:
        apiari, alveari = anagrafica_di_prova()
    ispezioni = ispezioni if ispezioni is not None else ispezioni_di_prova(alveari)
    llm = llm or LLMFinto(list(risposte), modello="llama3.1:8b")
    riepiloghi = RiepiloghiInMemoria()
    servizi = Servizi(
        None,
        apiari=apiari,
        alveari=alveari,
        ispezioni=ispezioni,
        raccolti=RaccoltiVuoti(),
        riepiloghi=riepiloghi,
        dashboard=DashboardFinto(),
        crea_llm=None if senza_llm else (lambda: llm),
        descrizione_llm=DESCRIZIONE,
    )
    installa(app_pronta, monkeypatch, servizi)
    return Ambiente(llm, riepiloghi, ispezioni)


@pytest.fixture
def ambiente(app_pronta, monkeypatch) -> Ambiente:
    return prepara(app_pronta, monkeypatch)


def apri() -> AppTest:
    return AppTest.from_file(str(PAGINA), default_timeout=30).run()


def selettore(at: AppTest):
    [s] = [s for s in at.selectbox if s.key.startswith("ispezione_da_riassumere_")]
    return s


def genera(at: AppTest) -> AppTest:
    return at.button(key="genera_riepilogo").click().run()


def metriche(at: AppTest) -> dict[str, str]:
    return {m.label: m.value for m in at.metric}


def contenuto(at: AppTest) -> str:
    return "\n".join(valori(at.markdown) + valori(at.caption))


# --------------------------------------------------------------------------- #
# Prima di generare
# --------------------------------------------------------------------------- #


def test_la_pagina_ha_banner_ispezioni_con_note_e_le_note_da_leggere(ambiente):
    at = apri()

    assert not at.exception and not at.error
    assert valori(at.title) == ["🤖 Assistente AI"]
    [banner] = [i for i in at.info if i.icon == "🤖"]
    assert banner.value.startswith("Il riepilogo qui sotto è generato da un'intelligenza")
    assert not at.expander  # banner non nascondibile, e ancora nessuno storico
    # solo le ispezioni con note, dalla più recente: 102 (A2) e 101 (A1)
    assert selettore(at).options == [
        "05/10/2026 · A2 · Rischio alto",
        "12/09/2026 · A1 · Nessun rischio",
    ]
    note = at.text_area(key="note_da_riassumere_102")
    assert note.disabled and note.value.startswith("Varroa *alta*")
    assert f"Assistente: **{DESCRIZIONE}** · prompt **{versione_prompt()}**" in contenuto(at)
    assert metriche(at) == {"Ispezioni con note": "2", "Riepiloghi salvati": "0"}
    assert any(t.startswith("Nessun riepilogo salvato") for t in valori(at.info))


def test_cambiando_ispezione_si_vedono_le_sue_note(ambiente):
    at = apri()
    selettore(at).select(101).run()

    assert at.text_area(key="note_da_riassumere_101").value == NOTA_LUNGA


def test_lo_spinner_dichiara_lattesa_possibile():
    sorgente = PAGINA.read_text(encoding="utf-8")

    assert "with st.spinner(" in sorgente
    assert "può richiedere fino a circa {minuti} minuti" in sorgente


# --------------------------------------------------------------------------- #
# Generare
# --------------------------------------------------------------------------- #


def test_il_riepilogo_si_mostra_strutturato_con_confidenza_e_lacune(ambiente):
    at = genera(apri())

    assert not at.exception and not at.error
    assert "Riepilogo dell'ispezione del 05/10/2026" in valori(at.subheader)
    assert metriche(at)["Stato di salute"] == "⚠ Attenzione"
    assert metriche(at)["Confidenza"] == "Media"
    corpo = contenuto(at)
    assert "- covata a macchie" in corpo  # elementi rilevati
    assert "- covata a macchie — gravità media" in corpo  # criticità
    assert "- **Priorità media** · ricontrollare tra una settimana (entro 7 giorni)" in corpo
    assert "**Cosa l'AI non ha potuto dedurre dalle note**" in corpo
    assert "- causa della covata a macchie" in corpo
    assert f"Scritto da **llama3\\.1:8b** (finto) con il prompt **{versione_prompt()}**" in corpo
    assert len(ambiente.llm.chiamate) == 1


def test_il_riepilogo_salvato_entra_nello_storico(ambiente):
    at = genera(apri())

    [salvato] = ambiente.riepiloghi.righe
    assert salvato["ispezione_id"] == 102
    assert metriche(at)["Riepiloghi salvati"] == "1"
    [voce] = at.expander
    assert (
        voce.label
        == f"08/11/2026 09:01 · llama3.1:8b · prompt {versione_prompt()} · confidenza media"
    )


def test_il_testo_del_modello_non_diventa_formattazione_e_le_azioni_vanno_per_priorita(
    app_pronta, monkeypatch
):
    prepara(app_pronta, monkeypatch, risposte=(RISPOSTA_CON_MARKDOWN,))

    at = genera(apri())

    corpo = contenuto(at)
    assert "- covata \\*\\*a mosaico\\*\\*" in corpo  # asterischi annullati, non grassetto
    assert "\\[link\\]\\(http://esempio\\.test\\)" in corpo  # nessun link cliccabile
    # le prime tre righe: il riepilogo appena generato (lo stesso c'è anche nello storico)
    azioni = [r for r in corpo.splitlines() if r.startswith("- **Priorità")][:3]
    assert [a.split("**")[1] for a in azioni] == [
        "Priorità alta",
        "Priorità media",
        "Priorità bassa",
    ]
    assert azioni[0].endswith("(entro 3 giorni)") and "entro" not in azioni[2]
    assert metriche(at)["Stato di salute"] == "✖ Critico"
    assert metriche(at)["Confidenza"] == "Bassa"


def test_gli_elenchi_vuoti_lo_dicono_invece_di_restare_bianchi(app_pronta, monkeypatch):
    prepara(app_pronta, monkeypatch, risposte=(RISPOSTA_SENZA_ELENCHI,))

    at = genera(apri())

    didascalie = valori(at.caption)
    for frase in (
        "Il modello non ha indicato elementi.",
        "Nessuna criticità indicata.",
        "Nessuna azione suggerita.",
        "Il modello non ha indicato lacune nelle note.",
    ):
        assert frase in didascalie
    assert metriche(at)["Stato di salute"] == "✔ Buono"
    assert metriche(at)["Confidenza"] == "Alta"


def test_una_risposta_illeggibile_lo_dice_e_non_salva(app_pronta, monkeypatch):
    ambiente = prepara(app_pronta, monkeypatch, risposte=("non è json", "nemmeno questo"))

    at = genera(apri())

    assert not at.exception and not at.error
    assert any("non ha prodotto un riepilogo leggibile" in w for w in valori(at.warning))
    assert "Stato di salute" not in metriche(at)
    assert ambiente.riepiloghi.righe == [] and len(ambiente.llm.chiamate) == 2
    assert any("con un tentativo correttivo" in c for c in valori(at.caption))


def test_un_timeout_del_modello_si_spiega_senza_traceback(app_pronta, monkeypatch):
    ambiente = prepara(
        app_pronta,
        monkeypatch,
        risposte=(LLMError("Il modello non ha risposto entro 60 secondi."),),
    )

    at = genera(apri())

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**L'assistente AI non ha risposto come doveva.**")
    assert "entro 60 secondi" in errore
    assert ambiente.riepiloghi.righe == []
    assert at.button(key="genera_riepilogo")  # si può riprovare


def test_senza_provider_configurato_lo_dice(app_pronta, monkeypatch):
    prepara(app_pronta, monkeypatch, senza_llm=True)

    at = genera(apri())

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**La configurazione non è valida.**")


def test_se_il_salvataggio_fallisce_il_riepilogo_si_vede_lo_stesso(ambiente):
    ambiente.riepiloghi.errore_salvataggio = DatabaseError("Il server MySQL non risponde.")

    at = genera(apri())

    assert not at.exception and not at.error
    assert metriche(at)["Confidenza"] == "Media"
    assert any("non è stato salvato" in w for w in valori(at.warning))


def test_le_note_inviate_fuori_si_dichiarano(app_pronta, monkeypatch):
    prepara(app_pronta, monkeypatch, llm=LLMEsterno([RISPOSTA], modello="un-modello:free"))

    at = genera(apri())

    assert "Le note di questa ispezione sono state inviate a un servizio esterno." in valori(
        at.caption
    )


# --------------------------------------------------------------------------- #
# Stati vuoti ed errori di lettura
# --------------------------------------------------------------------------- #


def test_senza_apiari_invita_a_crearne_uno(app_pronta, monkeypatch):
    apiari = ApiariInMemoria()
    alveari = AlveariInMemoria(apiari)
    prepara(app_pronta, monkeypatch, apiari=apiari, alveari=alveari,
            ispezioni=IspezioniInMemoria(alveari))  # fmt: skip

    at = apri()

    assert not at.exception and not at.error
    assert any(t.startswith("Nessun apiario registrato.") for t in valori(at.info))
    assert not at.button


def test_senza_ispezioni_con_note_rimanda_a_ispezioni(app_pronta, monkeypatch):
    apiari, alveari = anagrafica_di_prova()
    prepara(app_pronta, monkeypatch, apiari=apiari, alveari=alveari,
            ispezioni=IspezioniInMemoria(alveari))  # fmt: skip

    at = apri()

    [vuoto] = [t for t in valori(at.info) if t.startswith("Nessuna ispezione con note in Collina.")]
    assert "Ispezioni" in vuoto
    assert not at.button


def test_con_il_database_spento_lo_dice_e_si_ferma(app_pronta, monkeypatch):
    apiari, alveari = anagrafica_di_prova(errore=DATABASE_SPENTO)
    prepara(app_pronta, monkeypatch, apiari=apiari, alveari=alveari,
            ispezioni=ispezioni_di_prova(alveari, errore=DATABASE_SPENTO))  # fmt: skip

    at = apri()

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")
    assert not at.button


def test_se_lo_storico_non_si_legge_si_puo_generare_lo_stesso(ambiente):
    ambiente.riepiloghi.errore_lettura = DATABASE_SPENTO

    at = apri()

    assert not at.exception
    [errore] = valori(at.error)
    assert errore.startswith("**Non riesco a raggiungere il database.**")
    assert at.button(key="genera_riepilogo")
    assert metriche(at) == {"Ispezioni con note": "2"}
