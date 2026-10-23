"""Prova una chiamata VERA al provider di modelli di linguaggio scelto in `.env` (M5-T1).

    python scripts/verifica_llm.py                       # il provider di LLM_PROVIDER
    python scripts/verifica_llm.py --provider openrouter --modello meta-llama/llama-3.1-8b-instruct
    python scripts/verifica_llm.py --provider ollama --modello llama3.2:1b

È il passo manuale della Definition of Done di M5-T1: i test automatici usano un server finto
(nessuna rete, nessuna chiave), quindi dicono che il codice parla il formato documentato, non
che il provider risponda davvero. Questo script lo dimostra, una volta per provider.

Serve:
  ollama      Ollama installato e acceso (`ollama serve`) e il modello scaricato
              (`ollama pull llama3.1:8b`).
  openrouter  una chiave in `LLM_API_KEY` (e un po' di credito: la chiamata costa una frazione di
              centesimo, 20 token al massimo).

Fa due chiamate brevi: una semplice, e una che chiede JSON (per sapere se il modello rispetta il
formato: serve a M5-T3). Esce con 0 se la prima è riuscita, con 1 se no; l'esito della seconda è
solo informativo. Non stampa mai la chiave.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace

from beewatch import config
from beewatch.ai.llm import crea_client
from beewatch.exceptions import BeeWatchError
from beewatch.logging_config import configura


def main(argomenti: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prova una chiamata vera al provider LLM.")
    parser.add_argument("--provider", choices=("ollama", "openrouter"), default=None,
                        help="sostituisce LLM_PROVIDER solo per questa prova")  # fmt: skip
    parser.add_argument(
        "--modello", default=None, help="sostituisce LLM_MODEL solo per questa prova"
    )
    opzioni = parser.parse_args(argomenti)

    try:
        configura()
        cfg = config.ottieni().llm
        cfg = replace(
            cfg,
            provider=opzioni.provider or cfg.provider,
            modello=opzioni.modello or cfg.modello,
        )
        client = crea_client(cfg)
        print(f"Provider {cfg.provider}, modello {cfg.modello}, timeout {cfg.timeout} s")
        semplice = client.completa(
            "Rispondi solo con la parola OK.",
            "Test di collegamento.",
            temperatura=0.0,
            massimo_token=20,
        )
    except BeeWatchError as errore:
        print(f"Chiamata NON riuscita: {errore}", file=sys.stderr)
        return 1

    print(f"  risposta:    {semplice.testo.strip()[:80]!r}")
    print(f"  modello:     {semplice.modello}")
    print(f"  durata:      {semplice.durata_ms} ms")
    print(f"  token:       {semplice.token_prompt} → {semplice.token_risposta}")

    try:
        formato = client.completa(
            'Rispondi solo con un oggetto JSON, senza altro testo: {"ok": true}.',
            "Test di formato.",
            temperatura=0.0,
            massimo_token=40,
            risposta_json=True,
        )
        json.loads(formato.testo)
        print("  formato JSON: rispettato")
    except BeeWatchError as errore:
        print(f"  formato JSON: la chiamata è fallita ({errore})")
    except ValueError:
        print("  formato JSON: NON rispettato (risposta non JSON): M5-T3 dovrà gestirlo")
    print("Chiamata riuscita.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
