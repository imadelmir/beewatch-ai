"""Il predittore (M4-T7): ricarica il modello salvato e prevede, controllando prima le feature.

    predittore = Predittore()                       # percorso da MODEL_PATH
    stima = predittore.stima({"codice_stato": "CA", "anno": 2013, ...})
    stima.valore_kg, stima.inferiore_kg, stima.superiore_kg

Il costruttore carica `models/produzione_v1.joblib` e il suo `.json` e li controlla:

- i due file esistono; il `.json` ha le sezioni e lo schema giusti;
- lo sha256 del `.joblib` è quello scritto nel `.json` (non è un altro file o un file
  danneggiato);
- il `.joblib` si carica ed è una Pipeline che prevede;
- le colonne che la Pipeline si aspetta sono, nello stesso ordine, quelle dei metadati e
  quelle che il codice produce (`beewatch.ml.features.FEATURE`): se qualcuno ha cambiato le
  feature senza riaddestrare, si ferma qui e non dopo una previsione sbagliata;
- se la versione di scikit-learn è diversa da quella dell'addestramento, **avvisa** nel log
  (di solito funziona, e non è detto): non si ferma.

Ogni problema è un `ModelError` con un messaggio che dice cosa fare. Il costruttore scrive una
riga INFO a ogni caricamento: nell'app deve comparire una volta sola (`st.cache_resource`).

L'app non addestra mai il modello: se manca, lo dice.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from beewatch.config import ottieni
from beewatch.exceptions import ModelError
from beewatch.logging_config import ottieni_logger
from beewatch.ml.artefatto import (
    COMANDO_ADDESTRAMENTO,
    leggi_metadati,
    sha256_file,
)
from beewatch.ml.features import FEATURE

logger = ottieni_logger(__name__)


@dataclass(frozen=True)
class Stima:
    """Una previsione con il suo intervallo, tutti in kg per colonia."""

    valore_kg: float
    inferiore_kg: float
    superiore_kg: float
    livello: float  # la quota di errori osservati dentro l'intervallo (0,8 = «l'80 %»)


class Predittore:
    """Il modello caricato, i suoi metadati e il modo di prevedere con essi."""

    def __init__(self, percorso: Path | None = None) -> None:
        self._percorso = Path(percorso) if percorso is not None else ottieni().percorso_modello
        self._metadati = leggi_metadati(self._percorso)
        self._controlla_file()
        self._modello = self._carica()
        self._controlla_feature()
        self._avvisa_se_le_versioni_differiscono()
        logger.info(
            "Modello %s caricato da %s (scikit-learn %s)",
            self.versione,
            self._percorso,
            self._metadati["ambiente"].get("scikit-learn", "?"),
        )

    # ----------------------------------------------------------------------- #
    # Interfaccia
    # ----------------------------------------------------------------------- #

    @property
    def versione(self) -> str:
        return str(self._metadati["versione"])

    @property
    def metadati(self) -> dict[str, Any]:
        return self._metadati

    @property
    def feature(self) -> tuple[str, ...]:
        return tuple(self._metadati["feature"])

    @property
    def percorso(self) -> Path:
        return self._percorso

    def prevedi(self, feature: pd.DataFrame) -> np.ndarray:
        """La resa prevista per ogni riga di `feature` (kg per colonia).

        Servono tutte le colonne di `self.feature`; le altre si ignorano. Lo stato e l'anno
        devono esserci in ogni riga; i valori storici mancanti (il primo anno di uno stato)
        li completa il preprocessore.

        Raises:
            ModelError: colonne mancanti, stato o anno assenti.
        """
        mancanti = [c for c in self.feature if c not in feature.columns]
        if mancanti:
            raise ModelError(
                f"Per prevedere mancano le colonne: {', '.join(mancanti)}. "
                f"Il modello {self.versione} usa: {', '.join(self.feature)}."
            )
        ingresso = feature[list(self.feature)]
        if ingresso[["codice_stato", "anno"]].isna().any().any():
            raise ModelError("Per prevedere servono lo stato e l'anno di ogni riga.")
        return np.asarray(self._modello.predict(ingresso), dtype="float64")

    def stima(self, riga: Mapping[str, Any]) -> Stima:
        """La stima di una sola riga di feature, con l'intervallo dei metadati.

        Gli estremi sono `previsto + inferiore` e `previsto + superiore` (residui p10 e p90
        fuori campione); l'intervallo contiene sempre il valore centrale.
        """
        valore = float(self.prevedi(pd.DataFrame([dict(riga)]))[0])
        intervallo = self._metadati["intervallo"]
        return Stima(
            valore_kg=valore,
            inferiore_kg=min(valore, valore + float(intervallo["inferiore_kg"])),
            superiore_kg=max(valore, valore + float(intervallo["superiore_kg"])),
            livello=float(intervallo["livello"]),
        )

    # ----------------------------------------------------------------------- #
    # Controlli al caricamento
    # ----------------------------------------------------------------------- #

    def _controlla_file(self) -> None:
        if not self._percorso.is_file():
            raise ModelError(
                f"Il modello non è stato trovato: {self._percorso}. "
                f"Addestralo con: {COMANDO_ADDESTRAMENTO}"
            )
        atteso = self._metadati["file"]["sha256_joblib"]
        if sha256_file(self._percorso) != atteso:
            raise ModelError(
                f"Il file {self._percorso.name} non corrisponde ai suoi metadati "
                f"(impronta sha256 diversa): è stato sostituito o danneggiato. "
                f"Riaddestra il modello con: {COMANDO_ADDESTRAMENTO}"
            )

    def _carica(self) -> Any:
        try:
            # joblib è pickle: carica solo il modello del repository o uno addestrato da noi.
            # Lo sha256 controllato in `_controlla_file` evita un file sbagliato o danneggiato,
            # non un file malevolo: MODEL_PATH non va puntato a file di cui non ci si fida.
            modello = joblib.load(self._percorso)
        except Exception as errore:  # pickle può sollevare di tutto: versioni, file corrotto
            logger.error("Caricamento del modello non riuscito: %s", type(errore).__name__)
            raise ModelError(
                f"Il modello {self._percorso.name} non si può caricare (file danneggiato o "
                f"versione di scikit-learn incompatibile). "
                f"Riaddestralo con: {COMANDO_ADDESTRAMENTO}"
            ) from errore
        if not hasattr(modello, "predict") or not hasattr(modello, "named_steps"):
            raise ModelError(
                f"Il file {self._percorso.name} non contiene una Pipeline di scikit-learn. "
                f"Riaddestra il modello con: {COMANDO_ADDESTRAMENTO}"
            )
        return modello

    def _controlla_feature(self) -> None:
        dichiarate = tuple(self._metadati["feature"])
        nel_modello = tuple(getattr(self._modello, "feature_names_in_", ()))
        if not (dichiarate == nel_modello == tuple(FEATURE)):
            raise ModelError(
                "Le feature del modello non coincidono con quelle del programma: "
                f"modello {nel_modello or '?'}, metadati {dichiarate}, codice {tuple(FEATURE)}. "
                f"Riaddestra il modello con: {COMANDO_ADDESTRAMENTO}"
            )

    def _avvisa_se_le_versioni_differiscono(self) -> None:
        addestramento = self._metadati["ambiente"].get("scikit-learn")
        attuale = metadata.version("scikit-learn")
        if addestramento != attuale:
            logger.warning(
                "Il modello %s è stato addestrato con scikit-learn %s, qui c'è la %s: di "
                "solito funziona, ma non è garantito. Riaddestralo se le previsioni sembrano "
                "strane (%s).",
                self.versione,
                addestramento,
                attuale,
                COMANDO_ADDESTRAMENTO,
            )
