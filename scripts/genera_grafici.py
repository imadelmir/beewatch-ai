"""Disegna i grafici della valutazione finale (M4-T6) in `docs/images/`.

    python scripts/genera_grafici.py                  # legge Q8 da MySQL, scrive in docs/images/
    python scripts/genera_grafici.py --cartella altra/cartella

I numeri non si calcolano qui: vengono da `beewatch.ml.valutazione.valuta_finale`, la
stessa funzione che alimenta la model card e, in M4-T7, i metadati del modello. Questo
file contiene solo il disegno. Richiede matplotlib (extra `dev`, non è nell'immagine
Docker) e un database con i dati USDA (`python scripts/run_etl.py`).

Esce con 0 se i grafici sono stati scritti, con 1 se i dati non sono disponibili.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from beewatch import config
from beewatch.database import Database
from beewatch.exceptions import BeeWatchError
from beewatch.logging_config import configura
from beewatch.ml.features import TARGET
from beewatch.ml.train import (
    MEDIA_STATO_TREND,
    PERSISTENZA,
    RANDOM_FOREST_OTTIMIZZATA,
    carica_dataset_training,
)
from beewatch.ml.valutazione import PERIODO_CV, PERIODO_HOLD_OUT, ValutazioneFinale, valuta_finale

# Palette validata con la skill dataviz (blu e arancio: ΔE CVD 24,7, normale 33,6, contrasto
# >= 3:1 sulla superficie). Il testo usa i colori d'inchiostro, mai il colore della serie.
SUPERFICIE = "#fcfcfb"
SERIE_1 = "#2a78d6"  # il modello
SERIE_2 = "#eb6834"  # il riferimento (persistenza, limiti dell'intervallo)
CONTESTO = "#b9b8b1"  # serie di contesto, in grigio
INCHIOSTRO = "#0b0b0b"
INCHIOSTRO_2 = "#52514e"
GRIGLIA = "#e4e3df"

DPI = 130
LARGHEZZA, ALTEZZA = 7.2, 4.4

ETICHETTE_FEATURE = {
    "resa_media_3_anni_prima": "resa media dei 3 anni prima",
    "resa_anno_prima": "resa dell'anno prima",
    "colonie_anno_prima": "colonie dell'anno prima",
    "codice_stato": "stato",
    "anno": "anno",
}


def _decimali(valore: float, cifre: int = 2) -> str:
    """Numero con la virgola decimale, come nei documenti."""
    return f"{valore:.{cifre}f}".replace(".", ",").replace("-", "−")


def _nuova_figura(larghezza: float = LARGHEZZA, altezza: float = ALTEZZA, colonne: int = 1):
    figura, assi = plt.subplots(1, colonne, figsize=(larghezza, altezza), facecolor=SUPERFICIE)
    for asse in np.atleast_1d(assi):
        asse.set_facecolor(SUPERFICIE)
        asse.grid(True, color=GRIGLIA, linewidth=0.8)
        asse.set_axisbelow(True)
        for lato in ("top", "right"):
            asse.spines[lato].set_visible(False)
        for lato in ("left", "bottom"):
            asse.spines[lato].set_color(GRIGLIA)
        asse.tick_params(colors=INCHIOSTRO_2, labelsize=9)
        asse.xaxis.label.set_color(INCHIOSTRO_2)
        asse.yaxis.label.set_color(INCHIOSTRO_2)
    return figura, assi


def _salva(figura, percorso: Path, titolo: str, sottotitolo: str) -> Path:
    figura.text(0.01, 0.975, titolo, ha="left", va="top", fontsize=12, fontweight="bold")
    figura.text(0.01, 0.915, sottotitolo, ha="left", va="top", fontsize=9, color=INCHIOSTRO_2)
    figura.tight_layout(rect=(0, 0, 1, 0.86))
    figura.savefig(percorso, dpi=DPI, facecolor=SUPERFICIE, metadata={"Software": "BeeWatch AI"})
    plt.close(figura)
    return percorso


def previsto_vs_reale(v: ValutazioneFinale, cartella: Path) -> Path:
    figura, asse = _nuova_figura(larghezza=6.4, altezza=6.2)  # assi quadrati: stessa scala
    previsioni = v.previsioni
    cv = previsioni[previsioni["periodo"] == PERIODO_CV]
    hold_out = previsioni[previsioni["periodo"] == PERIODO_HOLD_OUT]
    valori = previsioni[["vero", "previsto"]]
    estremi = [valori.min().min() - 2, valori.max().max() + 2]

    asse.plot(estremi, estremi, color=INCHIOSTRO_2, linewidth=1.2, linestyle="--", zorder=1)
    asse.scatter(
        cv["previsto"],
        cv["vero"],
        s=30,
        color=CONTESTO,
        edgecolor=SUPERFICIE,
        linewidth=0.8,
        label="cross-validation 2004–2009",
        zorder=2,
    )
    asse.scatter(
        hold_out["previsto"],
        hold_out["vero"],
        s=34,
        color=SERIE_1,
        edgecolor=SUPERFICIE,
        linewidth=0.8,
        label="2010–2012",
        zorder=3,
    )
    asse.set_xlim(estremi)
    asse.set_ylim(estremi)
    asse.set_aspect("equal", adjustable="box")
    asse.set_xlabel("resa prevista (kg per colonia)")
    asse.set_ylabel("resa vera (kg per colonia)")
    asse.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INCHIOSTRO_2)
    finale = v.hold_out.risultati()[RANDOM_FOREST_OTTIMIZZATA]
    asse.text(
        0.98,
        0.04,
        f"2010–2012: MAE {_decimali(finale.mae_kg)} kg · R² {_decimali(finale.r2)}",
        transform=asse.transAxes,
        ha="right",
        fontsize=9,
        color=INCHIOSTRO,
    )
    return _salva(
        figura,
        cartella / "previsto_vs_reale.png",
        "Previsto contro reale",
        "Un punto per stato e anno, previsto un anno alla volta. Tratteggio: previsione perfetta.",
    )


def residui(v: ValutazioneFinale, cartella: Path) -> Path:
    figura, (sinistra, destra) = _nuova_figura(larghezza=9.6, altezza=4.2, colonne=2)
    previsioni = v.previsioni
    inferiore, superiore = v.intervallo_finale.inferiore_kg, v.intervallo_finale.superiore_kg

    sinistra.axhline(0, color=INCHIOSTRO_2, linewidth=1.2)
    sinistra.scatter(
        previsioni["previsto"],
        previsioni["residuo"],
        s=26,
        color=SERIE_1,
        edgecolor=SUPERFICIE,
        linewidth=0.7,
        zorder=3,
    )
    for limite in (inferiore, superiore):
        sinistra.axhline(limite, color=SERIE_2, linewidth=1.6, linestyle="--")
    # x in coordinate dell'asse (a destra), y in kg: l'etichetta sta sopra o sotto la linea.
    etichetta = sinistra.get_yaxis_transform()
    for valore, nome, posizione in ((superiore, "p90", "bottom"), (inferiore, "p10", "top")):
        sinistra.text(
            0.99,
            valore,
            f"{nome} {_decimali(valore, 1)}",
            transform=etichetta,
            ha="right",
            va=posizione,
            fontsize=9,
        )
    sinistra.set_xlabel("resa prevista (kg per colonia)")
    sinistra.set_ylabel("residuo = vero − previsto (kg)")
    sinistra.set_title("Residui e livello della previsione", loc="left", fontsize=10)

    destra.hist(previsioni["residuo"], bins=24, color=SERIE_1, edgecolor=SUPERFICIE, linewidth=1.5)
    for limite in (inferiore, superiore):
        destra.axvline(limite, color=SERIE_2, linewidth=1.6, linestyle="--")
    destra.axvline(0, color=INCHIOSTRO_2, linewidth=1.2)
    destra.set_xlabel("residuo (kg)")
    destra.set_ylabel("numero di previsioni")
    destra.set_title("Distribuzione dei residui, 80 % tra le linee", loc="left", fontsize=10)
    return _salva(
        figura,
        cartella / "residui.png",
        "Residui del modello adottato",
        f"{len(previsioni)} previsioni fuori campione (cross-validation 2004–2009 e 2010–2012). "
        "Linee arancio: p10 e p90.",
    )


def importanza_variabili(v: ValutazioneFinale, cartella: Path) -> Path:
    figura, asse = _nuova_figura()
    tabella = v.importanza.iloc[::-1]  # la più importante in alto
    etichette = [ETICHETTE_FEATURE.get(nome, nome) for nome in tabella.index]
    asse.barh(
        etichette,
        tabella["media_kg"],
        xerr=tabella["dev_std_kg"],
        color=SERIE_1,
        height=0.55,
        error_kw={"ecolor": INCHIOSTRO_2, "elinewidth": 1.2, "capsize": 3},
    )
    for posizione, (valore, dev) in enumerate(
        zip(tabella["media_kg"], tabella["dev_std_kg"], strict=True)
    ):
        asse.text(valore + dev + 0.05, posizione, _decimali(valore), va="center", fontsize=9)
    asse.set_xlabel("aumento del MAE se la variabile viene mischiata (kg per colonia)")
    asse.grid(False, axis="y")
    asse.set_xlim(0, float((tabella["media_kg"] + tabella["dev_std_kg"]).max()) * 1.18)
    if "anno" in tabella.index and tabella.loc["anno", "media_kg"] == 0:
        asse.text(
            0.98,
            0.04,
            "«anno» vale zero per costruzione: i suoi valori 2010–2012\n"
            "stanno tutti oltre il range di addestramento.",
            transform=asse.transAxes,
            ha="right",
            fontsize=8.5,
            color=INCHIOSTRO_2,
        )
    return _salva(
        figura,
        cartella / "importanza_variabili.png",
        "Importanza delle variabili",
        "Importanza per permutazione sul 2010–2012 (20 ripetizioni, barra: deviazione standard).",
    )


def distribuzione_target(v: ValutazioneFinale, dati: pd.DataFrame, cartella: Path) -> Path:
    figura, asse = _nuova_figura()
    d = v.distribuzione
    asse.hist(dati[TARGET], bins=30, color=SERIE_1, edgecolor=SUPERFICIE, linewidth=1.5)
    asse.axvline(d.mediana, color=INCHIOSTRO_2, linewidth=1.2)
    for limite in (d.p10, d.p90):
        asse.axvline(limite, color=SERIE_2, linewidth=1.6, linestyle="--")
    asse.set_xlabel("resa per colonia (kg)")
    asse.set_ylabel("numero di righe")
    alto = asse.get_ylim()[1]
    asse.text(
        d.mediana + 0.4, alto * 0.96, f"mediana {_decimali(d.mediana, 1)}", fontsize=9, va="top"
    )
    asse.text(d.p90 + 0.4, alto * 0.85, f"p90 {_decimali(d.p90, 1)}", fontsize=9, va="top")
    asse.text(
        d.p10 - 0.4, alto * 0.85, f"p10 {_decimali(d.p10, 1)}", fontsize=9, va="top", ha="right"
    )
    asse.text(
        0.98,
        0.62,
        f"asimmetria {_decimali(d.asimmetria)}\n"
        f"media {_decimali(d.media, 1)} · dev. std {_decimali(d.dev_std, 1)}",
        transform=asse.transAxes,
        ha="right",
        fontsize=9,
        color=INCHIOSTRO_2,
    )
    return _salva(
        figura,
        cartella / "distribuzione_target.png",
        "Distribuzione della resa per colonia",
        f"{d.righe} righe del pannello di addestramento (40 stati, 1998–2012). "
        "Linee arancio: p10 e p90.",
    )


def mae_per_periodo(v: ValutazioneFinale, cartella: Path) -> Path:
    figura, asse = _nuova_figura(larghezza=7.8)
    periodi = ["2004–05", "2006–07", "2008–09", "2010–12"]
    risultati = [*v.cv.risultati_per_fold(), v.hold_out.risultati()]
    serie = [
        (RANDOM_FOREST_OTTIMIZZATA, "random forest ottimizzata", SERIE_1),
        (PERSISTENZA, "persistenza", SERIE_2),
        (MEDIA_STATO_TREND, "media dello stato + tendenza", CONTESTO),
    ]
    larghezza, x = 0.26, np.arange(len(periodi))
    for indice, (nome, etichetta, colore) in enumerate(serie):
        valori = [r[nome].mae_kg for r in risultati]
        barre = asse.bar(
            x + (indice - 1) * (larghezza + 0.02),
            valori,
            larghezza,
            color=colore,
            edgecolor=SUPERFICIE,
            linewidth=1.5,
            label=etichetta,
        )
        for barra, valore in zip(barre, valori, strict=True):
            centro = barra.get_x() + barra.get_width() / 2
            asse.text(centro, valore + 0.06, _decimali(valore), ha="center", fontsize=8)
    asse.set_xticks(x, periodi)
    asse.set_ylabel("MAE (kg per colonia)")
    asse.set_ylim(0, max(r[nome].mae_kg for r in risultati for nome, _, _ in serie) * 1.3)
    asse.grid(False, axis="x")
    asse.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INCHIOSTRO_2, ncol=3)
    return _salva(
        figura,
        cartella / "mae_per_periodo.png",
        "MAE per periodo di valutazione",
        "I tre fold della cross-validation e il 2010–2012 (addestramento fino al 2009): "
        "nessun metodo vince sempre.",
    )


def disegna_tutti(v: ValutazioneFinale, dati: pd.DataFrame, cartella: Path) -> list[Path]:
    """Scrive i cinque grafici in `cartella` (creata se manca) e ne restituisce i percorsi."""
    plt.switch_backend("Agg")  # nessuna finestra: si scrive solo su file
    cartella.mkdir(parents=True, exist_ok=True)
    return [
        previsto_vs_reale(v, cartella),
        residui(v, cartella),
        importanza_variabili(v, cartella),
        distribuzione_target(v, dati, cartella),
        mae_per_periodo(v, cartella),
    ]


def main(argomenti: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Disegna i grafici della valutazione finale.")
    parser.add_argument(
        "--cartella",
        type=Path,
        default=None,
        help="dove scrivere i PNG (predefinito: docs/images/)",
    )
    opzioni = parser.parse_args(argomenti)
    cartella = opzioni.cartella or config.RADICE / "docs" / "images"
    try:
        configura()
        dati = carica_dataset_training(Database(config.ottieni().database))
        percorsi = disegna_tutti(valuta_finale(dati), dati, cartella)
    except BeeWatchError as errore:
        print(f"Grafici non generati: {errore}", file=sys.stderr)
        return 1
    for percorso in percorsi:
        print(percorso)
    return 0


if __name__ == "__main__":
    sys.exit(main())
