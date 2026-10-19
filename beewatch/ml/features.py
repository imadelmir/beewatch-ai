"""Feature del modello di resa (M4-T2): la storia di ogni stato e il preprocessore.

Due pezzi, usati **identici** in addestramento e in previsione:

- `costruisci_feature_storiche(dati)` aggiunge a ogni riga (stato, anno) ciò che
  si sapeva alla fine dell'anno precedente: la resa dell'anno prima, la media
  delle rese dei tre anni prima, le colonie dell'anno prima. Mai un valore
  dell'anno da prevedere.
- `crea_preprocessore()` restituisce il `ColumnTransformer` (imputazione,
  logaritmo, scaling, one-hot) che apre la Pipeline dei modelli (M4-T3) e impara
  mediane e scale solo dalle righe su cui viene addestrato.

La prima è l'unica trasformazione fuori dalla Pipeline, ed è voluto: per
calcolare un ritardo servono le righe degli anni precedenti dello stesso stato,
mentre un `ColumnTransformer` vede una riga alla volta. Non impara niente dai
dati (nessuna media, nessuna scala): legge valori passati. Tutto ciò che si
stima sui dati sta nel preprocessore.

I ritardi si cercano per chiave (stato, anno − k), non per posizione: se manca
un anno, la resa «dell'anno prima» è mancante, non quella di due anni prima.

Uso, in previsione: alle righe storiche dello stato si aggiunge la riga
dell'anno da prevedere, con la resa vuota, e si chiama la stessa funzione.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import MissingIndicator, SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from beewatch.exceptions import ModelError

# Il target (M2-T3). Sta qui perché `train.py` dipende dalle feature, non il contrario.
TARGET = "resa_per_colonia_kg"
CHIAVE = ("codice_stato", "anno")
COLONNE_RICHIESTE = (*CHIAVE, "numero_colonie", TARGET)

# Le feature storiche: ognuna usa solo anni precedenti a quello della riga.
RESA_ANNO_PRIMA = "resa_anno_prima"
RESA_MEDIA_3_ANNI_PRIMA = "resa_media_3_anni_prima"
COLONIE_ANNO_PRIMA = "colonie_anno_prima"
ANNI_MEDIA_MOBILE = 3

# Ciò che entra nel modello, con il motivo (ripetuto nella model card).
FEATURE = {
    "codice_stato": "il livello di resa di ogni stato (clima, flora, pratiche): one-hot",
    "anno": "la tendenza: la resa cala di circa mezzo chilo l'anno (M2-T3)",
    RESA_ANNO_PRIMA: "la persistenza, la baseline più forte (M4-T1)",
    RESA_MEDIA_3_ANNI_PRIMA: "un livello recente meno rumoroso di un anno solo",
    COLONIE_ANNO_PRIMA: "la scala dell'apicoltura dello stato, in logaritmo",
}
FEATURE_NUMERICHE = ("anno", RESA_ANNO_PRIMA, RESA_MEDIA_3_ANNI_PRIMA)
FEATURE_CATEGORICHE = ("codice_stato",)

# Ciò che resta fuori, con il motivo. Il preprocessore scarta ogni colonna non
# elencata in FEATURE: anche se arrivano nel DataFrame, queste non entrano.
FEATURE_ESCLUSE = {
    TARGET: "il target dell'anno da prevedere",
    "numero_colonie": "è dello stesso anno: alla fine dell'anno prima non si conosce",
    "produzione_totale_kg": "colonie × resa: contiene il target (R5, leakage)",
    "valore_produzione_usd": "produzione × prezzo: contiene il target (R5, leakage)",
    "scorte_kg": "mercato, non biologia (M2-T3); dello stesso anno sarebbe leakage",
    "prezzo_per_kg_usd": "mercato, non biologia (M2-T3); dello stesso anno sarebbe leakage",
}


# --------------------------------------------------------------------------- #
# Feature storiche
# --------------------------------------------------------------------------- #


def costruisci_feature_storiche(dati: pd.DataFrame) -> pd.DataFrame:
    """Una copia di `dati` con le tre feature storiche aggiunte; righe e indice invariati.

    Per la riga (stato, anno *t*):

    - `resa_anno_prima`: la resa dello stato nell'anno *t − 1*;
    - `resa_media_3_anni_prima`: la media delle rese di *t − 1*, *t − 2*, *t − 3*
      che esistono (basta una);
    - `colonie_anno_prima`: le colonie dello stato nell'anno *t − 1*.

    Senza l'anno (o gli anni) che servono il valore è mancante: lo completa il
    preprocessore. La riga di un anno futuro può avere la resa vuota.

    Raises:
        ModelError: mancano colonne, o la stessa coppia (stato, anno) compare due volte.
    """
    mancanti = [c for c in COLONNE_RICHIESTE if c not in dati.columns]
    if mancanti:
        raise ModelError(f"Per le feature storiche mancano le colonne: {', '.join(mancanti)}.")
    if dati.duplicated(list(CHIAVE)).any():
        raise ModelError("La stessa coppia (stato, anno) compare più di una volta.")

    storia = dati.set_index(list(CHIAVE))

    def anni_prima(colonna: str, anni: int) -> np.ndarray:
        chiavi = pd.MultiIndex.from_arrays([dati["codice_stato"], dati["anno"] - anni])
        return storia[colonna].reindex(chiavi).to_numpy(dtype="float64")

    rese_precedenti = pd.DataFrame(
        {k: anni_prima(TARGET, k) for k in range(1, ANNI_MEDIA_MOBILE + 1)}, index=dati.index
    )
    risultato = dati.copy()
    risultato[RESA_ANNO_PRIMA] = rese_precedenti[1]
    risultato[RESA_MEDIA_3_ANNI_PRIMA] = rese_precedenti.mean(axis=1)  # salta i mancanti
    risultato[COLONIE_ANNO_PRIMA] = anni_prima("numero_colonie", 1)
    return risultato


# --------------------------------------------------------------------------- #
# Preprocessore
# --------------------------------------------------------------------------- #


def crea_preprocessore() -> ColumnTransformer:
    """Il `ColumnTransformer` delle feature, da mettere in testa a ogni Pipeline.

    - numeriche (`anno` e le due rese passate): mediana al posto dei mancanti, poi
      standardizzazione;
    - `colonie_anno_prima`: logaritmo (le colonie vanno da migliaia a mezzo
      milione), mediana, standardizzazione;
    - `senza_storia`: 1 se manca la resa dell'anno prima (il primo anno di uno
      stato), così il modello distingue un valore stimato da uno vero;
    - `codice_stato`: one-hot; uno stato mai visto diventa tutti zeri, senza errore.

    Ogni altra colonna viene scartata (`remainder="drop"`).
    """
    numeriche = Pipeline(
        [("imputa", SimpleImputer(strategy="median")), ("scala", StandardScaler())]
    )
    colonie = Pipeline(
        [
            ("log", FunctionTransformer(np.log1p, feature_names_out="one-to-one")),
            ("imputa", SimpleImputer(strategy="median")),
            ("scala", StandardScaler()),
        ]
    )
    return ColumnTransformer(
        [
            ("numeriche", numeriche, list(FEATURE_NUMERICHE)),
            ("colonie", colonie, [COLONIE_ANNO_PRIMA]),
            ("senza_storia", MissingIndicator(features="all"), [RESA_ANNO_PRIMA]),
            (
                "stato",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                list(FEATURE_CATEGORICHE),
            ),
        ],
        remainder="drop",
    )
