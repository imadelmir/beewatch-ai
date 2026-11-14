"""Genera i loghi SVG dell'app (app/static/logo_*.svg) dal font Poppins del repository.

Il logo del mockup: cinque esagoni a nido d'ape (uno pieno, con il punto scuro al centro) e la
scritta «BeeWatch AI» in Poppins Bold, con «AI» nel giallo del tema. Le lettere diventano
tracciati SVG: il logo si vede uguale anche dove il font non c'è (st.logo lo mostra come
immagine). Si rilancia solo se cambia il disegno:

    python scripts/genera_logo.py
"""

from __future__ import annotations

import math
from pathlib import Path

from matplotlib.font_manager import FontProperties
from matplotlib.path import Path as Tracciato
from matplotlib.textpath import TextPath

RADICE = Path(__file__).resolve().parent.parent
STATICI = RADICE / "app" / "static"
FONT = FontProperties(fname=str(STATICI / "fonts" / "Poppins-Bold.ttf"))

TEMI = {
    "chiaro": {"testo": "#1E1A12", "accento": "#F5B301", "tenue": "#FFD878", "punto": "#4A3A12"},
    "scuro": {"testo": "#FFFFFF", "accento": "#FFC709", "tenue": "#FFDD55", "punto": "#1E1A12"},
}


def esagono(cx: float, cy: float, r: float) -> str:
    punti = [
        (cx + r * math.cos(math.radians(90 + 60 * k)), cy + r * math.sin(math.radians(90 + 60 * k)))
        for k in range(6)
    ]
    return "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in punti) + " Z"


def nido(colori: dict[str, str], x0: float = 0, y0: float = 0) -> str:
    """I cinque esagoni del marchio, in un riquadro di circa 40x52."""
    r, larghezza = 9.0, 9.0 * math.sqrt(3)
    cx, cy = x0 + 8.5, y0 + 9.5
    contorno = f'fill="none" stroke="{colori["tenue"]}" stroke-width="2"'
    pezzi = [
        f'<path d="{esagono(cx, cy, r)}" {contorno}/>',
        f'<path d="{esagono(cx + larghezza, cy, r)}" {contorno}/>',
        f'<path d="{esagono(cx, cy + 3 * r, r)}" {contorno}/>',
        f'<path d="{esagono(cx + larghezza, cy + 3 * r, r)}" fill="{colori["tenue"]}" '
        f'stroke="{colori["tenue"]}" stroke-width="2"/>',
        f'<path d="{esagono(cx + larghezza / 2, cy + 1.5 * r, r)}" fill="{colori["accento"]}" '
        f'stroke="{colori["accento"]}" stroke-width="2"/>',
        f'<circle cx="{cx + larghezza / 2:.2f}" cy="{cy + 1.5 * r:.2f}" r="3" '
        f'fill="{colori["punto"]}"/>',
    ]
    return "".join(pezzi)


def testo_svg(testo: str, x: float, base: float, dimensione: float) -> tuple[str, float]:
    """Il testo come tracciato SVG (y verso il basso) e la sua larghezza."""
    tracciato = TextPath((0, 0), testo, size=dimensione, prop=FONT)
    comandi, i = [], 0
    vertici, codici = tracciato.vertices, tracciato.codes
    while i < len(vertici):
        codice = codici[i]
        px, py = vertici[i][0] + x, base - vertici[i][1]
        if codice == Tracciato.MOVETO:
            comandi.append(f"M{px:.2f} {py:.2f}")
            i += 1
        elif codice == Tracciato.LINETO:
            comandi.append(f"L{px:.2f} {py:.2f}")
            i += 1
        elif codice == Tracciato.CURVE3:
            qx, qy = vertici[i + 1][0] + x, base - vertici[i + 1][1]
            comandi.append(f"Q{px:.2f} {py:.2f} {qx:.2f} {qy:.2f}")
            i += 2
        elif codice == Tracciato.CURVE4:
            q1 = (vertici[i + 1][0] + x, base - vertici[i + 1][1])
            q2 = (vertici[i + 2][0] + x, base - vertici[i + 2][1])
            comandi.append(f"C{px:.2f} {py:.2f} {q1[0]:.2f} {q1[1]:.2f} {q2[0]:.2f} {q2[1]:.2f}")
            i += 3
        else:  # CLOSEPOLY
            comandi.append("Z")
            i += 1
    return " ".join(comandi), tracciato.get_extents().x1


def logo(colori: dict[str, str]) -> str:
    beewatch, larghezza = testo_svg("BeeWatch", 50, 37, 25)
    ai, larghezza_ai = testo_svg("AI", 50 + larghezza + 6, 37, 25)
    totale = 50 + larghezza + 6 + larghezza_ai + 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {totale:.0f} 54" '
        f'width="{totale:.0f}" height="54">{nido(colori, 2, 2)}'
        f'<path d="{beewatch}" fill="{colori["testo"]}"/>'
        f'<path d="{ai}" fill="{colori["accento"]}"/></svg>\n'
    )


def icona(colori: dict[str, str]) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 54" width="40" height="54">'
        f"{nido(colori, 2, 2)}</svg>\n"
    )


if __name__ == "__main__":
    for nome, colori in TEMI.items():
        (STATICI / f"logo_{nome}.svg").write_text(logo(colori), encoding="utf-8")
        (STATICI / f"icona_{nome}.svg").write_text(icona(colori), encoding="utf-8")
    print("Loghi scritti in", STATICI)
