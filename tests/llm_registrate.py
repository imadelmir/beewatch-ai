"""Carica le risposte dei provider di `tests/fixtures/llm/` e le prepara su un `ServerFinto`.

    with ServerFinto() as server:
        accoda(server, "ollama_json_troncato", "ollama_valido")   # la prima, poi la seconda
        ...

Vedi `tests/fixtures/llm/README.md`: i file sono scritti a mano nel formato documentato dei
provider, non sono registrazioni di chiamate vere.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from llm_server import ServerFinto

CARTELLA = Path(__file__).parent / "fixtures" / "llm"


def carica(nome: str) -> dict[str, Any]:
    """Il file `nome`: {descrizione, stato, intestazioni, corpo}."""
    return json.loads((CARTELLA / f"{nome}.json").read_text(encoding="utf-8"))


def accoda(server: ServerFinto, *nomi: str) -> None:
    """Prepara sul server le risposte di questi scenari, in ordine."""
    for nome in nomi:
        voce = carica(nome)
        server.rispondi(voce["stato"], voce["corpo"], intestazioni=voce["intestazioni"])


def contenuto(nome: str) -> str:
    """Il testo che il modello ha scritto in uno scenario di successo (Ollama o OpenRouter)."""
    corpo = carica(nome)["corpo"]
    if "message" in corpo:
        return corpo["message"]["content"]
    return corpo["choices"][0]["message"]["content"]


def tutti() -> list[str]:
    return sorted(p.stem for p in CARTELLA.glob("*.json"))
