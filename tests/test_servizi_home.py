"""I servizi della Home (M6-T1): panoramica, elenco degli apiari, stato del modello."""

from __future__ import annotations

from decimal import Decimal

import pytest

from beewatch.exceptions import DatabaseError, ModelError, ValidationError
from beewatch.models import Apiario
from beewatch.services import ApiarioScelta, Panoramica, Servizi, StatoModello


class DashboardFinto:
    def __init__(self):
        self.utenti: list[int] = []

    def riepilogo(self, utente_id):
        self.utenti.append(utente_id)
        return {
            "alveari_attivi": 3,
            "ispezioni_30_giorni": 9,
            "produzione_stagione_kg": Decimal("42.50"),
        }


class ApiariFinti:
    def elenca(self, utente_id):
        return [
            Apiario(utente_id=utente_id, nome="Collina", localita="Segreta", id=1),
            Apiario(utente_id=utente_id, nome="Valle", id=2),
        ]


class AlveariFinti:
    def trascurati(self, utente_id):
        return [{"id": 1}]


class PredittoreStub:
    versione = "v9"
    metadati = {
        "algoritmo": "RandomForestRegressor",
        "metriche": {"hold_out_2010_2012": {"mae_kg": 3.4991}},
        "addestrato_il": "2026-10-23T12:00:00+00:00",
        "addestramento": {"righe": 600},
    }


def servizi(**extra) -> Servizi:
    return Servizi(
        None,
        crea_predittore=extra.pop("crea_predittore", PredittoreStub),
        dashboard=extra.pop("dashboard", DashboardFinto()),
        apiari=ApiariFinti(),
        alveari=AlveariFinti(),
        **extra,
    )


def test_la_panoramica_riunisce_le_caselle_e_gli_apiari():
    s = servizi()

    p = s.panoramica(1)

    assert p == Panoramica(
        apiari=(ApiarioScelta(1, "Collina"), ApiarioScelta(2, "Valle")),
        alveari_attivi=3,
        ispezioni_30_giorni=9,
        produzione_stagione_kg=42.5,
        alveari_da_controllare=1,
    )
    assert isinstance(p.produzione_stagione_kg, float)  # non un Decimal: si può mettere in cache


def test_la_panoramica_chiede_i_dati_dellutente_giusto():
    dashboard = DashboardFinto()
    servizi(dashboard=dashboard).panoramica(7)
    assert dashboard.utenti == [7]


def test_lelenco_degli_apiari_non_porta_ne_coordinate_ne_localita():
    scelte = servizi().elenca_apiari(1)
    assert scelte == [ApiarioScelta(1, "Collina"), ApiarioScelta(2, "Valle")]
    assert not hasattr(scelte[0], "localita") and not hasattr(scelte[0], "latitudine")


@pytest.mark.parametrize("utente", [0, -1, None, "1", True])
def test_utente_non_valido_nei_servizi_della_home(utente):
    for chiamata in (servizi().panoramica, servizi().elenca_apiari):
        with pytest.raises(ValidationError) as errore:
            chiamata(utente)
        assert errore.value.campo == "utente_id"


def test_un_errore_del_database_arriva_cosi_com_e():
    class Rotto:
        def riepilogo(self, utente_id):
            raise DatabaseError("MySQL non risponde")

    with pytest.raises(DatabaseError, match="MySQL"):
        servizi(dashboard=Rotto()).panoramica(1)


def test_lo_stato_del_modello_dice_versione_e_errore_medio():
    assert servizi().stato_modello() == StatoModello(
        versione="v9",
        algoritmo="RandomForestRegressor",
        mae_kg=3.4991,
        addestrato_il="2026-10-23T12:00:00+00:00",
        righe_addestramento=600,
    )


def test_senza_il_modello_lo_stato_e_un_model_error():
    def manca():
        raise ModelError("Il modello non è stato trovato.")

    with pytest.raises(ModelError, match="non è stato trovato"):
        servizi(crea_predittore=manca).stato_modello()


def test_la_descrizione_del_provider_si_passa_ai_servizi_e_ha_un_valore_di_ripiego():
    assert servizi(descrizione_llm="m via ollama").descrizione_llm == "m via ollama"
    assert servizi().descrizione_llm == "non configurato"
