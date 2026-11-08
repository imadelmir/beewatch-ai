"""I servizi nuovi della pagina Assistente AI: informazioni e storico dei riepiloghi (M6-T6).

Unitari, con anagrafica, ispezioni e riepiloghi in memoria e il client finto: nessuna rete,
nessun database. Lo storico su MySQL vero è in fondo a `test_riepiloghi_repository.py`.
"""

from __future__ import annotations

import logging

import pytest
from anagrafica_finta import anagrafica_di_prova, ispezioni_di_prova
from assistente_finto import RaccoltiVuoti, RiepiloghiInMemoria
from dati_finti import RISPOSTA
from llm_fake import LLMFinto

from beewatch.ai.prompt import versione_prompt
from beewatch.ai.riepilogo import Riepilogo
from beewatch.exceptions import ValidationError
from beewatch.services import InfoAssistente, RiepilogoSalvato, Servizi


def servizi(**argomenti) -> tuple[Servizi, RiepiloghiInMemoria]:
    apiari, alveari = anagrafica_di_prova()
    riepiloghi = RiepiloghiInMemoria()
    s = Servizi(
        None,
        apiari=apiari,
        alveari=alveari,
        ispezioni=ispezioni_di_prova(alveari),
        raccolti=RaccoltiVuoti(),
        riepiloghi=riepiloghi,
        crea_llm=lambda: LLMFinto([RISPOSTA], modello="llama3.1:8b"),
        descrizione_llm="llama3.1:8b via ollama (chiave: non richiesta)",
        **argomenti,
    )
    return s, riepiloghi


def test_info_assistente_dice_modello_prompt_e_attesa_massima():
    s, _ = servizi(timeout_llm=45)

    assert s.info_assistente() == InfoAssistente(
        descrizione="llama3.1:8b via ollama (chiave: non richiesta)",
        versione_prompt=versione_prompt(),
        attesa_massima_s=270,  # due chiamate (con quella correttiva) da tre volte 45 s
    )


def test_info_assistente_non_crea_il_client():
    def esplode():
        raise AssertionError("il client non va creato per dire le informazioni")

    apiari, alveari = anagrafica_di_prova()
    s = Servizi(None, apiari=apiari, alveari=alveari, crea_llm=esplode)

    assert s.info_assistente().attesa_massima_s == 360  # il timeout predefinito, 60 s


def test_lo_storico_dei_riepiloghi_va_dal_piu_recente():
    s, _ = servizi()
    primo = s.genera_riepilogo_ispezione(1, 102)
    secondo = s.genera_riepilogo_ispezione(1, 102)
    s.genera_riepilogo_ispezione(1, 101)  # un'altra ispezione

    storico = s.riepiloghi_ispezione(1, 102)

    assert [r.id for r in storico] == [secondo.id, primo.id]
    ultimo = storico[0]
    assert isinstance(ultimo, RiepilogoSalvato) and isinstance(ultimo.riepilogo, Riepilogo)
    assert ultimo.riepilogo == secondo.riepilogo
    assert (ultimo.modello, ultimo.provider, ultimo.versione_prompt) == (
        "llama3.1:8b", "finto", versione_prompt(),
    )  # fmt: skip
    assert ultimo.tentativi == 1 and ultimo.ispezione_id == 102
    assert ultimo.creato_il is not None


def test_lo_storico_di_unispezione_altrui_e_vuoto():
    s, _ = servizi()
    s.genera_riepilogo_ispezione(1, 102)

    assert s.riepiloghi_ispezione(2, 102) == []
    assert s.riepiloghi_ispezione(1, 101) == []


def test_un_riepilogo_salvato_che_non_rispetta_piu_lo_schema_si_salta(caplog):
    s, riepiloghi = servizi()
    buono = s.genera_riepilogo_ispezione(1, 102)
    riepiloghi.righe.append({**riepiloghi.righe[0], "id": 99, "riepilogo_json": {"vecchio": 1}})

    with caplog.at_level(logging.WARNING):
        storico = s.riepiloghi_ispezione(1, 102)

    assert [r.id for r in storico] == [buono.id]
    assert any("Riepilogo 99 non più leggibile" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    ("argomenti", "campo"),
    [({"utente_id": 0}, "utente_id"), ({"ispezione_id": "102"}, "ispezione_id")],
)
def test_gli_id_non_validi_dello_storico_si_rifiutano(argomenti, campo):
    s, _ = servizi()

    with pytest.raises(ValidationError) as errore:
        s.riepiloghi_ispezione(**{"utente_id": 1, "ispezione_id": 102, **argomenti})
    assert errore.value.campo == campo
