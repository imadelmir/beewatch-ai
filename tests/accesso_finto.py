"""Utenti in memoria per i test dell'accesso (M6-T11), con le regole di `UtentiRepository`.

L'hash è vero (bcrypt), ma con pochi giri per non rallentare la suite: `GIRI_TEST`. Le stesse
operazioni sul database vero sono in `test_servizi_accesso.py` (integration).
"""

from __future__ import annotations

import bcrypt

from beewatch.exceptions import ValidationError

GIRI_TEST = 4
EMAIL_DEMO = "demo@beewatch.local"
PASSWORD_DEMO = "beewatch-demo"  # quella del seed, documentata in sql/seed.sql


def hash_veloce(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(GIRI_TEST)).decode()


class UtentiInMemoria:
    def __init__(self, *, con_demo: bool = True) -> None:
        self.righe: dict[int, dict] = {}
        self.errore: Exception | None = None
        if con_demo:
            self.righe[1] = {
                "id": 1,
                "email": EMAIL_DEMO,
                "nome_completo": "Apicoltore Dimostrativo",
                "hash_password": hash_veloce(PASSWORD_DEMO),
                "attivo": True,
            }

    def crea(self, email: str, nome_completo: str, hash_password: str) -> int:
        if self.errore:
            raise self.errore
        if any(r["email"] == email for r in self.righe.values()):
            raise ValidationError("Esiste già un account con questa email.", campo="email")
        nuovo = max(self.righe, default=0) + 1
        self.righe[nuovo] = {
            "id": nuovo,
            "email": email,
            "nome_completo": nome_completo,
            "hash_password": hash_password,
            "attivo": True,
        }
        return nuovo

    def trova(self, utente_id: int) -> dict | None:
        if self.errore:
            raise self.errore
        return dict(self.righe[utente_id]) if utente_id in self.righe else None

    def aggiorna_profilo(self, utente_id: int, nome_completo: str, email: str) -> None:
        if self.errore:
            raise self.errore
        if any(r["email"] == email and r["id"] != utente_id for r in self.righe.values()):
            raise ValidationError("Esiste già un account con questa email.", campo="email")
        self.righe[utente_id].update(nome_completo=nome_completo, email=email)

    def cambia_password(self, utente_id: int, hash_password: str) -> None:
        self.righe[utente_id]["hash_password"] = hash_password

    def elimina(self, utente_id: int) -> None:
        if utente_id not in self.righe:
            raise ValidationError("Utente non trovato.", campo="utente_id")
        del self.righe[utente_id]

    def trova_per_email(self, email: str) -> dict | None:
        if self.errore:
            raise self.errore
        return next((dict(r) for r in self.righe.values() if r["email"] == email), None)


class SessioniInMemoria:
    """Le sessioni ricordate, come `SessioniRepository`: per impronta, con la scadenza."""

    def __init__(self, utenti: UtentiInMemoria | None = None) -> None:
        self.utenti = utenti
        self.righe: dict[str, dict] = {}
        self.errore: Exception | None = None

    def apri(self, utente_id: int, impronta: str, scade_il) -> None:
        if self.errore:
            raise self.errore
        self.righe[impronta] = {"utente_id": utente_id, "scade_il": scade_il}

    def utente_della_sessione(self, impronta: str) -> dict | None:
        if self.errore:
            raise self.errore
        from datetime import datetime

        sessione = self.righe.get(impronta)
        if sessione is None or sessione["scade_il"] <= datetime.now() or self.utenti is None:
            return None
        riga = self.utenti.righe.get(sessione["utente_id"])
        if riga is None or not riga["attivo"]:
            return None
        return {"id": riga["id"], "email": riga["email"], "nome_completo": riga["nome_completo"]}

    def chiudi(self, impronta: str) -> None:
        self.righe.pop(impronta, None)

    def chiudi_tutte(self, utente_id: int) -> None:
        for impronta in [k for k, v in self.righe.items() if v["utente_id"] == utente_id]:
            del self.righe[impronta]
