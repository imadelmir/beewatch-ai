"""Cross-validation temporale (M4-T4): finestra espandente per anno, solo sull'addestramento.

Tre fold, fissati dal backlog prima di guardare qualunque risultato:

| fold | addestramento | valutazione |
|---|---|---|
| 1 | 1998–2003 | 2004–2005 |
| 2 | 1998–2005 | 2006–2007 |
| 3 | 1998–2007 | 2008–2009 |

Ogni fold addestra sugli anni precedenti e valuta i due anni successivi; nessun
fold arriva al 2010–2012, che resta l'hold-out di M2-T3 (già usato in M4-T3 per
scegliere il modello). Un fold è un `confronta_modelli` sui dati fino all'ultimo
anno di valutazione: stessi modelli, stesse feature, stesse baseline, stessa
funzione `metriche()`, e preprocessore adattato solo all'addestramento del fold.
Gli anni dopo la valutazione non entrano nemmeno nel DataFrame.

`fold_temporali(dati)` dà gli stessi fold come indici posizionali, nella forma
che accetta il parametro `cv` di scikit-learn (servirà al tuning di M4-T5). Non
si usa `TimeSeriesSplit`: dividerebbe le righe, non gli anni, e uno stesso anno
finirebbe in parte nell'addestramento e in parte nella valutazione.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from beewatch.exceptions import ModelError
from beewatch.ml.train import (
    SEED,
    ULTIMO_ANNO_ADDESTRAMENTO,
    Confronto,
    Metriche,
    confronta_modelli,
    soddisfa_criterio,
)


@dataclass(frozen=True)
class Fold:
    """Si addestra fino a `fine_addestramento` compreso, si valutano `anni_valutazione`."""

    fine_addestramento: int
    anni_valutazione: tuple[int, ...]


# Il backlog (M4-T4): finestra espandente, due anni di valutazione per fold.
FOLD_TEMPORALI = (
    Fold(2003, (2004, 2005)),
    Fold(2005, (2006, 2007)),
    Fold(2007, (2008, 2009)),
)


def _controlla(fold: tuple[Fold, ...], ultimo_anno_addestramento: int) -> None:
    for f in fold:
        inizio = f.fine_addestramento + 1
        attesi = tuple(range(inizio, inizio + len(f.anni_valutazione)))
        if not f.anni_valutazione or f.anni_valutazione != attesi:
            raise ModelError(
                f"Gli anni di valutazione di un fold devono seguire senza buchi il "
                f"{f.fine_addestramento}: {f.anni_valutazione}."
            )
        if f.anni_valutazione[-1] > ultimo_anno_addestramento:
            raise ModelError(
                f"Un fold non può valutare anni oltre il {ultimo_anno_addestramento}: "
                "l'hold-out resta fuori dalla cross-validation."
            )


def fold_temporali(
    dati: pd.DataFrame,
    fold: tuple[Fold, ...] = FOLD_TEMPORALI,
    ultimo_anno_addestramento: int = ULTIMO_ANNO_ADDESTRAMENTO,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Per ogni fold, gli indici posizionali `(addestramento, valutazione)` di `dati`.

    Raises:
        ModelError: un fold ha anni di valutazione non consecutivi, o oltre l'hold-out.
    """
    _controlla(fold, ultimo_anno_addestramento)
    anni = dati["anno"].to_numpy()
    for f in fold:
        yield (
            np.flatnonzero(anni <= f.fine_addestramento),
            np.flatnonzero(np.isin(anni, f.anni_valutazione)),
        )


@dataclass(frozen=True)
class Riepilogo:
    """Media e deviazione standard campionaria (n − 1) di una metrica sui fold."""

    media: Metriche
    dev_std: Metriche


@dataclass(frozen=True, eq=False)
class CrossValidazione:
    """Un `Confronto` per fold: modelli e baseline sulle stesse righe di quel fold."""

    fold: tuple[Fold, ...]
    confronti: tuple[Confronto, ...]

    def risultati_per_fold(self) -> list[dict[str, Metriche]]:
        return [confronto.risultati() for confronto in self.confronti]

    def riepilogo(self) -> dict[str, Riepilogo]:
        """Per ogni modello e baseline, media e deviazione standard di MAE, RMSE e R²."""
        per_fold = self.risultati_per_fold()

        def aggrega(nome: str, funzione) -> Metriche:
            valori = [r[nome] for r in per_fold]
            return Metriche(
                mae_kg=funzione([m.mae_kg for m in valori]),
                rmse_kg=funzione([m.rmse_kg for m in valori]),
                r2=funzione([m.r2 for m in valori]),
            )

        return {
            nome: Riepilogo(aggrega(nome, statistics.fmean), aggrega(nome, statistics.stdev))
            for nome in per_fold[0]
        }

    def fold_sotto_la_persistenza(self) -> dict[str, int]:
        """Per ogni modello, in quanti fold il suo MAE è sotto quello della persistenza."""
        modelli = self.confronti[0].modelli
        conteggi = dict.fromkeys(modelli, 0)
        for risultati in self.risultati_per_fold():
            baseline = {n: m for n, m in risultati.items() if n not in modelli}
            for nome in modelli:
                conteggi[nome] += soddisfa_criterio(risultati[nome], baseline)
        return conteggi


def cross_validation_temporale(
    dati: pd.DataFrame,
    seed: int = SEED,
    fold: tuple[Fold, ...] = FOLD_TEMPORALI,
    ultimo_anno_addestramento: int = ULTIMO_ANNO_ADDESTRAMENTO,
    modelli: dict[str, Pipeline] | None = None,
) -> CrossValidazione:
    """Il confronto di M4-T3 ripetuto su ogni fold, con i dati fino alla sua valutazione.

    `modelli`, se dato, sostituisce i tre di M4-T3 (vedi `confronta_modelli`).

    Raises:
        ModelError: fold non validi (vedi `fold_temporali`), meno di due fold, o un
            fold che `confronta_modelli` non può calcolare.
    """
    _controlla(fold, ultimo_anno_addestramento)
    if len(fold) < 2:
        raise ModelError("Servono almeno due fold per media e deviazione standard.")
    confronti = tuple(
        confronta_modelli(
            dati[dati["anno"] <= f.anni_valutazione[-1]],
            seed=seed,
            ultimo_anno_addestramento=f.fine_addestramento,
            modelli=modelli,
        )
        for f in fold
    )
    return CrossValidazione(fold=tuple(fold), confronti=confronti)
