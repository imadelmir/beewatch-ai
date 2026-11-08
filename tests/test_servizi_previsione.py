"""I servizi nuovi della pagina Previsione: parametri a mano e storico per alveare (M6-T5).

Unitari con i finti di `previsione_finta.py`; le prove con MySQL e il modello committato sono in
fondo a `test_services.py` (integration).
"""

from __future__ import annotations

import math
from decimal import Decimal

import numpy as np
import pytest
from previsione_finta import (
    FEATURE_INCOMPATIBILI,
    ModelliFinti,
    PredittoreFinto,
    PrevisioniInMemoria,
    ProduzioneFinta,
)

from beewatch.exceptions import ModelError, ValidationError
from beewatch.services import IntervalloParametro, Servizi

PARAMETRI = {
    "resa_anno_prima": 40.0,
    "resa_media_3_anni_prima": 42.0,
    "colonie_anno_prima": 420_000,
}


class ProduzioneContata(ProduzioneFinta):
    def __init__(self, **argomenti) -> None:
        super().__init__(**argomenti)
        self.letture = 0

    def dati_addestramento(self) -> list[dict]:
        self.letture += 1
        return super().dati_addestramento()


def servizi(
    predittore: PredittoreFinto | None = None, produzione: ProduzioneFinta | None = None
) -> tuple[Servizi, PredittoreFinto, PrevisioniInMemoria]:
    predittore = predittore or PredittoreFinto()
    previsioni = PrevisioniInMemoria({1: "A1", 2: "A2"})
    s = Servizi(
        None,
        crea_predittore=lambda: predittore,
        produzione=produzione or ProduzioneFinta(),
        previsioni=previsioni,
        modelli=ModelliFinti(),
    )
    return s, predittore, previsioni


# --------------------------------------------------------------------------- #
# Intervalli dei parametri
# --------------------------------------------------------------------------- #


def test_gli_intervalli_sono_il_minimo_e_il_massimo_delladdestramento():
    s, _, _ = servizi()

    resa, media, colonie = s.intervalli_parametri()

    assert resa == IntervalloParametro("resa_anno_prima", "Resa dell'anno prima", 30.0, 53.0, "kg")
    assert (media.campo, media.minimo, media.massimo) == ("resa_media_3_anni_prima", 30.0, 53.0)
    assert (colonie.minimo, colonie.massimo, colonie.unita) == (401_998, 452_012, "colonie")


def test_gli_intervalli_si_leggono_una_volta_sola():
    produzione = ProduzioneContata()
    s, _, _ = servizi(produzione=produzione)

    s.intervalli_parametri()
    s.intervalli_parametri()

    assert produzione.letture == 1


def test_senza_dati_di_addestramento_lo_dice_con_il_rimedio():
    s, _, _ = servizi(produzione=ProduzioneFinta(vuota=True))

    with pytest.raises(ModelError, match="run_etl.py"):
        s.intervalli_parametri()


# --------------------------------------------------------------------------- #
# Previsione con i parametri a mano
# --------------------------------------------------------------------------- #


def test_i_parametri_a_mano_arrivano_al_modello_e_la_simulazione_non_si_salva():
    s, predittore, previsioni = servizi()

    r = s.prevedi_con_parametri(1, " nd ", 2010, **PARAMETRI)

    assert predittore.ricevute == [{"codice_stato": "ND", "anno": 2010, **PARAMETRI}]
    assert (r.stima_kg, r.limite_inferiore_kg, r.limite_superiore_kg) == (42, 39, 46)
    assert r.parametri_manuali and r.mostra_stima
    assert r.id is None and r.alveare_id is None
    assert previsioni.salvate == []  # le simulazioni non entrano nello storico
    assert (r.nome_stato, r.versione_modello, r.errore_medio_kg) == ("North Dakota", "v-finto", 3.5)


def test_le_previsioni_sui_dati_non_sono_simulazioni():
    s, _, previsioni = servizi()

    r = s.prevedi_produzione(1, None, "ND", 2012)

    assert not r.parametri_manuali and r.id == 1 and len(previsioni.salvate) == 1


def test_i_parametri_accettano_interi_decimal_e_numeri_numpy():
    s, predittore, _ = servizi()

    s.prevedi_con_parametri(
        1, "CA", 2005, resa_anno_prima=31, resa_media_3_anni_prima=Decimal("31.5"),
        colonie_anno_prima=np.int64(410_000),
    )  # fmt: skip

    ricevuta = predittore.ricevute[0]
    assert ricevuta["resa_media_3_anni_prima"] == 31.5
    assert all(type(ricevuta[c]) is float for c in PARAMETRI)


@pytest.mark.parametrize(
    ("campo", "valore", "frammento"),
    [
        ("resa_anno_prima", 120.0, "da 30 a 53 kg"),
        ("resa_anno_prima", 29.9, "da 30 a 53 kg"),
        ("resa_media_3_anni_prima", 0, "da 30 a 53 kg"),
        ("colonie_anno_prima", 5_000_000, "da 401998 a 452012 colonie"),
    ],
)
def test_un_parametro_fuori_dalladdestramento_e_incompatibile(campo, valore, frammento):
    s, predittore, _ = servizi()

    with pytest.raises(ValidationError, match="non sa stimare") as errore:
        s.prevedi_con_parametri(1, "CA", 2005, **{**PARAMETRI, campo: valore})

    assert errore.value.campo == campo
    assert frammento in str(errore.value)
    assert predittore.ricevute == []  # il modello non viene nemmeno interrogato


@pytest.mark.parametrize("cattivo", [None, "40", True, math.nan, math.inf])
def test_un_parametro_che_non_e_un_numero_si_rifiuta(cattivo):
    s, _, _ = servizi()

    with pytest.raises(ValidationError, match="deve essere un numero") as errore:
        s.prevedi_con_parametri(1, "CA", 2005, **{**PARAMETRI, "resa_anno_prima": cattivo})
    assert errore.value.campo == "resa_anno_prima"


@pytest.mark.parametrize(
    ("stato", "anno", "campo"),
    [
        ("TX", 2005, "codice_stato"),
        ("CA", 1998, "anno"),
        ("CA", 2014, "anno"),
        ("CA", 2005.0, "anno"),
    ],
)
def test_stato_e_anno_seguono_le_regole_della_previsione(stato, anno, campo):
    s, _, _ = servizi()

    with pytest.raises(ValidationError) as errore:
        s.prevedi_con_parametri(1, stato, anno, **PARAMETRI)
    assert errore.value.campo == campo


def test_feature_incompatibili_col_modello_danno_un_modelerror_chiaro():
    s, _, previsioni = servizi(PredittoreFinto(errore=FEATURE_INCOMPATIBILI))

    with pytest.raises(ModelError, match="mancano le colonne"):
        s.prevedi_produzione(1, None, "CA", 2005)
    assert previsioni.salvate == []


def test_una_banda_piu_larga_della_stima_nasconde_il_valore_anche_nelle_simulazioni():
    s, _, _ = servizi(PredittoreFinto(inferiore=-40.0, superiore=40.0))

    r = s.prevedi_con_parametri(1, "CA", 2005, **PARAMETRI)

    assert not r.mostra_stima and "più largo della stima" in r.messaggio


# --------------------------------------------------------------------------- #
# Storico per alveare
# --------------------------------------------------------------------------- #


def test_lo_storico_si_restringe_a_un_alveare():
    s, _, _ = servizi()
    prima = s.prevedi_produzione(1, 2, "CA", 2005)
    s.prevedi_produzione(1, None, "ND", 2006)
    terza = s.prevedi_produzione(1, 2, "ND", 2007)
    s.prevedi_produzione(1, 1, "CA", 2008)

    assert [p["id"] for p in s.storico_previsioni(1, alveare_id=2)] == [terza.id, prima.id]
    assert [p["id"] for p in s.storico_previsioni(1)] == [4, 3, 2, 1]
    assert s.storico_previsioni(1, alveare_id=2)[0]["alveare"] == "A2"
    assert s.storico_previsioni(2) == []  # un altro utente


@pytest.mark.parametrize("cattivo", [0, -3, "2", True])
def test_lalveare_dello_storico_deve_essere_un_id_valido(cattivo):
    s, _, _ = servizi()

    with pytest.raises(ValidationError) as errore:
        s.storico_previsioni(1, alveare_id=cattivo)
    assert errore.value.campo == "alveare_id"
