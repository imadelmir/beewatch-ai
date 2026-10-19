"""Training del modello di resa: dati dal database, split temporale, valutazione.

M4-T1 ne mette le fondamenta, che i modelli delle task successive useranno così
come sono:

- `carica_dataset_training(database)` costruisce il DataFrame di training con
  la query Q8 (`ProduzioneUsdaRepository.dati_addestramento`): il pannello dei 40
  stati con tutti i 15 anni. **Mai dal CSV**: MySQL è lo storage primario, e in
  `beewatch/ml/` nessun modulo apre il file del dataset (un test lo verifica).
- `dividi_temporale(dati)` separa addestramento (1998–2009) e verifica
  (2010–2012), la stessa divisione di M2-T3: è ciò che rende confrontabili i
  numeri. Mai uno split casuale: i dati hanno una tendenza nel tempo.
- `metriche(vero, previsto)` calcola MAE, RMSE e R². È **l'unico** codice di
  valutazione: baseline e modelli passano tutti da qui.
- `valuta_baseline(dati)` misura le quattro baseline, il termine di paragone
  che un modello deve battere per avere senso.
- `soddisfa_criterio(modello, baseline)` è il criterio di accettazione (DA-05):
  MAE del modello strettamente minore di quello della persistenza.

Le baseline prevedono un anno alla volta: per stimare l'anno *t* usano solo ciò
che si sa alla fine dell'anno *t − 1* (la persistenza, in particolare, usa la
resa vera dell'anno prima). È lo stesso orizzonte che avranno i modelli.

Uso:

    dati = carica_dataset_training(Database(ottieni().database))
    for nome, valori in valuta_baseline(dati).items():
        print(nome, valori.mae_kg)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from beewatch.database import Database
from beewatch.exceptions import ModelError
from beewatch.ml.features import TARGET
from beewatch.repositories_riferimento import ProduzioneUsdaRepository

COLONNE_DATASET = ("codice_stato", "anno", "numero_colonie", TARGET)

# M2-T3: si addestra sul 1998-2009, si verifica sul 2010-2012.
ULTIMO_ANNO_ADDESTRAMENTO = 2009

# I nomi delle baseline, nell'ordine in cui si presentano nella model card.
MEDIA_GLOBALE = "media globale"
MEDIA_STATO = "media dello stato"
MEDIA_STATO_TREND = "media dello stato + tendenza annuale"
PERSISTENZA = "persistenza (resa dell'anno prima)"


# --------------------------------------------------------------------------- #
# Dati
# --------------------------------------------------------------------------- #


def carica_dataset_training(database: Database) -> pd.DataFrame:
    """Il pannello di addestramento letto dal database (Q8), ordinato per stato e anno.

    Raises:
        ModelError: il database non contiene i dati USDA (l'ETL non è stato lanciato).
        DatabaseError: il database non risponde.
    """
    righe = ProduzioneUsdaRepository(database).dati_addestramento()
    if not righe:
        raise ModelError(
            "Il database non contiene i dati USDA completi per l'addestramento. "
            "Carica il dataset con: python scripts/run_etl.py"
        )
    dati = pd.DataFrame(righe, columns=list(COLONNE_DATASET))
    # Dal database arrivano Decimal (colonne DECIMAL): per il calcolo servono float.
    return dati.astype(
        {"codice_stato": "str", "anno": "int64", "numero_colonie": "int64", TARGET: "float64"}
    ).reset_index(drop=True)


def dividi_temporale(
    dati: pd.DataFrame, ultimo_anno_addestramento: int = ULTIMO_ANNO_ADDESTRAMENTO
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`(addestramento, verifica)`: anni fino a `ultimo_anno_addestramento`, e i successivi."""
    nel_passato = dati["anno"] <= ultimo_anno_addestramento
    addestramento, verifica = dati[nel_passato], dati[~nel_passato]
    if addestramento.empty or verifica.empty:
        vuoto = "l'addestramento" if addestramento.empty else "la verifica"
        raise ModelError(
            f"La divisione temporale al {ultimo_anno_addestramento} lascia vuoto {vuoto}."
        )
    return addestramento, verifica


# --------------------------------------------------------------------------- #
# Valutazione
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Metriche:
    """Errori in kg per colonia. MAE è la metrica della soglia (M2-T3)."""

    mae_kg: float
    rmse_kg: float
    r2: float


def metriche(vero: pd.Series | np.ndarray, previsto: pd.Series | np.ndarray) -> Metriche:
    """MAE, RMSE e R² di una previsione. Lo stesso codice per baseline e modelli."""
    vero = np.asarray(vero, dtype="float64")
    previsto = np.asarray(previsto, dtype="float64")
    if vero.shape != previsto.shape or vero.size == 0:
        raise ModelError("Valori veri e previsti devono avere la stessa lunghezza, non nulla.")
    if np.isnan(previsto).any():
        raise ModelError("La previsione contiene valori mancanti.")
    errori = previsto - vero
    varianza = float(((vero - vero.mean()) ** 2).sum())
    return Metriche(
        mae_kg=float(np.abs(errori).mean()),
        rmse_kg=math.sqrt(float((errori**2).mean())),
        r2=1.0 - float((errori**2).sum()) / varianza if varianza > 0 else float("nan"),
    )


# --------------------------------------------------------------------------- #
# Baseline
# --------------------------------------------------------------------------- #


def previsioni_baseline(
    addestramento: pd.DataFrame, verifica: pd.DataFrame, storico: pd.DataFrame
) -> dict[str, np.ndarray]:
    """Le previsioni delle quattro baseline per le righe di `verifica`.

    - **media globale**: la resa media di tutto l'addestramento;
    - **media dello stato**: la resa media dello stato nell'addestramento;
    - **media dello stato + tendenza annuale**: la media dello stato più una
      pendenza comune a tutti gli stati, stimata con i minimi quadrati sugli scarti
      dalla media del proprio stato (resa − media dello stato rispetto ad
      anno − anno medio dello stato), applicata dall'anno medio dello stato;
    - **persistenza**: la resa dello stesso stato nell'anno precedente, presa da
      `storico` (il dataset intero: per il 2011 è quella vera del 2010).

    Medie e pendenza usano solo `addestramento`.
    """
    media_globale = addestramento[TARGET].mean()
    per_stato = addestramento.groupby("codice_stato")
    media_stato = verifica["codice_stato"].map(per_stato[TARGET].mean())
    anno_medio = verifica["codice_stato"].map(per_stato["anno"].mean())

    scarto_resa = addestramento[TARGET] - per_stato[TARGET].transform("mean")
    scarto_anno = addestramento["anno"] - per_stato["anno"].transform("mean")
    pendenza = float((scarto_resa * scarto_anno).sum() / (scarto_anno**2).sum())

    resa_per_chiave = storico.set_index(["codice_stato", "anno"])[TARGET]
    anno_prima = pd.MultiIndex.from_arrays([verifica["codice_stato"], verifica["anno"] - 1])
    persistenza = resa_per_chiave.reindex(anno_prima).to_numpy()

    if media_stato.isna().any() or np.isnan(persistenza).any():
        raise ModelError(
            "Uno stato da verificare non ha dati di addestramento o dell'anno precedente."
        )
    return {
        MEDIA_GLOBALE: np.full(len(verifica), media_globale),
        MEDIA_STATO: media_stato.to_numpy(),
        MEDIA_STATO_TREND: (media_stato + pendenza * (verifica["anno"] - anno_medio)).to_numpy(),
        PERSISTENZA: persistenza,
    }


def valuta_baseline(
    dati: pd.DataFrame, ultimo_anno_addestramento: int = ULTIMO_ANNO_ADDESTRAMENTO
) -> dict[str, Metriche]:
    """Le metriche delle quattro baseline sullo split temporale di `dati`."""
    addestramento, verifica = dividi_temporale(dati, ultimo_anno_addestramento)
    return {
        nome: metriche(verifica[TARGET], previsto)
        for nome, previsto in previsioni_baseline(addestramento, verifica, dati).items()
    }


def migliore_baseline(risultati: dict[str, Metriche]) -> tuple[str, Metriche]:
    """La baseline con il MAE più basso: quella con cui un modello deve confrontarsi."""
    return min(risultati.items(), key=lambda voce: voce[1].mae_kg)


# --------------------------------------------------------------------------- #
# Criterio di accettazione (DA-05)
# --------------------------------------------------------------------------- #


def soddisfa_criterio(modello: Metriche, baseline: dict[str, Metriche]) -> bool:
    """DA-05: il modello è accettabile solo se `MAE_modello < MAE_persistenza`.

    Entrambe le metriche devono venire da `metriche()` sulla stessa verifica
    (pannello Q8, 2010–2012), cioè `baseline` è il risultato di `valuta_baseline`
    sugli stessi dati del modello. Il confronto usa i valori non arrotondati: un
    MAE che si scrive «4,06» come la persistenza può essere sopra o sotto.
    La soglia di M2-T3 (MAE < 4,25 kg) resta solo come riferimento storico.

    Raises:
        ModelError: fra le baseline manca la persistenza.
    """
    if PERSISTENZA not in baseline:
        raise ModelError("Il criterio DA-05 richiede la baseline di persistenza.")
    return modello.mae_kg < baseline[PERSISTENZA].mae_kg
