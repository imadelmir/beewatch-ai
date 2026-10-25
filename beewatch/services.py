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
from typing import Any

import numpy as np
import pandas as pd

from beewatch.ai.assistant import (
    MAX_PRECEDENTI,
    MAX_RACCOLTI,
    AssistenteIspezioni,
    ContestoIspezione,
)
from beewatch.ai.llm import LLMClient, crea_client
from beewatch.ai.prompt import versione_prompt
from beewatch.ai.riepilogo import Riepilogo
from beewatch.config import Config, ottieni
from beewatch.database import Database
from beewatch.exceptions import ConfigError, DatabaseError, ValidationError
from beewatch.logging_config import ottieni_logger
from beewatch.ml.artefatto import percorso_per_la_tabella, riga_tabella_modelli
from beewatch.ml.features import FEATURE, TARGET, costruisci_feature_storiche
from beewatch.ml.predictor import Predittore
from beewatch.models import Previsione
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
    ) -> None:
        self._crea_predittore = crea_predittore
        self._predittore: Predittore | None = None
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

        feature = self._feature(stato.codice, anno)
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
        if mostra:
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
        else:
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
        )

    def storico_previsioni(self, utente_id: int, limite: int = 20) -> list[Riga]:
        """Le ultime previsioni dell'utente, dalla più recente, col modello che le ha prodotte."""
        utente = _id_positivo(utente_id, "utente_id", obbligatorio=True)
        return self._previsioni.ultime_previsioni(utente, limite)

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
    )
