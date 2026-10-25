"""L'assistente delle ispezioni: dal contesto dell'alveare al riepilogo validato (M5-T5).

Questo modulo non parla con il database né con Streamlit. Riceve un `ContestoIspezione` (lo
carica `Servizi`, che ha i repository), lo trasforma in testo per il prompt, chiama il modello
con `genera_riepilogo` (M5-T3) e restituisce l'esito. Persistenza e controlli di appartenenza
sono nel servizio: qui c'è solo ciò che dipende dal modello.

**Cosa entra nel prompt.** L'alveare (codice, stato, data di installazione, anno della regina),
l'ispezione (data, rischio valutato dall'apicoltore, peso, telaini, regina, sciamatura), fino a tre
ispezioni precedenti e fino a cinque raccolti dell'apiario. Il nome dell'apiario sì,
**coordinate e località no**: il modello non ha bisogno di sapere dove sono le arnie.
**Le previsioni di produzione non entrano**: sono stime per uno stato USA, non dicono nulla di
questa famiglia, e un consiglio operativo derivato da un numero del genere sarebbe un errore.

**Cosa finisce nel log.** Le quattro sezioni di contesto, così come vanno al modello (a livello
INFO: è la prova richiesta dalla Definition of Done di M5-T5, e gli stessi dati vanno al provider).
Il testo della nota dell'ispezione corrente solo a livello DEBUG; a INFO ne compare la lunghezza.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from beewatch.ai.llm import LLMClient
from beewatch.ai.prompt import costruisci_richiesta, prompt_di_sistema, versione_prompt
from beewatch.ai.riepilogo import EsitoRiepilogo, genera_riepilogo
from beewatch.logging_config import ottieni_logger
from beewatch.models import Alveare, Ispezione, Raccolto

logger = ottieni_logger(__name__)

MAX_PRECEDENTI = 3  # ispezioni precedenti nel contesto
MAX_RACCOLTI = 5
LUNGHEZZA_NOTA_PRECEDENTE = 200  # le note delle ispezioni precedenti si accorciano
NON_REGISTRATO = "non registrato"


@dataclass(frozen=True)
class ContestoIspezione:
    """Tutto ciò che si sa dell'ispezione da riassumere, già filtrato per l'utente."""

    apiario: str  # solo il nome
    alveare: Alveare
    ispezione: Ispezione
    precedenti: tuple[Ispezione, ...] = ()  # dalla più recente
    raccolti: tuple[Raccolto, ...] = ()  # dal più recente


def _si_no(valore: bool) -> str:
    return "sì" if valore else "no"


def _kg(valore: Decimal | None) -> str:
    return NON_REGISTRATO if valore is None else f"{valore} kg".replace(".", ",")


def _numero(valore: int | None) -> str:
    return NON_REGISTRATO if valore is None else str(valore)


def _accorcia(testo: str, massimo: int) -> str:
    uno = " ".join(testo.split())
    return uno if len(uno) <= massimo else uno[: massimo - 1].rstrip() + "…"


def descrivi_alveare(alveare: Alveare, apiario: str) -> str:
    return "\n".join(
        [
            f"Apiario: {apiario}",
            f"Codice: {alveare.codice}",
            f"Stato registrato: {alveare.stato.value.replace('_', ' ')}",
            f"Installato il: {alveare.data_installazione or NON_REGISTRATO}",
            f"Anno della regina: {_numero(alveare.anno_regina)}",
        ]
    )


def descrivi_ispezione(ispezione: Ispezione) -> str:
    return "\n".join(
        [
            f"Data: {ispezione.data_ispezione}",
            f"Rischio valutato dall'apicoltore: {ispezione.livello_rischio.value}",
            f"Peso: {_kg(ispezione.peso_kg)}",
            f"Telaini di covata: {_numero(ispezione.telaini_covata)}",
            f"Telaini di scorte: {_numero(ispezione.telaini_scorte)}",
            f"Regina vista: {_si_no(ispezione.regina_vista)}",
            f"Sciamatura: {_si_no(ispezione.sciamatura)}",
        ]
    )


def descrivi_precedente(ispezione: Ispezione) -> str:
    riga = (
        f"- {ispezione.data_ispezione}: rischio {ispezione.livello_rischio.value}, "
        f"peso {_kg(ispezione.peso_kg)}, covata {_numero(ispezione.telaini_covata)}, "
        f"scorte {_numero(ispezione.telaini_scorte)}, regina vista {_si_no(ispezione.regina_vista)}"
    )
    if ispezione.note and ispezione.note.strip():
        riga += f"; note: «{_accorcia(ispezione.note, LUNGHEZZA_NOTA_PRECEDENTE)}»"
    return riga


def descrivi_raccolto(raccolto: Raccolto) -> str:
    return (
        f"- {raccolto.data_raccolto}: miele {raccolto.tipo_miele.value.replace('_', ' ')}, "
        f"{_kg(raccolto.quantita_kg)}"
    )


def sezioni_del_contesto(contesto: ContestoIspezione) -> dict[str, str]:
    """Le sezioni di testo del prompt (senza la nota): alveare, ispezione, storico, raccolti."""
    return {
        "alveare": descrivi_alveare(contesto.alveare, contesto.apiario),
        "ispezione": descrivi_ispezione(contesto.ispezione),
        "storico": "\n".join(descrivi_precedente(i) for i in contesto.precedenti[:MAX_PRECEDENTI]),
        "raccolti": "\n".join(descrivi_raccolto(r) for r in contesto.raccolti[:MAX_RACCOLTI]),
    }


class AssistenteIspezioni:
    """Chiede al modello il riepilogo di un'ispezione. Il client si passa dal di fuori."""

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    @property
    def in_locale(self) -> bool:
        """True se le note restano sul computer (Ollama), False se escono (OpenRouter)."""
        return self._client.in_locale

    def riassumi(self, contesto: ContestoIspezione) -> EsitoRiepilogo:
        """Il riepilogo dell'ispezione, con il suo esito.

        Raises:
            LLMError: il provider non risponde o rifiuta la richiesta (già ritentato, M5-T2).
                Una risposta malformata invece non solleva: vedi `EsitoRiepilogo.valido`.
        """
        sezioni = sezioni_del_contesto(contesto)
        nota = contesto.ispezione.note
        richiesta = costruisci_richiesta(**sezioni, note=nota)

        logger.info(
            "Contesto per il riepilogo (ispezione %s, alveare %s, prompt %s, provider %s, "
            "nota di %d caratteri, %d ispezioni precedenti, %d raccolti):\n%s",
            contesto.ispezione.id,
            contesto.alveare.codice,
            versione_prompt(),
            self._client.provider,
            len(nota or ""),
            min(len(contesto.precedenti), MAX_PRECEDENTI),
            min(len(contesto.raccolti), MAX_RACCOLTI),
            "\n".join(f"[{nome}]\n{testo}" for nome, testo in sezioni.items()),
        )
        logger.debug("Richiesta completa al modello:\n%s", richiesta)

        return genera_riepilogo(self._client, prompt_di_sistema().testo, richiesta)
