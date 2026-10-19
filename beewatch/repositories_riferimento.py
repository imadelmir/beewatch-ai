"""Repository dei riepiloghi, dei dati di riferimento e della tracciabilità.

Seconda metà di `repositories.py`, separata per restare sotto le 400 righe per
file (DoD di M3-T3). Stesse regole: parametri con `%s`, filtro per `utente_id`
dove il dato è di un utente, un metodo una transazione.

- `DashboardRepository`: le caselle della dashboard (Q1);
- `UtentiRepository`: la cancellazione di un utente e di tutti i suoi dati (Q11);
- `ProduzioneUsdaRepository`: la serie storica USDA (Q7), il pannello di
  addestramento (Q8), i codici di `stati_usa` e il caricamento dell'ETL;
- `PrevisioniRepository`: salvataggio e storico delle stime (Q9);
- `ConversazioniRepository`: lettura di una conversazione (Q10).
"""

from __future__ import annotations

from collections.abc import Iterable

from beewatch.models import Previsione
from beewatch.repositories import (
    _ALVEARE_DELL_UTENTE,
    Riga,
    _non_trovato,
    _Repository,
    _richiedi,
)


class DashboardRepository(_Repository):
    def riepilogo(self, utente_id: int) -> Riga:
        """Q1 · le caselle della dashboard, con tre sottoquery indipendenti (vedi M2-T4)."""
        return self._righe(
            "SELECT "
            "(SELECT COUNT(*) FROM alveari al JOIN apiari ap ON ap.id = al.apiario_id "
            " WHERE ap.utente_id = %s AND al.attivo AND ap.attivo) AS alveari_attivi, "
            "(SELECT COUNT(*) FROM ispezioni i JOIN alveari al ON al.id = i.alveare_id "
            " JOIN apiari ap ON ap.id = al.apiario_id WHERE ap.utente_id = %s "
            " AND i.data_ispezione >= CURDATE() - INTERVAL 30 DAY) AS ispezioni_30_giorni, "
            "(SELECT COALESCE(SUM(r.quantita_kg), 0) FROM raccolti r "
            " JOIN apiari ap ON ap.id = r.apiario_id WHERE ap.utente_id = %s "
            " AND YEAR(r.data_raccolto) = YEAR(CURDATE())) AS produzione_stagione_kg",
            (utente_id, utente_id, utente_id),
        )[0]


class UtentiRepository(_Repository):
    def elimina(self, utente_id: int) -> None:
        """Q11 · cancellazione GDPR (art. 17): le cascate dello schema portano via tutto."""
        with self._db.transazione() as cursore:
            _richiedi(cursore, "SELECT 1 FROM utenti WHERE id = %s", (utente_id,),
                      _non_trovato("Utente", "utente_id"))  # fmt: skip
            cursore.execute("DELETE FROM utenti WHERE id = %s", (utente_id,))


# Q8: solo gli stati con tutti i 15 anni del dataset (regola R10 di M2-T2).
ANNI_SERIE_COMPLETA = 15

# Le colonne che l'ETL carica in `produzione_usda` (sono quelle di `etl.COLONNE_PULITE`).
COLONNE_PRODUZIONE = (
    "codice_stato", "anno", "numero_colonie", "resa_per_colonia_kg", "produzione_totale_kg",
    "scorte_kg", "prezzo_per_kg_usd", "valore_produzione_usd",
)  # fmt: skip
_AGGIORNABILI = COLONNE_PRODUZIONE[2:]  # tutto tranne la chiave naturale
_UPSERT_PRODUZIONE = (
    f"INSERT INTO produzione_usda ({', '.join(COLONNE_PRODUZIONE)}) "
    f"VALUES ({', '.join(['%s'] * len(COLONNE_PRODUZIONE))}) AS nuovo "
    "ON DUPLICATE KEY UPDATE " + ", ".join(f"{c} = nuovo.{c}" for c in _AGGIORNABILI)
)


class ProduzioneUsdaRepository(_Repository):
    def serie_storica_stato(self, codice_stato: str) -> list[Riga]:
        """Q7 · resa e colonie di uno stato, anno per anno."""
        return self._righe(
            "SELECT anno, resa_per_colonia_kg, numero_colonie FROM produzione_usda "
            "WHERE codice_stato = %s ORDER BY anno",
            (codice_stato,),
        )

    def dati_addestramento(self) -> list[Riga]:
        """Q8 · il pannello bilanciato per M4: solo gli stati con la serie completa (R10)."""
        return self._righe(
            "SELECT p.codice_stato, p.anno, p.numero_colonie, p.resa_per_colonia_kg "
            "FROM produzione_usda p WHERE p.codice_stato IN (SELECT codice_stato "
            "FROM produzione_usda GROUP BY codice_stato HAVING COUNT(*) = %s) "
            "ORDER BY p.codice_stato, p.anno",
            (ANNI_SERIE_COMPLETA,),
        )

    def codici_stati(self) -> set[str]:
        """I codici presenti in `stati_usa` (li carica il seed)."""
        return {r["codice"] for r in self._righe("SELECT codice FROM stati_usa")}

    def carica(self, righe: Iterable[Riga]) -> tuple[int, int, int]:
        """Upsert idempotente sulla chiave naturale (stato, anno), in UNA transazione.

        Ogni riga ha le chiavi di `COLONNE_PRODUZIONE`. Restituisce quante righe
        sono state inserite, aggiornate e lasciate invariate. Se una riga fallisce,
        la transazione si annulla e non resta scritto niente.

        Le righe si scrivono una alla volta perché MySQL dice, per ciascuna, cosa è
        successo: 1 = inserita, 2 = aggiornata, 0 = identica a quella che c'era
        (il driver non usa CLIENT_FOUND_ROWS). Con `executemany` il conteggio
        sarebbe uno solo per tutto il blocco.
        """
        conteggi = {0: 0, 1: 0, 2: 0}
        with self._db.transazione() as cursore:
            for riga in righe:
                cursore.execute(_UPSERT_PRODUZIONE, tuple(riga[c] for c in COLONNE_PRODUZIONE))
                conteggi[cursore.rowcount] += 1
        return conteggi[1], conteggi[2], conteggi[0]


class PrevisioniRepository(_Repository):
    def salva_previsione(self, previsione: Previsione) -> Previsione:
        with self._db.transazione() as cursore:
            if previsione.alveare_id is not None:
                _richiedi(cursore, _ALVEARE_DELL_UTENTE,
                          (previsione.alveare_id, previsione.utente_id),
                          _non_trovato("Alveare", "alveare_id"))  # fmt: skip
            cursore.execute(
                "INSERT INTO previsioni (utente_id, alveare_id, versione_modello, "
                "codice_stato_riferimento, anno_riferimento, stima_kg, limite_inferiore_kg, "
                "limite_superiore_kg) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (previsione.utente_id, previsione.alveare_id, previsione.versione_modello,
                 previsione.codice_stato_riferimento, previsione.anno_riferimento,
                 previsione.stima_kg, previsione.limite_inferiore_kg,
                 previsione.limite_superiore_kg),
            )  # fmt: skip
            nuovo_id = cursore.lastrowid
        return Previsione(**{**previsione.__dict__, "id": nuovo_id})

    def ultime_previsioni(self, utente_id: int, limite: int = 20) -> list[Riga]:
        """Q9 · storico delle stime, ognuna con il modello che l'ha prodotta e il suo errore."""
        return self._righe(
            "SELECT pr.id, pr.creato_il, al.codice AS alveare, pr.codice_stato_riferimento, "
            "pr.anno_riferimento, pr.stima_kg, pr.limite_inferiore_kg, pr.limite_superiore_kg, "
            "m.versione, m.algoritmo, m.mae_kg FROM previsioni pr "
            "JOIN modelli m ON m.versione = pr.versione_modello "
            "LEFT JOIN alveari al ON al.id = pr.alveare_id "
            "WHERE pr.utente_id = %s ORDER BY pr.creato_il DESC, pr.id DESC LIMIT %s",
            (utente_id, limite),
        )


class ConversazioniRepository(_Repository):
    def messaggi(self, utente_id: int, conversazione_id: int) -> list[Riga]:
        """Q10 · i messaggi di una conversazione dell'utente, in ordine."""
        return self._righe(
            "SELECT m.ruolo, m.contenuto, m.provider, m.modello, m.versione_prompt, "
            "m.durata_ms, m.creato_il FROM messaggi m "
            "JOIN conversazioni c ON c.id = m.conversazione_id "
            "WHERE c.id = %s AND c.utente_id = %s ORDER BY m.creato_il, m.id",
            (conversazione_id, utente_id),
        )
