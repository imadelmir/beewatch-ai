"""Addestra il modello di resa e lo salva con i suoi metadati (M4-T7).

    python scripts/train_model.py                          # models/produzione_v1.joblib
    python scripts/train_model.py --modello altra/cartella/nome.joblib
    python scripts/train_model.py --versione v1.1.0 --seed 7
    python scripts/train_model.py --senza-registrazione    # non scrive nella tabella `modelli`

Serve un database con i dati USDA (`python scripts/run_etl.py`): il training legge sempre da lì,
mai dal CSV. Scrive il `.joblib`, il `.json` accanto e, salvo `--senza-registrazione`, la riga
della tabella `modelli` come modello attivo. Lo stesso comando con gli stessi dati e lo stesso
seed dà le stesse previsioni.

Esce con 0 se il modello è stato salvato, con 1 se non si è potuto addestrare (database spento
o senza dati, configurazione non valida).

Questo file contiene solo la lettura degli argomenti: il lavoro lo fa
`beewatch.ml.addestramento.addestra_e_salva`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from beewatch import config
from beewatch.database import Database
from beewatch.exceptions import BeeWatchError
from beewatch.logging_config import configura
from beewatch.ml.addestramento import addestra_e_salva
from beewatch.ml.artefatto import VERSIONE_PREDEFINITA
from beewatch.ml.train import SEED


def main(argomenti: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Addestra e salva il modello di resa per colonia.")
    parser.add_argument(
        "--modello",
        type=Path,
        default=None,
        help="dove salvare il .joblib (predefinito: MODEL_PATH, cioè models/produzione_v1.joblib)",
    )
    parser.add_argument("--versione", default=VERSIONE_PREDEFINITA, help="versione del modello")
    parser.add_argument("--seed", type=int, default=SEED, help="seme della casualità")
    parser.add_argument(
        "--senza-registrazione",
        action="store_true",
        help="scrive solo i due file, non la riga della tabella modelli",
    )
    opzioni = parser.parse_args(argomenti)

    try:
        configura()
        cfg = config.ottieni()
        percorso = opzioni.modello or cfg.percorso_modello
        metadati = addestra_e_salva(
            Database(cfg.database),
            percorso,
            versione=opzioni.versione,
            seed=opzioni.seed,
            registra=not opzioni.senza_registrazione,
        )
    except BeeWatchError as errore:
        print(f"Modello non addestrato: {errore}", file=sys.stderr)
        return 1

    hold_out = metadati["metriche"]["hold_out_2010_2012"]
    criterio = metadati["metriche"]["criterio_da05"]
    print(f"Modello {metadati['versione']} salvato in {percorso}")
    print(f"  righe di addestramento: {metadati['addestramento']['righe']}")
    print(
        f"  2010–2012 (addestrato fino al 2009): MAE {hold_out['mae_kg']:.4f} kg, "
        f"RMSE {hold_out['rmse_kg']:.4f}, R² {hold_out['r2']:.4f}"
    )
    print(
        f"  DA-05: MAE {criterio['modello_mae_kg']:.6f} contro persistenza "
        f"{criterio['persistenza_mae_kg']:.6f} → "
        f"{'soddisfatto' if criterio['soddisfatto'] else 'NON soddisfatto'}"
    )
    print(f"  impronta del pannello: {metadati['dataset']['sha256_pannello']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
