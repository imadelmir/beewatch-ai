"""Test dei modelli del dominio (`beewatch.models`, M3-T2).

Ogni entità deve rifiutare i valori non validi con `ValidationError` e il nome
del campo sbagliato, e normalizzare quelli validi (spazi, numeri come `Decimal`,
codici come `Enum`). Le regole sono quelle dello schema SQL più quelle legate
alla data di oggi.

L'ultimo test (integration) confronta gli `Enum` con le righe del seed nel
database di test: se qualcuno aggiunge uno stato dell'alveare da una parte sola,
fallisce.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from beewatch.database import Database
from beewatch.exceptions import ValidationError
from beewatch.models import (
    Alveare,
    Apiario,
    Ispezione,
    LivelloRischio,
    Previsione,
    Raccolto,
    StatoAlveare,
    TipoMiele,
)

OGGI = date.today()
DOMANI = OGGI + timedelta(days=1)
IERI = OGGI - timedelta(days=1)

VALIDI: dict[type, dict[str, Any]] = {
    Apiario: {"utente_id": 1, "nome": "Collina"},
    Alveare: {"apiario_id": 1, "codice": "A1", "stato": StatoAlveare.IN_SALUTE},
    Ispezione: {"alveare_id": 1, "data_ispezione": IERI, "livello_rischio": LivelloRischio.BASSO},
    Raccolto: {
        "apiario_id": 1,
        "tipo_miele": TipoMiele.ACACIA,
        "data_raccolto": IERI,
        "quantita_kg": Decimal("12.5"),
    },
    Previsione: {
        "utente_id": 1,
        "versione_modello": "v1.0.0",
        "codice_stato_riferimento": "CA",
        "anno_riferimento": 2026,
        "stima_kg": Decimal("30"),
        "limite_inferiore_kg": Decimal("20"),
        "limite_superiore_kg": Decimal("40"),
    },
}


def crea(tipo: type, **modifiche: Any) -> Any:
    return tipo(**{**VALIDI[tipo], **modifiche})


# --------------------------------------------------------------------------- #
# Casi validi e normalizzazione
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("tipo", list(VALIDI), ids=lambda t: t.__name__)
def test_i_valori_minimi_validi_creano_lentita(tipo: type) -> None:
    entita = crea(tipo)
    assert entita.id is None  # non ancora salvata


@pytest.mark.parametrize("tipo", list(VALIDI), ids=lambda t: t.__name__)
def test_le_entita_non_si_modificano_dopo_la_creazione(tipo: type) -> None:
    entita = crea(tipo)
    with pytest.raises(dataclasses.FrozenInstanceError):
        entita.id = 5  # type: ignore[misc]


def test_i_testi_perdono_gli_spazi_attorno_e_il_vuoto_vale_assente() -> None:
    apiario = crea(Apiario, nome="  Collina  ", localita="   ", note="\n")
    assert apiario.nome == "Collina"
    assert apiario.localita is None
    assert apiario.note is None


@pytest.mark.parametrize(
    "scritto,atteso",
    [
        ("38.5", Decimal("38.5")),
        ("38,5", Decimal("38.5")),
        (38, Decimal(38)),
        (0.1, Decimal("0.1")),
    ],
    ids=["testo", "virgola", "intero", "float_senza_errori_di_arrotondamento"],
)
def test_i_numeri_diventano_decimal_esatti(scritto: Any, atteso: Decimal) -> None:
    ispezione = crea(Ispezione, peso_kg=scritto)
    assert ispezione.peso_kg == atteso
    assert isinstance(ispezione.peso_kg, Decimal)


def test_i_valori_fissi_si_possono_dare_anche_con_il_codice() -> None:
    """Serve ai repository, che leggono il codice dal database."""
    assert crea(Alveare, stato="sciamato").stato is StatoAlveare.SCIAMATO
    assert crea(Ispezione, livello_rischio="alto").livello_rischio is LivelloRischio.ALTO
    assert crea(Raccolto, tipo_miele="melata").tipo_miele is TipoMiele.MELATA


def test_i_valori_fissi_sono_anche_stringhe_uguali_al_codice() -> None:
    assert StatoAlveare.IN_SALUTE == "in_salute"
    assert f"{TipoMiele.NON_DEFINITO}" == "non_definito"


def test_valori_al_limite_ammessi() -> None:
    crea(Ispezione, data_ispezione=OGGI, peso_kg=0, telaini_covata=0, telaini_scorte=30)
    crea(Alveare, anno_regina=2000)
    crea(Alveare, anno_regina=OGGI.year)
    crea(Apiario, latitudine="-90", longitudine="180.000000")
    crea(Raccolto, quantita_kg="0.01")
    crea(Raccolto, quantita_kg="9999.99")
    crea(Previsione, stima_kg=20, limite_inferiore_kg=20, limite_superiore_kg=20)
    # Le lunghezze massime delle colonne VARCHAR sono ammesse, un carattere in più no.
    crea(Apiario, nome="x" * 120, localita="y" * 160)
    crea(Alveare, codice="A" * 20)
    crea(Previsione, versione_modello="v" * 40)
    crea(Previsione, feature={"anno": 2013, "stato": "CA", "mancante": None, "resa": 21.5})
    crea(Previsione, feature=None)


def test_note_e_coordinate_non_compaiono_nella_rappresentazione() -> None:
    """Un oggetto finito per sbaglio in un log non deve portarsi dietro dati personali."""
    testo = repr(crea(Apiario, latitudine="45.123456", longitudine="7.654321", note="segreto"))
    assert "45.123456" not in testo and "7.654321" not in testo and "segreto" not in testo
    assert "segreto" not in repr(crea(Ispezione, note="segreto"))
    assert "segreto" not in repr(crea(Raccolto, note="segreto"))
    assert "segreto" not in repr(crea(Alveare, note="segreto"))


# --------------------------------------------------------------------------- #
# Valori rifiutati: ogni caso indica il campo giusto
# --------------------------------------------------------------------------- #

RIFIUTATI = [
    # tipo, campo, valore
    (Apiario, "utente_id", 0),
    (Apiario, "utente_id", True),
    (Apiario, "utente_id", "1"),
    (Apiario, "nome", ""),
    (Apiario, "nome", "   "),
    (Apiario, "nome", None),
    (Apiario, "nome", "x" * 121),
    (Apiario, "nome", 42),
    (Apiario, "localita", "x" * 161),
    (Apiario, "latitudine", "90.000001"),
    (Apiario, "latitudine", -91),
    (Apiario, "longitudine", 180.5),
    (Apiario, "longitudine", "1.1234567"),  # DECIMAL(9, 6): MySQL arrotonderebbe in silenzio
    (Apiario, "latitudine", "nord"),
    (Apiario, "attivo", 1),
    (Apiario, "id", -3),
    (Alveare, "apiario_id", None),
    (Alveare, "codice", ""),
    (Alveare, "codice", "A" * 21),
    (Alveare, "stato", "felice"),
    (Alveare, "stato", None),
    (Alveare, "anno_regina", 1999),
    (Alveare, "anno_regina", OGGI.year + 1),
    (Alveare, "anno_regina", 2020.0),
    (Alveare, "data_installazione", "2024-04-01"),
    (Ispezione, "data_ispezione", DOMANI),
    (Ispezione, "data_ispezione", None),
    (Ispezione, "data_ispezione", datetime(2024, 5, 1, 10, 0)),
    (Ispezione, "livello_rischio", "altissimo"),
    (Ispezione, "peso_kg", -0.01),
    (Ispezione, "peso_kg", "10000"),
    (Ispezione, "peso_kg", "12.345"),  # DECIMAL(6, 2)
    (Ispezione, "peso_kg", "NaN"),
    (Ispezione, "peso_kg", "Infinity"),
    (Ispezione, "peso_kg", True),
    (Ispezione, "telaini_covata", 31),
    (Ispezione, "telaini_covata", -1),
    (Ispezione, "telaini_scorte", 3.5),
    (Ispezione, "regina_vista", "sì"),
    (Ispezione, "sciamatura", None),
    (Ispezione, "note", "è" * 40_000),  # oltre i 65 535 byte di una colonna TEXT
    (Raccolto, "tipo_miele", "manuka"),
    (Raccolto, "quantita_kg", 0),
    (Raccolto, "quantita_kg", -2),
    (Raccolto, "quantita_kg", None),
    (Raccolto, "quantita_kg", "10000.00"),
    (Raccolto, "data_raccolto", None),
    (Raccolto, "alveare_id", 0),
    (Previsione, "versione_modello", ""),
    (Previsione, "versione_modello", "v" * 41),
    (Previsione, "codice_stato_riferimento", "ca"),
    (Previsione, "codice_stato_riferimento", "CAL"),
    (Previsione, "codice_stato_riferimento", "C1"),
    (Previsione, "anno_riferimento", 1989),
    (Previsione, "anno_riferimento", 2101),
    (Previsione, "stima_kg", "30.123"),
    (Previsione, "limite_superiore_kg", None),
    (Previsione, "feature", [1, 2]),  # non un dizionario
    (Previsione, "feature", {1: 2.0}),  # chiave non testuale
    (Previsione, "feature", {"resa": float("nan")}),  # MySQL non accetta NaN come JSON
    (Previsione, "feature", {"resa": float("inf")}),
    (Previsione, "feature", {"resa": object()}),  # non serializzabile
]


@pytest.mark.parametrize(
    "tipo,campo,valore",
    RIFIUTATI,
    ids=[f"{t.__name__}-{c}-{i}" for i, (t, c, _) in enumerate(RIFIUTATI)],
)
def test_un_valore_non_valido_e_rifiutato_indicando_il_campo(
    tipo: type, campo: str, valore: Any
) -> None:
    with pytest.raises(ValidationError) as info:
        crea(tipo, **{campo: valore})
    assert info.value.campo == campo
    assert str(info.value)  # c'è un messaggio per l'utente


@pytest.mark.parametrize(
    "inferiore,stima,superiore",
    [(20, 19, 40), (20, 41, 40), (40, 30, 20)],
    ids=["stima_sotto", "stima_sopra", "limiti_invertiti"],
)
def test_la_stima_deve_stare_dentro_il_suo_intervallo(
    inferiore: int, stima: int, superiore: int
) -> None:
    with pytest.raises(ValidationError, match="intervallo") as info:
        crea(
            Previsione,
            stima_kg=stima,
            limite_inferiore_kg=inferiore,
            limite_superiore_kg=superiore,
        )
    assert info.value.campo == "stima_kg"


def test_le_feature_di_una_previsione_sono_una_copia_non_il_dizionario_di_chi_chiama() -> None:
    originali = {"anno": 2013, "resa": 21.5}
    previsione = crea(Previsione, feature=originali)
    originali["resa"] = 999.0
    assert previsione.feature == {"anno": 2013, "resa": 21.5}


def test_il_messaggio_di_un_valore_fisso_elenca_quelli_ammessi() -> None:
    with pytest.raises(ValidationError) as info:
        crea(Alveare, stato="felice")
    for ammesso in StatoAlveare:
        assert ammesso.value in str(info.value)


def test_il_modulo_non_dipende_da_database_ne_da_streamlit() -> None:
    import ast
    import inspect

    from beewatch import models

    importati = set()
    for nodo in ast.walk(ast.parse(inspect.getsource(models))):
        if isinstance(nodo, ast.ImportFrom):
            importati.add(nodo.module or "")
        elif isinstance(nodo, ast.Import):
            importati.update(alias.name for alias in nodo.names)

    vietati = ("mysql", "streamlit", "beewatch.database", "beewatch.repositories")
    assert not [n for n in importati if n.startswith(vietati)]


# --------------------------------------------------------------------------- #
# Integrazione: gli Enum coincidono con il seed
# --------------------------------------------------------------------------- #


@pytest.mark.integration
@pytest.mark.parametrize(
    "tabella,tipo",
    [
        ("stati_alveare", StatoAlveare),
        ("livelli_rischio", LivelloRischio),
        ("tipi_miele", TipoMiele),
    ],
)
def test_integrazione_i_codici_degli_enum_sono_quelli_del_seed(
    database_test: Database, tabella: str, tipo: type
) -> None:
    with database_test.transazione() as cursore:
        cursore.execute(f"SELECT codice FROM {tabella}")  # nome di tabella fisso, non un input
        nel_database = {riga["codice"] for riga in cursore.fetchall()}

    assert nel_database == {membro.value for membro in tipo}
