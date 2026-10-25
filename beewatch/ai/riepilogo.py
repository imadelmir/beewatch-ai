"""Il riepilogo di un'ispezione: schema, parser e generazione con un solo tentativo correttivo.

Il modello risponde con testo, non con un oggetto: anche chiedendo JSON può restituire una
risposta troncata, circondata da frasi o con campi mancanti. Questo modulo trasforma quel testo
in un `Riepilogo` valido oppure dice, in modo onesto, che non ci è riuscito. Non solleva mai
un'eccezione per una risposta malformata (solo `LLMError` se è il *provider* a non rispondere).

Tre livelli, usabili da soli:

- `estrai_json`: toglie recinti di codice e frasi attorno, restituisce il dizionario;
- `valida_riepilogo`: controlla il dizionario contro lo schema e costruisce il `Riepilogo`;
- `genera_riepilogo`: chiama il modello; se la risposta non è valida riprova UNA volta
  dicendogli cosa non andava; al secondo fallimento restituisce un riepilogo «non disponibile».

Il testo dei prompt non sta qui (M5-T4) e nemmeno la persistenza (M5-T5).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from beewatch.ai.llm import LLMClient, RispostaLLM
from beewatch.exceptions import LLMError
from beewatch.logging_config import ottieni_logger

logger = ottieni_logger(__name__)

STATI_SALUTE = ("buono", "attenzione", "critico", "non_determinabile")
CONFIDENZE = ("alta", "media", "bassa")
GRAVITA = ("bassa", "media", "alta")
PRIORITA = ("bassa", "media", "alta")

LUNGHEZZA_MASSIMA_TESTO = 1000  # per ogni frase del riepilogo
ELEMENTI_MASSIMI = 20  # per ogni elenco
GIORNI_MASSIMI = 365
CANDIDATI_JSON_MASSIMI = 50  # quante «{» provare nel testo prima di arrendersi

MESSAGGIO_NON_DISPONIBILE = (
    "Il modello non ha prodotto un riepilogo leggibile. Le note dell'ispezione sono salvate "
    "e non sono state modificate: puoi riprovare."
)


class RiepilogoNonValido(LLMError):
    """La risposta del modello non è un riepilogo conforme allo schema.

    Figlia di `LLMError`: per chi non distingue è un errore del modello come gli altri.
    `problemi` elenca cosa non va, in italiano, un elemento per problema.
    """

    def __init__(self, problemi: list[str]) -> None:
        self.problemi = list(problemi)
        super().__init__("Risposta del modello non valida: " + "; ".join(self.problemi))


@dataclass(frozen=True)
class Criticita:
    descrizione: str
    gravita: str  # uno di GRAVITA


@dataclass(frozen=True)
class Azione:
    azione: str
    priorita: str  # uno di PRIORITA
    entro_giorni: int | None = None  # None = nessuna scadenza indicata


@dataclass(frozen=True)
class Riepilogo:
    """Cosa si può dire di un'ispezione leggendo le sue note.

    `campi_non_deducibili` elenca ciò che le note non permettono di sapere: dichiararlo è
    parte dello schema, perché il modello non deve riempire i vuoti con ipotesi.
    """

    stato_salute: str  # uno di STATI_SALUTE
    elementi_rilevati: tuple[str, ...]
    criticita: tuple[Criticita, ...]
    azioni_suggerite: tuple[Azione, ...]
    confidenza: str  # uno di CONFIDENZE
    campi_non_deducibili: tuple[str, ...]

    @classmethod
    def non_disponibile(cls) -> Riepilogo:
        """Il riepilogo onesto di quando il modello non ha prodotto nulla di utilizzabile."""
        return cls(
            stato_salute="non_determinabile",
            elementi_rilevati=(),
            criticita=(),
            azioni_suggerite=(),
            confidenza="bassa",
            campi_non_deducibili=(MESSAGGIO_NON_DISPONIBILE,),
        )

    def a_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    def a_dict(self) -> dict[str, Any]:
        """Dizionario con liste e tipi JSON (le tuple diventano liste): è lo schema di partenza."""
        return json.loads(self.a_json())


@dataclass(frozen=True)
class EsitoRiepilogo:
    """Il risultato di `genera_riepilogo`, con tutto ciò che serve a tracciarlo.

    `risposte` contiene una `RispostaLLM` per ogni chiamata fatta (una, o due se c'è stato il
    tentativo correttivo): provider, modello, durata e token di ciascuna.
    """

    riepilogo: Riepilogo
    valido: bool  # False = `riepilogo` è il «non disponibile», non l'opinione del modello
    risposte: tuple[RispostaLLM, ...]
    problemi: tuple[str, ...] = ()  # perché l'ultima risposta non andava (vuoto se valido)

    @property
    def corretto_al_secondo_tentativo(self) -> bool:
        return self.valido and len(self.risposte) > 1

    @property
    def durata_ms(self) -> int:
        return sum(r.durata_ms for r in self.risposte)

    @property
    def token_prompt(self) -> int | None:
        return _somma(r.token_prompt for r in self.risposte)

    @property
    def token_risposta(self) -> int | None:
        return _somma(r.token_risposta for r in self.risposte)


def _somma(valori: Any) -> int | None:
    """Somma dei token delle chiamate; None se anche solo una non li dichiara."""
    elenco = list(valori)
    if any(v is None for v in elenco):
        return None
    return sum(elenco)


# --------------------------------------------------------------------------- #
# Estrazione del JSON
# --------------------------------------------------------------------------- #


def estrai_json(testo: str) -> dict[str, Any]:
    """Il dizionario JSON contenuto in `testo`, anche se circondato da altro.

    Gestisce: recinti ```json … ```, frasi prima e dopo l'oggetto, parentesi graffe nel testo
    prima dell'oggetto vero. Non ripara JSON rotto (troncato, virgole mancanti): in quel caso
    solleva `RiepilogoNonValido`, e sarà il tentativo correttivo a chiedere una risposta nuova.
    Tra più oggetti decifrabili preferisce quello che ha `stato_salute`.
    """
    if not isinstance(testo, str) or not testo.strip():
        raise RiepilogoNonValido(["la risposta è vuota"])

    decodificatore = json.JSONDecoder()
    trovati: list[dict[str, Any]] = []
    posizione = testo.find("{")
    provati = 0
    while posizione != -1 and provati < CANDIDATI_JSON_MASSIMI:
        provati += 1
        try:
            oggetto, fine = decodificatore.raw_decode(testo, posizione)
        except ValueError:
            posizione = testo.find("{", posizione + 1)
            continue
        if isinstance(oggetto, dict):
            trovati.append(oggetto)
        # Si riparte dopo l'oggetto: le «{» al suo interno non sono candidati.
        posizione = testo.find("{", fine)

    for oggetto in trovati:
        if "stato_salute" in oggetto:
            return oggetto
    # Un oggetto troncato lascia intatti gli oggetti annidati al suo interno (ogni criticità,
    # ogni azione): decifrarli e prenderli per la risposta sarebbe un errore peggiore del
    # fallimento. Se il testo parla di `stato_salute` ma nessun oggetto lo contiene, è rotto.
    if '"stato_salute"' not in testo and trovati:
        return trovati[0]
    if "{" not in testo:
        raise RiepilogoNonValido(["la risposta non contiene un oggetto JSON"])
    raise RiepilogoNonValido(
        ["il JSON è malformato o troncato (la risposta si interrompe prima della fine)"]
    )


# --------------------------------------------------------------------------- #
# Validazione
# --------------------------------------------------------------------------- #

CAMPI = (
    "stato_salute",
    "elementi_rilevati",
    "criticita",
    "azioni_suggerite",
    "confidenza",
    "campi_non_deducibili",
)


def _valore_ammesso(
    valore: Any, ammessi: tuple[str, ...], percorso: str, problemi: list[str]
) -> str:
    if not isinstance(valore, str):
        problemi.append(f"{percorso}: deve essere una stringa tra {', '.join(ammessi)}")
        return ""
    normalizzato = valore.strip().lower()
    if normalizzato not in ammessi:
        problemi.append(f"{percorso}: «{valore[:40]}» non ammesso (ammessi: {', '.join(ammessi)})")
        return ""
    return normalizzato


def _frase(valore: Any, percorso: str, problemi: list[str]) -> str:
    if not isinstance(valore, str):
        problemi.append(f"{percorso}: deve essere un testo")
        return ""
    pulito = valore.strip()
    if not pulito:
        problemi.append(f"{percorso}: non può essere vuoto")
        return ""
    if len(pulito) > LUNGHEZZA_MASSIMA_TESTO:
        problemi.append(f"{percorso}: oltre {LUNGHEZZA_MASSIMA_TESTO} caratteri")
        return ""
    return pulito


def _elenco(valore: Any, percorso: str, problemi: list[str]) -> list[Any]:
    if not isinstance(valore, list):
        problemi.append(f"{percorso}: deve essere un elenco")
        return []
    if len(valore) > ELEMENTI_MASSIMI:
        problemi.append(f"{percorso}: più di {ELEMENTI_MASSIMI} elementi")
        return []
    return valore


def _giorni(valore: Any, percorso: str, problemi: list[str]) -> int | None:
    if valore is None:
        return None
    # `True` è un int per Python: un booleano qui è un errore del modello, non un numero.
    if isinstance(valore, bool) or not isinstance(valore, int):
        problemi.append(f"{percorso}: deve essere un numero intero di giorni oppure null")
        return None
    if not 1 <= valore <= GIORNI_MASSIMI:
        problemi.append(f"{percorso}: {valore} fuori da 1-{GIORNI_MASSIMI}")
        return None
    return valore


def valida_riepilogo(dati: Any) -> Riepilogo:
    """Il `Riepilogo` di un dizionario, o `RiepilogoNonValido` con TUTTI i problemi.

    Elencarli tutti (non solo il primo) serve al messaggio correttivo: il modello sbaglia meno
    se gli si dice tutto in una volta. Tutti i campi sono obbligatori, anche se con elenco vuoto:
    un campo assente è indistinguibile da uno dimenticato. I campi in più vengono ignorati.
    """
    if not isinstance(dati, dict):
        raise RiepilogoNonValido(
            ["la risposta deve essere un oggetto JSON, non un elenco o un valore"]
        )

    problemi: list[str] = []
    mancanti = [campo for campo in CAMPI if campo not in dati]
    if mancanti:
        problemi.append("campi mancanti: " + ", ".join(mancanti))

    stato = confidenza = ""
    if "stato_salute" in dati:
        stato = _valore_ammesso(dati["stato_salute"], STATI_SALUTE, "stato_salute", problemi)
    if "confidenza" in dati:
        confidenza = _valore_ammesso(dati["confidenza"], CONFIDENZE, "confidenza", problemi)

    elementi = _frasi_elenco(dati, "elementi_rilevati", problemi)
    non_deducibili = _frasi_elenco(dati, "campi_non_deducibili", problemi)

    criticita: list[Criticita] = []
    if "criticita" in dati:
        for i, voce in enumerate(_elenco(dati["criticita"], "criticita", problemi)):
            percorso = f"criticita[{i}]"
            if not isinstance(voce, dict):
                problemi.append(f"{percorso}: deve essere un oggetto con descrizione e gravita")
                continue
            descrizione = _frase(voce.get("descrizione"), f"{percorso}.descrizione", problemi)
            gravita = _valore_ammesso(voce.get("gravita"), GRAVITA, f"{percorso}.gravita", problemi)
            if descrizione and gravita:
                criticita.append(Criticita(descrizione, gravita))

    azioni: list[Azione] = []
    if "azioni_suggerite" in dati:
        for i, voce in enumerate(_elenco(dati["azioni_suggerite"], "azioni_suggerite", problemi)):
            percorso = f"azioni_suggerite[{i}]"
            if not isinstance(voce, dict):
                problemi.append(f"{percorso}: deve essere un oggetto con azione e priorita")
                continue
            testo = _frase(voce.get("azione"), f"{percorso}.azione", problemi)
            priorita = _valore_ammesso(
                voce.get("priorita"), PRIORITA, f"{percorso}.priorita", problemi
            )
            giorni = _giorni(voce.get("entro_giorni"), f"{percorso}.entro_giorni", problemi)
            if testo and priorita:
                azioni.append(Azione(testo, priorita, giorni))

    if problemi:
        raise RiepilogoNonValido(problemi)

    return Riepilogo(
        stato_salute=stato,
        elementi_rilevati=tuple(elementi),
        criticita=tuple(criticita),
        azioni_suggerite=tuple(azioni),
        confidenza=confidenza,
        campi_non_deducibili=tuple(non_deducibili),
    )


def _frasi_elenco(dati: dict[str, Any], campo: str, problemi: list[str]) -> list[str]:
    if campo not in dati:
        return []
    frasi = []
    for i, voce in enumerate(_elenco(dati[campo], campo, problemi)):
        frase = _frase(voce, f"{campo}[{i}]", problemi)
        if frase:
            frasi.append(frase)
    return frasi


def parsa_riepilogo(testo: str) -> Riepilogo:
    """Dal testo del modello al `Riepilogo`, o `RiepilogoNonValido`."""
    return valida_riepilogo(estrai_json(testo))


# --------------------------------------------------------------------------- #
# Generazione
# --------------------------------------------------------------------------- #


def messaggio_correttivo(utente: str, risposta_precedente: str, problemi: list[str]) -> str:
    """La richiesta del secondo tentativo: l'originale, la risposta sbagliata e cosa correggere."""
    elenco = "\n".join(f"- {problema}" for problema in problemi)
    return (
        f"{utente}\n\n"
        "La tua risposta precedente non era valida:\n"
        f"{risposta_precedente.strip()[:2000]}\n\n"
        f"Problemi trovati:\n{elenco}\n\n"
        "Rispondi di nuovo con UN SOLO oggetto JSON con tutti i campi richiesti, "
        "senza testo prima o dopo e senza recinti di codice."
    )


def genera_riepilogo(
    client: LLMClient,
    sistema: str,
    utente: str,
    *,
    temperatura: float = 0.2,
    massimo_token: int | None = None,
) -> EsitoRiepilogo:
    """Chiede il riepilogo al modello e lo valida, con al massimo UN tentativo correttivo.

    - risposta valida al primo colpo: `valido=True`, una sola chiamata;
    - non valida: seconda chiamata con `messaggio_correttivo`; se va bene `valido=True`;
    - non valida di nuovo: nessuna terza chiamata, `valido=False` e `Riepilogo.non_disponibile()`.

    Una risposta malformata non solleva mai. `LLMError` (provider irraggiungibile, chiave
    rifiutata…) invece sì: non è un problema di formato e riprovare con un'altra frase non lo
    risolve; è già stato ritentato dal client (M5-T2).
    """
    risposte: list[RispostaLLM] = []
    richiesta = utente
    problemi: list[str] = []
    for tentativo in (1, 2):
        risposta = client.completa(
            sistema,
            richiesta,
            temperatura=temperatura,
            massimo_token=massimo_token,
            risposta_json=True,
        )
        risposte.append(risposta)
        try:
            riepilogo = parsa_riepilogo(risposta.testo)
        except RiepilogoNonValido as errore:
            problemi = errore.problemi
            logger.warning(
                "Riepilogo non valido al tentativo %d (risposta di %d caratteri): %s",
                tentativo,
                len(risposta.testo),
                "; ".join(problemi),
            )
            richiesta = messaggio_correttivo(utente, risposta.testo, problemi)
            continue
        return EsitoRiepilogo(riepilogo=riepilogo, valido=True, risposte=tuple(risposte))

    logger.error(
        "Riepilogo non ottenuto dopo il tentativo correttivo: si restituisce il fallback onesto"
    )
    return EsitoRiepilogo(
        riepilogo=Riepilogo.non_disponibile(),
        valido=False,
        risposte=tuple(risposte),
        problemi=tuple(problemi),
    )
