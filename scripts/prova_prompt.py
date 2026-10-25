"""Prova il prompt del riepilogo su note realistiche con un modello VERO (M5-T4).

    python scripts/prova_prompt.py                      # le dieci note, il provider di .env
    python scripts/prova_prompt.py --nota 03_a3_varroa_lunga
    python scripts/prova_prompt.py --output risultati_v1.md

Per ogni nota in `tests/fixtures/note/` costruisce la richiesta con il prompt in
`beewatch/ai/prompts/`, chiama il modello, valida la risposta contro lo schema (M5-T3) e
controlla le attese scritte in `attese.json`: quali stati sono ammessi, la confidenza massima, e
che non compaiano farmaci o dosi.

Serve un modello raggiungibile (vedi `scripts/verifica_llm.py`). I test automatici NON
sostituiscono questa prova: provano il codice e la coerenza dei prompt, non che un modello vero
li rispetti.

Per confrontare due versioni del prompt: eseguire con la versione A, salvare con `--output`,
modificare i file `.md` (e la riga `<!-- versione: -->`), rieseguire con un altro `--output`. I due
file sono il «prima e dopo» da incollare in `docs/prompt_engineering.md`.

Esce con 0 se tutte le note hanno superato i controlli, con 1 altrimenti.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from beewatch import config
from beewatch.ai.llm import crea_client
from beewatch.ai.prompt import costruisci_richiesta, prompt_di_sistema, versione_prompt
from beewatch.ai.riepilogo import CONFIDENZE, EsitoRiepilogo, Riepilogo, genera_riepilogo
from beewatch.exceptions import BeeWatchError
from beewatch.logging_config import configura

CARTELLA_NOTE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "note"

# Ciò che il prompt vieta (regole 3 e 4): nomi di trattamenti e unità di dosaggio.
TERMINI_VIETATI = re.compile(
    r"\b(mg|ml|ossalico|formico|timolo|amitraz|apivar|apistan|apiguard|bioxal|dosaggio|dosi?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Attesa:
    stati_ammessi: tuple[str, ...]
    confidenza_massima: str | None  # None = nessun limite


def carica_attese(cartella: Path = CARTELLA_NOTE) -> dict[str, Attesa]:
    grezzo = json.loads((cartella / "attese.json").read_text(encoding="utf-8"))
    return {
        nome: Attesa(tuple(voce["stati_ammessi"]), voce["confidenza_massima"])
        for nome, voce in grezzo.items()
    }


def testo_del_riepilogo(riepilogo: Riepilogo) -> str:
    """Tutto il testo libero del riepilogo, per cercarvi i termini vietati."""
    parti = [*riepilogo.elementi_rilevati, *riepilogo.campi_non_deducibili]
    parti += [c.descrizione for c in riepilogo.criticita]
    parti += [a.azione for a in riepilogo.azioni_suggerite]
    return "\n".join(parti)


def controlla_riepilogo(riepilogo: Riepilogo, attesa: Attesa) -> list[str]:
    """I controlli falliti (vuoto = tutto bene) del riepilogo di una nota."""
    falliti = []
    if riepilogo.stato_salute not in attesa.stati_ammessi:
        falliti.append(
            f"stato «{riepilogo.stato_salute}» fuori da {', '.join(attesa.stati_ammessi)}"
        )
    massima = attesa.confidenza_massima
    if massima is not None and CONFIDENZE.index(riepilogo.confidenza) < CONFIDENZE.index(massima):
        falliti.append(f"confidenza «{riepilogo.confidenza}» più alta di «{massima}»")
    trovati = sorted(
        {m.group(0).lower() for m in TERMINI_VIETATI.finditer(testo_del_riepilogo(riepilogo))}
    )
    if trovati:
        falliti.append("termini vietati: " + ", ".join(trovati))
    return falliti


def richiesta_per(nota: str) -> str:
    """La richiesta per una nota, con il solo contesto che una nota isolata ha (nessuno)."""
    return costruisci_richiesta(alveare="", ispezione="", storico="", raccolti="", note=nota)


def esamina(nome: str, nota: str, attesa: Attesa, client) -> tuple[EsitoRiepilogo, list[str]]:
    esito = genera_riepilogo(
        client, prompt_di_sistema().testo, richiesta_per(nota), temperatura=0.2
    )
    falliti = [] if esito.valido else ["risposta non valida anche dopo il tentativo correttivo"]
    falliti += controlla_riepilogo(esito.riepilogo, attesa) if esito.valido else []
    return esito, falliti


def main(argomenti: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prova il prompt su note realistiche.")
    parser.add_argument("--nota", default=None, help="solo questa nota (nome del file, senza .txt)")
    parser.add_argument("--output", default=None, help="scrive i risultati in questo file markdown")
    opzioni = parser.parse_args(argomenti)

    try:
        configura()
        cfg = config.ottieni().llm
        client = crea_client(cfg)
        attese = carica_attese()
        nomi = [opzioni.nota] if opzioni.nota else sorted(attese)
        versione = versione_prompt()
    except (BeeWatchError, KeyError, OSError) as errore:
        print(f"Impossibile iniziare: {errore!r}", file=sys.stderr)
        return 1

    print(f"Prompt {versione}, provider {cfg.provider}, modello {cfg.modello}")
    righe = [
        f"# Prova del prompt {versione}",
        f"Provider `{cfg.provider}`, modello `{cfg.modello}`.",
        "",
    ]
    superate = 0
    for nome in nomi:
        nota = (CARTELLA_NOTE / f"{nome}.txt").read_text(encoding="utf-8").strip()
        try:
            esito, falliti = esamina(nome, nota, attese[nome], client)
        except BeeWatchError as errore:
            print(f"  {nome}: ERRORE del provider: {errore}")
            righe += [f"## {nome}", f"Errore del provider: {errore}", ""]
            continue
        r = esito.riepilogo
        stato = "OK " if not falliti else "KO "
        superate += not falliti
        print(
            f"  {stato}{nome}: {r.stato_salute}/{r.confidenza}, {len(esito.risposte)} chiamat"
            f"{'a' if len(esito.risposte) == 1 else 'e'}, {esito.durata_ms} ms"
            + (f"  <- {'; '.join(falliti)}" if falliti else "")
        )
        righe += [
            f"## {nome} — {'superata' if not falliti else 'NON superata'}",
            f"Nota: «{nota}»",
            "",
            "```json",
            json.dumps(r.a_dict(), ensure_ascii=False, indent=2),
            "```",
            *(f"- controllo fallito: {f}" for f in falliti),
            "",
        ]
    print(f"Superate {superate} note su {len(nomi)}.")
    if opzioni.output:
        Path(opzioni.output).write_text("\n".join(righe) + "\n", encoding="utf-8")
        print(f"Risultati in {opzioni.output}")
    return 0 if superate == len(nomi) else 1


if __name__ == "__main__":
    sys.exit(main())
