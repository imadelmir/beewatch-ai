"""Repository delle sessioni ricordate dal browser («Ricordami»).

File a sé perché `repositories.py` e `repositories_riferimento.py` sono al limite delle 400
righe. Stesse regole: parametri con `%s`, un metodo una transazione. Il token non arriva mai qui:
solo la sua impronta SHA-256 (`beewatch/sicurezza.py`).
"""

from __future__ import annotations

from datetime import datetime

from beewatch.repositories import Riga, _Repository


class SessioniRepository(_Repository):
    def apri(self, utente_id: int, impronta: str, scade_il: datetime) -> None:
        """Una sessione nuova; intanto si tolgono quelle scadute di tutti (pulizia a costo zero)."""
        with self._db.transazione() as cursore:
            cursore.execute("DELETE FROM sessioni WHERE scade_il < NOW()")
            cursore.execute(
                "INSERT INTO sessioni (utente_id, impronta, scade_il) VALUES (%s, %s, %s)",
                (utente_id, impronta, scade_il),
            )

    def utente_della_sessione(self, impronta: str) -> Riga | None:
        """L'utente di una sessione non scaduta, se l'account è ancora attivo."""
        righe = self._righe(
            "SELECT u.id, u.email, u.nome_completo FROM sessioni s "
            "JOIN utenti u ON u.id = s.utente_id "
            "WHERE s.impronta = %s AND s.scade_il > NOW() AND u.attivo",
            (impronta,),
        )
        return righe[0] if righe else None

    def chiudi(self, impronta: str) -> None:
        """«Esci»: la sessione di questo browser non vale più."""
        with self._db.transazione() as cursore:
            cursore.execute("DELETE FROM sessioni WHERE impronta = %s", (impronta,))

    def chiudi_tutte(self, utente_id: int) -> None:
        """Dopo un cambio di password: ogni browser deve rifare l'accesso."""
        with self._db.transazione() as cursore:
            cursore.execute("DELETE FROM sessioni WHERE utente_id = %s", (utente_id,))
