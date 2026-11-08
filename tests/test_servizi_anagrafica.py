"""I servizi dell'anagrafica: apiari e alveari (M6-T3).

Unitari con l'anagrafica in memoria (`anagrafica_finta.py`) e, in fondo, **lo stesso scenario**
sui repository veri con MySQL (integration): così i finti usati dai test della pagina non possono
divergere dalle regole vere senza che un test se ne accorga.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import date
from decimal import Decimal

import pytest
from anagrafica_finta import AlveariInMemoria, ApiariInMemoria, anagrafica_di_prova

from beewatch.database import Database
from beewatch.exceptions import ValidationError
from beewatch.models import StatoAlveare
from beewatch.services import AlveareInElenco, Servizi


def servizi_in_memoria() -> tuple[Servizi, ApiariInMemoria, AlveariInMemoria]:
    apiari, alveari = anagrafica_di_prova()
    return Servizi(None, apiari=apiari, alveari=alveari), apiari, alveari


# --------------------------------------------------------------------------- #
# Apiari
# --------------------------------------------------------------------------- #


def test_lanagrafica_elenca_gli_apiari_attivi_dellutente_con_le_coordinate():
    servizi, _, _ = servizi_in_memoria()

    apiari = servizi.apiari_in_anagrafica(1)

    assert [a.nome for a in apiari] == ["Collina", "Valle"]  # non quello dell'utente 2
    assert apiari[0].latitudine == Decimal("45.71")


def test_crea_apiario_pulisce_i_testi_e_restituisce_lid():
    servizi, apiari, _ = servizi_in_memoria()

    nuovo = servizi.crea_apiario(1, nome="  Bosco  ", localita="", latitudine=45.5, note=" ")

    assert nuovo.id and nuovo.nome == "Bosco"
    assert nuovo.localita is None and nuovo.note is None  # vuoto vale come assente
    assert nuovo.latitudine == Decimal("45.5")
    assert apiari.righe[nuovo.id].attivo


@pytest.mark.parametrize(
    ("campi", "campo"),
    [
        ({"nome": ""}, "nome"),
        ({"nome": "x" * 121}, "nome"),
        ({"nome": "Ok", "latitudine": 91}, "latitudine"),
        ({"nome": "Ok", "longitudine": -181}, "longitudine"),
        ({"nome": "Collina"}, "nome"),  # già usato
    ],
)
def test_crea_apiario_rifiuta_i_campi_non_validi_indicando_il_campo(campi, campo):
    servizi, apiari, _ = servizi_in_memoria()
    prima = dict(apiari.righe)

    with pytest.raises(ValidationError) as errore:
        servizi.crea_apiario(1, **campi)

    assert errore.value.campo == campo
    assert apiari.righe == prima  # niente scritto


def test_aggiorna_apiario_sostituisce_i_campi():
    servizi, apiari, _ = servizi_in_memoria()

    servizi.aggiorna_apiario(1, 11, nome="Valle bassa", localita="Fondovalle")

    assert apiari.righe[11].nome == "Valle bassa" and apiari.righe[11].localita == "Fondovalle"


def test_non_si_aggiorna_ne_si_elimina_lapiario_di_un_altro_utente():
    servizi, apiari, _ = servizi_in_memoria()

    with pytest.raises(ValidationError):
        servizi.aggiorna_apiario(1, 20, nome="Mio")
    with pytest.raises(ValidationError):
        servizi.elimina_apiario(1, 20)

    assert apiari.righe[20].nome == "Altrui" and apiari.righe[20].attivo


def test_elimina_apiario_e_logico_e_lo_toglie_dagli_elenchi():
    servizi, apiari, _ = servizi_in_memoria()

    servizi.elimina_apiario(1, 11)

    assert 11 in apiari.righe and not apiari.righe[11].attivo  # la riga resta
    assert [a.nome for a in servizi.apiari_in_anagrafica(1)] == ["Collina"]
    assert [a.nome for a in servizi.elenca_apiari(1)] == ["Collina"]


@pytest.mark.parametrize("cattivo", [0, -1, None, "3", True])
def test_gli_id_non_validi_si_rifiutano_prima_del_repository(cattivo):
    servizi, _, _ = servizi_in_memoria()

    with pytest.raises(ValidationError):
        servizi.elimina_apiario(1, cattivo)
    with pytest.raises(ValidationError):
        servizi.alveari_dell_apiario(cattivo, 10)


# --------------------------------------------------------------------------- #
# Alveari
# --------------------------------------------------------------------------- #


def test_gli_alveari_dellapiario_sono_gli_attivi_per_codice_con_lultima_ispezione():
    servizi, _, _ = servizi_in_memoria()

    elenco = servizi.alveari_dell_apiario(1, 10)

    assert [a.codice for a in elenco] == ["A1", "A2"]  # A9 è disattivato
    a1, a2 = elenco
    assert a1 == AlveareInElenco(
        id=1, apiario_id=10, codice="A1", stato=StatoAlveare.IN_SALUTE,
        data_installazione=date(2025, 4, 1), anno_regina=None, note="Regina marcata blu",
        ultima_ispezione=date(2026, 10, 30), peso_kg=38.5,
    )  # fmt: skip
    assert a2.ultima_ispezione is None and a2.peso_kg is None


def test_lapiario_di_un_altro_utente_ha_un_elenco_vuoto():
    servizi, _, _ = servizi_in_memoria()

    assert servizi.alveari_dell_apiario(1, 20) == []
    assert servizi.alveari_dell_apiario(1, 11) == []  # Valle: vuoto davvero


def test_gli_alveari_di_un_apiario_eliminato_spariscono_dallelenco():
    servizi, _, _ = servizi_in_memoria()

    servizi.elimina_apiario(1, 10)

    assert servizi.alveari_dell_apiario(1, 10) == []


def test_crea_alveare_accetta_lo_stato_come_testo_e_come_enum():
    servizi, _, alveari = servizi_in_memoria()

    uno = servizi.crea_alveare(1, apiario_id=11, codice=" B1 ", stato="in_osservazione")
    due = servizi.crea_alveare(
        1, apiario_id=11, codice="B2", stato=StatoAlveare.SCIAMATO,
        data_installazione=date(2026, 3, 1), anno_regina=2025, note="Da riunire",
    )  # fmt: skip

    assert uno.codice == "B1" and uno.stato is StatoAlveare.IN_OSSERVAZIONE
    assert alveari.righe[due.id].anno_regina == 2025
    assert [a.codice for a in servizi.alveari_dell_apiario(1, 11)] == ["B1", "B2"]


@pytest.mark.parametrize(
    ("campi", "campo"),
    [
        ({"codice": ""}, "codice"),
        ({"codice": "x" * 21}, "codice"),
        ({"codice": "A1"}, "codice"),  # già usato nell'apiario
        ({"codice": "A9"}, "codice"),  # anche se disattivato: la query lo conta
        ({"codice": "N1", "stato": "felice"}, "stato"),
        ({"codice": "N1", "anno_regina": 1999}, "anno_regina"),
        ({"codice": "N1", "anno_regina": date.today().year + 1}, "anno_regina"),
        ({"codice": "N1", "apiario_id": 20}, "apiario_id"),  # di un altro utente
    ],
)
def test_crea_alveare_rifiuta_i_campi_non_validi_indicando_il_campo(campi, campo):
    servizi, _, alveari = servizi_in_memoria()
    prima = dict(alveari.righe)
    argomenti = {"apiario_id": 10, "stato": StatoAlveare.IN_SALUTE, **campi}

    with pytest.raises(ValidationError) as errore:
        servizi.crea_alveare(1, **argomenti)

    assert errore.value.campo == campo
    assert alveari.righe == prima


def test_aggiorna_alveare_cambia_i_campi_e_puo_spostarlo_di_apiario():
    servizi, _, alveari = servizi_in_memoria()

    servizi.aggiorna_alveare(
        1, 2, apiario_id=11, codice="V1", stato=StatoAlveare.IN_SALUTE, anno_regina=2025
    )

    assert alveari.righe[2].apiario_id == 11 and alveari.righe[2].codice == "V1"
    assert [a.codice for a in servizi.alveari_dell_apiario(1, 10)] == ["A1"]
    assert [a.codice for a in servizi.alveari_dell_apiario(1, 11)] == ["V1"]


def test_non_si_tocca_lalveare_di_un_altro_utente():
    servizi, _, alveari = servizi_in_memoria()

    with pytest.raises(ValidationError):
        servizi.aggiorna_alveare(1, 30, apiario_id=10, codice="X1", stato="debole")
    with pytest.raises(ValidationError):
        servizi.elimina_alveare(1, 30)

    assert alveari.righe[30].attivo and alveari.righe[30].apiario_id == 20


def test_elimina_alveare_e_logico():
    servizi, _, alveari = servizi_in_memoria()

    servizi.elimina_alveare(1, 2)

    assert not alveari.righe[2].attivo
    assert [a.codice for a in servizi.alveari_dell_apiario(1, 10)] == ["A1"]


# --------------------------------------------------------------------------- #
# Lo stesso scenario, in memoria e con MySQL vero
# --------------------------------------------------------------------------- #


def scenario(servizi: Servizi, utente: int, altro: int, apiario_altrui: int) -> None:
    """Un giro completo dell'anagrafica, con gli errori attesi lungo la strada."""
    collina = servizi.crea_apiario(utente, nome="Collina", latitudine="45.123456")
    valle = servizi.crea_apiario(utente, nome="Valle")
    with pytest.raises(ValidationError, match="Hai già un apiario con questo nome"):
        servizi.crea_apiario(utente, nome="Collina")

    a1 = servizi.crea_alveare(utente, apiario_id=collina.id, codice="A1", stato="in_salute")
    servizi.crea_alveare(utente, apiario_id=collina.id, codice="A2", stato="debole")
    with pytest.raises(ValidationError, match="già un alveare con questo codice"):
        servizi.crea_alveare(utente, apiario_id=collina.id, codice="A1", stato="debole")
    with pytest.raises(ValidationError) as errore:
        servizi.crea_alveare(utente, apiario_id=apiario_altrui, codice="Z1", stato="debole")
    assert errore.value.campo == "apiario_id"

    elenco = servizi.alveari_dell_apiario(utente, collina.id)
    assert [(a.codice, a.stato) for a in elenco] == [
        ("A1", StatoAlveare.IN_SALUTE),
        ("A2", StatoAlveare.DEBOLE),
    ]
    assert all(a.ultima_ispezione is None and a.peso_kg is None for a in elenco)

    servizi.aggiorna_alveare(
        utente, a1.id, apiario_id=valle.id, codice="V1", stato="in_osservazione",
        anno_regina=2025,
    )  # fmt: skip
    assert [a.codice for a in servizi.alveari_dell_apiario(utente, valle.id)] == ["V1"]
    assert servizi.alveari_dell_apiario(utente, valle.id)[0].anno_regina == 2025

    servizi.aggiorna_apiario(utente, valle.id, nome="Valle bassa", localita="Fondovalle")
    assert [a.nome for a in servizi.apiari_in_anagrafica(utente)] == ["Collina", "Valle bassa"]
    assert servizi.apiari_in_anagrafica(utente)[0].latitudine == Decimal("45.123456")

    servizi.elimina_alveare(utente, a1.id)
    assert servizi.alveari_dell_apiario(utente, valle.id) == []
    servizi.elimina_apiario(utente, collina.id)
    assert [a.nome for a in servizi.apiari_in_anagrafica(utente)] == ["Valle bassa"]
    assert servizi.alveari_dell_apiario(utente, collina.id) == []

    with pytest.raises(ValidationError):  # l'altro utente non vede né tocca
        servizi.elimina_apiario(altro, valle.id)
    assert servizi.alveari_dell_apiario(altro, valle.id) == []


def test_scenario_completo_in_memoria():
    apiari = ApiariInMemoria()
    alveari = AlveariInMemoria(apiari)
    servizi = Servizi(None, apiari=apiari, alveari=alveari)
    altrui = servizi.crea_apiario(2, nome="Altrui")

    scenario(servizi, utente=1, altro=2, apiario_altrui=altrui.id)


@pytest.fixture
def due_utenti(database_test: Database) -> Iterator[Callable[[], int]]:
    """Utenti di prova cancellati a fine test: le cascate dello schema portano via il resto."""
    creati: list[int] = []

    def crea() -> int:
        with database_test.transazione() as cursore:
            cursore.execute(
                "INSERT INTO utenti (email, nome_completo, hash_password) VALUES (%s, %s, %s)",
                (f"anagrafica-{uuid.uuid4().hex}@beewatch.test", "Utente di prova", "x" * 60),
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
    servizi = Servizi(database_test)
    utente, altro = due_utenti(), due_utenti()
    altrui = servizi.crea_apiario(altro, nome="Altrui")

    scenario(servizi, utente=utente, altro=altro, apiario_altrui=altrui.id)
