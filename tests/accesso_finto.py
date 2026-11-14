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

    def trova_per_email(self, email: str) -> dict | None:
        if self.errore:
            raise self.errore
        return next((dict(r) for r in self.righe.values() if r["email"] == email), None)
