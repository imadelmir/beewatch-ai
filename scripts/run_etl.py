"""Carica il dataset USDA nel database e stampa il report (M3-T5).

    python scripts/run_etl.py                         # data/honeyproduction.csv
    python scripts/run_etl.py --file percorso/al/file.csv
    python scripts/run_etl.py --report-dir altra/cartella

Si può rilanciare quante volte serve: le righe già presenti vengono aggiornate o
lasciate com'erano, mai duplicate. Il report va a video e in `reports/`.

Esce con 0 se tutto è andato bene, con 1 se il caricamento non è avvenuto (file
assente o malformato, database spento, seed mancante): in quel caso nel database
non è stato scritto niente.

Questo file contiene solo la lettura degli argomenti: il lavoro lo fa
`beewatch.etl.run_pipeline`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from beewatch import config
from beewatch.database import Database
from beewatch.etl import run_pipeline
from beewatch.exceptions import BeeWatchError
from beewatch.logging_config import configura


def main(argomenti: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Carica il dataset USDA (honeyproduction.csv) nella tabella produzione_usda."
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="il CSV da caricare (predefinito: data/honeyproduction.csv)",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="dove salvare il report (predefinito: reports/)",
    )
    opzioni = parser.parse_args(argomenti)

    try:
        configura()
        cfg = config.ottieni()
        report = run_pipeline(
            opzioni.file or config.RADICE / "data" / "honeyproduction.csv",
            Database(cfg.database),
            opzioni.report_dir or config.RADICE / "reports",
        )
    except BeeWatchError as errore:
        print(f"ETL non eseguito: {errore}", file=sys.stderr)
        return 1
    print(report.testo(), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
