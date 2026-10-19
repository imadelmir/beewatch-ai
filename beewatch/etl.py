"""ETL del dataset USDA: lettura del CSV e pulizia (M3-T4).

Due funzioni, ognuna con un compito solo:

- `extract(percorso)` legge `honeyproduction.csv` e controlla che sia il file
  giusto e ben formato: esiste, ha le colonne attese, i numeri sono numeri e gli
  interi sono interi. Se no, `ETLError` con un messaggio che dice cosa non va e
  dove. Un file corrotto si ferma qui, non arriva al database.
- `transform(grezzo)` applica le regole R1–R12 di `docs/markdown/M2-dati/dati.md`
  e restituisce due tabelle: le righe pulite, con i nomi e le unità del
  database, e quelle scartate, ognuna con il proprio motivo.

Entrambe sono pure: non scrivono file, non toccano il database e non modificano
il DataFrame ricevuto. L'unico effetto è il log (`WARNING` per le chiavi
duplicate, R9, e per le scorte superiori alla produzione, R11), che le regole
stesse richiedono.

Il caricamento nel database è `load()` (M3-T5).

Uso:

    grezzo = extract(Path("data/honeyproduction.csv"))
    puliti, scartati = transform(grezzo)
    conteggio_scarti(scartati)   # {"stato_non_valido": 2, ...}
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from beewatch.exceptions import ETLError
from beewatch.logging_config import ottieni_logger

logger = ottieni_logger(__name__)

# R3: definizione internazionale esatta della libbra. Scritta una volta sola.
LB_IN_KG = 0.45359237

# Le colonne del CSV, nell'ordine della fonte. I nomi originali esistono solo qui.
COLONNE_FONTE = (
    "state", "numcol", "yieldpercol", "totalprod", "stocks", "priceperlb", "prodvalue", "year",
)  # fmt: skip
# R12 (+ R8 per l'anno): devono essere interi. Gli altri due numeri sono decimali.
COLONNE_INTERE = ("numcol", "totalprod", "stocks", "prodvalue", "year")
COLONNE_DECIMALI = ("yieldpercol", "priceperlb")

# Le colonne in uscita: quelle della tabella `produzione_usda`.
COLONNE_PULITE = (
    "codice_stato", "anno", "numero_colonie", "resa_per_colonia_kg", "produzione_totale_kg",
    "scorte_kg", "prezzo_per_kg_usd", "valore_produzione_usd",
)  # fmt: skip

# R7: i 44 stati del dataset (dati.md, «Range e qualità»). La lista è chiusa.
STATI_AMMESSI = frozenset(
    "AL AR AZ CA CO FL GA HI IA ID IL IN KS KY LA MD ME MI MN MO MS MT "
    "NC ND NE NJ NM NV NY OH OK OR PA SC SD TN TX UT VA VT WA WI WV WY".split()
)
ANNO_MINIMO = 1990  # R8

# Range accettati dall'ETL (dati.md, «Range e qualità»), nelle unità della fonte:
# (minimo, minimo compreso, massimo). Fuori da questi è un errore di formato.
RANGE_ACCETTATI: dict[str, tuple[float, bool, float | None]] = {
    "numcol": (1, True, 1_000_000),
    "yieldpercol": (1, True, 200),
    "totalprod": (0, False, None),
    "stocks": (0, True, None),
    "priceperlb": (0.10, True, 10.00),
    "prodvalue": (0, False, None),
}

# I motivi di scarto: ognuno è una regola di dati.md.
MOTIVO_CAMPO_MANCANTE = "campo_obbligatorio_mancante"  # R2
MOTIVO_STATO_NON_VALIDO = "stato_non_valido"  # R7
MOTIVO_ANNO_NON_PLAUSIBILE = "anno_non_plausibile"  # R8
MOTIVO_CHIAVE_DUPLICATA = "chiave_duplicata"  # R9

_PRIMA_RIGA_DATI = 2  # la riga 1 del file è l'intestazione


def _righe_file(indici: pd.Index, quante: int = 5) -> str:
    """Le righe del file (1 = intestazione) da citare in un messaggio, al massimo `quante`."""
    numeri = [str(i + _PRIMA_RIGA_DATI) for i in list(indici)[:quante]]
    altre = len(indici) - quante
    return ", ".join(numeri) + (f" e altre {altre}" if altre > 0 else "")


# --------------------------------------------------------------------------- #
# Extract
# --------------------------------------------------------------------------- #


def extract(percorso: Path) -> pd.DataFrame:
    """Legge il CSV USDA e ne verifica la forma.

    Restituisce le otto colonne della fonte con i tipi giusti: `state` testo,
    le colonne di R12 e `year` interi (nullable: una cella vuota resta vuota, la
    gestisce R2 in `transform`), resa e prezzo decimali. L'indice è la posizione
    della riga nel file (0 = prima riga di dati).

    Raises:
        ETLError: file assente o illeggibile, colonne mancanti, valori non
            numerici, decimali dove servono interi, valori fuori dal range
            accettato.
    """
    percorso = Path(percorso)
    if not percorso.is_file():
        raise ETLError(
            f"Il file del dataset non esiste: {percorso}. Scarica honeyproduction.csv "
            f"(Kaggle, «Honey Production in the USA 1998-2012») e mettilo in data/."
        )
    try:
        grezzo = pd.read_csv(percorso, dtype=str, encoding="utf-8-sig", skipinitialspace=True)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as errore:
        raise ETLError(
            f"Il file {percorso.name} non è un CSV leggibile ({type(errore).__name__})."
        ) from errore

    mancanti = [c for c in COLONNE_FONTE if c not in grezzo.columns]
    if mancanti:
        raise ETLError(
            f"Nel file {percorso.name} mancano le colonne: {', '.join(mancanti)}. "
            f"Servono: {', '.join(COLONNE_FONTE)}."
        )

    dati = pd.DataFrame(index=grezzo.index)
    dati["state"] = grezzo["state"]
    for colonna in COLONNE_INTERE + COLONNE_DECIMALI:
        dati[colonna] = _numeri(grezzo[colonna], colonna, percorso.name)
    _controlla_range(dati, percorso.name)
    return dati[list(COLONNE_FONTE)]


def _numeri(valori: pd.Series, colonna: str, file: str) -> pd.Series:
    """La colonna come numeri; le celle vuote restano vuote (R2 decide dopo)."""
    numeri = pd.to_numeric(valori, errors="coerce")
    non_numerici = valori.notna() & numeri.isna()
    if non_numerici.any():
        raise ETLError(
            f"Nel file {file} la colonna «{colonna}» contiene valori non numerici "
            f"(righe {_righe_file(valori.index[non_numerici])})."
        )
    if colonna not in COLONNE_INTERE:
        return numeri.astype("float64")
    # R12: interi anche se scritti con l'esponente («2.2e+07»), ma non con decimali.
    non_interi = numeri.notna() & (numeri % 1 != 0)
    if non_interi.any():
        raise ETLError(
            f"Nel file {file} la colonna «{colonna}» deve contenere numeri interi "
            f"(righe {_righe_file(valori.index[non_interi])})."
        )
    return numeri.astype("Int64")


def _controlla_range(dati: pd.DataFrame, file: str) -> None:
    for colonna, (minimo, compreso, massimo) in RANGE_ACCETTATI.items():
        valori = dati[colonna]
        sotto = valori < minimo if compreso else valori <= minimo
        fuori = (sotto | (valori > massimo if massimo is not None else False)).fillna(False)
        if fuori.any():
            limite = f"{'≥' if compreso else '>'} {minimo}" + (
                f" e ≤ {massimo}" if massimo is not None else ""
            )
            raise ETLError(
                f"Nel file {file} la colonna «{colonna}» ha valori fuori dal range accettato "
                f"({limite}; righe {_righe_file(valori.index[fuori])})."
            )


# --------------------------------------------------------------------------- #
# Transform
# --------------------------------------------------------------------------- #


def transform(
    grezzo: pd.DataFrame, *, anno_corrente: int | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Applica le regole R1–R12 al risultato di `extract`.

    Args:
        grezzo: il DataFrame di `extract` (non viene modificato).
        anno_corrente: limite superiore di R8; se omesso, l'anno di oggi.

    Returns:
        `(puliti, scartati)`. `puliti` ha le colonne di `produzione_usda`
        (`COLONNE_PULITE`), nessun valore mancante e nessun arrotondamento (R6).
        `scartati` ha le colonne della fonte più `riga` (numero di riga nel file)
        e `motivo`. Ogni riga in ingresso finisce in una delle due.
    """
    anno_massimo = anno_corrente if anno_corrente is not None else date.today().year
    dati = grezzo.copy()
    # R7: normalizzato prima di tutto. Uno stato fatto di soli spazi è un campo vuoto (R2).
    dati["state"] = dati["state"].str.strip().str.upper().replace("", pd.NA)

    # Il primo motivo trovato vince, nell'ordine delle regole.
    motivo = pd.Series(pd.NA, index=dati.index, dtype="string")
    motivo[dati[list(COLONNE_FONTE)].isna().any(axis=1)] = MOTIVO_CAMPO_MANCANTE  # R2
    motivo[motivo.isna() & ~dati["state"].isin(STATI_AMMESSI)] = MOTIVO_STATO_NON_VALIDO
    fuori_anni = (dati["year"] < ANNO_MINIMO) | (dati["year"] > anno_massimo)  # R8
    motivo[motivo.isna() & fuori_anni.fillna(False)] = MOTIVO_ANNO_NON_PLAUSIBILE
    # R9: fra le righe valide, la prima occorrenza della coppia resta, le altre no.
    duplicate = dati[motivo.isna()].duplicated(["state", "year"], keep="first")
    motivo[duplicate[duplicate].index] = MOTIVO_CHIAVE_DUPLICATA
    for _, riga in dati[motivo == MOTIVO_CHIAVE_DUPLICATA].iterrows():
        logger.warning(
            "Chiave duplicata nel dataset: %s %s (riga %d). La fonte è cambiata?",
            riga["state"], riga["year"], riga.name + _PRIMA_RIGA_DATI,
        )  # fmt: skip

    scartati = grezzo[motivo.notna()].copy()
    scartati.insert(0, "riga", scartati.index + _PRIMA_RIGA_DATI)
    scartati["motivo"] = motivo[motivo.notna()].astype(str)

    validi = dati[motivo.isna()]
    puliti = pd.DataFrame(
        {
            "codice_stato": validi["state"].astype(str),
            "anno": validi["year"].astype("int64"),
            "numero_colonie": validi["numcol"].astype("int64"),
            # R3: le quantità in kg; R4: il prezzo in USD/kg (si divide: un kg costa
            # più di una libbra); R6: nessun arrotondamento.
            "resa_per_colonia_kg": validi["yieldpercol"].astype("float64") * LB_IN_KG,
            "produzione_totale_kg": validi["totalprod"].astype("float64") * LB_IN_KG,
            "scorte_kg": validi["stocks"].astype("float64") * LB_IN_KG,
            "prezzo_per_kg_usd": validi["priceperlb"].astype("float64") / LB_IN_KG,
            # R5: derivata, conservata per fedeltà alla fonte (esclusa dai predittori in M4).
            "valore_produzione_usd": validi["prodvalue"].astype("int64"),
        }
    ).reset_index(drop=True)

    # R11: plausibile (scorte degli anni precedenti), si segnala e si tiene.
    for _, riga in puliti[puliti["scorte_kg"] > puliti["produzione_totale_kg"]].iterrows():
        logger.warning(
            "Scorte superiori alla produzione: %s %d. La riga resta (regola R11).",
            riga["codice_stato"], riga["anno"],
        )  # fmt: skip

    return puliti[list(COLONNE_PULITE)], scartati.reset_index(drop=True)


def conteggio_scarti(scartati: pd.DataFrame) -> dict[str, int]:
    """Quante righe sono state scartate per ciascun motivo."""
    return {str(m): int(n) for m, n in scartati["motivo"].value_counts().sort_index().items()}
