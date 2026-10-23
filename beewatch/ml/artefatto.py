"""Il modello salvato (M4-T7): un `.joblib` con la Pipeline e, accanto, un `.json` che lo descrive.

    models/produzione_v1.joblib     la Pipeline intera (preprocessore + random forest)
    models/produzione_v1.json       versione, data, iperparametri, feature in ordine, dataset,
                                    metriche e intervallo, importanza, versioni delle librerie,
                                    sha256 del .joblib

Questo modulo conosce solo il **formato**: scrivere, leggere e controllare i due file. Non
importa nulla dell'addestramento (lo fa `beewatch.ml.addestramento`) né della valutazione, così
`beewatch.ml.predictor`, che gira dentro l'app, carica soltanto ciò che serve per prevedere.

Dal dizionario dei metadati si ricava anche la riga della tabella `modelli`
(`riga_tabella_modelli`): file e tabella dicono le stesse cose perché nascono dallo stesso
dizionario (DA-06). Il `.json` è la fonte quando il database è vuoto (clone pulito), la
tabella serve alla chiave esterna di `previsioni` e alla tracciabilità.

**Sicurezza.** `joblib` è `pickle`: caricare un file altrui esegue il suo codice. Il modello
del repository è nostro e committato; lo sha256 nel `.json` protegge da un file sbagliato o
danneggiato, non da uno malevolo. Non puntare `MODEL_PATH` a file di cui non ci si fida.
"""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from beewatch.config import RADICE
from beewatch.exceptions import ModelError
from beewatch.ml.features import TARGET

SCHEMA_ARTEFATTO = 1
VERSIONE_PREDEFINITA = "v1.0.0"
COMANDO_ADDESTRAMENTO = "python scripts/train_model.py"

# Le sezioni che un `.json` valido deve avere (il contenuto fine lo controllano i test).
SEZIONI_OBBLIGATORIE = (
    "schema",
    "versione",
    "addestrato_il",
    "algoritmo",
    "iperparametri",
    "target",
    "feature",
    "dataset",
    "addestramento",
    "metriche",
    "intervallo",
    "importanza_variabili",
    "ambiente",
    "file",
)
LIBRERIE = ("scikit-learn", "pandas", "numpy", "joblib")


def percorso_metadati(percorso_joblib: Path) -> Path:
    """Il `.json` che sta accanto al `.joblib` (stesso nome, estensione diversa)."""
    return Path(percorso_joblib).with_suffix(".json")


def sha256_file(percorso: Path) -> str:
    impronta = hashlib.sha256()
    with Path(percorso).open("rb") as file:
        for blocco in iter(lambda: file.read(1 << 20), b""):
            impronta.update(blocco)
    return impronta.hexdigest()


def impronta_pannello(dati: pd.DataFrame) -> str:
    """SHA-256 del pannello di addestramento, in una forma che non dipende dal computer.

    Righe ordinate per (stato, anno), colonne in ordine fisso, quattro decimali (la precisione
    di `produzione_usda`), a-capo `\\n`: gli stessi dati nel database danno la stessa impronta.
    """
    colonne = ["codice_stato", "anno", "numero_colonie", TARGET]
    canonico = (
        dati[colonne]
        .sort_values(["codice_stato", "anno"])
        .to_csv(index=False, float_format="%.4f", lineterminator="\n")
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def versioni_ambiente() -> dict[str, str]:
    """Python e le librerie da cui dipende il formato del `.joblib`."""
    versioni = {"python": platform.python_version()}
    for libreria in LIBRERIE:
        versioni[libreria] = metadata.version(libreria)
    return versioni


def scrivi_artefatto(
    modello: Any, metadati: dict[str, Any], percorso_joblib: Path
) -> dict[str, Any]:
    """Salva il modello e i suoi metadati; restituisce i metadati completi di `file`.

    Il `.joblib` si scrive per primo, poi si calcola il suo sha256 e lo si mette nel `.json`.
    """
    percorso_joblib = Path(percorso_joblib)
    percorso_joblib.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(modello, percorso_joblib, compress=3)
    completi = {
        **metadati,
        "file": {"joblib": percorso_joblib.name, "sha256_joblib": sha256_file(percorso_joblib)},
    }
    testo = json.dumps(completi, indent=2, ensure_ascii=False) + "\n"
    percorso_metadati(percorso_joblib).write_bytes(testo.encode("utf-8"))  # sempre LF
    return completi


def controlla_metadati(metadati: Any, origine: str) -> dict[str, Any]:
    """Verifica la forma del `.json`: un dizionario con tutte le sezioni e lo schema giusto."""
    if not isinstance(metadati, dict):
        raise ModelError(f"I metadati del modello ({origine}) non sono un oggetto JSON.")
    mancanti = [s for s in SEZIONI_OBBLIGATORIE if s not in metadati]
    if mancanti:
        raise ModelError(
            f"I metadati del modello ({origine}) non sono completi: mancano {', '.join(mancanti)}. "
            f"Riaddestra il modello con: {COMANDO_ADDESTRAMENTO}"
        )
    if metadati["schema"] != SCHEMA_ARTEFATTO:
        raise ModelError(
            f"I metadati del modello ({origine}) hanno lo schema {metadati['schema']}, "
            f"il programma conosce lo schema {SCHEMA_ARTEFATTO}. "
            f"Riaddestra il modello con: {COMANDO_ADDESTRAMENTO}"
        )
    return metadati


def leggi_metadati(percorso_joblib: Path) -> dict[str, Any]:
    """Legge e controlla il `.json` del modello.

    Raises:
        ModelError: file assente, non JSON, incompleto o di uno schema sconosciuto.
    """
    percorso = percorso_metadati(percorso_joblib)
    if not percorso.is_file():
        raise ModelError(
            f"Mancano i metadati del modello: {percorso}. "
            f"Addestra il modello con: {COMANDO_ADDESTRAMENTO}"
        )
    try:
        metadati = json.loads(percorso.read_text(encoding="utf-8"))
    except (OSError, ValueError) as errore:
        raise ModelError(
            f"I metadati del modello ({percorso.name}) non sono leggibili come JSON. "
            f"Riaddestra il modello con: {COMANDO_ADDESTRAMENTO}"
        ) from errore
    return controlla_metadati(metadati, percorso.name)


def percorso_per_la_tabella(percorso: Path) -> str:
    """Il percorso come sta in `modelli.percorso_file`: relativo alla radice se ci sta dentro."""
    assoluto = Path(percorso).resolve()
    try:
        return assoluto.relative_to(RADICE).as_posix()
    except ValueError:
        return assoluto.as_posix()


def riga_tabella_modelli(metadati: dict[str, Any], percorso_file: str) -> dict[str, Any]:
    """La riga della tabella `modelli` che corrisponde a questi metadati, come attiva.

    `mae_kg`, `rmse_kg` e `r2` sono quelli del 2010–2012 (il criterio di DA-05); quelli della
    cross-validation restano nel `.json`. `addestrato_il` è in UTC, senza fuso (DATETIME).
    """
    hold_out = metadati["metriche"]["hold_out_2010_2012"]
    importanza = {n: v["media_kg"] for n, v in metadati["importanza_variabili"]["valori"].items()}
    return {
        "versione": metadati["versione"],
        "algoritmo": metadati["algoritmo"],
        "addestrato_il": datetime.fromisoformat(metadati["addestrato_il"]).replace(tzinfo=None),
        "righe_addestramento": metadati["addestramento"]["righe"],
        "variabili_usate": json.dumps(metadati["feature"], ensure_ascii=False),
        "importanza_variabili": json.dumps(importanza, ensure_ascii=False),
        "mae_kg": hold_out["mae_kg"],
        "rmse_kg": hold_out["rmse_kg"],
        "r2": hold_out["r2"],
        "percorso_file": percorso_file,
        "attivo": True,
        "note": metadati["addestramento"]["strategia"],
    }
