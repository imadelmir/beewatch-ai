"""Test del servizio di previsione, M4-T8.

Unitari, con repository e predittore finti: nessun database, nessun file di modello. Si
verifica che gli ingressi non validi diano un errore chiaro, che le feature usino solo gli anni
precedenti, che la stima abbia sempre il suo intervallo e rispetti la regola «intervallo più
largo della stima», che il salvataggio porti versione e feature e che il predittore si carichi
una volta sola. Integration: il servizio vero, con MySQL e il modello committato.
"""

from __future__ import annotations

import json
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from beewatch.database import Database
from beewatch.exceptions import ModelError, ValidationError
from beewatch.ml.features import FEATURE
from beewatch.ml.predictor import Predittore, Stima
from beewatch.models import Previsione
from beewatch.repositories import AlveariRepository
from beewatch.repositories_riferimento import (
    ModelliRepository,
    PrevisioniRepository,
    ProduzioneUsdaRepository,
)
from beewatch.services import RisultatoPrevisione, Servizi, StatoPrevedibile, crea_servizi

# --------------------------------------------------------------------------- #
# Finti
# --------------------------------------------------------------------------- #

RESE = {1998: 30.0, 1999: 31.0, 2000: 32.0, 2001: 29.0, 2002: 28.0}  # kg per colonia
COLONIE = {1998: 1000, 1999: 1100, 2000: 1200, 2001: 1300, 2002: 1400}


class ProduzioneFinta:
    """Uno stato («CA») con la serie completa 1998–2002; ne esiste anche uno incompleto."""

    def __init__(self, rese: dict[int, float] | None = None) -> None:
        self.rese = rese or RESE

    def stati_del_pannello(self) -> list[dict]:
        anni = sorted(self.rese)
        return [
            {"codice": "CA", "nome": "California", "primo_anno": anni[0], "ultimo_anno": anni[-1]}
        ]

    def serie_storica_stato(self, codice_stato: str) -> list[dict]:
        return [
            {
                "anno": a,
                "resa_per_colonia_kg": Decimal(str(r)),
                "numero_colonie": COLONIE.get(a, 1500),
            }
            for a, r in sorted(self.rese.items())
        ]


class PredittoreFinto:
    """Prevede la media delle rese passate; l'intervallo viene dal costruttore."""

    versione = "v-finto"
    percorso = Path("models/finto.joblib")

    def __init__(self, inferiore: float = -3.0, superiore: float = 4.0) -> None:
        self.inferiore, self.superiore = inferiore, superiore
        self.ricevute: list[dict] = []
        self.metadati: dict[str, Any] = {
            "metriche": {"hold_out_2010_2012": {"mae_kg": 3.5, "rmse_kg": 4.5, "r2": 0.6}},
            "versione": "v-finto",
            "algoritmo": "finto",
            "addestrato_il": "2026-01-01T00:00:00+00:00",
            "addestramento": {"righe": 10, "strategia": "prova"},
            "feature": list(FEATURE),
            "importanza_variabili": {"valori": {n: {"media_kg": 0.1} for n in FEATURE}},
        }

    def stima(self, riga: dict) -> Stima:
        self.ricevute.append(dict(riga))
        valore = float(riga["resa_media_3_anni_prima"])
        return Stima(valore, valore + self.inferiore, valore + self.superiore, 0.8)


class PrevisioniFinte:
    def __init__(self, errore: Exception | None = None) -> None:
        self.salvate: list[Previsione] = []
        self.errore = errore
        self.storico_chiesto: list[tuple[int, int]] = []

    def salva_previsione(self, previsione: Previsione) -> Previsione:
        if self.errore:
            raise self.errore
        self.salvate.append(previsione)
        return Previsione(**{**previsione.__dict__, "id": len(self.salvate)})

    def ultime_previsioni(self, utente_id: int, limite: int) -> list[dict]:
        self.storico_chiesto.append((utente_id, limite))
        return [{"id": 1}]


class ModelliFinti:
    def __init__(self, presente: bool = False) -> None:
        self.presente = presente
        self.registrati: list[dict] = []

    def trova(self, versione: str):
        return {"versione": versione} if self.presente else None

    def registra(self, riga: dict) -> None:
        self.registrati.append(riga)


def servizi(
    produzione: ProduzioneFinta | None = None,
    predittore: PredittoreFinto | None = None,
    previsioni: PrevisioniFinte | None = None,
    modelli: ModelliFinti | None = None,
) -> tuple[Servizi, PredittoreFinto, PrevisioniFinte, ModelliFinti]:
    predittore = predittore or PredittoreFinto()
    previsioni = previsioni or PrevisioniFinte()
    modelli = modelli or ModelliFinti()
    s = Servizi(
        None,
        crea_predittore=lambda: predittore,
        produzione=produzione or ProduzioneFinta(),
        previsioni=previsioni,
        modelli=modelli,
    )
    return s, predittore, previsioni, modelli


# --------------------------------------------------------------------------- #
# Stati e anni
# --------------------------------------------------------------------------- #


def test_gli_stati_prevedibili_hanno_gli_anni_che_il_modello_accetta() -> None:
    s, *_ = servizi()
    assert s.stati_prevedibili() == [
        StatoPrevedibile(codice="CA", nome="California", primo_anno=1999, ultimo_anno=2003)
    ]  # dal secondo anno dei dati all'anno dopo l'ultimo


# --------------------------------------------------------------------------- #
# Ingressi non validi
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("utente", [0, -1, "1", None, True, 1.5])
def test_un_utente_non_valido_e_un_errore_che_nomina_il_campo(utente) -> None:
    s, *_ = servizi()
    with pytest.raises(ValidationError) as errore:
        s.prevedi_produzione(utente, None, "CA", 2003)
    assert errore.value.campo == "utente_id"


@pytest.mark.parametrize("alveare", [0, -3, "3", True, 2.0])
def test_un_alveare_non_valido_e_un_errore_che_nomina_il_campo(alveare) -> None:
    s, *_ = servizi()
    with pytest.raises(ValidationError) as errore:
        s.prevedi_produzione(1, alveare, "CA", 2003)
    assert errore.value.campo == "alveare_id"


@pytest.mark.parametrize("stato", ["MD", "ZZ", "", "  ", None, 5, "CAL"])
def test_uno_stato_fuori_dal_pannello_e_un_errore_che_lo_dice(stato) -> None:
    s, *_ = servizi()
    with pytest.raises(ValidationError, match="non fa parte") as errore:
        s.prevedi_produzione(1, None, stato, 2003)
    assert errore.value.campo == "codice_stato"


@pytest.mark.parametrize("anno", [1998, 2004, 1990, 2003.0, "2003", None, True])
def test_un_anno_fuori_intervallo_o_non_intero_e_un_errore_con_gli_anni_validi(anno) -> None:
    s, *_ = servizi()
    with pytest.raises(ValidationError, match="dal 1999 al 2003") as errore:
        s.prevedi_produzione(1, None, "CA", anno)
    assert errore.value.campo == "anno"


def test_lo_stato_si_normalizza_maiuscolo_e_senza_spazi() -> None:
    s, *_ = servizi()
    assert s.prevedi_produzione(1, None, " ca ", 2003).codice_stato == "CA"


def test_con_ingressi_non_validi_non_si_carica_il_modello_ne_si_salva_niente() -> None:
    caricamenti = []
    previsioni = PrevisioniFinte()
    s = Servizi(
        None,
        crea_predittore=lambda: caricamenti.append(1) or PredittoreFinto(),
        produzione=ProduzioneFinta(),
        previsioni=previsioni,
        modelli=ModelliFinti(),
    )

    with pytest.raises(ValidationError):
        s.prevedi_produzione(1, None, "CA", 1990)

    assert caricamenti == [] and previsioni.salvate == []


# --------------------------------------------------------------------------- #
# Le feature: solo gli anni precedenti
# --------------------------------------------------------------------------- #


def test_le_feature_dellanno_futuro_vengono_dai_tre_anni_prima() -> None:
    s, predittore, *_ = servizi()

    risultato = s.prevedi_produzione(1, None, "CA", 2003)

    assert predittore.ricevute == [
        {
            "codice_stato": "CA",
            "anno": 2003,
            "resa_anno_prima": 28.0,
            "resa_media_3_anni_prima": pytest.approx((32.0 + 29.0 + 28.0) / 3),
            "colonie_anno_prima": 1400.0,
        }
    ]
    assert tuple(risultato.feature) == tuple(FEATURE)  # nell'ordine del modello


def test_per_un_anno_gia_nei_dati_la_resa_di_quellanno_non_entra_nelle_feature() -> None:
    base = servizi()[0].prevedi_produzione(1, None, "CA", 2001)
    alterate = {**RESE, 2001: 999.0, 2002: 999.0}  # l'anno da prevedere e quello dopo

    s, *_ = servizi(produzione=ProduzioneFinta(alterate))
    dopo = s.prevedi_produzione(1, None, "CA", 2001)

    assert dopo.feature == base.feature  # nessuna informazione dal futuro
    assert dopo.stima_kg == base.stima_kg


def test_i_valori_delle_feature_si_scrivono_come_json_senza_nan() -> None:
    risultato = servizi()[0].prevedi_produzione(1, None, "CA", 1999)  # un solo anno di storia

    json.dumps(risultato.feature, allow_nan=False)
    assert risultato.feature["resa_anno_prima"] == 30.0
    assert (
        risultato.feature["resa_media_3_anni_prima"] == 30.0
    )  # la media dei pochi anni che ci sono


def test_i_valori_mancanti_arrivano_al_predittore_come_nan() -> None:
    class SenzaStoria(ProduzioneFinta):
        def serie_storica_stato(self, codice_stato: str) -> list[dict]:
            return [r for r in super().serie_storica_stato(codice_stato) if r["anno"] != 2002]

    s, predittore, *_ = servizi(produzione=SenzaStoria())

    risultato = s.prevedi_produzione(1, None, "CA", 2003)

    assert risultato.feature["resa_anno_prima"] is None  # al database e al JSON: None
    assert np.isnan(predittore.ricevute[0]["resa_anno_prima"])  # al modello: NaN


# --------------------------------------------------------------------------- #
# Stima, intervallo, regola
# --------------------------------------------------------------------------- #


def test_il_risultato_ha_sempre_lintervallo_e_la_stima_dentro() -> None:
    s, *_ = servizi(predittore=PredittoreFinto(-3.4, 4.2))

    r = s.prevedi_produzione(1, 7, "CA", 2003)  # media 29,67

    assert isinstance(r, RisultatoPrevisione)
    assert r.stima_kg == 30  # al chilo più vicino
    assert (r.limite_inferiore_kg, r.limite_superiore_kg) == (
        26,
        34,
    )  # verso l'esterno: 26,27 e 33,87
    assert r.limite_inferiore_kg <= r.stima_kg <= r.limite_superiore_kg
    assert r.livello == 0.8 and r.errore_medio_kg == 3.5
    assert (r.nome_stato, r.anno, r.alveare_id, r.utente_id) == ("California", 2003, 7, 1)
    assert all(
        isinstance(v, int) for v in (r.stima_kg, r.limite_inferiore_kg, r.limite_superiore_kg)
    )


def test_gli_estremi_si_arrotondano_verso_lesterno_e_non_restringono_lintervallo() -> None:
    s, *_ = servizi(predittore=PredittoreFinto(-0.01, 0.01))

    r = s.prevedi_produzione(1, None, "CA", 2003)

    assert (r.limite_inferiore_kg, r.stima_kg, r.limite_superiore_kg) == (
        29,
        30,
        30,
    )  # 29,66 | 29,67 | 29,68


def test_lanno_dopo_gli_ultimi_dati_e_una_previsione_e_gli_altri_una_prova_a_ritroso() -> None:
    s, *_ = servizi()
    assert s.prevedi_produzione(1, None, "CA", 2003).retrospettiva is False
    assert s.prevedi_produzione(1, None, "CA", 2002).retrospettiva is True


def test_se_lintervallo_e_piu_largo_della_stima_non_si_mostra_e_non_si_salva() -> None:
    s, _, previsioni, modelli = servizi(predittore=PredittoreFinto(-20.0, 20.0))  # 9 … 50: 41 > 30

    r = s.prevedi_produzione(1, None, "CA", 2003)

    assert r.mostra_stima is False and r.id is None
    assert "più largo della stima" in r.messaggio and "41 kg" in r.messaggio
    assert previsioni.salvate == [] and modelli.registrati == []
    assert r.limite_inferiore_kg < r.stima_kg < r.limite_superiore_kg  # l'intervallo c'è comunque


def test_a_parita_di_larghezza_e_stima_la_stima_si_mostra() -> None:
    s, *_ = servizi(predittore=PredittoreFinto(-14.6, 14.4))  # 15,07 → 15 e 44,07 → 45: ampiezza 30

    r = s.prevedi_produzione(1, None, "CA", 2003)

    assert r.limite_superiore_kg - r.limite_inferiore_kg == r.stima_kg
    assert r.mostra_stima is True and r.messaggio is None


# --------------------------------------------------------------------------- #
# Salvataggio
# --------------------------------------------------------------------------- #


def test_la_previsione_si_salva_con_versione_del_modello_e_feature() -> None:
    s, _, previsioni, _ = servizi()

    r = s.prevedi_produzione(5, 9, "CA", 2003)

    assert r.id == 1 and len(previsioni.salvate) == 1
    p = previsioni.salvate[0]
    assert (p.utente_id, p.alveare_id, p.versione_modello) == (5, 9, "v-finto")
    assert (p.codice_stato_riferimento, p.anno_riferimento) == ("CA", 2003)
    assert (p.stima_kg, p.limite_inferiore_kg, p.limite_superiore_kg) == (
        Decimal(30), Decimal(26), Decimal(34)
    )  # fmt: skip
    assert p.feature == r.feature and set(p.feature) == set(FEATURE)


def test_un_alveare_che_non_e_dellutente_e_un_errore_del_repository() -> None:
    previsioni = PrevisioniFinte(errore=ValidationError("Alveare non trovato.", campo="alveare_id"))
    s, *_ = servizi(previsioni=previsioni)

    with pytest.raises(ValidationError) as errore:
        s.prevedi_produzione(1, 99, "CA", 2003)

    assert errore.value.campo == "alveare_id"


def test_se_il_modello_non_e_nella_tabella_lo_si_registra_dai_metadati() -> None:
    s, predittore, _, modelli = servizi(modelli=ModelliFinti(presente=False))

    s.prevedi_produzione(1, None, "CA", 2003)
    s.prevedi_produzione(1, None, "CA", 2002)

    assert len(modelli.registrati) == 2  # il finto non ricorda: in produzione `trova` lo dirà
    riga = modelli.registrati[0]
    assert riga["versione"] == "v-finto" and riga["attivo"] is True
    assert riga["percorso_file"].endswith("finto.joblib")


def test_se_il_modello_e_gia_nella_tabella_non_si_tocca() -> None:
    s, _, _, modelli = servizi(modelli=ModelliFinti(presente=True))
    s.prevedi_produzione(1, None, "CA", 2003)
    assert modelli.registrati == []


def test_lo_storico_chiede_al_repository_per_lutente() -> None:
    s, _, previsioni, _ = servizi()

    assert s.storico_previsioni(4, limite=5) == [{"id": 1}]
    assert previsioni.storico_chiesto == [(4, 5)]
    with pytest.raises(ValidationError):
        s.storico_previsioni(0)


# --------------------------------------------------------------------------- #
# Il predittore: una volta sola, e solo quando serve
# --------------------------------------------------------------------------- #


def test_il_predittore_non_si_carica_finche_non_serve() -> None:
    caricamenti: list[int] = []
    s = Servizi(
        None,
        crea_predittore=lambda: caricamenti.append(1) or PredittoreFinto(),
        produzione=ProduzioneFinta(),
        previsioni=PrevisioniFinte(),
        modelli=ModelliFinti(),
    )

    s.stati_prevedibili()
    assert caricamenti == []

    for _ in range(3):
        s.prevedi_produzione(1, None, "CA", 2003)
    assert caricamenti == [1]  # una volta sola


def test_piu_thread_caricano_il_predittore_una_volta_sola() -> None:
    caricamenti: list[int] = []

    def lento() -> PredittoreFinto:
        caricamenti.append(1)
        time.sleep(0.05)
        return PredittoreFinto()

    s = Servizi(None, crea_predittore=lento, produzione=ProduzioneFinta(),
                previsioni=PrevisioniFinte(), modelli=ModelliFinti())  # fmt: skip
    trovati: list[object] = []
    thread = [threading.Thread(target=lambda: trovati.append(s.predittore)) for _ in range(8)]

    for t in thread:
        t.start()
    for t in thread:
        t.join()

    assert caricamenti == [1] and len({id(p) for p in trovati}) == 1


def test_se_il_modello_manca_lerrore_arriva_e_il_tentativo_dopo_riprova() -> None:
    tentativi: list[int] = []

    def crea() -> PredittoreFinto:
        tentativi.append(1)
        if len(tentativi) == 1:
            raise ModelError("Il modello non è stato trovato.")
        return PredittoreFinto()

    s = Servizi(None, crea_predittore=crea, produzione=ProduzioneFinta(),
                previsioni=PrevisioniFinte(), modelli=ModelliFinti())  # fmt: skip

    with pytest.raises(ModelError, match="non è stato trovato"):
        s.prevedi_produzione(1, None, "CA", 2003)
    assert s.prevedi_produzione(1, None, "CA", 2003).mostra_stima is True
    assert len(tentativi) == 2


def test_crea_servizi_usa_la_configurazione_senza_aprire_connessioni(monkeypatch) -> None:
    from types import SimpleNamespace

    from beewatch import services

    percorsi: list[Path] = []
    monkeypatch.setattr(services, "Database", lambda cfg: ("database", cfg))
    monkeypatch.setattr(services, "Predittore", lambda percorso: percorsi.append(percorso) or "p")
    configurazione = SimpleNamespace(database="cfg-db", percorso_modello=Path("m.joblib"))

    s = crea_servizi(configurazione)

    assert isinstance(s, Servizi) and percorsi == []  # il modello non si carica adesso
    assert s.predittore == "p" and percorsi == [Path("m.joblib")]


# --------------------------------------------------------------------------- #
# Integration: servizio vero, MySQL e modello committato
# --------------------------------------------------------------------------- #

PERCORSO_COMMITTATO = Path(__file__).resolve().parents[1] / "models" / "produzione_v1.joblib"


@pytest.fixture
def puliti(database_test: Database):
    def pulisci() -> None:
        with database_test.transazione() as cursore:
            cursore.execute("DELETE FROM previsioni")
            cursore.execute("DELETE FROM modelli")

    pulisci()
    yield
    pulisci()


@pytest.fixture
def servizi_veri(database_test: Database, dataset_nel_database: None, puliti: None) -> Servizi:
    return Servizi(database_test, crea_predittore=lambda: Predittore(PERCORSO_COMMITTATO))


@pytest.mark.integration
def test_integrazione_gli_stati_prevedibili_sono_i_quaranta_del_pannello(
    servizi_veri: Servizi,
) -> None:
    stati = servizi_veri.stati_prevedibili()

    assert len(stati) == 40
    assert {s.codice for s in stati}.isdisjoint({"MD", "NV", "OK", "SC"})  # serie incomplete
    california = next(s for s in stati if s.codice == "CA")
    assert (california.nome, california.primo_anno, california.ultimo_anno) == (
        "California",
        1999,
        2013,
    )


@pytest.mark.integration
def test_integrazione_prevedere_il_2013_salva_la_previsione_e_registra_il_modello(
    servizi_veri: Servizi, database_test: Database
) -> None:
    alveare = AlveariRepository(database_test).trova_alveari_attivi(1)[0]

    r = servizi_veri.prevedi_produzione(1, alveare.id, "CA", 2013)

    assert r.mostra_stima and r.retrospettiva is False and r.id is not None
    assert r.limite_inferiore_kg <= r.stima_kg <= r.limite_superiore_kg
    assert (r.versione_modello, r.nome_stato) == ("v1.0.0", "California")
    # La stima è quella che il predittore dà con le feature dei dati del database.
    atteso = Predittore(PERCORSO_COMMITTATO).stima(r.feature)
    assert r.stima_kg == round(atteso.valore_kg)
    # Il modello è stato registrato (la tabella era vuota) e la previsione sta nello storico.
    assert ModelliRepository(database_test).attivo()["versione"] == "v1.0.0"
    storico = PrevisioniRepository(database_test).ultime_previsioni(1)
    assert [riga["id"] for riga in storico] == [r.id]
    assert storico[0]["feature_json"] == r.feature
    assert storico[0]["alveare"] == alveare.codice
    assert (storico[0]["stima_kg"], storico[0]["versione"]) == (Decimal(r.stima_kg), "v1.0.0")


@pytest.mark.integration
def test_integrazione_le_feature_vengono_dai_dati_del_database(
    servizi_veri: Servizi, database_test: Database
) -> None:
    serie = ProduzioneUsdaRepository(database_test).serie_storica_stato("CA")
    ultime = {r["anno"]: float(r["resa_per_colonia_kg"]) for r in serie}

    r = servizi_veri.prevedi_produzione(1, None, "CA", 2013)

    assert r.feature["resa_anno_prima"] == pytest.approx(ultime[2012])
    assert r.feature["resa_media_3_anni_prima"] == pytest.approx(
        (ultime[2012] + ultime[2011] + ultime[2010]) / 3
    )
    assert r.feature["anno"] == 2013 and r.feature["codice_stato"] == "CA"


@pytest.mark.integration
def test_integrazione_un_anno_gia_osservato_e_una_prova_a_ritroso(servizi_veri: Servizi) -> None:
    r = servizi_veri.prevedi_produzione(1, None, "ND", 2005)

    assert r.retrospettiva is True and r.id is not None


@pytest.mark.integration
def test_integrazione_un_alveare_di_un_altro_utente_e_rifiutato_e_non_salva(
    servizi_veri: Servizi, database_test: Database
) -> None:
    with database_test.transazione() as cursore:
        cursore.execute("SELECT id FROM alveari ORDER BY id LIMIT 1")
        alveare_id = cursore.fetchone()["id"]

    with pytest.raises(ValidationError, match="Alveare non trovato"):
        servizi_veri.prevedi_produzione(999, alveare_id, "CA", 2013)  # utente inesistente

    assert PrevisioniRepository(database_test).ultime_previsioni(999) == []


@pytest.mark.integration
def test_integrazione_due_previsioni_non_registrano_due_volte_il_modello(
    servizi_veri: Servizi, database_test: Database
) -> None:
    servizi_veri.prevedi_produzione(1, None, "CA", 2013)
    servizi_veri.prevedi_produzione(1, None, "ND", 2013)

    with database_test.transazione() as cursore:
        cursore.execute("SELECT COUNT(*) AS n FROM modelli")
        assert cursore.fetchone()["n"] == 1
    assert len(PrevisioniRepository(database_test).ultime_previsioni(1)) == 2
