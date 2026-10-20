"""Tuning degli iperparametri della random forest (M4-T5), sui fold temporali di M4-T4.

La ricerca è un `GridSearchCV` sulla griglia del backlog, con `cv` = i tre fold
per anno di `fold_temporali` e lo scoring sul MAE, la metrica di DA-05. Il
dataset viene **ristretto agli anni fino al 2009 prima** di costruire feature e
indici: il 2010–2012 non entra né nella ricerca né in questa task, e gli indici
dei fold sono posizioni dello stesso DataFrame che riceve `GridSearchCV`.

Regole fissate prima di eseguire la ricerca:

- si sceglie la configurazione con il MAE medio più basso sui tre fold;
- default e configurazione scelta si rivalutano con `cross_validation_temporale`
  (stessi fold, stesse righe, stessa `metriche()` di M4-T4);
- la configurazione scelta si adotta solo se il suo MAE medio è più basso di
  quello dei default **e** migliora in almeno due fold su tre (`da_adottare`);
  altrimenti restano i default.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import GridSearchCV

from beewatch.ml.features import TARGET, costruisci_feature_storiche
from beewatch.ml.train import RANDOM_FOREST, SEED, ULTIMO_ANNO_ADDESTRAMENTO, crea_modelli
from beewatch.ml.validazione import (
    FOLD_TEMPORALI,
    CrossValidazione,
    Fold,
    cross_validation_temporale,
    fold_temporali,
)

# La griglia del backlog: 2 × 3 × 3 = 18 configurazioni.
GRIGLIA_RANDOM_FOREST: dict[str, list[Any]] = {
    "modello__n_estimators": [200, 500],
    "modello__max_depth": [None, 8, 15],
    "modello__min_samples_leaf": [1, 3, 5],
}

DEFAULT = f"{RANDOM_FOREST} (default)"
OTTIMIZZATA = f"{RANDOM_FOREST} (ottimizzata)"


@dataclass(frozen=True, eq=False)
class EsitoTuning:
    """La ricerca e il confronto fra default e configurazione scelta, sugli stessi fold."""

    migliori_parametri: dict[str, Any]
    ricerca: pd.DataFrame  # una riga per configurazione: parametri, MAE medio e std, rango
    confronto: CrossValidazione  # default e ottimizzata (più le baseline), stessi fold

    def mae_per_fold(self, nome: str) -> list[float]:
        return [r[nome].mae_kg for r in self.confronto.risultati_per_fold()]

    def fold_migliorati(self) -> int:
        """In quanti fold la configurazione scelta ha un MAE più basso dei default."""
        coppie = zip(self.mae_per_fold(OTTIMIZZATA), self.mae_per_fold(DEFAULT), strict=True)
        return sum(ottimizzato < default for ottimizzato, default in coppie)

    def guadagno_medio_kg(self) -> float:
        """MAE medio dei default meno MAE medio della scelta: positivo se il tuning aiuta."""
        return statistics.fmean(self.mae_per_fold(DEFAULT)) - statistics.fmean(
            self.mae_per_fold(OTTIMIZZATA)
        )

    def da_adottare(self) -> bool:
        """La regola fissata prima della ricerca: meglio in media e in almeno due fold."""
        return self.guadagno_medio_kg() > 0 and self.fold_migliorati() >= 2


def ottimizza_random_forest(
    dati: pd.DataFrame,
    seed: int = SEED,
    griglia: dict[str, list[Any]] | None = None,
    fold: tuple[Fold, ...] = FOLD_TEMPORALI,
    ultimo_anno_addestramento: int = ULTIMO_ANNO_ADDESTRAMENTO,
) -> EsitoTuning:
    """Cerca la configurazione della random forest sui fold temporali e la confronta con i default.

    Raises:
        ModelError: fold non validi (vedi `fold_temporali`).
    """
    griglia = GRIGLIA_RANDOM_FOREST if griglia is None else griglia
    # Prima si toglie l'hold-out, poi si costruiscono ingressi e indici sullo stesso
    # frame. L'ordine (stato, anno) è quello di Q8: la random forest dipende
    # dall'ordine delle righe, così il risultato non dipende da come arrivano.
    tuning = (
        dati[dati["anno"] <= ultimo_anno_addestramento]
        .sort_values(["codice_stato", "anno"])
        .reset_index(drop=True)
    )
    ingressi = costruisci_feature_storiche(tuning).drop(columns=[TARGET])
    indici = list(fold_temporali(tuning, fold, ultimo_anno_addestramento))

    default = crea_modelli(seed)[RANDOM_FOREST]
    ricerca = GridSearchCV(
        default, griglia, scoring="neg_mean_absolute_error", cv=indici, refit=False
    )
    ricerca.fit(ingressi, tuning[TARGET])

    risultati = ricerca.cv_results_
    migliore = int(np.flatnonzero(risultati["rank_test_score"] == 1)[0])
    migliori_parametri = dict(risultati["params"][migliore])
    tabella = pd.DataFrame(
        {
            **{nome.removeprefix("modello__"): risultati[f"param_{nome}"] for nome in griglia},
            "mae_medio": -risultati["mean_test_score"],
            "mae_dev_std": risultati["std_test_score"],
            "rango": risultati["rank_test_score"],
        }
    )

    ottimizzata = crea_modelli(seed)[RANDOM_FOREST].set_params(**migliori_parametri)
    confronto = cross_validation_temporale(
        tuning,
        seed=seed,
        fold=fold,
        ultimo_anno_addestramento=ultimo_anno_addestramento,
        modelli={DEFAULT: default, OTTIMIZZATA: ottimizzata},
    )
    return EsitoTuning(migliori_parametri=migliori_parametri, ricerca=tabella, confronto=confronto)
