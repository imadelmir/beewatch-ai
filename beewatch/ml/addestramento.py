"""L'addestramento del modello da salvare (M4-T7), da MySQL ai due file e alla tabella `modelli`.

    python scripts/train_model.py

fa, in ordine:

1. legge il pannello Q8 dal database (mai dal CSV);
2. **valuta** la configurazione adottata con `valuta_finale` (cross-validation, 2010–2012,
   intervallo, importanza): sono le metriche che finiscono nei metadati;
3. **riaddestra** la stessa configurazione su tutte le righe (1998–2012) con le sole colonne di
   `FEATURE`: è il modello che l'app userà;
4. scrive `models/produzione_v1.joblib` e il suo `.json`;
5. inserisce o aggiorna la riga in `modelli` e la rende l'unica attiva, dallo stesso
   dizionario dei metadati (DA-06).

Perché la valutazione e il modello salvato non sono lo stesso oggetto: la valutazione ha bisogno
di anni che il modello non ha visto (addestramento fino al 2009, verifica 2010–2012), mentre
per prevedere il 2013 conviene che il modello conosca anche il 2010–2012. **Il modello
salvato non ha quindi una verifica propria**: le metriche dei metadati sono quelle del modello
addestrato fino al 2009, stessa configurazione, stessi dati. Il campo
`addestramento.strategia` lo dice, e la model card anche.

Riproducibilità: stessi dati (stessa `sha256_pannello`), stesso seed e stesse versioni delle
librerie danno le stesse previsioni; un test lo verifica.

Sta in un modulo a parte, e non in `train.py`, per il verso delle dipendenze: la valutazione
importa `train`, quindi `train` non può importare la valutazione.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.pipeline import Pipeline

from beewatch.config import RADICE
from beewatch.database import Database
from beewatch.etl import SHA256_DATASET_UFFICIALE
from beewatch.logging_config import ottieni_logger
from beewatch.ml.artefatto import (
    SCHEMA_ARTEFATTO,
    VERSIONE_PREDEFINITA,
    impronta_pannello,
    riga_tabella_modelli,
    scrivi_artefatto,
    versioni_ambiente,
)
from beewatch.ml.features import FEATURE, FEATURE_ESCLUSE, TARGET, costruisci_feature_storiche
from beewatch.ml.train import (
    PARAMETRI_RF_OTTIMIZZATI,
    PERSISTENZA,
    RANDOM_FOREST_OTTIMIZZATA,
    SEED,
    ULTIMO_ANNO_ADDESTRAMENTO,
    Metriche,
    carica_dataset_training,
    crea_modello_finale,
    soddisfa_criterio,
)
from beewatch.ml.valutazione import ValutazioneFinale, valuta_finale
from beewatch.repositories_riferimento import ModelliRepository

logger = ottieni_logger(__name__)

STRATEGIA = (
    "La stessa configurazione della valutazione, riaddestrata su tutte le righe del pannello "
    "(1998–2012) per prevedere l'anno dopo gli ultimi dati. Le metriche sono quelle del modello "
    "addestrato fino al 2009 e verificato sul 2010–2012: il modello salvato non ha una verifica "
    "propria."
)


def addestra_modello_finale(dati: pd.DataFrame, seed: int = SEED) -> Pipeline:
    """La Pipeline adottata, addestrata su tutte le righe di `dati` (solo le colonne di FEATURE)."""
    ingressi = costruisci_feature_storiche(dati)[list(FEATURE)]
    return crea_modello_finale(seed).fit(ingressi, dati[TARGET])


def _metriche(m: Metriche) -> dict[str, float]:
    return {"mae_kg": m.mae_kg, "rmse_kg": m.rmse_kg, "r2": m.r2}


def crea_metadati(
    dati: pd.DataFrame,
    valutazione: ValutazioneFinale,
    versione: str = VERSIONE_PREDEFINITA,
    seed: int = SEED,
    addestrato_il: datetime | None = None,
) -> dict[str, Any]:
    """I metadati del modello (senza la sezione `file`, che aggiunge `scrivi_artefatto`)."""
    momento = (addestrato_il or datetime.now(UTC)).replace(microsecond=0)
    hold_out = valutazione.hold_out.risultati()
    finale = hold_out[RANDOM_FOREST_OTTIMIZZATA]
    baseline = {n: m for n, m in hold_out.items() if n not in valutazione.hold_out.modelli}
    cv = valutazione.cv.riepilogo()[RANDOM_FOREST_OTTIMIZZATA]
    intervallo = valutazione.intervallo_finale
    return {
        "schema": SCHEMA_ARTEFATTO,
        "versione": versione,
        "addestrato_il": momento.isoformat(),
        "algoritmo": "RandomForestRegressor",
        "iperparametri": {**PARAMETRI_RF_OTTIMIZZATI, "random_state": seed},
        "target": {"nome": TARGET, "unita": "kg per colonia"},
        "feature": list(FEATURE),
        "feature_motivi": dict(FEATURE),
        "feature_escluse": dict(FEATURE_ESCLUSE),
        "dataset": {
            "origine": "MySQL, query Q8 su produzione_usda (pannello bilanciato)",
            "righe": len(dati),
            "stati": int(dati["codice_stato"].nunique()),
            "anno_minimo": int(dati["anno"].min()),
            "anno_massimo": int(dati["anno"].max()),
            "sha256_pannello": impronta_pannello(dati),
            "sha256_csv_ufficiale": SHA256_DATASET_UFFICIALE,
        },
        "addestramento": {"righe": len(dati), "seed": seed, "strategia": STRATEGIA},
        "metriche": {
            "hold_out_2010_2012": {
                "righe": len(valutazione.hold_out.verifica),
                "addestramento_fino_al": ULTIMO_ANNO_ADDESTRAMENTO,
                **_metriche(finale),
            },
            "cross_validation": {
                "fold": len(valutazione.cv.fold),
                "mae_kg": {"media": cv.media.mae_kg, "dev_std": cv.dev_std.mae_kg},
                "rmse_kg": {"media": cv.media.rmse_kg, "dev_std": cv.dev_std.rmse_kg},
                "r2": {"media": cv.media.r2, "dev_std": cv.dev_std.r2},
            },
            "baseline_hold_out": {n: _metriche(m) for n, m in baseline.items()},
            "criterio_da05": {
                "modello_mae_kg": finale.mae_kg,
                "persistenza_mae_kg": baseline[PERSISTENZA].mae_kg,
                "soddisfatto": soddisfa_criterio(finale, baseline),
            },
            "nota": "Il 2010–2012 non è un test indipendente: ha scelto la famiglia di modelli.",
        },
        "intervallo": {
            "livello": intervallo.livello,
            "inferiore_kg": intervallo.inferiore_kg,
            "superiore_kg": intervallo.superiore_kg,
            "residui": len(valutazione.previsioni),
            "copertura_hold_out_da_cv": valutazione.copertura_hold_out,
            "calibrazione": (
                "Quantili p10 e p90 dei residui fuori campione (vero − previsto): 240 della "
                "cross-validation 2004–2009 e 120 del 2010–2012. L'ampiezza è costante: copre "
                "meno delle previsioni alte."
            ),
        },
        "importanza_variabili": {
            "unita": "aumento del MAE in kg se la variabile viene mischiata (2010–2012)",
            "valori": {
                nome: {"media_kg": float(r.media_kg), "dev_std_kg": float(r.dev_std_kg)}
                for nome, r in valutazione.importanza.iterrows()
            },
        },
        "ambiente": versioni_ambiente(),
    }


def _percorso_per_la_tabella(percorso: Path) -> str:
    """Il percorso come sta in `modelli.percorso_file`: relativo alla radice se ci sta dentro."""
    assoluto = Path(percorso).resolve()
    try:
        return assoluto.relative_to(RADICE).as_posix()
    except ValueError:
        return assoluto.as_posix()


def addestra_e_salva(
    database: Database,
    percorso_joblib: Path,
    versione: str = VERSIONE_PREDEFINITA,
    seed: int = SEED,
    registra: bool = True,
) -> dict[str, Any]:
    """Addestra, valuta, salva i due file e (se `registra`) la riga di `modelli`.

    Returns:
        I metadati completi, quelli scritti nel `.json`.

    Raises:
        ModelError: il database non ha i dati USDA.
        DatabaseError: il database non risponde.
    """
    dati = carica_dataset_training(database)
    logger.info("Addestramento %s su %d righe (seed %d)", versione, len(dati), seed)
    valutazione = valuta_finale(dati, seed)
    modello = addestra_modello_finale(dati, seed)
    metadati = scrivi_artefatto(
        modello, crea_metadati(dati, valutazione, versione, seed), percorso_joblib
    )
    if registra:
        riga = riga_tabella_modelli(metadati, _percorso_per_la_tabella(percorso_joblib))
        ModelliRepository(database).registra(riga)
        logger.info("Modello %s registrato in `modelli` come attivo", versione)
    return metadati
