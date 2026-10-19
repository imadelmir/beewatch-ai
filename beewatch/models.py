"""Modelli del dominio: apiari, alveari, ispezioni, raccolti, previsioni.

Ogni entità è una dataclass congelata che **si rifiuta di esistere con valori
non validi**: il controllo avviene alla costruzione e solleva `ValidationError`
con il nome del campo sbagliato, così un form può evidenziare la casella giusta.
Un oggetto che esiste è quindi sempre coerente, e chi lo riceve (repository,
servizi, interfaccia) non deve ricontrollarlo.

Le regole sono quelle dello schema (`sql/schema.sql`: CHECK, NOT NULL, lunghezze
delle colonne) più quelle che un CHECK non può esprimere perché dipendono dalla
data di oggi: un'ispezione non può essere nel futuro, l'anno della regina
nemmeno. Una regola che vale qui vale anche nel database: il database resta
l'ultima difesa, il modello è la prima e quella che sa spiegare l'errore.

I valori fissi (stato dell'alveare, livello di rischio, tipo di miele) sono
`Enum` il cui valore è il `codice` della rispettiva tabella di riferimento: nel
codice non compaiono stringhe come "in_salute". Il passaggio dal codice all'`id`
numerico del database è compito dei repository.

Il modulo non importa nulla del database né di Streamlit.

Esempio:

    ispezione = Ispezione(
        alveare_id=3,
        data_ispezione=date(2026, 5, 2),
        livello_rischio=LivelloRischio.BASSO,
        peso_kg="38.5",                 # diventa Decimal("38.5")
        telaini_covata=6,
    )
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, TypeVar

from beewatch.exceptions import ValidationError

# Limiti che vengono dallo schema: cambiano solo se cambia `sql/schema.sql`.
TELAINI_MASSIMI = 30
CHILI_MASSIMI = Decimal("9999.99")  # DECIMAL(6, 2)
ANNO_REGINA_MINIMO = 2000
ANNO_RIFERIMENTO = (1990, 2100)
BYTE_MASSIMI_TESTO = 65_535  # colonne TEXT: le note non vanno mai troncate, quindi si rifiutano

_CODICE_STATO_USA = re.compile(r"[A-Z]{2}")


# --------------------------------------------------------------------------- #
# Valori fissi
# --------------------------------------------------------------------------- #
# Il valore di ogni membro è il `codice` della riga corrispondente in
# `sql/seed.sql`. Un test di integrazione verifica che coincidano.


class StatoAlveare(StrEnum):
    IN_SALUTE = "in_salute"
    IN_OSSERVAZIONE = "in_osservazione"
    DEBOLE = "debole"
    SCIAMATO = "sciamato"
    MORTO = "morto"


class LivelloRischio(StrEnum):
    NESSUNO = "nessuno"
    BASSO = "basso"
    MEDIO = "medio"
    ALTO = "alto"


class TipoMiele(StrEnum):
    ACACIA = "acacia"
    MILLEFIORI = "millefiori"
    CASTAGNO = "castagno"
    TIGLIO = "tiglio"
    MELATA = "melata"
    GIRASOLE = "girasole"
    EUCALIPTO = "eucalipto"
    NON_DEFINITO = "non_definito"


# --------------------------------------------------------------------------- #
# Controlli dei singoli campi
# --------------------------------------------------------------------------- #
# Ognuno restituisce il valore nella sua forma canonica (testo senza spazi
# attorno, Decimal, Enum) oppure solleva ValidationError con il nome del campo.

_E = TypeVar("_E", bound=StrEnum)


def _id(valore: Any, campo: str, *, obbligatorio: bool = True) -> int | None:
    if valore is None and not obbligatorio:
        return None
    if isinstance(valore, bool) or not isinstance(valore, int) or valore < 1:
        raise ValidationError(f"Il riferimento «{campo}» non è valido.", campo=campo)
    return valore


def _testo(
    valore: Any, campo: str, *, massimo: int | None = None, obbligatorio: bool
) -> str | None:
    """Testo senza spazi attorno. Vuoto vale come assente."""
    if valore is not None and not isinstance(valore, str):
        raise ValidationError(f"Il campo «{campo}» deve essere un testo.", campo=campo)
    testo = (valore or "").strip()
    if not testo:
        if obbligatorio:
            raise ValidationError(f"Il campo «{campo}» è obbligatorio.", campo=campo)
        return None
    if massimo is not None and len(testo) > massimo:
        raise ValidationError(
            f"Il campo «{campo}» può contenere al massimo {massimo} caratteri.", campo=campo
        )
    if len(testo.encode("utf-8")) > BYTE_MASSIMI_TESTO:
        raise ValidationError(f"Il testo di «{campo}» è troppo lungo.", campo=campo)
    return testo


def _decimale(
    valore: Any,
    campo: str,
    *,
    minimo: Decimal | None = None,
    massimo: Decimal | None = None,
    minimo_escluso: bool = False,
    decimali: int = 2,
    obbligatorio: bool = True,
) -> Decimal | None:
    """Un numero come `Decimal`. Un float passa dalla sua forma testuale: 0.1 resta 0.1.

    Accetta anche la virgola come separatore ("38,5"). Rifiuta più cifre decimali
    di quante ne conserva la colonna: MySQL le arrotonderebbe senza dirlo.
    """
    if valore is None:
        if obbligatorio:
            raise ValidationError(f"Il campo «{campo}» è obbligatorio.", campo=campo)
        return None
    if isinstance(valore, bool):
        raise ValidationError(f"Il campo «{campo}» deve essere un numero.", campo=campo)
    testo = valore.strip().replace(",", ".") if isinstance(valore, str) else str(valore)
    try:
        numero = Decimal(testo)
    except InvalidOperation:
        raise ValidationError(f"Il campo «{campo}» deve essere un numero.", campo=campo) from None
    if not numero.is_finite():
        raise ValidationError(f"Il campo «{campo}» deve essere un numero.", campo=campo)
    if numero.as_tuple().exponent < -decimali:
        raise ValidationError(
            f"Il campo «{campo}» ammette al massimo {decimali} cifre decimali.", campo=campo
        )
    if minimo is not None and (numero <= minimo if minimo_escluso else numero < minimo):
        confronto = "maggiore di" if minimo_escluso else "almeno"
        raise ValidationError(f"Il campo «{campo}» deve essere {confronto} {minimo}.", campo=campo)
    if massimo is not None and numero > massimo:
        raise ValidationError(f"Il campo «{campo}» non può superare {massimo}.", campo=campo)
    return numero


def _intero(
    valore: Any, campo: str, *, minimo: int, massimo: int, obbligatorio: bool = True
) -> int | None:
    if valore is None and not obbligatorio:
        return None
    if isinstance(valore, bool) or not isinstance(valore, int):
        raise ValidationError(f"Il campo «{campo}» deve essere un numero intero.", campo=campo)
    if not minimo <= valore <= massimo:
        raise ValidationError(
            f"Il campo «{campo}» deve essere fra {minimo} e {massimo}.", campo=campo
        )
    return valore


def _data(
    valore: Any, campo: str, *, non_futura: bool = False, obbligatorio: bool = True
) -> date | None:
    if valore is None and not obbligatorio:
        return None
    # datetime è una sottoclasse di date: qui si vuole il giorno, non l'istante.
    if type(valore) is not date:
        raise ValidationError(f"Il campo «{campo}» deve essere una data.", campo=campo)
    if non_futura and valore > date.today():
        raise ValidationError(f"La data di «{campo}» non può essere nel futuro.", campo=campo)
    return valore


def _booleano(valore: Any, campo: str) -> bool:
    if not isinstance(valore, bool):
        raise ValidationError(f"Il campo «{campo}» deve essere sì o no.", campo=campo)
    return valore


def _valore_fisso(tipo: type[_E], valore: Any, campo: str) -> _E:
    """Un membro dell'Enum, dato il membro stesso o il suo codice."""
    try:
        return tipo(valore)
    except ValueError:
        ammessi = ", ".join(m.value for m in tipo)
        raise ValidationError(
            f"Valore non ammesso per «{campo}». Ammessi: {ammessi}.", campo=campo
        ) from None


def _imposta(oggetto: object, **valori: Any) -> None:
    """Scrive i valori normalizzati in una dataclass congelata (solo da __post_init__)."""
    for nome, valore in valori.items():
        object.__setattr__(oggetto, nome, valore)


# --------------------------------------------------------------------------- #
# Entità
# --------------------------------------------------------------------------- #
# `id` è None per un oggetto non ancora salvato: lo assegna il database.


@dataclass(frozen=True)
class Apiario:
    """Un luogo fisico dove stanno gli alveari. Appartiene a un utente."""

    utente_id: int
    nome: str
    localita: str | None = None
    # repr=False: coordinate e note non devono finire in un log per caso.
    latitudine: Decimal | None = field(default=None, repr=False)
    longitudine: Decimal | None = field(default=None, repr=False)
    note: str | None = field(default=None, repr=False)
    attivo: bool = True
    id: int | None = None

    def __post_init__(self) -> None:
        _imposta(
            self,
            utente_id=_id(self.utente_id, "utente_id"),
            nome=_testo(self.nome, "nome", massimo=120, obbligatorio=True),
            localita=_testo(self.localita, "localita", massimo=160, obbligatorio=False),
            latitudine=_decimale(
                self.latitudine, "latitudine", minimo=Decimal(-90), massimo=Decimal(90),
                decimali=6, obbligatorio=False,
            ),
            longitudine=_decimale(
                self.longitudine, "longitudine", minimo=Decimal(-180), massimo=Decimal(180),
                decimali=6, obbligatorio=False,
            ),
            note=_testo(self.note, "note", obbligatorio=False),
            attivo=_booleano(self.attivo, "attivo"),
            id=_id(self.id, "id", obbligatorio=False),
        )  # fmt: skip


@dataclass(frozen=True)
class Alveare:
    """Una singola arnia. Il codice è unico dentro l'apiario, non nel database."""

    apiario_id: int
    codice: str
    stato: StatoAlveare
    data_installazione: date | None = None
    anno_regina: int | None = None
    note: str | None = field(default=None, repr=False)
    attivo: bool = True
    id: int | None = None

    def __post_init__(self) -> None:
        _imposta(
            self,
            apiario_id=_id(self.apiario_id, "apiario_id"),
            codice=_testo(self.codice, "codice", massimo=20, obbligatorio=True),
            stato=_valore_fisso(StatoAlveare, self.stato, "stato"),
            data_installazione=_data(
                self.data_installazione, "data_installazione", obbligatorio=False
            ),
            # Non nel futuro: è l'anno di nascita di una regina che esiste già.
            anno_regina=_intero(
                self.anno_regina, "anno_regina", minimo=ANNO_REGINA_MINIMO,
                massimo=date.today().year, obbligatorio=False,
            ),
            note=_testo(self.note, "note", obbligatorio=False),
            attivo=_booleano(self.attivo, "attivo"),
            id=_id(self.id, "id", obbligatorio=False),
        )  # fmt: skip


@dataclass(frozen=True)
class Ispezione:
    """Una visita all'alveare: cosa si è visto e quando."""

    alveare_id: int
    data_ispezione: date
    livello_rischio: LivelloRischio
    peso_kg: Decimal | None = None
    telaini_covata: int | None = None
    telaini_scorte: int | None = None
    regina_vista: bool = False
    sciamatura: bool = False
    note: str | None = field(default=None, repr=False)
    id: int | None = None

    def __post_init__(self) -> None:
        _imposta(
            self,
            alveare_id=_id(self.alveare_id, "alveare_id"),
            data_ispezione=_data(self.data_ispezione, "data_ispezione", non_futura=True),
            livello_rischio=_valore_fisso(LivelloRischio, self.livello_rischio, "livello_rischio"),
            peso_kg=_decimale(
                self.peso_kg, "peso_kg", minimo=Decimal(0), massimo=CHILI_MASSIMI,
                obbligatorio=False,
            ),
            telaini_covata=_intero(
                self.telaini_covata, "telaini_covata", minimo=0, massimo=TELAINI_MASSIMI,
                obbligatorio=False,
            ),
            telaini_scorte=_intero(
                self.telaini_scorte, "telaini_scorte", minimo=0, massimo=TELAINI_MASSIMI,
                obbligatorio=False,
            ),
            regina_vista=_booleano(self.regina_vista, "regina_vista"),
            sciamatura=_booleano(self.sciamatura, "sciamatura"),
            note=_testo(self.note, "note", obbligatorio=False),
            id=_id(self.id, "id", obbligatorio=False),
        )  # fmt: skip


@dataclass(frozen=True)
class Raccolto:
    """Una smielatura. Appartiene all'apiario; l'alveare è un dettaglio facoltativo.

    Che l'alveare, se indicato, appartenga proprio a quell'apiario lo verifica il
    repository al salvataggio: serve il database per saperlo.
    """

    apiario_id: int
    tipo_miele: TipoMiele
    data_raccolto: date
    quantita_kg: Decimal
    alveare_id: int | None = None
    note: str | None = field(default=None, repr=False)
    id: int | None = None

    def __post_init__(self) -> None:
        _imposta(
            self,
            apiario_id=_id(self.apiario_id, "apiario_id"),
            tipo_miele=_valore_fisso(TipoMiele, self.tipo_miele, "tipo_miele"),
            data_raccolto=_data(self.data_raccolto, "data_raccolto"),
            quantita_kg=_decimale(
                self.quantita_kg, "quantita_kg", minimo=Decimal(0), minimo_escluso=True,
                massimo=CHILI_MASSIMI,
            ),
            alveare_id=_id(self.alveare_id, "alveare_id", obbligatorio=False),
            note=_testo(self.note, "note", obbligatorio=False),
            id=_id(self.id, "id", obbligatorio=False),
        )  # fmt: skip


@dataclass(frozen=True)
class Previsione:
    """Una stima di resa, sempre con il suo intervallo (M2-T3: mai un numero secco)."""

    utente_id: int
    versione_modello: str
    codice_stato_riferimento: str
    anno_riferimento: int
    stima_kg: Decimal
    limite_inferiore_kg: Decimal
    limite_superiore_kg: Decimal
    alveare_id: int | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        codice = _testo(
            self.codice_stato_riferimento, "codice_stato_riferimento", obbligatorio=True
        )
        if not _CODICE_STATO_USA.fullmatch(codice):
            raise ValidationError(
                "Il codice dello stato deve essere di due lettere maiuscole (es. CA).",
                campo="codice_stato_riferimento",
            )
        limiti = {"minimo": -CHILI_MASSIMI, "massimo": CHILI_MASSIMI}
        stima = _decimale(self.stima_kg, "stima_kg", **limiti)
        inferiore = _decimale(self.limite_inferiore_kg, "limite_inferiore_kg", **limiti)
        superiore = _decimale(self.limite_superiore_kg, "limite_superiore_kg", **limiti)
        if not inferiore <= stima <= superiore:
            raise ValidationError(
                "La stima deve stare dentro il suo intervallo (inferiore ≤ stima ≤ superiore).",
                campo="stima_kg",
            )
        _imposta(
            self,
            utente_id=_id(self.utente_id, "utente_id"),
            versione_modello=_testo(
                self.versione_modello, "versione_modello", massimo=40, obbligatorio=True
            ),
            codice_stato_riferimento=codice,
            anno_riferimento=_intero(
                self.anno_riferimento, "anno_riferimento", minimo=ANNO_RIFERIMENTO[0],
                massimo=ANNO_RIFERIMENTO[1],
            ),
            stima_kg=stima,
            limite_inferiore_kg=inferiore,
            limite_superiore_kg=superiore,
            alveare_id=_id(self.alveare_id, "alveare_id", obbligatorio=False),
            id=_id(self.id, "id", obbligatorio=False),
        )  # fmt: skip
