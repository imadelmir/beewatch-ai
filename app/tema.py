"""Il tema chiaro e scuro del mockup, e l'interruttore per sceglierlo.

I colori dei due temi sono quelli delle tavole «Design System» del mockup ad alta fedeltà. Stanno
in due posti, ognuno per ciò che sa fare:

- `.streamlit/config.toml` (`[theme.light]`, `[theme.dark]`): il tema **nativo**, che colora campi,
  tabelle, grafici e messaggi di Streamlit;
- qui, `PALETTE`: le variabili `--bw-*` per il file `app/stile/beewatch.css`, che fa il resto
  (sfondo a nido d'ape, card, sidebar, pastiglie). Un test controlla che i colori coincidano.

**Come si cambia tema.** Streamlit non ha un comando per cambiare il tema da Python: lo sceglie il
browser e lo ricorda (`localStorage`, una voce per indirizzo della pagina). L'interruttore scrive
quella voce e ricarica la pagina; la sessione riprende grazie al cookie dell'accesso (vedi
`avvio.riprendi_accesso`). La chiave dipende da Streamlit (`stActiveTheme-<percorso>-v2`): le
versioni sono bloccate e un test controlla che il formato ci sia ancora.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import streamlit as st

Tema = Literal["light", "dark"]

FILE_CSS = Path(__file__).parent / "stile" / "beewatch.css"

# I token del design system. Le varianti «tenue» sono gli sfondi delle pastiglie e delle voci
# attive.
PALETTE: dict[str, dict[str, str]] = {
    "light": {
        "accento": "#F5B301",
        "accento2": "#FFD256",
        "sfondo": "#FDF9EC",
        "superficie": "#FFFFFF",
        "bordo": "#F2E9D2",
        "testo": "#1E1A12",
        "testo2": "#7C7566",
        "successo": "#2FA96A",
        "attenzione": "#E8890B",
        "critico": "#E0524A",
        # derivati
        "accento-testo": "#B98200",
        "accento-tenue": "#FFF4D1",
        "attenzione-tenue": "#FDEBD6",
        "critico-tenue": "#FBE3E1",
        "successo-tenue": "#E1F4EA",
        "voce-attiva": "#FFF1C7",
        "voce-attiva-testo": "#1E1A12",
        "ombra": "0 1px 2px rgba(30, 26, 18, 0.04), 0 8px 24px -12px rgba(30, 26, 18, 0.10)",
        "favo": "rgba(232, 190, 90, 0.20)",
        "alone": "rgba(255, 214, 102, 0.35)",
    },
    "dark": {
        "accento": "#FFC709",
        "accento2": "#FFDD55",
        "sfondo": "#0A0A0A",
        "superficie": "#151412",
        "bordo": "#2A2620",
        "testo": "#FFFFFF",
        "testo2": "#9B968D",
        "successo": "#4ADE80",
        "attenzione": "#FFA726",
        "critico": "#FF6B6B",
        # derivati
        "accento-testo": "#FFC709",
        "accento-tenue": "rgba(255, 199, 9, 0.10)",
        "attenzione-tenue": "rgba(255, 167, 38, 0.10)",
        "critico-tenue": "rgba(255, 107, 107, 0.10)",
        "successo-tenue": "rgba(74, 222, 128, 0.10)",
        "voce-attiva": "#FFC709",
        "voce-attiva-testo": "#1E1A12",
        "ombra": "0 1px 2px rgba(0, 0, 0, 0.4)",
        "favo": "rgba(255, 199, 9, 0.05)",
        "alone": "rgba(255, 170, 0, 0.10)",
    },
}

ETICHETTE_TEMA: dict[str, Tema] = {"Scuro": "dark", "Chiaro": "light"}
ICONE_TEMA = {"Scuro": ":material/dark_mode:", "Chiaro": ":material/light_mode:"}

# Gli indirizzi delle pagine dell'app (Streamlit li ricava dal nome del file, senza il numero
# davanti): il browser ricorda il tema per indirizzo, e l'interruttore lo scrive per tutti.
# Un test controlla che coincidano con le pagine del router.
PERCORSI_APP = [
    "", "accedi", "registrati", "onboarding", "home", "Alveari", "Ispezioni", "Previsione",
    "Assistente_AI", "Dashboard", "Trasparenza", "Report", "Impostazioni",
]  # fmt: skip


def tema_attivo() -> Tema:
    """Il tema che il browser sta mostrando; chiaro se non si sa (prima esecuzione, test)."""
    try:
        tipo = st.context.theme.type
    except Exception:  # pragma: no cover - fuori da una sessione Streamlit
        tipo = None
    return "dark" if tipo == "dark" else "light"


def _favo(colore: str) -> str:
    """Il nido d'ape dello sfondo: una tessera SVG ripetuta, del colore dato."""
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='112' height='194' viewBox='0 0 56 97'>"
        f"<path fill='none' stroke='{colore}' stroke-width='0.6' "
        "d='M28 64.7L0 48.5V16.2L28 0l28 16.2v32.3L28 64.7zm0 0V97'/></svg>"
    )
    # Codificato: Streamlit scarta un blocco di stile che contenga «<» (protezione dall'HTML).
    return f'url("data:image/svg+xml,{quote(svg)}")'


def variabili(tema: Tema) -> str:
    """Le variabili CSS `--bw-*` del tema, pronte per `:root`."""
    colori = PALETTE[tema]
    righe = [f"--bw-{nome}: {valore};" for nome, valore in colori.items()]
    righe.append(f"--bw-favo: {_favo(colori['favo'])};")
    righe.append(
        f"--bw-alone: radial-gradient(ellipse 60% 50% at 100% 0%, {colori['alone']}, transparent);"
    )
    return "\n".join(righe)


def applica_stile() -> None:
    """Inietta lo stile del mockup con i colori del tema attivo. Non occupa spazio nella pagina."""
    css = FILE_CSS.read_text(encoding="utf-8")
    # Con il solo <style>, Streamlit lo mette fra gli «eventi», che il router svuota quando passa
    # alla pagina: un elemento vuoto lo tiene nel corpo, e il CSS stesso nasconde il contenitore.
    st.html(
        f"<style>:root {{\n{variabili(tema_attivo())}\n}}\n{css}</style>"
        '<span class="bw-stile"></span>'
    )


def scrivi_tema(tema: Tema) -> None:
    """Fa ricordare al browser il tema per ogni pagina dell'app, poi ricarica.

    La pagina riparte da capo: l'accesso riprende dal cookie della sessione.
    """
    valori = {"valore": json.dumps("Dark" if tema == "dark" else "Light"),
              "percorsi": json.dumps(PERCORSI_APP)}  # fmt: skip
    script = """<script>
const valore = JSON.stringify({valore});  // Streamlit lo rilegge con JSON.parse
const base = window.location.pathname.replace(/[^/]*$/, "");
const chiave = (p) => "stActiveTheme-" + p + "-v2";
for (const k of Object.keys(window.localStorage)) {{
  if (k.startsWith("stActiveTheme-")) window.localStorage.removeItem(k);
}}
for (const p of {percorsi}) window.localStorage.setItem(chiave(base + p), valore);
window.localStorage.setItem(chiave(window.location.pathname), valore);
window.location.reload();
</script>""".format(**valori)
    st.html(script, unsafe_allow_javascript=True)


def interruttore_tema() -> None:
    """L'interruttore «Scuro | Chiaro» del mockup. Cambiando scelta, cambia il tema dell'app."""
    attuale = "Scuro" if tema_attivo() == "dark" else "Chiaro"
    with st.container(key="bw_tema"):
        scelta = st.segmented_control(
            "Tema",
            options=list(ETICHETTE_TEMA),
            default=attuale,
            format_func=lambda o: f"{ICONE_TEMA[o]} {o}",
            key="bw_tema_scelta",
            label_visibility="collapsed",
        )
    if scelta and scelta != attuale:
        scrivi_tema(ETICHETTE_TEMA[scelta])
