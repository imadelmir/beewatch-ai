"""I servizi delle ispezioni: storico filtrato e registrazione (M6-T4).

Unitari con le ispezioni in memoria (`anagrafica_finta.py`) e, in fondo, **lo stesso scenario**
sui repository veri con MySQL (integration): note lunghe e accentate comprese, perché sono la
materia prima dell'assistente AI e devono tornare indietro identiche.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from decimal import Decimal

import pytest
from anagrafica_finta import (
    NOTA_LUNGA,
    AlveariInMemoria,
    ApiariInMemoria,
    IspezioniInMemoria,
    anagrafica_di_prova,
    ispezioni_di_prova,
)

from beewatch.database import Database
from beewatch.exceptions import ValidationError
from beewatch.models import LivelloRischio
from beewatch.services import IspezioneInElenco, Servizi

COLLINA, VALLE, ALTRUI = 10, 11, 20


def servizi_in_memoria() -> tuple[Servizi, IspezioniInMemoria]:
    apiari, alveari = anagrafica_di_prova()
    ispezioni = ispezioni_di_prova(alveari)
    return Servizi(None, apiari=apiari, alveari=alveari, ispezioni=ispezioni), ispezioni


def ids(storico: list[IspezioneInElenco]) -> list[int]:
    return [i.id for i in storico]


# --------------------------------------------------------------------------- #
# Storico
# --------------------------------------------------------------------------- #


def test_lo_storico_e_degli_alveari_attivi_dellapiario_dalla_piu_recente():
    servizi, _ = servizi_in_memoria()

    storico = servizi.ispezioni_dell_apiario(1, COLLINA)

    # 105 è dell'alveare eliminato A9, 106 di un altro utente
    assert ids(storico) == [103, 102, 101, 104]
    assert [i.codice_alveare for i in storico] == ["A1", "A2", "A1", "A2"]
    prima = storico[0]
    assert prima == IspezioneInElenco(
        id=103, alveare_id=1, codice_alveare="A1", data_ispezione=date(2026, 10, 30),
        livello_rischio=LivelloRischio.BASSO, peso_kg=38.5, telaini_covata=None,
        telaini_scorte=None, regina_vista=False, sciamatura=True, note=None,
    )  # fmt: skip
    assert isinstance(prima.peso_kg, float)  # la pagina non deve conoscere Decimal


def test_a_parita_di_data_viene_prima_lultima_registrata():
    servizi, ispezioni = servizi_in_memoria()
    nuova = servizi.registra_ispezione(
        1, alveare_id=2, data_ispezione=date(2026, 10, 30), livello_rischio="nessuno"
    )

    assert ids(servizi.ispezioni_dell_apiario(1, COLLINA))[:2] == [nuova.id, 103]


def test_lo_storico_si_restringe_a_un_alveare():
    servizi, _ = servizi_in_memoria()

    assert ids(servizi.ispezioni_dell_apiario(1, COLLINA, alveare_id=2)) == [102, 104]


@pytest.mark.parametrize(
    ("dal", "al", "attese"),
    [
        (date(2026, 9, 12), None, [103, 102, 101]),  # gli estremi sono compresi
        (None, date(2026, 10, 5), [102, 101, 104]),
        (date(2026, 9, 12), date(2026, 10, 5), [102, 101]),
        (date(2026, 10, 5), date(2026, 10, 5), [102]),
        (date(2026, 11, 1), None, []),
    ],
)
def test_lo_storico_si_filtra_per_intervallo_di_date(dal, al, attese):
    servizi, _ = servizi_in_memoria()

    assert ids(servizi.ispezioni_dell_apiario(1, COLLINA, dal=dal, al=al)) == attese


def test_una_data_dinizio_dopo_la_fine_si_rifiuta():
    servizi, _ = servizi_in_memoria()

    with pytest.raises(ValidationError, match="viene dopo") as errore:
        servizi.ispezioni_dell_apiario(1, COLLINA, dal=date(2026, 10, 6), al=date(2026, 10, 5))
    assert errore.value.campo == "dal"


@pytest.mark.parametrize(("campo", "valore"), [("dal", "2026-10-01"), ("al", 20261001)])
def test_le_date_dei_filtri_devono_essere_date(campo, valore):
    servizi, _ = servizi_in_memoria()

    with pytest.raises(ValidationError) as errore:
        servizi.ispezioni_dell_apiario(1, COLLINA, **{campo: valore})
    assert errore.value.campo == campo


def test_apiari_e_alveari_altrui_danno_uno_storico_vuoto():
    servizi, _ = servizi_in_memoria()

    assert servizi.ispezioni_dell_apiario(1, ALTRUI) == []
    assert servizi.ispezioni_dell_apiario(1, COLLINA, alveare_id=30) == []
    assert servizi.ispezioni_dell_apiario(2, COLLINA) == []
    assert servizi.ispezioni_dell_apiario(1, VALLE) == []  # nessun alveare


@pytest.mark.parametrize(
    ("argomenti", "campo"),
    [
        ({"utente_id": 0}, "utente_id"),
        ({"apiario_id": "10"}, "apiario_id"),
        ({"alveare_id": True}, "alveare_id"),
    ],
)
def test_gli_id_non_validi_dello_storico_si_rifiutano(argomenti, campo):
    servizi, _ = servizi_in_memoria()
    chiamata = {"utente_id": 1, "apiario_id": COLLINA, **argomenti}

    with pytest.raises(ValidationError) as errore:
        servizi.ispezioni_dell_apiario(**chiamata)
    assert errore.value.campo == campo


# --------------------------------------------------------------------------- #
# Registrazione
# --------------------------------------------------------------------------- #


def test_registra_ispezione_salva_tutti_i_campi_e_restituisce_lid():
    servizi, ispezioni = servizi_in_memoria()

    nuova = servizi.registra_ispezione(
        1, alveare_id=2, data_ispezione=date(2026, 11, 1), livello_rischio="medio",
        peso_kg=36.25, telaini_covata=5, telaini_scorte=3, regina_vista=True,
        sciamatura=False, note="  Covata a mosaico, da ricontrollare.  ",
    )  # fmt: skip

    assert nuova.id == 107 and ispezioni.righe[107] == nuova
    assert nuova.livello_rischio is LivelloRischio.MEDIO
    assert nuova.peso_kg == Decimal("36.25")  # dal float del widget, senza code binarie
    assert nuova.note == "Covata a mosaico, da ricontrollare."
    assert servizi.ispezioni_dell_apiario(1, COLLINA)[0].id == 107


def test_una_nota_lunga_e_accentata_torna_identica():
    servizi, _ = servizi_in_memoria()
    nota = NOTA_LUNGA + " Àncora: perché, città, così, più — «virgolette» e 🐝."
    assert len(nota) > 2000

    nuova = servizi.registra_ispezione(
        1, alveare_id=1, data_ispezione=date(2026, 11, 2), livello_rischio="nessuno", note=nota
    )

    [riletta] = [i for i in servizi.ispezioni_dell_apiario(1, COLLINA) if i.id == nuova.id]
    assert riletta.note == nota


def test_una_data_futura_si_rifiuta_e_non_si_salva_nulla():
    servizi, ispezioni = servizi_in_memoria()
    prima = dict(ispezioni.righe)

    with pytest.raises(ValidationError) as errore:
        servizi.registra_ispezione(
            1, alveare_id=1, data_ispezione=date.today() + timedelta(days=1),
            livello_rischio="nessuno",
        )  # fmt: skip
    assert errore.value.campo == "data_ispezione"
    assert ispezioni.righe == prima


@pytest.mark.parametrize(
    ("campi", "campo"),
    [
        ({"livello_rischio": "altissimo"}, "livello_rischio"),
        ({"peso_kg": -1}, "peso_kg"),
        ({"peso_kg": 38.123}, "peso_kg"),
        ({"telaini_covata": 31}, "telaini_covata"),
        ({"telaini_scorte": -1}, "telaini_scorte"),
        ({"data_ispezione": None}, "data_ispezione"),
        ({"note": "x" * 70_000}, "note"),
    ],
)
def test_registra_ispezione_rifiuta_i_campi_non_validi_indicando_il_campo(campi, campo):
    servizi, ispezioni = servizi_in_memoria()
    chiamata = {
        "alveare_id": 1, "data_ispezione": date(2026, 11, 1), "livello_rischio": "nessuno",
        **campi,
    }  # fmt: skip

    with pytest.raises(ValidationError) as errore:
        servizi.registra_ispezione(1, **chiamata)
    assert errore.value.campo == campo
    assert len(ispezioni.righe) == 6


@pytest.mark.parametrize(
    "alveare",
    [9, 30, 999],  # eliminato, di un altro utente, inesistente
)
def test_si_registra_solo_su_un_alveare_attivo_dellutente(alveare):
    servizi, ispezioni = servizi_in_memoria()

    with pytest.raises(ValidationError, match="forse è stato eliminato") as errore:
        servizi.registra_ispezione(
            1, alveare_id=alveare, data_ispezione=date(2026, 11, 1), livello_rischio="basso"
        )
    assert errore.value.campo == "alveare_id"
    assert len(ispezioni.righe) == 6


# --------------------------------------------------------------------------- #
# Lo stesso scenario, in memoria e con MySQL vero
# --------------------------------------------------------------------------- #

NOTA_SCENARIO = NOTA_LUNGA + " Àncora: perché, città, così, più — «virgolette» e 🐝."


def scenario(servizi: Servizi, utente: int, altro: int) -> None:
    """Un giro completo delle ispezioni, con gli errori attesi lungo la strada."""
    collina = servizi.crea_apiario(utente, nome="Collina")
    a1 = servizi.crea_alveare(utente, apiario_id=collina.id, codice="A1", stato="in_salute")
    a2 = servizi.crea_alveare(utente, apiario_id=collina.id, codice="A2", stato="debole")
    assert servizi.ispezioni_dell_apiario(utente, collina.id) == []

    vecchia = servizi.registra_ispezione(
        utente, alveare_id=a1.id, data_ispezione=date(2026, 9, 1), livello_rischio="nessuno",
        peso_kg=40.1, telaini_covata=6, telaini_scorte=4, regina_vista=True, note=NOTA_SCENARIO,
    )  # fmt: skip
    nuova = servizi.registra_ispezione(
        utente, alveare_id=a2.id, data_ispezione=date(2026, 10, 1),
        livello_rischio=LivelloRischio.ALTO, sciamatura=True,
    )  # fmt: skip

    storico = servizi.ispezioni_dell_apiario(utente, collina.id)
    assert [(i.id, i.codice_alveare) for i in storico] == [(nuova.id, "A2"), (vecchia.id, "A1")]
    letta = storico[1]
    assert letta.note == NOTA_SCENARIO  # oltre 2000 caratteri, accenti ed emoji intatti
    assert (letta.peso_kg, letta.telaini_covata, letta.telaini_scorte) == (40.1, 6, 4)
    assert letta.regina_vista is True and letta.sciamatura is False
    assert storico[0].livello_rischio is LivelloRischio.ALTO and storico[0].sciamatura is True

    assert ids(servizi.ispezioni_dell_apiario(utente, collina.id, alveare_id=a1.id)) == [vecchia.id]
    filtrate = servizi.ispezioni_dell_apiario(
        utente, collina.id, dal=date(2026, 9, 2), al=date(2026, 10, 1)
    )
    assert ids(filtrate) == [nuova.id]

    with pytest.raises(ValidationError) as errore:  # la data futura
        servizi.registra_ispezione(
            utente, alveare_id=a1.id, data_ispezione=date.today() + timedelta(days=1),
            livello_rischio="nessuno",
        )  # fmt: skip
    assert errore.value.campo == "data_ispezione"

    servizi.elimina_alveare(utente, a2.id)  # le sue ispezioni escono dallo storico
    assert ids(servizi.ispezioni_dell_apiario(utente, collina.id)) == [vecchia.id]
    with pytest.raises(ValidationError) as errore:
        servizi.registra_ispezione(
            utente, alveare_id=a2.id, data_ispezione=date(2026, 10, 2), livello_rischio="basso"
        )
    assert errore.value.campo == "alveare_id"

    assert servizi.ispezioni_dell_apiario(altro, collina.id) == []  # l'altro utente non vede
    with pytest.raises(ValidationError):
        servizi.registra_ispezione(
            altro, alveare_id=a1.id, data_ispezione=date(2026, 10, 2), livello_rischio="basso"
        )


def test_scenario_completo_in_memoria():
    apiari = ApiariInMemoria()
    alveari = AlveariInMemoria(apiari)
    servizi = Servizi(None, apiari=apiari, alveari=alveari, ispezioni=IspezioniInMemoria(alveari))

    scenario(servizi, utente=1, altro=2)


@pytest.fixture
def due_utenti(database_test: Database) -> Iterator[Callable[[], int]]:
    """Utenti di prova cancellati a fine test: le cascate dello schema portano via il resto."""
    creati: list[int] = []

    def crea() -> int:
        with database_test.transazione() as cursore:
            cursore.execute(
                "INSERT INTO utenti (email, nome_completo, hash_password) VALUES (%s, %s, %s)",
                (f"ispezioni-{uuid.uuid4().hex}@beewatch.test", "Utente di prova", "x" * 60),
            )
            creati.append(cursore.lastrowid)
        return creati[-1]

    yield crea
    with database_test.transazione() as cursore:
        for utente in creati:
            cursore.execute("DELETE FROM utenti WHERE id = %s", (utente,))


@pytest.mark.integration
def test_integrazione_lo_stesso_scenario_con_mysql(
    database_test: Database, due_utenti: Callable[[], int]
):
    scenario(Servizi(database_test), utente=due_utenti(), altro=due_utenti())
