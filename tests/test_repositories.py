"""Test dei repository (`beewatch.repositories*`, M3-T3).

Quasi tutto è di integrazione: un repository è SQL, e l'unico modo onesto di
provarlo è eseguirlo su MySQL vero. Girano sul database `<DB_NAME>_test` dello
stack Docker temporaneo (fixture in `conftest.py`), che ha schema e seed.

Isolamento fra i test: ogni test crea i propri utenti (fixture `nuovo_utente`) e
a fine test li cancella con `UtentiRepository.elimina` (Q11), che per le cascate
dello schema porta via apiari, alveari, ispezioni, raccolti, previsioni e
conversazioni. Le righe di `produzione_usda` e `modelli`, che non appartengono a
un utente, vengono tolte una per una.

Le date sono sempre relative a oggi: Q1, Q3 e Q6 confrontano con `CURDATE()`.

In fondo, due controlli statici che girano anche senza MySQL: nessun SQL fuori
dai repository, e nessun file di repository oltre le 400 righe.
"""

from __future__ import annotations

import ast
import re
import uuid
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from beewatch.database import Database
from beewatch.exceptions import DatabaseError, ValidationError
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
from beewatch.repositories import (
    AlveariRepository,
    ApiariRepository,
    IspezioniRepository,
    RaccoltiRepository,
)
from beewatch.repositories_riferimento import (
    ConversazioniRepository,
    DashboardRepository,
    PrevisioniRepository,
    ProduzioneUsdaRepository,
    UtentiRepository,
)

PACCHETTO = Path(__file__).resolve().parents[1] / "beewatch"
OGGI = date.today()


def giorni_fa(n: int) -> date:
    return OGGI - timedelta(days=n)


def _esegui(db: Database, sql: str, parametri: tuple = ()) -> list[dict]:
    """SQL di preparazione dei test (dati che i repository non creano: utenti, modelli...)."""
    with db.transazione() as cursore:
        cursore.execute(sql, parametri)
        return cursore.fetchall() if cursore.with_rows else []


def _conta(db: Database, tabella: str, colonna: str, valori: list[int]) -> int:
    if not valori:
        return 0
    segnaposto = ", ".join(["%s"] * len(valori))
    return _esegui(
        db, f"SELECT COUNT(*) AS n FROM {tabella} WHERE {colonna} IN ({segnaposto})", tuple(valori)
    )[0]["n"]


# --------------------------------------------------------------------------- #
# Fixture
# --------------------------------------------------------------------------- #


@pytest.fixture
def nuovo_utente(database_test: Database) -> Iterator[Callable[[], int]]:
    """Fabbrica di utenti di prova; a fine test li cancella tutti (Q11, a cascata)."""
    creati: list[int] = []

    def _crea() -> int:
        with database_test.transazione() as cursore:
            cursore.execute(
                "INSERT INTO utenti (email, nome_completo, hash_password) VALUES (%s, %s, %s)",
                (f"test-{uuid.uuid4().hex}@beewatch.test", "Utente di prova", "x" * 60),
            )
            creati.append(cursore.lastrowid)
        return creati[-1]

    yield _crea
    for utente_id in creati:
        try:
            UtentiRepository(database_test).elimina(utente_id)
        except ValidationError:
            pass  # già cancellato dal test


@pytest.fixture
def repo(database_test: Database) -> dict[str, object]:
    return {
        "apiari": ApiariRepository(database_test),
        "alveari": AlveariRepository(database_test),
        "ispezioni": IspezioniRepository(database_test),
        "raccolti": RaccoltiRepository(database_test),
    }


@pytest.fixture
def apiario_con_alveare(
    repo: dict, nuovo_utente: Callable[[], int]
) -> tuple[int, Apiario, Alveare]:
    utente = nuovo_utente()
    apiario = repo["apiari"].crea(Apiario(utente_id=utente, nome="Collina"))
    alveare = repo["alveari"].crea(
        utente, Alveare(apiario_id=apiario.id, codice="A1", stato=StatoAlveare.IN_SALUTE)
    )
    return utente, apiario, alveare


# --------------------------------------------------------------------------- #
# Apiari
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_apiario_creato_e_riletto_identico(repo: dict, nuovo_utente: Callable[[], int]) -> None:
    utente = nuovo_utente()
    scritto = Apiario(
        utente_id=utente, nome="Collina", localita="Bergamo",
        latitudine=Decimal("45.71"), longitudine=Decimal("9.67"), note="Esposto a sud 🐝",
    )  # fmt: skip

    salvato = repo["apiari"].crea(scritto)

    assert salvato.id is not None
    letto = repo["apiari"].trova(utente, salvato.id)
    assert letto == salvato  # Decimal, testo e booleano tornano uguali


@pytest.mark.integration
def test_il_nome_dellapiario_e_unico_per_utente_non_nel_database(
    repo: dict, nuovo_utente: Callable[[], int]
) -> None:
    primo, secondo = nuovo_utente(), nuovo_utente()
    repo["apiari"].crea(Apiario(utente_id=primo, nome="Collina"))

    with pytest.raises(ValidationError) as info:
        repo["apiari"].crea(
            Apiario(utente_id=primo, nome="collina")
        )  # la collazione ignora le maiuscole
    assert info.value.campo == "nome"
    repo["apiari"].crea(Apiario(utente_id=secondo, nome="Collina"))  # un altro utente può


@pytest.mark.integration
def test_aggiorna_e_disattiva_un_apiario(repo: dict, nuovo_utente: Callable[[], int]) -> None:
    utente = nuovo_utente()
    apiario = repo["apiari"].crea(Apiario(utente_id=utente, nome="Collina"))
    altro = repo["apiari"].crea(Apiario(utente_id=utente, nome="Pianura"))

    repo["apiari"].aggiorna(Apiario(**{**apiario.__dict__, "nome": "Collina alta"}))
    repo["apiari"].aggiorna(Apiario(**{**apiario.__dict__, "nome": "Collina alta"}))  # invariato
    with pytest.raises(ValidationError) as info:
        repo["apiari"].aggiorna(Apiario(**{**altro.__dict__, "nome": "Collina alta"}))
    assert info.value.campo == "nome"

    repo["apiari"].disattiva(utente, altro.id)

    assert [a.nome for a in repo["apiari"].elenca(utente)] == ["Collina alta"]
    tutti = repo["apiari"].elenca(utente, anche_disattivi=True)
    assert [(a.nome, a.attivo) for a in tutti] == [("Collina alta", True), ("Pianura", False)]


@pytest.mark.integration
def test_un_apiario_non_salvato_non_si_aggiorna(
    repo: dict, nuovo_utente: Callable[[], int]
) -> None:
    with pytest.raises(ValidationError) as info:
        repo["apiari"].aggiorna(Apiario(utente_id=nuovo_utente(), nome="Mai salvato"))
    assert info.value.campo == "id"


@pytest.mark.integration
def test_il_testo_dellutente_resta_testo_anche_se_sembra_sql(
    repo: dict, nuovo_utente: Callable[[], int]
) -> None:
    utente = nuovo_utente()
    nome = "x'); DROP TABLE apiari; --"
    apiario = repo["apiari"].crea(Apiario(utente_id=utente, nome=nome))
    assert repo["apiari"].trova(utente, apiario.id).nome == nome  # parametri, non concatenazione


# --------------------------------------------------------------------------- #
# Isolamento fra utenti (D2)
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_un_utente_non_vede_ne_modifica_i_dati_di_un_altro(
    repo: dict, database_test: Database, apiario_con_alveare: tuple, nuovo_utente: Callable[[], int]
) -> None:
    proprietario, apiario, alveare = apiario_con_alveare
    repo["ispezioni"].crea(
        proprietario,
        Ispezione(alveare_id=alveare.id, data_ispezione=OGGI, livello_rischio="alto", peso_kg=20),
    )
    raccolto = repo["raccolti"].crea(
        proprietario,
        Raccolto(apiario_id=apiario.id, tipo_miele="acacia", data_raccolto=OGGI, quantita_kg=5),
    )
    intruso = nuovo_utente()

    assert repo["apiari"].trova(intruso, apiario.id) is None
    assert repo["apiari"].elenca(intruso, anche_disattivi=True) == []
    assert repo["alveari"].trova(intruso, alveare.id) is None
    assert repo["alveari"].trova_alveari_attivi(intruso) == []
    assert repo["alveari"].elenco_con_ultima_ispezione(intruso) == []
    assert repo["alveari"].trascurati(intruso) == []
    assert repo["ispezioni"].ispezioni_per_alveare(intruso, alveare.id) == []
    assert repo["ispezioni"].andamento_peso(intruso, alveare.id) == []
    assert repo["ispezioni"].a_rischio_alto(intruso) == []
    assert repo["raccolti"].per_apiario(intruso, apiario.id) == []
    assert repo["raccolti"].produzione_per_stagione(intruso) == []
    assert DashboardRepository(database_test).riepilogo(intruso) == {
        "alveari_attivi": 0, "ispezioni_30_giorni": 0, "produzione_stagione_kg": 0,
    }  # fmt: skip

    tentativi = [
        lambda: repo["apiari"].aggiorna(Apiario(**{**apiario.__dict__, "utente_id": intruso})),
        lambda: repo["apiari"].disattiva(intruso, apiario.id),
        lambda: repo["alveari"].crea(
            intruso, Alveare(apiario_id=apiario.id, codice="X", stato="morto")
        ),
        lambda: repo["alveari"].aggiorna(intruso, alveare),
        lambda: repo["alveari"].disattiva(intruso, alveare.id),
        lambda: repo["ispezioni"].crea(
            intruso, Ispezione(alveare_id=alveare.id, data_ispezione=OGGI, livello_rischio="basso")
        ),
        lambda: repo["raccolti"].crea(
            intruso,
            Raccolto(apiario_id=apiario.id, tipo_miele="acacia", data_raccolto=OGGI, quantita_kg=1),
        ),
        lambda: repo["raccolti"].elimina(intruso, raccolto.id),
    ]
    for tentativo in tentativi:
        with pytest.raises(ValidationError, match="non trovato"):
            tentativo()

    # Nulla è cambiato per il proprietario.
    assert repo["apiari"].trova(proprietario, apiario.id) == apiario
    assert repo["alveari"].trova(proprietario, alveare.id) == alveare
    assert len(repo["raccolti"].per_apiario(proprietario, apiario.id)) == 1


# --------------------------------------------------------------------------- #
# Alveari
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_alveare_creato_aggiornato_e_disattivato(repo: dict, apiario_con_alveare: tuple) -> None:
    utente, apiario, alveare = apiario_con_alveare
    assert repo["alveari"].trova(utente, alveare.id) == alveare
    assert repo["alveari"].trova(utente, alveare.id).stato is StatoAlveare.IN_SALUTE

    cambiato = Alveare(
        **{**alveare.__dict__, "stato": StatoAlveare.SCIAMATO, "anno_regina": 2024,
           "data_installazione": date(2024, 4, 12), "note": "Sciamato a maggio"}
    )  # fmt: skip
    repo["alveari"].aggiorna(utente, cambiato)
    assert repo["alveari"].trova(utente, alveare.id) == cambiato

    repo["alveari"].disattiva(utente, alveare.id)
    assert repo["alveari"].trova_alveari_attivi(utente) == []
    assert repo["alveari"].trova(utente, alveare.id).attivo is False  # disattivato, non cancellato


@pytest.mark.integration
def test_il_codice_dellalveare_e_unico_nellapiario(repo: dict, apiario_con_alveare: tuple) -> None:
    utente, apiario, _ = apiario_con_alveare
    with pytest.raises(ValidationError) as info:
        repo["alveari"].crea(utente, Alveare(apiario_id=apiario.id, codice="A1", stato="debole"))
    assert info.value.campo == "codice"

    altro_apiario = repo["apiari"].crea(Apiario(utente_id=utente, nome="Pianura"))
    repo["alveari"].crea(utente, Alveare(apiario_id=altro_apiario.id, codice="A1", stato="debole"))


@pytest.mark.integration
def test_alveari_attivi_esclude_quelli_degli_apiari_disattivati(
    repo: dict, apiario_con_alveare: tuple
) -> None:
    utente, apiario, alveare = apiario_con_alveare
    assert repo["alveari"].trova_alveari_attivi(utente) == [alveare]
    repo["apiari"].disattiva(utente, apiario.id)
    assert repo["alveari"].trova_alveari_attivi(utente) == []


@pytest.mark.integration
def test_q2_elenco_alveari_con_lultima_ispezione(repo: dict, apiario_con_alveare: tuple) -> None:
    utente, apiario, a1 = apiario_con_alveare
    a2 = repo["alveari"].crea(utente, Alveare(apiario_id=apiario.id, codice="A2", stato="debole"))
    for giorni, peso in ((20, "30.50"), (3, "32.10")):
        repo["ispezioni"].crea(
            utente,
            Ispezione(alveare_id=a1.id, data_ispezione=giorni_fa(giorni), livello_rischio="nessuno",
                      peso_kg=peso),
        )  # fmt: skip

    righe = repo["alveari"].elenco_con_ultima_ispezione(utente)

    assert [(r["codice"], r["stato"], r["ultima_ispezione"], r["peso_kg"]) for r in righe] == [
        ("A1", "In salute", giorni_fa(3), Decimal("32.10")),
        ("A2", "Debole", None, None),
    ]
    assert righe[0]["apiario"] == "Collina" and righe[0]["colore"] == "#3FB463"
    assert a2.id == righe[1]["id"]


@pytest.mark.integration
def test_q3_alveari_trascurati(repo: dict, apiario_con_alveare: tuple) -> None:
    utente, apiario, recente = apiario_con_alveare
    vecchio = repo["alveari"].crea(
        utente, Alveare(apiario_id=apiario.id, codice="B", stato="debole")
    )
    mai = repo["alveari"].crea(utente, Alveare(apiario_id=apiario.id, codice="C", stato="debole"))
    spento = repo["alveari"].crea(
        utente, Alveare(apiario_id=apiario.id, codice="D", stato="morto", attivo=False)
    )
    for alveare, giorni in ((recente, 5), (vecchio, 45)):
        repo["ispezioni"].crea(
            utente,
            Ispezione(
                alveare_id=alveare.id, data_ispezione=giorni_fa(giorni), livello_rischio="basso"
            ),
        )

    trascurati = repo["alveari"].trascurati(utente)

    assert [(r["codice"], r["ultima"]) for r in trascurati] == [("B", giorni_fa(45)), ("C", None)]
    assert spento.id not in {r["id"] for r in trascurati}  # i disattivati non contano
    assert [r["codice"] for r in repo["alveari"].trascurati(utente, giorni=60)] == ["C"]
    assert mai.id == trascurati[1]["id"]


# --------------------------------------------------------------------------- #
# Ispezioni
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_ispezioni_salvate_e_rilette_dalla_piu_recente(
    repo: dict, apiario_con_alveare: tuple
) -> None:
    utente, _, alveare = apiario_con_alveare
    vecchia = repo["ispezioni"].crea(
        utente,
        Ispezione(alveare_id=alveare.id, data_ispezione=giorni_fa(10), livello_rischio="medio",
                  peso_kg="21.40", telaini_covata=3, telaini_scorte=2, regina_vista=True,
                  note="Covata a macchie, è da ricontrollare"),
    )  # fmt: skip
    nuova = repo["ispezioni"].crea(
        utente,
        Ispezione(alveare_id=alveare.id, data_ispezione=giorni_fa(1),
                  livello_rischio=LivelloRischio.NESSUNO, sciamatura=True),
    )  # fmt: skip

    lette = repo["ispezioni"].ispezioni_per_alveare(utente, alveare.id)

    assert lette == [nuova, vecchia]  # tutti i campi, Enum e booleani compresi


@pytest.mark.integration
def test_q4_andamento_del_peso_in_ordine_senza_le_pesate_mancanti(
    repo: dict, apiario_con_alveare: tuple
) -> None:
    utente, _, alveare = apiario_con_alveare
    for giorni, peso in ((30, "20.00"), (20, None), (10, "25.50")):
        repo["ispezioni"].crea(
            utente,
            Ispezione(alveare_id=alveare.id, data_ispezione=giorni_fa(giorni),
                      livello_rischio="nessuno", peso_kg=peso, telaini_covata=4),
        )  # fmt: skip

    andamento = repo["ispezioni"].andamento_peso(utente, alveare.id)

    assert [(r["data_ispezione"], r["peso_kg"]) for r in andamento] == [
        (giorni_fa(30), Decimal("20.00")),
        (giorni_fa(10), Decimal("25.50")),
    ]
    assert andamento[0]["telaini_covata"] == 4


@pytest.mark.integration
def test_q6_ispezioni_a_rischio_degli_ultimi_60_giorni(
    repo: dict, apiario_con_alveare: tuple
) -> None:
    utente, _, alveare = apiario_con_alveare
    casi = [("alto", 2), ("medio", 30), ("basso", 1), ("alto", 61), ("nessuno", 3)]
    for rischio, giorni in casi:
        repo["ispezioni"].crea(
            utente,
            Ispezione(alveare_id=alveare.id, data_ispezione=giorni_fa(giorni),
                      livello_rischio=rischio, note=f"{rischio} {giorni}"),
        )  # fmt: skip

    righe = repo["ispezioni"].a_rischio_alto(utente)

    # Q6 come approvata in M2-T4: gravità >= 3, cioè «medio» e «alto».
    assert [(r["rischio"], r["data_ispezione"]) for r in righe] == [
        ("Rischio alto", giorni_fa(2)),
        ("Rischio medio", giorni_fa(30)),
    ]
    assert righe[0]["codice"] == "A1" and righe[0]["note"] == "alto 2"


@pytest.mark.integration
def test_eliminare_unispezione(repo: dict, apiario_con_alveare: tuple) -> None:
    utente, _, alveare = apiario_con_alveare
    ispezione = repo["ispezioni"].crea(
        utente, Ispezione(alveare_id=alveare.id, data_ispezione=OGGI, livello_rischio="basso")
    )
    repo["ispezioni"].elimina(utente, ispezione.id)
    assert repo["ispezioni"].ispezioni_per_alveare(utente, alveare.id) == []
    with pytest.raises(ValidationError, match="non trovato"):
        repo["ispezioni"].elimina(utente, ispezione.id)


# --------------------------------------------------------------------------- #
# Raccolti
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_raccolti_dellapiario_con_e_senza_alveare(repo: dict, apiario_con_alveare: tuple) -> None:
    utente, apiario, alveare = apiario_con_alveare
    totale = repo["raccolti"].crea(
        utente,
        Raccolto(apiario_id=apiario.id, tipo_miele=TipoMiele.ACACIA, data_raccolto=giorni_fa(10),
                 quantita_kg="18.40"),
    )  # fmt: skip
    del_melario = repo["raccolti"].crea(
        utente,
        Raccolto(apiario_id=apiario.id, alveare_id=alveare.id, tipo_miele="castagno",
                 data_raccolto=giorni_fa(2), quantita_kg="6.25", note="Melario A1"),
    )  # fmt: skip

    assert repo["raccolti"].per_apiario(utente, apiario.id) == [del_melario, totale]

    repo["raccolti"].elimina(utente, totale.id)
    assert repo["raccolti"].per_apiario(utente, apiario.id) == [del_melario]


@pytest.mark.integration
def test_d8_lalveare_di_un_raccolto_deve_essere_dello_stesso_apiario(
    repo: dict, apiario_con_alveare: tuple
) -> None:
    utente, _, alveare = apiario_con_alveare
    altro_apiario = repo["apiari"].crea(Apiario(utente_id=utente, nome="Pianura"))

    with pytest.raises(ValidationError) as info:
        repo["raccolti"].crea(
            utente,
            Raccolto(apiario_id=altro_apiario.id, alveare_id=alveare.id, tipo_miele="acacia",
                     data_raccolto=OGGI, quantita_kg=3),
        )  # fmt: skip
    assert info.value.campo == "alveare_id"
    assert repo["raccolti"].per_apiario(utente, altro_apiario.id) == []


@pytest.mark.integration
def test_q5_produzione_per_anno_e_tipo(repo: dict, apiario_con_alveare: tuple) -> None:
    utente, apiario, _ = apiario_con_alveare
    anno = OGGI.year
    for data, tipo, kg in (
        (date(anno - 1, 6, 1), "acacia", "10.00"),
        (date(anno - 1, 7, 1), "acacia", "5.50"),
        (date(anno - 1, 8, 1), "castagno", "4.00"),
        (OGGI, "acacia", "2.25"),
    ):
        repo["raccolti"].crea(
            utente,
            Raccolto(apiario_id=apiario.id, tipo_miele=tipo, data_raccolto=data, quantita_kg=kg),
        )

    righe = repo["raccolti"].produzione_per_stagione(utente)

    assert [(r["anno"], r["tipo"], r["totale_kg"]) for r in righe] == [
        (anno, "Acacia", Decimal("2.25")),
        (anno - 1, "Acacia", Decimal("15.50")),
        (anno - 1, "Castagno", Decimal("4.00")),
    ]


# --------------------------------------------------------------------------- #
# Dashboard e cancellazione dell'utente
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_q1_riepilogo_della_dashboard(
    repo: dict, database_test: Database, apiario_con_alveare: tuple
) -> None:
    utente, apiario, alveare = apiario_con_alveare
    repo["alveari"].crea(utente, Alveare(apiario_id=apiario.id, codice="SPENTO", stato="morto",
                                         attivo=False))  # fmt: skip
    for giorni in (1, 29, 31):
        repo["ispezioni"].crea(
            utente,
            Ispezione(
                alveare_id=alveare.id, data_ispezione=giorni_fa(giorni), livello_rischio="basso"
            ),
        )
    for data, kg in ((OGGI, "7.50"), (date(OGGI.year - 1, 6, 1), "100.00")):
        repo["raccolti"].crea(
            utente, Raccolto(apiario_id=apiario.id, tipo_miele="acacia", data_raccolto=data,
                             quantita_kg=kg)
        )  # fmt: skip

    assert DashboardRepository(database_test).riepilogo(utente) == {
        "alveari_attivi": 1,
        "ispezioni_30_giorni": 2,
        "produzione_stagione_kg": Decimal("7.50"),
    }


@pytest.mark.integration
def test_q11_cancellare_un_utente_porta_via_tutti_i_suoi_dati(
    repo: dict, database_test: Database, apiario_con_alveare: tuple
) -> None:
    utente, apiario, alveare = apiario_con_alveare
    ispezione = repo["ispezioni"].crea(
        utente, Ispezione(alveare_id=alveare.id, data_ispezione=OGGI, livello_rischio="basso")
    )
    raccolto = repo["raccolti"].crea(
        utente,
        Raccolto(apiario_id=apiario.id, tipo_miele="acacia", data_raccolto=OGGI, quantita_kg=1),
    )

    UtentiRepository(database_test).elimina(utente)

    assert _conta(database_test, "utenti", "id", [utente]) == 0
    assert _conta(database_test, "apiari", "id", [apiario.id]) == 0
    assert _conta(database_test, "alveari", "id", [alveare.id]) == 0
    assert _conta(database_test, "ispezioni", "id", [ispezione.id]) == 0
    assert _conta(database_test, "raccolti", "id", [raccolto.id]) == 0
    with pytest.raises(ValidationError, match="non trovato"):
        UtentiRepository(database_test).elimina(utente)


# --------------------------------------------------------------------------- #
# Riferimento USDA
# --------------------------------------------------------------------------- #


@pytest.fixture
def produzione_di_prova(database_test: Database) -> Iterator[None]:
    """HI con tutti i 15 anni, NV con 3: righe tolte a fine test."""
    righe = [("HI", a) for a in range(1998, 2013)] + [("NV", a) for a in (2010, 2011, 2012)]
    with database_test.transazione() as cursore:
        for stato, anno in righe:
            cursore.execute(
                "INSERT INTO produzione_usda (codice_stato, anno, numero_colonie, "
                "resa_per_colonia_kg, produzione_totale_kg, scorte_kg, prezzo_per_kg_usd, "
                "valore_produzione_usd) VALUES (%s, %s, %s, %s, 1, 1, 1, 1)",
                (stato, anno, 1000 + anno - 1998, Decimal("40.5") + (anno - 1998)),
            )
    yield
    _esegui(database_test, "DELETE FROM produzione_usda WHERE codice_stato IN ('HI', 'NV')")


@pytest.mark.integration
def test_q7_serie_storica_di_uno_stato(database_test: Database, produzione_di_prova: None) -> None:
    serie = ProduzioneUsdaRepository(database_test).serie_storica_stato("NV")
    assert serie == [
        {"anno": 2010, "resa_per_colonia_kg": Decimal("52.5000"), "numero_colonie": 1012},
        {"anno": 2011, "resa_per_colonia_kg": Decimal("53.5000"), "numero_colonie": 1013},
        {"anno": 2012, "resa_per_colonia_kg": Decimal("54.5000"), "numero_colonie": 1014},
    ]
    assert ProduzioneUsdaRepository(database_test).serie_storica_stato("ZZ") == []


@pytest.mark.integration
def test_q8_dati_di_addestramento_solo_stati_con_la_serie_completa(
    database_test: Database, produzione_di_prova: None
) -> None:
    righe = ProduzioneUsdaRepository(database_test).dati_addestramento()
    assert {r["codice_stato"] for r in righe} == {"HI"}  # NV ha solo 3 anni (R10)
    assert [r["anno"] for r in righe] == list(range(1998, 2013))
    assert set(righe[0]) == {"codice_stato", "anno", "numero_colonie", "resa_per_colonia_kg"}


@pytest.mark.integration
def test_i_codici_degli_stati_sono_i_44_del_seed(database_test: Database) -> None:
    codici = ProduzioneUsdaRepository(database_test).codici_stati()
    assert len(codici) == 44 and {"AL", "HI", "WY"} <= codici


# --------------------------------------------------------------------------- #
# Previsioni e conversazioni
# --------------------------------------------------------------------------- #


@pytest.fixture
def modello_di_prova(database_test: Database) -> Iterator[str]:
    versione = f"test-{uuid.uuid4().hex[:8]}"
    _esegui(
        database_test,
        "INSERT INTO modelli (versione, algoritmo, addestrato_il, righe_addestramento, "
        "variabili_usate, mae_kg, rmse_kg, r2, percorso_file) "
        "VALUES (%s, 'Prova', NOW(), 600, '[\"anno\"]', 3.8, 5.1, 0.7, 'models/prova.joblib')",
        (versione,),
    )
    yield versione
    _esegui(database_test, "DELETE FROM previsioni WHERE versione_modello = %s", (versione,))
    _esegui(database_test, "DELETE FROM modelli WHERE versione = %s", (versione,))


@pytest.mark.integration
def test_previsione_salvata_e_q9_con_il_modello_che_la_produce(
    database_test: Database, apiario_con_alveare: tuple, modello_di_prova: str,
    nuovo_utente: Callable[[], int],
) -> None:  # fmt: skip
    utente, _, alveare = apiario_con_alveare
    previsioni = PrevisioniRepository(database_test)
    base = {"utente_id": utente, "versione_modello": modello_di_prova,
            "codice_stato_riferimento": "CA", "anno_riferimento": 2026}  # fmt: skip

    prima = previsioni.salva_previsione(
        Previsione(
            **base, stima_kg="30.00", limite_inferiore_kg="22.00", limite_superiore_kg="38.00"
        )
    )
    seconda = previsioni.salva_previsione(
        Previsione(**base, alveare_id=alveare.id, stima_kg=31, limite_inferiore_kg=23,
                   limite_superiore_kg=39)
    )  # fmt: skip

    righe = previsioni.ultime_previsioni(utente)
    assert [r["id"] for r in righe] == [seconda.id, prima.id]
    assert righe[0]["alveare"] == "A1" and righe[1]["alveare"] is None
    assert righe[0]["mae_kg"] == Decimal("3.800") and righe[0]["versione"] == modello_di_prova
    intervallo = ("limite_inferiore_kg", "stima_kg", "limite_superiore_kg")
    assert [righe[1][c] for c in intervallo] == [Decimal(v) for v in ("22.00", "30.00", "38.00")]
    assert previsioni.ultime_previsioni(utente, limite=1)[0]["id"] == seconda.id
    assert previsioni.ultime_previsioni(nuovo_utente()) == []

    with pytest.raises(ValidationError) as info:
        previsioni.salva_previsione(
            Previsione(**{**base, "utente_id": nuovo_utente()}, alveare_id=alveare.id,
                       stima_kg=1, limite_inferiore_kg=0, limite_superiore_kg=2)
        )  # fmt: skip
    assert info.value.campo == "alveare_id"


@pytest.mark.integration
def test_una_previsione_con_un_modello_inesistente_e_rifiutata_dal_database(
    database_test: Database, nuovo_utente: Callable[[], int]
) -> None:
    with pytest.raises(DatabaseError):
        PrevisioniRepository(database_test).salva_previsione(
            Previsione(utente_id=nuovo_utente(), versione_modello="non-esiste",
                       codice_stato_riferimento="CA", anno_riferimento=2026, stima_kg=1,
                       limite_inferiore_kg=0, limite_superiore_kg=2)
        )  # fmt: skip


@pytest.mark.integration
def test_q10_i_messaggi_di_una_conversazione_in_ordine(
    database_test: Database, nuovo_utente: Callable[[], int]
) -> None:
    utente, altro = nuovo_utente(), nuovo_utente()
    with database_test.transazione() as cursore:
        cursore.execute("INSERT INTO conversazioni (utente_id) VALUES (%s)", (utente,))
        conversazione = cursore.lastrowid
        for ruolo, testo in (("utente", "Come sta A3?"), ("assistente", "Sospetta varroa.")):
            cursore.execute(
                "INSERT INTO messaggi (conversazione_id, ruolo, contenuto) VALUES (%s, %s, %s)",
                (conversazione, ruolo, testo),
            )

    messaggi = ConversazioniRepository(database_test).messaggi(utente, conversazione)

    assert [(m["ruolo"], m["contenuto"]) for m in messaggi] == [
        ("utente", "Come sta A3?"),
        ("assistente", "Sospetta varroa."),
    ]
    assert ConversazioniRepository(database_test).messaggi(altro, conversazione) == []


# --------------------------------------------------------------------------- #
# Controlli statici (girano anche senza MySQL)
# --------------------------------------------------------------------------- #

_SQL = re.compile(r"\b(SELECT|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b")


def _stringhe_di_codice(file: Path) -> list[str]:
    """Le stringhe del modulo, docstring escluse (gli esempi d'uso non sono query)."""
    albero = ast.parse(file.read_text(encoding="utf-8"))
    tipi_con_docstring = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    docstring = {
        id(nodo.body[0].value)
        for nodo in ast.walk(albero)
        if isinstance(nodo, tipi_con_docstring)
        and nodo.body
        and isinstance(nodo.body[0], ast.Expr)
        and isinstance(nodo.body[0].value, ast.Constant)
    }
    return [
        nodo.value
        for nodo in ast.walk(albero)
        if isinstance(nodo, ast.Constant)
        and isinstance(nodo.value, str)
        and id(nodo) not in docstring
    ]


def test_nessun_sql_fuori_dai_repository() -> None:
    """DoD M3-T3. Eccezione dichiarata: il `SELECT 1` di database.py e healthcheck.py."""
    for file in sorted(PACCHETTO.rglob("*.py")):
        if file.name.startswith("repositories"):
            continue
        query = [s for s in _stringhe_di_codice(file) if _SQL.search(s) and s != "SELECT 1"]
        assert not query, f"SQL fuori dai repository in {file.name}: {query}"


def test_il_controllo_sullsql_riconosce_una_query() -> None:
    """Il controllo sopra non deve passare perché non vede niente."""
    assert any(_SQL.search(s) for s in _stringhe_di_codice(PACCHETTO / "repositories.py"))


def test_i_file_dei_repository_restano_sotto_le_400_righe() -> None:
    for file in PACCHETTO.glob("repositories*.py"):
        righe = len(file.read_text(encoding="utf-8").splitlines())
        assert righe <= 400, f"{file.name}: {righe} righe"
