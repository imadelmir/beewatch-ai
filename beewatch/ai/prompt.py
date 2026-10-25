"""Caricamento e composizione dei prompt (M5-T4).

I testi dei prompt stanno in `beewatch/ai/prompts/*.md`, uno per file, ciascuno con la versione
nella prima riga (`<!-- versione: v1 -->`): si rivedono come documenti e la versione finisce nel
database con ogni riepilogo. Qui non c'è nessuna chiamata al modello (M5-T1/T2), nessuna
validazione della risposta (M5-T3) e nessuna lettura dal database (M5-T5): solo i testi.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from beewatch.exceptions import ConfigError
from beewatch.logging_config import ottieni_logger

logger = ottieni_logger(__name__)

CARTELLA = Path(__file__).parent / "prompts"
NOME_SISTEMA = "system"
NOME_RIEPILOGO = "riepilogo"

LUNGHEZZA_MASSIMA_NOTE = 4000  # oltre, la nota si tronca e il modello lo sa
SENZA_DATI = "(nessun dato)"
SENZA_NOTE = "(l'apicoltore non ha scritto note)"

_VERSIONE = re.compile(r"\A<!--\s*versione:\s*([A-Za-z0-9._-]{1,20})\s*-->\s*\n")
_SEGNAPOSTO = re.compile(r"\{\{(\w+)\}\}")
CAMPI_RICHIESTA = ("alveare", "ispezione", "storico", "raccolti", "note")

# I delimitatori del blocco delle note: se la nota li contenesse, potrebbe chiudere il blocco in
# anticipo e far passare il resto come istruzioni.
_APERTURA_NOTE = "<<<NOTE"
_CHIUSURA_NOTE = "FINE NOTE>>>"


@dataclass(frozen=True)
class Prompt:
    nome: str
    versione: str
    testo: str  # senza la riga della versione


@cache
def carica_prompt(nome: str) -> Prompt:
    """Il prompt `nome` dalla cartella `prompts/`, con la sua versione.

    Raises:
        ConfigError: file mancante o senza la riga `<!-- versione: … -->`: è un errore di
            installazione, non dell'utente.
    """
    percorso = CARTELLA / f"{nome}.md"
    try:
        grezzo = percorso.read_text(encoding="utf-8")
    except OSError as errore:
        raise ConfigError(f"Il file del prompt «{nome}» non si legge: {percorso}.") from errore
    corrispondenza = _VERSIONE.match(grezzo)
    if corrispondenza is None:
        raise ConfigError(
            f"Il file del prompt «{nome}» non inizia con la riga «<!-- versione: vN -->»."
        )
    return Prompt(nome=nome, versione=corrispondenza.group(1), testo=grezzo[corrispondenza.end() :])


def prompt_di_sistema() -> Prompt:
    return carica_prompt(NOME_SISTEMA)


def versione_prompt() -> str:
    """La versione da salvare con ogni riepilogo: quella del sistema e della richiesta, uguali.

    I due file si versionano insieme (se ne cambia uno, si aumenta la versione di entrambi): una
    sola etichetta dice quale insieme di istruzioni ha prodotto una risposta.
    """
    sistema, richiesta = carica_prompt(NOME_SISTEMA), carica_prompt(NOME_RIEPILOGO)
    if sistema.versione != richiesta.versione:
        raise ConfigError(
            f"I prompt hanno versioni diverse ({sistema.versione} e {richiesta.versione}): "
            "vanno aggiornati insieme."
        )
    return sistema.versione


def _neutralizza_delimitatori(note: str) -> str:
    return note.replace(_APERTURA_NOTE, "<< <NOTE").replace(_CHIUSURA_NOTE, "FINE NOTE> >>")


def _prepara_note(note: str | None) -> str:
    if note is None or not note.strip():
        return SENZA_NOTE
    pulite = _neutralizza_delimitatori(note.strip())
    if len(pulite) > LUNGHEZZA_MASSIMA_NOTE:
        logger.warning(
            "Nota di %d caratteri troncata a %d prima di inviarla al modello",
            len(pulite),
            LUNGHEZZA_MASSIMA_NOTE,
        )
        pulite = (
            pulite[:LUNGHEZZA_MASSIMA_NOTE]
            + "\n[nota troncata: il resto del testo non è stato inviato]"
        )
    return pulite


def costruisci_richiesta(
    *,
    alveare: str,
    ispezione: str,
    storico: str,
    raccolti: str,
    note: str | None,
) -> str:
    """La richiesta per il modello: il modello `riepilogo.md` con i dati al posto dei segnaposto.

    Ogni valore è già testo pronto (lo prepara l'assistente, M5-T5). Un valore vuoto diventa
    «(nessun dato)»: il modello deve vedere che manca, non trovare una sezione vuota. La
    sostituzione è in un solo passaggio: un `{{segnaposto}}` scritto dentro una nota resta com'è.
    """
    modello = carica_prompt(NOME_RIEPILOGO).testo
    valori = {
        "alveare": alveare,
        "ispezione": ispezione,
        "storico": storico,
        "raccolti": raccolti,
        "note": _prepara_note(note),
    }
    usati = set(_SEGNAPOSTO.findall(modello))
    if usati != set(CAMPI_RICHIESTA):
        raise ConfigError(
            "Il prompt «riepilogo» ha segnaposto diversi da quelli attesi: "
            f"{sorted(usati)} invece di {sorted(CAMPI_RICHIESTA)}."
        )

    def sostituisci(corrispondenza: re.Match[str]) -> str:
        valore = valori[corrispondenza.group(1)]
        return valore.strip() if valore and valore.strip() else SENZA_DATI

    return _SEGNAPOSTO.sub(sostituisci, modello).strip()
