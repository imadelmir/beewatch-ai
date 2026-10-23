"""Valutazione finale del modello adottato (M4-T6): residui, intervallo, importanza, target.

Tutto ciò che la model card dice del modello finale (la random forest ottimizzata di
M4-T5) si calcola qui, senza matplotlib: i grafici li disegna `scripts/genera_grafici.py`
a partire da questi risultati. Lo stesso codice darà in M4-T7 l'intervallo e
l'importanza che finiscono nel file dei metadati del modello.

Che cosa si misura, e che cosa no:

- **Previsioni fuori campione.** Ogni riga ha una previsione fatta da un modello che non
  l'ha vista in addestramento, un anno alla volta (stesso protocollo di M4-T3 e M4-T4):
  le 240 righe dei tre fold della cross-validation (2004–2009) e le 120 del 2010–2012.
- **Il 2010–2012 non è un test indipendente.** Ha già servito a scegliere il modello
  (M4-T3). Qui è l'ultimo periodo, quello su cui il modello finale si addestra fino al
  2009: i suoi errori sono veri errori fuori campione, ma la scelta del modello li ha
  visti.
- **Residuo = valore vero − previsto**, in kg per colonia: positivo se il modello
  sottostima.
- **Intervallo di previsione.** Quantili empirici p10–p90 dei residui: l'80 % degli
  errori fuori campione sta dentro, quindi `previsto + p10 … previsto + p90` contiene il
  valore vero nell'80 % dei casi osservati. Si calibra sui residui della sola
  cross-validation (2004–2009) e si controlla la copertura sul 2010–2012, che non ha
  contribuito a costruirlo: è la verifica onesta della promessa «80 %». L'intervallo
  da usare in produzione usa tutti i 360 residui (`intervallo_finale`).
- **Importanza delle variabili.** `permutation_importance` sulla Pipeline intera, sul
  2010–2012: di quanti kg peggiora il MAE se i valori di una feature vengono mischiati.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

from beewatch.exceptions import ModelError
from beewatch.ml.features import FEATURE, TARGET, costruisci_feature_storiche
from beewatch.ml.train import (
    RANDOM_FOREST,
    RANDOM_FOREST_OTTIMIZZATA,
    SEED,
    ULTIMO_ANNO_ADDESTRAMENTO,
    Confronto,
    confronta_modelli,
    crea_modelli,
    crea_modello_finale,
    dividi_temporale,
)
from beewatch.ml.validazione import CrossValidazione, cross_validation_temporale

LIVELLO_INTERVALLO = 0.8  # «l'80 % dei casi» (M2-T3, dati.md)
RIPETIZIONI_IMPORTANZA = 20
PERIODO_CV = "cross-validation"
PERIODO_HOLD_OUT = "2010–2012"


@dataclass(frozen=True)
class Intervallo:
    """Quanto sommare alla previsione per ottenere gli estremi dell'intervallo (kg).

    `inferiore_kg` è di norma negativo e `superiore_kg` positivo: gli estremi sono
    `previsto + inferiore_kg` e `previsto + superiore_kg`.
    """

    livello: float
    inferiore_kg: float
    superiore_kg: float

    def larghezza_kg(self) -> float:
        return self.superiore_kg - self.inferiore_kg


@dataclass(frozen=True)
class DistribuzioneTarget:
    """Come si distribuisce la resa per colonia (kg) nel pannello di addestramento."""

    righe: int
    media: float
    mediana: float
    dev_std: float
    minimo: float
    massimo: float
    p10: float
    p90: float
    asimmetria: float  # skewness campionaria: 0 = simmetrica, > 0 = coda a destra


@dataclass(frozen=True, eq=False)
class ValutazioneFinale:
    """Tutto ciò che serve a model card, grafici e metadati del modello."""

    previsioni: pd.DataFrame  # periodo, fold, codice_stato, anno, vero, previsto, residuo
    cv: CrossValidazione  # modello finale e baseline, tre fold
    hold_out: Confronto  # random forest di default, ottimizzata e baseline, 2010–2012
    intervallo_cv: Intervallo  # calibrato sui residui della sola cross-validation
    copertura_hold_out: float  # quota dei residui 2010–2012 dentro `intervallo_cv`
    intervallo_finale: Intervallo  # calibrato su tutti i residui fuori campione
    importanza: pd.DataFrame  # indice = feature; colonne media_kg, dev_std_kg
    distribuzione: DistribuzioneTarget


def calcola_intervallo(
    residui: pd.Series | np.ndarray, livello: float = LIVELLO_INTERVALLO
) -> Intervallo:
    """I quantili centrali che contengono la quota `livello` dei residui."""
    valori = np.asarray(residui, dtype="float64")
    if valori.size == 0 or np.isnan(valori).any():
        raise ModelError("Servono residui, tutti presenti, per costruire l'intervallo.")
    if not 0 < livello < 1:
        raise ModelError("Il livello dell'intervallo deve stare fra 0 e 1.")
    coda = (1 - livello) / 2
    inferiore, superiore = np.quantile(valori, [coda, 1 - coda])
    return Intervallo(livello=livello, inferiore_kg=float(inferiore), superiore_kg=float(superiore))


def copertura(residui: pd.Series | np.ndarray, intervallo: Intervallo) -> float:
    """La quota dei residui che cade dentro l'intervallo (estremi compresi)."""
    valori = np.asarray(residui, dtype="float64")
    if valori.size == 0:
        raise ModelError("Servono residui per calcolare la copertura.")
    dentro = (valori >= intervallo.inferiore_kg) & (valori <= intervallo.superiore_kg)
    return float(dentro.mean())


def _righe_previsioni(confronto: Confronto, nome: str, periodo: str, fold: int) -> pd.DataFrame:
    verifica = confronto.verifica
    previsto = confronto.previsioni[nome]
    return pd.DataFrame(
        {
            "periodo": periodo,
            "fold": fold,
            "codice_stato": verifica["codice_stato"].to_numpy(),
            "anno": verifica["anno"].to_numpy(),
            "vero": verifica[TARGET].to_numpy(),
            "previsto": previsto,
            "residuo": verifica[TARGET].to_numpy() - previsto,
        }
    )


def previsioni_fuori_campione(
    cv: CrossValidazione, hold_out: Confronto, nome: str = RANDOM_FOREST_OTTIMIZZATA
) -> pd.DataFrame:
    """Le previsioni del modello `nome` sui tre fold e sul 2010–2012, una riga per previsione."""
    parti = [
        _righe_previsioni(confronto, nome, PERIODO_CV, numero)
        for numero, confronto in enumerate(cv.confronti, start=1)
    ]
    parti.append(_righe_previsioni(hold_out, nome, PERIODO_HOLD_OUT, 0))
    return pd.concat(parti, ignore_index=True)


def distribuzione_target(dati: pd.DataFrame) -> DistribuzioneTarget:
    """Descrizione della resa per colonia nel pannello `dati` (kg)."""
    if dati.empty:
        raise ModelError("Il pannello è vuoto: niente distribuzione del target.")
    resa = dati[TARGET].astype("float64")
    p10, p90 = resa.quantile([0.1, 0.9])
    return DistribuzioneTarget(
        righe=len(resa),
        media=float(resa.mean()),
        mediana=float(resa.median()),
        dev_std=float(resa.std()),
        minimo=float(resa.min()),
        massimo=float(resa.max()),
        p10=float(p10),
        p90=float(p90),
        asimmetria=float(resa.skew()),
    )


def importanza_variabili(
    dati: pd.DataFrame,
    seed: int = SEED,
    ripetizioni: int = RIPETIZIONI_IMPORTANZA,
    ultimo_anno_addestramento: int = ULTIMO_ANNO_ADDESTRAMENTO,
) -> pd.DataFrame:
    """Importanza per permutazione delle feature del modello finale, sul 2010–2012.

    Il modello si addestra fino a `ultimo_anno_addestramento`; per ogni feature si mischiano
    i suoi valori nelle righe di verifica `ripetizioni` volte e si misura di quanti kg
    peggiora il MAE. Colonne: `media_kg`, `dev_std_kg`; righe dalla più alla meno importante.
    """
    addestramento, verifica = dividi_temporale(dati, ultimo_anno_addestramento)
    ingressi = costruisci_feature_storiche(dati)[list(FEATURE)]
    modello = crea_modello_finale(seed).fit(
        ingressi.loc[addestramento.index], addestramento[TARGET]
    )
    esito = permutation_importance(
        modello,
        ingressi.loc[verifica.index],
        verifica[TARGET],
        scoring="neg_mean_absolute_error",
        n_repeats=ripetizioni,
        random_state=seed,
    )
    tabella = pd.DataFrame(
        {"media_kg": esito.importances_mean, "dev_std_kg": esito.importances_std},
        index=list(FEATURE),
    )
    return tabella.sort_values("media_kg", ascending=False)


def errori_per(previsioni: pd.DataFrame, colonna: str) -> pd.DataFrame:
    """MAE, errore medio con segno e numero di righe per ogni valore di `colonna`."""
    gruppi = previsioni.groupby(colonna)
    return pd.DataFrame(
        {
            "righe": gruppi.size(),
            "mae_kg": gruppi["residuo"].apply(lambda r: float(np.abs(r).mean())),
            "errore_medio_kg": gruppi["residuo"].mean(),
        }
    )


def errori_per_fascia(previsioni: pd.DataFrame, fasce: int = 3) -> pd.DataFrame:
    """Gli errori divisi per livello della previsione: l'errore cresce con la resa?

    Le fasce hanno lo stesso numero di righe (terzili per `fasce=3`).
    """
    fascia = pd.qcut(previsioni["previsto"], fasce, labels=False)
    gruppi = previsioni.groupby(fascia)
    return pd.DataFrame(
        {
            "righe": gruppi.size(),
            "previsto_medio_kg": gruppi["previsto"].mean(),
            "mae_kg": gruppi["residuo"].apply(lambda r: float(np.abs(r).mean())),
            "errore_medio_kg": gruppi["residuo"].mean(),
            "ampiezza_p10_p90_kg": gruppi["residuo"].apply(
                lambda r: calcola_intervallo(r).larghezza_kg()
            ),
        }
    )


def copertura_per_fascia(
    previsioni: pd.DataFrame, intervallo: Intervallo, fasce: int = 3
) -> pd.Series:
    """La copertura di `intervallo` in ogni fascia (le stesse di `errori_per_fascia`)."""
    fascia = pd.qcut(previsioni["previsto"], fasce, labels=False)
    dentro = previsioni["residuo"].between(intervallo.inferiore_kg, intervallo.superiore_kg)
    return dentro.groupby(fascia).mean()


def valuta_finale(
    dati: pd.DataFrame,
    seed: int = SEED,
    ripetizioni_importanza: int = RIPETIZIONI_IMPORTANZA,
) -> ValutazioneFinale:
    """Valuta il modello adottato: previsioni fuori campione, intervallo, importanza, target.

    `dati` è il pannello Q8 (1998–2012). Modelli e baseline vengono valutati con le stesse
    funzioni e gli stessi campioni di M4-T3 e M4-T4.
    """
    finale = {RANDOM_FOREST_OTTIMIZZATA: crea_modello_finale(seed)}
    cv = cross_validation_temporale(dati, seed=seed, modelli=finale)
    hold_out = confronta_modelli(
        dati,
        seed=seed,
        modelli={RANDOM_FOREST: crea_modelli(seed)[RANDOM_FOREST], **finale},
    )
    previsioni = previsioni_fuori_campione(cv, hold_out)

    residui_cv = previsioni.loc[previsioni["periodo"] == PERIODO_CV, "residuo"]
    residui_hold_out = previsioni.loc[previsioni["periodo"] == PERIODO_HOLD_OUT, "residuo"]
    intervallo_cv = calcola_intervallo(residui_cv)
    return ValutazioneFinale(
        previsioni=previsioni,
        cv=cv,
        hold_out=hold_out,
        intervallo_cv=intervallo_cv,
        copertura_hold_out=copertura(residui_hold_out, intervallo_cv),
        intervallo_finale=calcola_intervallo(previsioni["residuo"]),
        importanza=importanza_variabili(dati, seed, ripetizioni_importanza),
        distribuzione=distribuzione_target(dati),
    )
