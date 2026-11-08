"""I servizi dell'applicazione: l'unico punto che l'interfaccia chiama (M4-T8).

`app/` non scrive query, non carica il modello e non parla con il provider AI: riceve un
`Servizi` e ne chiama i metodi. Così la logica sta in un posto solo, si prova senza Streamlit
e le pagine restano sottili.

    servizi = crea_servizi()                      # in app/: st.cache_resource
    risultato = servizi.prevedi_produzione(utente_id=1, alveare_id=3,
                                           codice_stato="CA", anno=2013)

**Una classe e non funzioni di modulo** perché il servizio ha dipendenze (database, predittore,
più avanti l'assistente) che i test devono poter sostituire con un finto, e che l'interfaccia
deve poter tenere in cache una volta sola. Le dipendenze si passano al costruttore.

**L'assistente AI** (M5-T5) segue la stessa regola: il client del modello di linguaggio si crea
alla prima richiesta di un riepilogo, non all'avvio, e un'app senza provider configurato parte e
mostra il problema solo quando serve.

**Il predittore si carica alla prima previsione**, non all'avvio: l'applicazione parte anche
senza il file del modello e lo dice solo quando serve. Si carica una volta sola, anche con più
thread (Streamlit li usa), e se il caricamento fallisce non si ricorda il fallimento: il
tentativo dopo riprova.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from beewatch.ai.assistant import (
    MAX_PRECEDENTI,
    MAX_RACCOLTI,
    AssistenteIspezioni,
    ContestoIspezione,
)
from beewatch.ai.llm import FATTORE_TETTO_TEMPO, LLMClient, crea_client
from beewatch.ai.prompt import versione_prompt
from beewatch.ai.riepilogo import Riepilogo, RiepilogoNonValido, valida_riepilogo
from beewatch.config import Config, ottieni
from beewatch.database import Database
from beewatch.exceptions import ConfigError, DatabaseError, ModelError, ValidationError
from beewatch.logging_config import ottieni_logger
from beewatch.ml.artefatto import percorso_per_la_tabella, riga_tabella_modelli
from beewatch.ml.features import (
    COLONIE_ANNO_PRIMA,
    FEATURE,
    RESA_ANNO_PRIMA,
    RESA_MEDIA_3_ANNI_PRIMA,
    TARGET,
    costruisci_feature_storiche,
)
from beewatch.ml.predictor import Predittore
from beewatch.models import (
    Alveare,
    Apiario,
    Ispezione,
    LivelloRischio,
    Previsione,
    StatoAlveare,
)
from beewatch.repositories import (
    AlveariRepository,
    ApiariRepository,
    IspezioniRepository,
    RaccoltiRepository,
    Riga,
)
from beewatch.repositories_riferimento import (
    DashboardRepository,
    ModelliRepository,
    PrevisioniRepository,
    ProduzioneUsdaRepository,
    RiepiloghiRepository,
)

logger = ottieni_logger(__name__)


@dataclass(frozen=True)
class StatoPrevedibile:
    """Uno stato per cui il modello può prevedere, con gli anni che accetta."""

    codice: str
    nome: str
    primo_anno: int  # il secondo anno dei dati: serve almeno un anno di storia
    ultimo_anno: int  # l'anno dopo gli ultimi dati: il solo che sia davvero futuro


@dataclass(frozen=True)
class RisultatoPrevisione:
    """Una previsione, **sempre con il suo intervallo**: mai un numero secco (M2-T3).

    Stima ed estremi sono in chili interi per colonia (nessuna precisione sotto il chilo: i
    dati di partenza non l'hanno). Se `mostra_stima` è falso l'intervallo è più largo della
    stima e l'interfaccia **non deve mostrare il valore centrale**, solo `messaggio`; in quel
    caso la previsione non viene salvata e `id` è None.
    """

    id: int | None
    utente_id: int
    alveare_id: int | None
    codice_stato: str
    nome_stato: str
    anno: int
    stima_kg: int
    limite_inferiore_kg: int
    limite_superiore_kg: int
    livello: float  # la quota di errori osservati dentro l'intervallo
    mostra_stima: bool
    messaggio: str | None
    retrospettiva: bool  # l'anno è già nei dati: una prova a ritroso, non una previsione
    versione_modello: str
    errore_medio_kg: float  # il MAE del modello sul 2010–2012
    feature: dict[str, Any]  # i valori con cui il modello ha previsto
    parametri_manuali: bool = False  # feature scritte dall'utente: una simulazione, non salvata


@dataclass(frozen=True)
class IntervalloParametro:
    """L'intervallo che il modello ha visto in addestramento per un parametro scritto a mano."""

    campo: str
    etichetta: str
    minimo: float
    massimo: float
    unita: str


@dataclass(frozen=True)
class ApiarioScelta:
    """Un apiario nell'elenco di scelta: solo ciò che serve a sceglierlo (niente coordinate)."""

    id: int
    nome: str


@dataclass(frozen=True)
class Panoramica:
    """Le caselle della Home: quattro numeri e gli apiari tra cui scegliere (query Q1, Q3)."""

    apiari: tuple[ApiarioScelta, ...]
    alveari_attivi: int
    ispezioni_30_giorni: int
    produzione_stagione_kg: float
    alveari_da_controllare: int  # attivi, mai ispezionati o non ispezionati da oltre 30 giorni


@dataclass(frozen=True)
class StatoModello:
    """Che modello è caricato e quanto sbaglia: ciò che la Home e la sidebar mostrano."""

    versione: str
    algoritmo: str
    mae_kg: float  # l'errore medio sul 2010–2012
    addestrato_il: str
    righe_addestramento: int


@dataclass(frozen=True)
class AlveareInElenco:
    """Un alveare attivo come lo mostra la pagina Alveari: anagrafica e ultima ispezione (Q2)."""

    id: int
    apiario_id: int
    codice: str
    stato: StatoAlveare
    data_installazione: date | None
    anno_regina: int | None
    note: str | None
    ultima_ispezione: date | None
    peso_kg: float | None  # il peso registrato nell'ultima ispezione


@dataclass(frozen=True)
class IspezioneInElenco:
    """Una riga dello storico delle ispezioni, con il codice dell'alveare a cui si riferisce."""

    id: int
    alveare_id: int
    codice_alveare: str
    data_ispezione: date
    livello_rischio: LivelloRischio
    peso_kg: float | None
    telaini_covata: int | None
    telaini_scorte: int | None
    regina_vista: bool
    sciamatura: bool
    note: str | None


@dataclass(frozen=True)
class RiepilogoGenerato:
    """Il riepilogo AI di un'ispezione, con ciò che serve a mostrarlo e a tracciarlo.

    Se `valido` è falso il modello non ha prodotto nulla di utilizzabile (nemmeno dopo il
    tentativo correttivo): `riepilogo` è allora il «non disponibile» onesto, `messaggio` lo
    spiega e nulla è stato salvato. Se `salvato` è falso con `valido` vero, il riepilogo c'è ma
    il database non l'ha accolto (`id` è None e `messaggio` lo dice): l'interfaccia lo mostra
    comunque.
    """

    id: int | None
    ispezione_id: int
    riepilogo: Riepilogo
    valido: bool
    salvato: bool
    messaggio: str | None
    provider: str
    modello: str
    versione_prompt: str
    durata_ms: int
    token_prompt: int | None
    token_risposta: int | None
    tentativi: int  # chiamate al modello: 2 = è servito il tentativo correttivo
    in_locale: bool  # False = le note sono state inviate a un servizio esterno


INTERO_APIARIO = "Intero apiario"  # i raccolti non attribuiti a un alveare
ALVEARE_ELIMINATO = "Alveare eliminato"
ANNI_CONFRONTO = 6  # quanti anni mostra il confronto previsto/reale


@dataclass(frozen=True)
class DatiDashboard:
    """I numeri e le tabelle della Dashboard di un apiario, già aggregati con pandas.

    `raccolti_per_anno` ha le colonne `anno`, `alveare`, `kg`; `per_alveare` le colonne
    `alveare`, `kg`, con anche gli alveari attivi senza raccolti (zero) e, se ci sono, i chili
    raccolti dall'apiario intero senza indicare l'alveare.
    """

    numero_alveari: int
    produzione_totale_kg: float
    media_per_alveare_kg: float | None  # None senza alveari: una media su zero non esiste
    ultima_ispezione: date | None
    raccolti_per_anno: pd.DataFrame
    per_alveare: pd.DataFrame


@dataclass(frozen=True)
class MetricheModello:
    """Le metriche del modello come le scrive il suo file di metadati (`models/*.json`)."""

    versione: str
    algoritmo: str
    righe_addestramento: int
    mae_kg: float
    rmse_kg: float
    r2: float
    cv_mae_kg: float
    cv_mae_dev_std_kg: float
    migliore_baseline: str
    migliore_baseline_mae_kg: float


@dataclass(frozen=True)
class RiepilogoSalvato:
    """Un riepilogo già salvato di un'ispezione, con il modello e il prompt che l'hanno scritto."""

    id: int
    ispezione_id: int
    riepilogo: Riepilogo
    provider: str
    modello: str
    versione_prompt: str
    durata_ms: int
    token_prompt: int | None
    token_risposta: int | None
    tentativi: int
    creato_il: Any  # datetime del database


@dataclass(frozen=True)
class InfoAssistente:
    """Che cosa userà l'assistente, da dire prima di generare (senza segreti né chiamate)."""

    descrizione: str  # «modello via provider (chiave: …)»
    versione_prompt: str
    attesa_massima_s: int  # tetto di una generazione, tentativo correttivo compreso


def _id_positivo(valore: Any, campo: str, *, obbligatorio: bool) -> int | None:
    if valore is None and not obbligatorio:
        return None
    if isinstance(valore, bool) or not isinstance(valore, int | np.integer) or valore <= 0:
        raise ValidationError(
            f"Il campo «{campo}» deve essere un numero intero positivo.", campo=campo
        )
    return int(valore)


def _numero(valore: float) -> float | None:
    """Un valore adatto al JSON: i mancanti (NaN) diventano None."""
    return (
        None
        if valore is None or (isinstance(valore, float) and math.isnan(valore))
        else float(valore)
    )


def _parametro(valore: Any, intervallo: IntervalloParametro) -> float:
    """Un parametro scritto a mano: un numero finito dentro l'intervallo visto in addestramento."""
    campo, nome = intervallo.campo, intervallo.etichetta
    if isinstance(valore, bool) or not isinstance(valore, int | float | Decimal | np.number):
        raise ValidationError(f"«{nome}» deve essere un numero.", campo=campo)
    numero = float(valore)
    if not math.isfinite(numero):
        raise ValidationError(f"«{nome}» deve essere un numero.", campo=campo)
    if not intervallo.minimo <= numero <= intervallo.massimo:
        raise ValidationError(
            f"«{nome}» = {numero:g} {intervallo.unita} è fuori da ciò che il modello ha visto in "
            f"addestramento (da {intervallo.minimo:g} a {intervallo.massimo:g} "
            f"{intervallo.unita}): oltre quei valori non sa stimare, la previsione non sarebbe "
            "affidabile.",
            campo=campo,
        )
    return numero


def _in_elenco(ispezione: Ispezione, codice_alveare: str) -> IspezioneInElenco:
    peso = ispezione.peso_kg
    return IspezioneInElenco(
        id=ispezione.id, alveare_id=ispezione.alveare_id, codice_alveare=codice_alveare,
        data_ispezione=ispezione.data_ispezione, livello_rischio=ispezione.livello_rischio,
        peso_kg=None if peso is None else float(peso), telaini_covata=ispezione.telaini_covata,
        telaini_scorte=ispezione.telaini_scorte, regina_vista=ispezione.regina_vista,
        sciamatura=ispezione.sciamatura, note=ispezione.note,
    )  # fmt: skip


class Servizi:
    """Database, predittore e le operazioni che l'interfaccia può chiedere."""

    def __init__(
        self,
        database: Database,
        crea_predittore: Callable[[], Predittore] = Predittore,
        *,
        produzione: ProduzioneUsdaRepository | None = None,
        previsioni: PrevisioniRepository | None = None,
        modelli: ModelliRepository | None = None,
        crea_llm: Callable[[], LLMClient] | None = None,
        ispezioni: IspezioniRepository | None = None,
        alveari: AlveariRepository | None = None,
        apiari: ApiariRepository | None = None,
        raccolti: RaccoltiRepository | None = None,
        riepiloghi: RiepiloghiRepository | None = None,
        dashboard: DashboardRepository | None = None,
        descrizione_llm: str = "non configurato",
        timeout_llm: int = 60,
    ) -> None:
        self._crea_predittore = crea_predittore
        self._predittore: Predittore | None = None
        self._intervalli: tuple[IntervalloParametro, ...] | None = None
        self._crea_llm = crea_llm
        self._assistente: AssistenteIspezioni | None = None
        self._blocco = threading.Lock()
        self._produzione = produzione or ProduzioneUsdaRepository(database)
        self._previsioni = previsioni or PrevisioniRepository(database)
        self._modelli = modelli or ModelliRepository(database)
        self._ispezioni = ispezioni or IspezioniRepository(database)
        self._alveari = alveari or AlveariRepository(database)
        self._apiari = apiari or ApiariRepository(database)
        self._raccolti = raccolti or RaccoltiRepository(database)
        self._riepiloghi = riepiloghi or RiepiloghiRepository(database)
        self._dashboard = dashboard or DashboardRepository(database)
        self.descrizione_llm = descrizione_llm  # «modello via provider (chiave: …)», senza segreti
        self._timeout_llm = timeout_llm

    # ----------------------------------------------------------------------- #
    # Dipendenze
    # ----------------------------------------------------------------------- #

    @property
    def predittore(self) -> Predittore:
        """Il predittore, caricato alla prima richiesta e una volta sola.

        Raises:
            ModelError: il modello manca o non è utilizzabile.
        """
        with self._blocco:
            if self._predittore is None:
                self._predittore = self._crea_predittore()
            return self._predittore

    @property
    def assistente(self) -> AssistenteIspezioni:
        """L'assistente AI, creato alla prima richiesta e una volta sola.

        Raises:
            ConfigError: nessun provider configurato per questi servizi.
            LLMError: il provider scelto non si può usare (per esempio OpenRouter senza chiave).
        """
        with self._blocco:
            if self._assistente is None:
                if self._crea_llm is None:
                    raise ConfigError("L'assistente AI non è configurato per questi servizi.")
                self._assistente = AssistenteIspezioni(self._crea_llm())
            return self._assistente

    # ----------------------------------------------------------------------- #
    # Panoramica e stato del sistema (Home)
    # ----------------------------------------------------------------------- #

    def elenca_apiari(self, utente_id: int) -> list[ApiarioScelta]:
        """Gli apiari attivi dell'utente, per nome: tra questi si sceglie l'apiario attivo."""
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        return [ApiarioScelta(a.id, a.nome) for a in self._apiari.elenca(utente)]

    def panoramica(self, utente_id: int) -> Panoramica:
        """I numeri della Home per l'utente: alveari, ispezioni recenti, produzione, da controllare.

        Raises:
            ValidationError: utente non valido.
            DatabaseError: il database non risponde.
        """
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        riga = self._dashboard.riepilogo(utente)
        return Panoramica(
            apiari=tuple(self.elenca_apiari(utente)),
            alveari_attivi=int(riga["alveari_attivi"]),
            ispezioni_30_giorni=int(riga["ispezioni_30_giorni"]),
            produzione_stagione_kg=float(riga["produzione_stagione_kg"]),
            alveari_da_controllare=len(self._alveari.trascurati(utente)),
        )

    def stato_modello(self) -> StatoModello:
        """Il modello di previsione: lo carica (una volta sola) e ne dice versione ed errore.

        Raises:
            ModelError: il modello manca o non è utilizzabile.
        """
        predittore = self.predittore
        metadati = predittore.metadati
        return StatoModello(
            versione=predittore.versione,
            algoritmo=str(metadati["algoritmo"]),
            mae_kg=float(metadati["metriche"]["hold_out_2010_2012"]["mae_kg"]),
            addestrato_il=str(metadati["addestrato_il"]),
            righe_addestramento=int(metadati["addestramento"]["righe"]),
        )

    # ----------------------------------------------------------------------- #
    # Anagrafica: apiari e alveari (M6-T3)
    # ----------------------------------------------------------------------- #
    # La cancellazione è logica (`attivo = FALSE`): ispezioni, raccolti e previsioni di un
    # alveare restano nello storico e i numeri passati non cambiano. I controlli sui valori
    # stanno nei modelli (`Apiario`, `Alveare`), quelli che richiedono il database (nome o codice
    # già usati, apiario di un altro utente) nei repository: qui si traducono gli argomenti.

    def apiari_in_anagrafica(self, utente_id: int) -> list[Apiario]:
        """Gli apiari attivi dell'utente con tutti i campi, per l'anagrafica (anche coordinate)."""
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        return self._apiari.elenca(utente)

    def crea_apiario(
        self,
        utente_id: int,
        *,
        nome: str,
        localita: str | None = None,
        latitudine: Any = None,
        longitudine: Any = None,
        note: str | None = None,
    ) -> Apiario:
        """Registra un apiario e lo restituisce con il suo id.

        Raises:
            ValidationError: un campo non valido, o un altro apiario con lo stesso nome.
            DatabaseError: il database non risponde.
        """
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        apiario = Apiario(
            utente_id=utente, nome=nome, localita=localita, latitudine=latitudine,
            longitudine=longitudine, note=note,
        )  # fmt: skip
        nuovo = self._apiari.crea(apiario)
        logger.info("Apiario %s creato per l'utente %s", nuovo.id, utente)
        return nuovo

    def aggiorna_apiario(
        self,
        utente_id: int,
        apiario_id: int,
        *,
        nome: str,
        localita: str | None = None,
        latitudine: Any = None,
        longitudine: Any = None,
        note: str | None = None,
    ) -> Apiario:
        """Sostituisce i campi di un apiario dell'utente (che resta attivo).

        Raises:
            ValidationError: campo non valido, nome già usato, apiario non dell'utente.
            DatabaseError: il database non risponde.
        """
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        apiario = Apiario(
            utente_id=utente, nome=nome, localita=localita, latitudine=latitudine,
            longitudine=longitudine, note=note,
            id=_id_positivo(apiario_id, "apiario_id", obbligatorio=True),
        )  # fmt: skip
        self._apiari.aggiorna(apiario)
        return apiario

    def elimina_apiario(self, utente_id: int, apiario_id: int) -> None:
        """Toglie un apiario dagli elenchi (cancellazione logica: lo storico resta).

        Raises:
            ValidationError: apiario inesistente o di un altro utente.
            DatabaseError: il database non risponde.
        """
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        apiario = _id_positivo(apiario_id, "apiario_id", obbligatorio=True)
        self._apiari.disattiva(utente, apiario)
        logger.info("Apiario %s disattivato dall'utente %s", apiario, utente)

    def alveari_dell_apiario(self, utente_id: int, apiario_id: int) -> list[AlveareInElenco]:
        """Gli alveari attivi di un apiario, per codice, con data e peso dell'ultima ispezione.

        Un apiario di un altro utente (o disattivato) dà un elenco vuoto: non si rivela che esiste.
        """
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        apiario = _id_positivo(apiario_id, "apiario_id", obbligatorio=True)
        ultime = {r["id"]: r for r in self._alveari.elenco_con_ultima_ispezione(utente)}
        elenco = []
        for alveare in self._alveari.trova_alveari_attivi(utente):
            if alveare.apiario_id != apiario:
                continue
            ultima = ultime.get(alveare.id, {})
            peso = ultima.get("peso_kg")
            elenco.append(
                AlveareInElenco(
                    id=alveare.id,
                    apiario_id=alveare.apiario_id,
                    codice=alveare.codice,
                    stato=alveare.stato,
                    data_installazione=alveare.data_installazione,
                    anno_regina=alveare.anno_regina,
                    note=alveare.note,
                    ultima_ispezione=ultima.get("ultima_ispezione"),
                    peso_kg=None if peso is None else float(peso),
                )  # fmt: skip
            )
        return sorted(elenco, key=lambda a: a.codice)

    def crea_alveare(
        self,
        utente_id: int,
        *,
        apiario_id: int,
        codice: str,
        stato: StatoAlveare | str,
        data_installazione: date | None = None,
        anno_regina: int | None = None,
        note: str | None = None,
    ) -> Alveare:
        """Registra un alveare in un apiario dell'utente e lo restituisce con il suo id.

        Raises:
            ValidationError: campo non valido, codice già usato nell'apiario, apiario non suo.
            DatabaseError: il database non risponde.
        """
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        alveare = Alveare(
            apiario_id=apiario_id, codice=codice, stato=stato,
            data_installazione=data_installazione, anno_regina=anno_regina, note=note,
        )  # fmt: skip
        nuovo = self._alveari.crea(utente, alveare)
        logger.info("Alveare %s creato nell'apiario %s", nuovo.id, nuovo.apiario_id)
        return nuovo

    def aggiorna_alveare(
        self,
        utente_id: int,
        alveare_id: int,
        *,
        apiario_id: int,
        codice: str,
        stato: StatoAlveare | str,
        data_installazione: date | None = None,
        anno_regina: int | None = None,
        note: str | None = None,
    ) -> Alveare:
        """Sostituisce i campi di un alveare dell'utente; può spostarlo in un altro suo apiario.

        Raises:
            ValidationError: campo non valido, codice già usato, alveare o apiario non suoi.
            DatabaseError: il database non risponde.
        """
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        alveare = Alveare(
            apiario_id=apiario_id, codice=codice, stato=stato,
            data_installazione=data_installazione, anno_regina=anno_regina, note=note,
            id=_id_positivo(alveare_id, "alveare_id", obbligatorio=True),
        )  # fmt: skip
        self._alveari.aggiorna(utente, alveare)
        return alveare

    def elimina_alveare(self, utente_id: int, alveare_id: int) -> None:
        """Toglie un alveare dagli elenchi (cancellazione logica: le ispezioni restano).

        Raises:
            ValidationError: alveare inesistente o di un altro utente.
            DatabaseError: il database non risponde.
        """
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        alveare = _id_positivo(alveare_id, "alveare_id", obbligatorio=True)
        self._alveari.disattiva(utente, alveare)
        logger.info("Alveare %s disattivato dall'utente %s", alveare, utente)

    # ----------------------------------------------------------------------- #
    # Ispezioni
    # ----------------------------------------------------------------------- #

    def ispezioni_dell_apiario(
        self,
        utente_id: int,
        apiario_id: int,
        *,
        alveare_id: int | None = None,
        dal: date | None = None,
        al: date | None = None,
    ) -> list[IspezioneInElenco]:
        """Lo storico delle ispezioni degli alveari attivi di un apiario, dalla più recente.

        `alveare_id` lo restringe a un alveare; `dal` e `al` (compresi) a un intervallo di date.
        Un apiario o un alveare di un altro utente danno un elenco vuoto, come per gli alveari.
        Legge un alveare alla volta (`ispezioni_per_alveare`): un apiario ne ha qualche decina
        al massimo, e il repository resta com'è.

        Raises:
            ValidationError: id non validi, date non valide o `dal` dopo `al`.
            DatabaseError: il database non risponde.
        """
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        apiario = _id_positivo(apiario_id, "apiario_id", obbligatorio=True)
        solo = _id_positivo(alveare_id, "alveare_id", obbligatorio=False)
        for valore, campo in ((dal, "dal"), (al, "al")):
            if valore is not None and not isinstance(valore, date):
                raise ValidationError(f"Il campo «{campo}» deve essere una data.", campo=campo)
        if dal is not None and al is not None and dal > al:
            raise ValidationError(
                "La data d'inizio («dal») viene dopo quella di fine («al»).", campo="dal"
            )
        storico = []
        for alveare in self._alveari.trova_alveari_attivi(utente):
            if alveare.apiario_id != apiario or solo not in (None, alveare.id):
                continue
            for ispezione in self._ispezioni.ispezioni_per_alveare(utente, alveare.id):
                giorno = ispezione.data_ispezione
                if (dal is None or giorno >= dal) and (al is None or giorno <= al):
                    storico.append(_in_elenco(ispezione, alveare.codice))
        return sorted(storico, key=lambda i: (i.data_ispezione, i.id), reverse=True)

    def registra_ispezione(
        self,
        utente_id: int,
        *,
        alveare_id: int,
        data_ispezione: date,
        livello_rischio: LivelloRischio | str,
        peso_kg: Any = None,
        telaini_covata: int | None = None,
        telaini_scorte: int | None = None,
        regina_vista: bool = False,
        sciamatura: bool = False,
        note: str | None = None,
    ) -> Ispezione:
        """Registra una visita a un alveare attivo dell'utente e la restituisce con il suo id.

        Il modello rifiuta la data futura, i numeri fuori intervallo e le note oltre i 65.535
        byte; qui si aggiunge che l'alveare deve essere uno di quelli attivi dell'utente.

        Raises:
            ValidationError: campo non valido, alveare inesistente, eliminato o non suo.
            DatabaseError: il database non risponde.
        """
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        ispezione = Ispezione(
            alveare_id=alveare_id, data_ispezione=data_ispezione,
            livello_rischio=livello_rischio, peso_kg=peso_kg, telaini_covata=telaini_covata,
            telaini_scorte=telaini_scorte, regina_vista=regina_vista, sciamatura=sciamatura,
            note=note,
        )  # fmt: skip
        if all(a.id != ispezione.alveare_id for a in self._alveari.trova_alveari_attivi(utente)):
            raise ValidationError(
                "Alveare non trovato fra quelli attivi: forse è stato eliminato.",
                campo="alveare_id",
            )
        nuova = self._ispezioni.crea(utente, ispezione)
        logger.info("Ispezione %s registrata per l'alveare %s", nuova.id, nuova.alveare_id)
        return nuova

    # ----------------------------------------------------------------------- #
    # Previsione della produzione
    # ----------------------------------------------------------------------- #

    def stati_prevedibili(self) -> list[StatoPrevedibile]:
        """Gli stati per cui si può prevedere, in ordine alfabetico di nome."""
        return [
            StatoPrevedibile(
                codice=r["codice"],
                nome=r["nome"],
                primo_anno=int(r["primo_anno"]) + 1,
                ultimo_anno=int(r["ultimo_anno"]) + 1,
            )
            for r in self._produzione.stati_del_pannello()
        ]

    def prevedi_produzione(
        self, utente_id: int, alveare_id: int | None, codice_stato: str, anno: int
    ) -> RisultatoPrevisione:
        """La stima di resa per colonia di uno stato in un anno, con il suo intervallo.

        Passi: valida gli ingressi; costruisce le feature **solo con gli anni precedenti**
        a `anno` (la resa dell'anno stesso, anche se è nei dati, non entra); chiede la stima
        al predittore; arrotonda ai chili (stima al più vicino, estremi verso l'esterno, così
        l'intervallo non si restringe); applica la regola «se l'intervallo è più largo della
        stima, non si mostra la stima»; se la si mostra la salva, con la versione del modello
        e le feature usate. Se il modello non è ancora nella tabella `modelli` lo registra dai
        suoi metadati: la chiave esterna di `previsioni` lo richiede.

        Raises:
            ValidationError: utente, alveare, stato o anno non validi (con il campo sbagliato);
                l'alveare non è dell'utente.
            ModelError: il modello manca o non è utilizzabile.
            DatabaseError: il database non risponde.
        """
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        alveare = _id_positivo(alveare_id, "alveare_id", obbligatorio=False)
        stato = self._stato(codice_stato)
        anno = self._anno(anno, stato)

        return self._stima(utente, alveare, stato, anno, self._feature(stato.codice, anno))

    def intervalli_parametri(self) -> tuple[IntervalloParametro, ...]:
        """Gli intervalli dei parametri a mano: il minimo e il massimo visti in addestramento.

        Vengono dal pannello di addestramento (Q8), letto una volta sola: un modello a foreste
        casuali non sa andare oltre i valori che ha visto, quindi fuori da qui la stima non vale.

        Raises:
            ModelError: il pannello non è nel database (il dataset non è stato caricato).
            DatabaseError: il database non risponde.
        """
        if self._intervalli is None:
            righe = self._produzione.dati_addestramento()
            if not righe:
                raise ModelError(
                    "I dati di addestramento non sono nel database: carica il dataset con "
                    "`python scripts/run_etl.py`."
                )
            rese = [float(r["resa_per_colonia_kg"]) for r in righe]
            colonie = [float(r["numero_colonie"]) for r in righe]
            self._intervalli = (
                IntervalloParametro(RESA_ANNO_PRIMA, "Resa dell'anno prima", min(rese),
                                    max(rese), "kg"),
                IntervalloParametro(RESA_MEDIA_3_ANNI_PRIMA, "Resa media dei 3 anni prima",
                                    min(rese), max(rese), "kg"),
                IntervalloParametro(COLONIE_ANNO_PRIMA, "Colonie dell'anno prima",
                                    min(colonie), max(colonie), "colonie"),
            )  # fmt: skip
        return self._intervalli

    def prevedi_con_parametri(
        self,
        utente_id: int,
        codice_stato: str,
        anno: int,
        *,
        resa_anno_prima: Any,
        resa_media_3_anni_prima: Any,
        colonie_anno_prima: Any,
    ) -> RisultatoPrevisione:
        """Una simulazione: la stima con i valori storici scritti dall'utente, non letti dai dati.

        Lo stato e l'anno seguono le regole di `prevedi_produzione`; ogni parametro deve stare
        nell'intervallo visto in addestramento (`intervalli_parametri`), altrimenti si rifiuta con
        il campo e l'intervallo ammesso. Non si salva: lo storico raccoglie solo le previsioni
        fatte sui dati veri.

        Raises:
            ValidationError: utente, stato, anno o un parametro non validi o incompatibili.
            ModelError: il modello manca o non è utilizzabile.
            DatabaseError: il database non risponde.
        """
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        stato = self._stato(codice_stato)
        anno = self._anno(anno, stato)
        valori = {
            RESA_ANNO_PRIMA: resa_anno_prima,
            RESA_MEDIA_3_ANNI_PRIMA: resa_media_3_anni_prima,
            COLONIE_ANNO_PRIMA: colonie_anno_prima,
        }
        feature: dict[str, Any] = {"codice_stato": stato.codice, "anno": anno}
        for intervallo in self.intervalli_parametri():
            feature[intervallo.campo] = _parametro(valori[intervallo.campo], intervallo)
        return self._stima(utente, None, stato, anno, feature, salva=False)

    def storico_previsioni(
        self, utente_id: int, limite: int = 20, alveare_id: int | None = None
    ) -> list[Riga]:
        """Le ultime previsioni dell'utente, dalla più recente, col modello che le ha prodotte.

        Con `alveare_id` solo quelle collegate a quell'alveare.
        """
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        alveare = _id_positivo(alveare_id, "alveare_id", obbligatorio=False)
        if alveare is None:
            return self._previsioni.ultime_previsioni(utente, limite)
        return self._previsioni.ultime_previsioni(utente, limite, alveare_id=alveare)

    # ----------------------------------------------------------------------- #
    # Dashboard (M6-T7)
    # ----------------------------------------------------------------------- #

    def dashboard_apiario(self, utente_id: int, apiario_id: int) -> DatiDashboard:
        """I KPI e le tabelle della Dashboard per un apiario dell'utente.

        La produzione viene dai raccolti registrati: quelli senza alveare finiscono sotto
        «Intero apiario», così il totale torna e nessun chilo viene attribuito a caso. La media
        per alveare è il totale diviso per gli alveari attivi, e la pagina lo dice.

        Raises:
            ValidationError: id non validi.
            DatabaseError: il database non risponde.
        """
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        apiario = _id_positivo(apiario_id, "apiario_id", obbligatorio=True)
        alveari = self.alveari_dell_apiario(utente, apiario)
        codici = {a.id: a.codice for a in alveari}
        raccolti = pd.DataFrame(
            [
                {
                    "anno": r.data_raccolto.year,
                    "alveare": INTERO_APIARIO if r.alveare_id is None
                    else codici.get(r.alveare_id, ALVEARE_ELIMINATO),
                    "kg": float(r.quantita_kg),
                }
                for r in self._raccolti.per_apiario(utente, apiario)
            ],
            columns=["anno", "alveare", "kg"],
        )  # fmt: skip
        per_anno = raccolti.groupby(["anno", "alveare"], as_index=False)["kg"].sum()
        totali = raccolti.groupby("alveare")["kg"].sum()
        # Ogni alveare attivo compare, anche a zero: la variabilità si vede solo così.
        nomi = list(codici.values()) + [n for n in totali.index if n not in codici.values()]
        per_alveare = pd.DataFrame(
            {"alveare": nomi, "kg": [float(totali.get(n, 0.0)) for n in nomi]}
        )
        totale = float(raccolti["kg"].sum())
        ispezioni = [a.ultima_ispezione for a in alveari if a.ultima_ispezione is not None]
        return DatiDashboard(
            numero_alveari=len(alveari),
            produzione_totale_kg=totale,
            media_per_alveare_kg=totale / len(alveari) if alveari else None,
            ultima_ispezione=max(ispezioni, default=None),
            raccolti_per_anno=per_anno.sort_values(["anno", "alveare"]).reset_index(drop=True),
            per_alveare=per_alveare,
        )

    def metriche_modello(self) -> MetricheModello:
        """Le metriche del modello in uso, lette dai suoi metadati: mai scritte nel codice.

        Raises:
            ModelError: il modello o i suoi metadati mancano o non sono utilizzabili.
        """
        metadati = self.predittore.metadati
        metriche = metadati["metriche"]
        tenuta, cv = metriche["hold_out_2010_2012"], metriche["cross_validation"]
        baseline = min(metriche["baseline_hold_out"].items(), key=lambda b: b[1]["mae_kg"])
        return MetricheModello(
            versione=self.predittore.versione,
            algoritmo=str(metadati["algoritmo"]),
            righe_addestramento=int(metadati["addestramento"]["righe"]),
            mae_kg=float(tenuta["mae_kg"]),
            rmse_kg=float(tenuta["rmse_kg"]),
            r2=float(tenuta["r2"]),
            cv_mae_kg=float(cv["mae_kg"]["media"]),
            cv_mae_dev_std_kg=float(cv["mae_kg"]["dev_std"]),
            migliore_baseline=str(baseline[0]),
            migliore_baseline_mae_kg=float(baseline[1]["mae_kg"]),
        )

    def confronto_previsto_reale(self, codice_stato: str) -> pd.DataFrame:
        """Gli ultimi anni di uno stato: la stima del modello accanto alla resa vera.

        Ogni stima usa solo gli anni precedenti, come `prevedi_produzione`, ma non si salva.
        Colonne: `anno`, `previsto_kg`, `inferiore_kg`, `superiore_kg`, `reale_kg`.

        Raises:
            ValidationError: stato non tra quelli del pannello.
            ModelError: il modello manca o non è utilizzabile.
            DatabaseError: il database non risponde.
        """
        stato = self._stato(codice_stato)
        reali = {
            int(r["anno"]): float(r["resa_per_colonia_kg"])
            for r in self._produzione.serie_storica_stato(stato.codice)
        }
        anni = [a for a in sorted(reali) if a >= stato.primo_anno][-ANNI_CONFRONTO:]
        righe = []
        for anno in anni:
            feature = self._feature(stato.codice, anno)
            stima = self.predittore.stima(
                {**feature, **{k: np.nan for k, v in feature.items() if v is None}}
            )
            righe.append(
                {
                    "anno": anno,
                    "previsto_kg": round(stima.valore_kg, 1),
                    "inferiore_kg": round(stima.inferiore_kg, 1),
                    "superiore_kg": round(stima.superiore_kg, 1),
                    "reale_kg": reali[anno],
                }
            )
        return pd.DataFrame(
            righe, columns=["anno", "previsto_kg", "inferiore_kg", "superiore_kg", "reale_kg"]
        )

    # ----------------------------------------------------------------------- #
    # Riepilogo AI di un'ispezione
    # ----------------------------------------------------------------------- #

    def genera_riepilogo_ispezione(self, utente_id: int, ispezione_id: int) -> RiepilogoGenerato:
        """Il riepilogo strutturato delle note di un'ispezione, generato, validato e salvato.

        Passi: carica l'ispezione (solo se è dell'utente), l'alveare, l'apiario, fino a tre
        ispezioni precedenti e fino a cinque raccolti (non successivi all'ispezione); li passa
        all'assistente; se la risposta è valida la salva in `riepiloghi_ispezione` con provider,
        modello, versione del prompt, durata e token. Ogni chiamata genera un riepilogo nuovo:
        i vecchi si conservano.

        Cosa succede quando qualcosa va storto:
        - il provider non risponde (`LLMError`): si propaga, **nulla viene salvato**;
        - il modello risponde male anche dopo il tentativo correttivo: `valido=False`, nulla
          salvato;
        - il database non salva (`DatabaseError`): il riepilogo c'è e si restituisce con
          `salvato=False` e un messaggio, perché è già costato una chiamata al modello.

        Raises:
            ValidationError: ispezione non trovata (o non dell'utente), oppure senza note.
            ConfigError: nessun provider configurato.
            LLMError: il provider non risponde o rifiuta la richiesta.
            DatabaseError: il database non risponde durante la lettura del contesto.
        """
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        identificativo = _id_positivo(ispezione_id, "ispezione_id", obbligatorio=True)

        contesto = self._contesto_ispezione(utente, identificativo)
        assistente = self.assistente
        esito = assistente.riassumi(contesto)

        ultima = esito.risposte[-1]
        riepilogo = esito.riepilogo
        versione = versione_prompt()
        comuni = {
            "ispezione_id": identificativo,
            "riepilogo": riepilogo,
            "provider": ultima.provider,
            "modello": ultima.modello,
            "versione_prompt": versione,
            "durata_ms": esito.durata_ms,
            "token_prompt": esito.token_prompt,
            "token_risposta": esito.token_risposta,
            "tentativi": len(esito.risposte),
            "in_locale": assistente.in_locale,
        }

        if not esito.valido:
            logger.warning(
                "Riepilogo dell'ispezione %s non ottenuto (%s %s, %d chiamate): non salvato",
                identificativo,
                ultima.provider,
                ultima.modello,
                len(esito.risposte),
            )
            return RiepilogoGenerato(
                id=None,
                valido=False,
                salvato=False,
                messaggio=(
                    "Il modello non ha prodotto un riepilogo leggibile. Riprova: le note "
                    "dell'ispezione non sono state toccate."
                ),
                **comuni,
            )

        try:
            nuovo_id = self._riepiloghi.salva(
                utente,
                identificativo,
                riepilogo=riepilogo.a_dict(),
                stato_salute=riepilogo.stato_salute,
                confidenza=riepilogo.confidenza,
                provider=ultima.provider,
                modello=ultima.modello,
                versione_prompt=versione,
                durata_ms=esito.durata_ms,
                token_prompt=esito.token_prompt,
                token_risposta=esito.token_risposta,
                tentativi=len(esito.risposte),
            )
        except DatabaseError:
            logger.exception("Riepilogo dell'ispezione %s generato ma non salvato", identificativo)
            return RiepilogoGenerato(
                id=None,
                valido=True,
                salvato=False,
                messaggio=(
                    "Il riepilogo è pronto ma non è stato salvato: il database non ha "
                    "risposto. Copialo prima di chiudere la pagina."
                ),
                **comuni,
            )

        logger.info(
            "Riepilogo %s salvato per l'ispezione %s: %s/%s, %s %s, prompt %s, %d ms, token %s→%s",
            nuovo_id,
            identificativo,
            riepilogo.stato_salute,
            riepilogo.confidenza,
            ultima.provider,
            ultima.modello,
            versione,
            esito.durata_ms,
            esito.token_prompt,
            esito.token_risposta,
        )
        return RiepilogoGenerato(id=nuovo_id, valido=True, salvato=True, messaggio=None, **comuni)

    def info_assistente(self) -> InfoAssistente:
        """Modello, versione del prompt e attesa massima: da mostrare prima di generare.

        L'attesa massima è il tetto del client (tre volte `LLM_TIMEOUT`) per due chiamate, perché
        una risposta malformata ne fa fare una seconda, correttiva. Non crea il client.
        """
        return InfoAssistente(
            descrizione=self.descrizione_llm,
            versione_prompt=versione_prompt(),
            attesa_massima_s=2 * FATTORE_TETTO_TEMPO * self._timeout_llm,
        )

    def riepiloghi_ispezione(
        self, utente_id: int, ispezione_id: int, limite: int = 20
    ) -> list[RiepilogoSalvato]:
        """I riepiloghi salvati di un'ispezione dell'utente, dal più recente.

        Il JSON salvato si rilegge con lo stesso schema con cui è stato validato. Una riga che non
        lo rispetta più (uno schema cambiato dopo) si salta e si scrive nel log: non si mostra un
        riepilogo che il codice di oggi non saprebbe leggere.

        Raises:
            ValidationError: id non validi.
            DatabaseError: il database non risponde.
        """
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        identificativo = _id_positivo(ispezione_id, "ispezione_id", obbligatorio=True)
        salvati = []
        for riga in self._riepiloghi.elenco(utente, identificativo, limite):
            try:
                riepilogo = valida_riepilogo(riga["riepilogo_json"])
            except RiepilogoNonValido as errore:
                logger.warning("Riepilogo %s non più leggibile: %s", riga["id"], errore)
                continue
            salvati.append(
                RiepilogoSalvato(
                    id=riga["id"],
                    ispezione_id=riga["ispezione_id"],
                    riepilogo=riepilogo,
                    provider=riga["provider"],
                    modello=riga["modello"],
                    versione_prompt=riga["versione_prompt"],
                    durata_ms=int(riga["durata_ms"]),
                    token_prompt=riga["token_prompt"],
                    token_risposta=riga["token_risposta"],
                    tentativi=int(riga["tentativi"]),
                    creato_il=riga["creato_il"],
                )  # fmt: skip
            )
        return salvati

    def riepilogo_salvato(self, utente_id: int, ispezione_id: int) -> Riga | None:
        """L'ultimo riepilogo salvato di un'ispezione dell'utente, o None se non ce n'è."""
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        identificativo = _id_positivo(ispezione_id, "ispezione_id", obbligatorio=True)
        return self._riepiloghi.ultimo(utente, identificativo)

    def _contesto_ispezione(self, utente_id: int, ispezione_id: int) -> ContestoIspezione:
        ispezione = self._ispezioni.trova(utente_id, ispezione_id)
        if ispezione is None:
            raise ValidationError("Ispezione non trovata.", campo="ispezione_id")
        if not (ispezione.note and ispezione.note.strip()):
            raise ValidationError(
                "L'ispezione non ha note da riassumere: scrivine qualcuna e riprova.", campo="note"
            )
        alveare = self._alveari.trova(utente_id, ispezione.alveare_id)
        apiario = self._apiari.trova(utente_id, alveare.apiario_id) if alveare else None
        if alveare is None or apiario is None:
            raise ValidationError("Ispezione non trovata.", campo="ispezione_id")

        chiave = (ispezione.data_ispezione, ispezione.id)
        precedenti = tuple(
            i
            for i in self._ispezioni.ispezioni_per_alveare(utente_id, alveare.id)
            if (i.data_ispezione, i.id) < chiave
        )[:MAX_PRECEDENTI]
        raccolti = tuple(
            r
            for r in self._raccolti.per_apiario(utente_id, apiario.id)
            if r.data_raccolto <= ispezione.data_ispezione
            and r.alveare_id in (None, alveare.id)  # dell'apiario intero, o di questo alveare
        )[:MAX_RACCOLTI]
        return ContestoIspezione(
            apiario=apiario.nome,
            alveare=alveare,
            ispezione=ispezione,
            precedenti=precedenti,
            raccolti=raccolti,
        )

    # ----------------------------------------------------------------------- #
    # Passi di `prevedi_produzione`
    # ----------------------------------------------------------------------- #

    def _stato(self, codice: Any) -> StatoPrevedibile:
        testo = codice.strip().upper() if isinstance(codice, str) else ""
        disponibili = {s.codice: s for s in self.stati_prevedibili()}
        if testo not in disponibili:
            raise ValidationError(
                f"Lo stato «{codice}» non fa parte dei {len(disponibili)} per cui il modello "
                "può prevedere (servono tutti i quindici anni del dataset).",
                campo="codice_stato",
            )
        return disponibili[testo]

    @staticmethod
    def _anno(anno: Any, stato: StatoPrevedibile) -> int:
        valido = isinstance(anno, int | np.integer) and not isinstance(anno, bool)
        if not valido or not stato.primo_anno <= anno <= stato.ultimo_anno:
            raise ValidationError(
                f"Per {stato.nome} si può prevedere dal {stato.primo_anno} al {stato.ultimo_anno}.",
                campo="anno",
            )
        return int(anno)

    def _feature(self, codice_stato: str, anno: int) -> dict[str, Any]:
        """Le feature di (stato, anno): la storia fino all'anno prima, più la riga da prevedere.

        La riga da prevedere ha resa e colonie vuote: la stessa funzione di M4-T2 che ha
        costruito le feature di addestramento le costruisce qui, e non può leggere la resa
        dell'anno che si sta prevedendo nemmeno se è già nei dati.
        """
        serie = [r for r in self._produzione.serie_storica_stato(codice_stato) if r["anno"] < anno]
        storia = pd.DataFrame(
            {
                "codice_stato": codice_stato,
                "anno": [int(r["anno"]) for r in serie] + [anno],
                "numero_colonie": [float(r["numero_colonie"]) for r in serie] + [np.nan],
                TARGET: [float(r["resa_per_colonia_kg"]) for r in serie] + [np.nan],
            }
        )
        riga = costruisci_feature_storiche(storia).iloc[-1]
        return {
            nome: (str(riga[nome]) if nome == "codice_stato" else
                   int(riga[nome]) if nome == "anno" else _numero(float(riga[nome])))
            for nome in FEATURE
        }  # fmt: skip

    def _stima(
        self,
        utente: int,
        alveare: int | None,
        stato: StatoPrevedibile,
        anno: int,
        feature: dict[str, Any],
        *,
        salva: bool = True,
    ) -> RisultatoPrevisione:
        """Stima, arrotonda, applica la regola dell'intervallo e, se si mostra e `salva`, salva."""
        stima = self.predittore.stima(
            {**feature, **{k: np.nan for k, v in feature.items() if v is None}}
        )
        centro = round(stima.valore_kg)
        inferiore = math.floor(stima.inferiore_kg)
        superiore = math.ceil(stima.superiore_kg)
        larghezza = superiore - inferiore
        mostra = larghezza <= centro
        messaggio = None
        if not mostra:
            messaggio = (
                f"L'intervallo di errore ({larghezza} kg) è più largo della stima ({centro} kg): "
                "con questi dati non si può dare una previsione utile."
            )

        metadati = self.predittore.metadati
        versione = self.predittore.versione
        identificativo = None
        if mostra and salva:
            self._registra_il_modello_se_manca()
            salvata = self._previsioni.salva_previsione(
                Previsione(
                    utente_id=utente,
                    alveare_id=alveare,
                    versione_modello=versione,
                    codice_stato_riferimento=stato.codice,
                    anno_riferimento=anno,
                    stima_kg=centro,
                    limite_inferiore_kg=inferiore,
                    limite_superiore_kg=superiore,
                    feature=feature,
                )
            )
            identificativo = salvata.id
            logger.info(
                "Previsione %s salvata: %s %d, modello %s",
                identificativo,
                stato.codice,
                anno,
                versione,
            )
        elif not mostra:
            logger.info("Stima non mostrabile: %s %d, intervallo %d kg > stima %d kg",
                        stato.codice, anno, larghezza, centro)  # fmt: skip

        return RisultatoPrevisione(
            id=identificativo,
            utente_id=utente,
            alveare_id=alveare,
            codice_stato=stato.codice,
            nome_stato=stato.nome,
            anno=anno,
            stima_kg=centro,
            limite_inferiore_kg=inferiore,
            limite_superiore_kg=superiore,
            livello=stima.livello,
            mostra_stima=mostra,
            messaggio=messaggio,
            retrospettiva=anno < stato.ultimo_anno,
            versione_modello=versione,
            errore_medio_kg=float(metadati["metriche"]["hold_out_2010_2012"]["mae_kg"]),
            feature=feature,
            parametri_manuali=not salva,
        )

    def _registra_il_modello_se_manca(self) -> None:
        versione = self.predittore.versione
        if self._modelli.trova(versione) is None:
            riga = riga_tabella_modelli(
                self.predittore.metadati, percorso_per_la_tabella(self.predittore.percorso)
            )
            self._modelli.registra(riga)
            logger.info("Modello %s registrato in `modelli` dai suoi metadati", versione)


def crea_servizi(configurazione: Config | None = None) -> Servizi:
    """I servizi con le dipendenze vere, dalla configurazione (`.env`).

    Non apre connessioni e non carica il modello: lo fanno alla prima richiesta. In `app/` si
    chiama una volta sola, dentro `st.cache_resource`.
    """
    cfg = configurazione or ottieni()
    return Servizi(
        Database(cfg.database),
        crea_predittore=lambda: Predittore(cfg.percorso_modello),
        crea_llm=lambda: crea_client(cfg.llm),
        descrizione_llm=cfg.llm.descrizione(),
        timeout_llm=cfg.llm.timeout,
    )
