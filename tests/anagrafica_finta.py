"""Apiari, alveari e ispezioni in memoria, con le regole dei repository veri (M6-T3, M6-T4).

Servono ai test dei servizi e della pagina Alveari, senza database. Riproducono ciò che i
repository controllano con le query (`beewatch/repositories.py`): appartenenza all'utente, nome
dell'apiario unico per utente e codice dell'alveare unico nell'apiario (contando anche quelli
disattivati, come fa la query), cancellazione logica, messaggi d'errore. Un test d'integrazione
(`test_servizi_anagrafica.py`) fa le stesse operazioni sui repository veri: se le regole qui
divergessero da quelle, se ne accorgerebbe.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from beewatch.exceptions import DatabaseError, ValidationError
from beewatch.models import Alveare, Apiario, Ispezione, LivelloRischio, StatoAlveare


class ApiariInMemoria:
    def __init__(self, *apiari: Apiario, errore: Exception | None = None) -> None:
        self.righe: dict[int, Apiario] = {a.id: a for a in apiari}
        self.errore = errore

    def _prova(self) -> None:
        if self.errore:
            raise self.errore

    def _nome_libero(self, apiario: Apiario) -> None:
        for altro in self.righe.values():
            if (
                altro.utente_id == apiario.utente_id
                and altro.nome == apiario.nome
                and altro.id != (apiario.id or 0)
            ):
                raise ValidationError("Hai già un apiario con questo nome.", campo="nome")

    def dell_utente(self, utente_id: int, apiario_id: int) -> Apiario | None:
        apiario = self.righe.get(apiario_id)
        return apiario if apiario and apiario.utente_id == utente_id else None

    def crea(self, apiario: Apiario) -> Apiario:
        self._prova()
        self._nome_libero(apiario)
        nuovo = replace(apiario, id=max(self.righe, default=0) + 1)
        self.righe[nuovo.id] = nuovo
        return nuovo

    def trova(self, utente_id: int, apiario_id: int) -> Apiario | None:
        self._prova()
        return self.dell_utente(utente_id, apiario_id)

    def elenca(self, utente_id: int, *, anche_disattivi: bool = False) -> list[Apiario]:
        self._prova()
        scelti = [
            a for a in self.righe.values()
            if a.utente_id == utente_id and (anche_disattivi or a.attivo)
        ]  # fmt: skip
        return sorted(scelti, key=lambda a: a.nome)

    def aggiorna(self, apiario: Apiario) -> None:
        self._prova()
        if apiario.id is None or not self.dell_utente(apiario.utente_id, apiario.id):
            raise ValidationError("Apiario non trovato.", campo="id")
        self._nome_libero(apiario)
        self.righe[apiario.id] = apiario

    def disattiva(self, utente_id: int, apiario_id: int) -> None:
        self._prova()
        apiario = self.dell_utente(utente_id, apiario_id)
        if apiario is None:
            raise ValidationError("Apiario non trovato.", campo="id")
        self.righe[apiario_id] = replace(apiario, attivo=False)


class AlveariInMemoria:
    """Alveari legati agli apiari di `apiari`; `ispezioni` = {alveare_id: (data, peso)}."""

    def __init__(
        self,
        apiari: ApiariInMemoria,
        *alveari: Alveare,
        ispezioni: dict[int, tuple[date, Decimal | None]] | None = None,
        errore: Exception | None = None,
    ) -> None:
        self.apiari = apiari
        self.righe: dict[int, Alveare] = {a.id: a for a in alveari}
        self.ispezioni = ispezioni or {}
        self.errore = errore

    def _prova(self) -> None:
        if self.errore:
            raise self.errore

    def _dell_utente(self, utente_id: int, alveare_id: int) -> Alveare | None:
        alveare = self.righe.get(alveare_id)
        if alveare and self.apiari.dell_utente(utente_id, alveare.apiario_id):
            return alveare
        return None

    def _controlla(self, utente_id: int, alveare: Alveare) -> None:
        if not self.apiari.dell_utente(utente_id, alveare.apiario_id):
            raise ValidationError("Apiario non trovato.", campo="apiario_id")
        for altro in self.righe.values():
            if (
                altro.apiario_id == alveare.apiario_id
                and altro.codice == alveare.codice
                and altro.id != (alveare.id or 0)
            ):
                raise ValidationError(
                    "Nell'apiario c'è già un alveare con questo codice.", campo="codice"
                )

    def crea(self, utente_id: int, alveare: Alveare) -> Alveare:
        self._prova()
        self._controlla(utente_id, alveare)
        nuovo = replace(alveare, id=max(self.righe, default=0) + 1)
        self.righe[nuovo.id] = nuovo
        return nuovo

    def trova(self, utente_id: int, alveare_id: int) -> Alveare | None:
        self._prova()
        return self._dell_utente(utente_id, alveare_id)

    def trova_alveari_attivi(self, utente_id: int) -> list[Alveare]:
        self._prova()
        attivi = [
            a for a in self.righe.values()
            if a.attivo and (ap := self.apiari.dell_utente(utente_id, a.apiario_id)) and ap.attivo
        ]  # fmt: skip
        return sorted(attivi, key=lambda a: (self.apiari.righe[a.apiario_id].nome, a.codice))

    def elenco_con_ultima_ispezione(self, utente_id: int) -> list[dict]:
        self._prova()
        return [
            {
                "id": a.id,
                "codice": a.codice,
                "ultima_ispezione": self.ispezioni.get(a.id, (None, None))[0],
                "peso_kg": self.ispezioni.get(a.id, (None, None))[1],
            }
            for a in self.righe.values()
            if self.apiari.dell_utente(utente_id, a.apiario_id)
        ]

    def trascurati(self, utente_id: int, giorni: int = 30) -> list[dict]:
        self._prova()
        return [
            {"id": a.id, "codice": a.codice}
            for a in self.trova_alveari_attivi(utente_id)
            if a.id not in self.ispezioni
        ]

    def aggiorna(self, utente_id: int, alveare: Alveare) -> None:
        self._prova()
        if alveare.id is None or not self._dell_utente(utente_id, alveare.id):
            raise ValidationError("Alveare non trovato.", campo="id")
        self._controlla(utente_id, alveare)
        self.righe[alveare.id] = alveare

    def disattiva(self, utente_id: int, alveare_id: int) -> None:
        self._prova()
        alveare = self._dell_utente(utente_id, alveare_id)
        if alveare is None:
            raise ValidationError("Alveare non trovato.", campo="id")
        self.righe[alveare_id] = replace(alveare, attivo=False)


class IspezioniInMemoria:
    """Le ispezioni degli alveari di `alveari`, come `IspezioniRepository`.

    Come il repository vero, `crea` controlla solo che l'alveare sia dell'utente (non che sia
    attivo: quello lo aggiunge il servizio) e l'elenco va dalla più recente.
    """

    def __init__(
        self, alveari: AlveariInMemoria, *ispezioni: Ispezione, errore: Exception | None = None
    ) -> None:
        self.alveari = alveari
        self.righe: dict[int, Ispezione] = {i.id: i for i in ispezioni}
        self.errore = errore

    def _prova(self) -> None:
        if self.errore:
            raise self.errore

    def crea(self, utente_id: int, ispezione: Ispezione) -> Ispezione:
        self._prova()
        if not self.alveari._dell_utente(utente_id, ispezione.alveare_id):
            raise ValidationError("Alveare non trovato.", campo="alveare_id")
        nuova = replace(ispezione, id=max(self.righe, default=0) + 1)
        self.righe[nuova.id] = nuova
        return nuova

    def trova(self, utente_id: int, ispezione_id: int) -> Ispezione | None:
        self._prova()
        ispezione = self.righe.get(ispezione_id)
        if ispezione and self.alveari._dell_utente(utente_id, ispezione.alveare_id):
            return ispezione
        return None

    def ispezioni_per_alveare(self, utente_id: int, alveare_id: int) -> list[Ispezione]:
        self._prova()
        if not self.alveari._dell_utente(utente_id, alveare_id):
            return []
        scelte = [i for i in self.righe.values() if i.alveare_id == alveare_id]
        return sorted(scelte, key=lambda i: (i.data_ispezione, i.id), reverse=True)


NOTA_LUNGA = (
    "Covata compatta e opercolata su sei telaini, uova fresche: la regina c'è e depone. "
    "Scorte di miele e polline abbondanti ai lati; api calme, nessun segno di saccheggio. "
) * 15 + "Varroa: caduta naturale bassa sul vassoio. Perché no? Più avanti si vedrà — è così."


def ispezioni_di_prova(alveari: AlveariInMemoria, errore: Exception | None = None):
    """Quattro ispezioni di Collina (A1 e A2), una dell'alveare eliminato A9, una altrui."""
    return IspezioniInMemoria(
        alveari,
        Ispezione(alveare_id=1, data_ispezione=date(2026, 9, 12), id=101,
                  livello_rischio=LivelloRischio.NESSUNO, peso_kg=Decimal("41.20"),
                  telaini_covata=6, telaini_scorte=4, regina_vista=True, note=NOTA_LUNGA),
        Ispezione(alveare_id=2, data_ispezione=date(2026, 10, 5), id=102,
                  livello_rischio=LivelloRischio.ALTO, telaini_covata=2,
                  note="Varroa *alta* sul vassoio: trattamento da programmare."),
        Ispezione(alveare_id=1, data_ispezione=date(2026, 10, 30), id=103,
                  livello_rischio=LivelloRischio.BASSO, peso_kg=Decimal("38.50"),
                  sciamatura=True),
        Ispezione(alveare_id=2, data_ispezione=date(2026, 8, 20), id=104,
                  livello_rischio=LivelloRischio.MEDIO),
        Ispezione(alveare_id=9, data_ispezione=date(2026, 10, 1), id=105,
                  livello_rischio=LivelloRischio.ALTO),
        Ispezione(alveare_id=30, data_ispezione=date(2026, 10, 2), id=106,
                  livello_rischio=LivelloRischio.NESSUNO),
        errore=errore,
    )  # fmt: skip


def anagrafica_di_prova(
    errore: Exception | None = None,
) -> tuple[ApiariInMemoria, AlveariInMemoria]:
    """Due apiari dell'utente 1 (Collina con tre alveari, Valle vuoto) e uno dell'utente 2."""
    apiari = ApiariInMemoria(
        Apiario(utente_id=1, nome="Collina", localita="Colli di Bergamo", id=10,
                latitudine=Decimal("45.71"), longitudine=Decimal("9.67")),
        Apiario(utente_id=1, nome="Valle", id=11),
        Apiario(utente_id=2, nome="Altrui", id=20),
        errore=errore,
    )  # fmt: skip
    alveari = AlveariInMemoria(
        apiari,
        Alveare(apiario_id=10, codice="A2", stato=StatoAlveare.DEBOLE, id=2, anno_regina=2024),
        Alveare(apiario_id=10, codice="A1", stato=StatoAlveare.IN_SALUTE, id=1,
                data_installazione=date(2025, 4, 1), note="Regina marcata blu"),
        Alveare(apiario_id=10, codice="A9", stato=StatoAlveare.MORTO, id=9, attivo=False),
        Alveare(apiario_id=20, codice="X1", stato=StatoAlveare.IN_SALUTE, id=30),
        ispezioni={1: (date(2026, 10, 30), Decimal("38.50"))},
        errore=errore,
    )  # fmt: skip
    return apiari, alveari


DATABASE_SPENTO = DatabaseError("Il server MySQL non risponde.")
