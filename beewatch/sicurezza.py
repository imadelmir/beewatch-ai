"""Le password: solo come hash bcrypt, mai in chiaro (M6-T11).

La colonna `utenti.hash_password` è `CHAR(60)`: è la lunghezza di un hash bcrypt, che contiene
anche il sale e il numero di giri (`$2b$12$...`). Il seed usa lo stesso formato per l'utente
dimostrativo.

bcrypt guarda solo i primi 72 byte di una password e la versione 5 rifiuta quelle più lunghe:
il limite si controlla prima, con un messaggio per l'utente, invece di troncare in silenzio.
"""

from __future__ import annotations

import bcrypt

GIRI = 12  # il costo dell'hash: 2^12 iterazioni, come nel seed
BYTE_MASSIMI_PASSWORD = 72  # oltre, bcrypt non distinguerebbe due password diverse
CARATTERI_MINIMI_PASSWORD = 8

# Un hash valido di una password che nessuno conosce: quando l'email non esiste si verifica
# comunque contro questo, così il tempo di risposta non dice se l'account c'è.
HASH_FITTIZIO = bcrypt.hashpw(b"nessun-utente-ha-questa-password", bcrypt.gensalt(GIRI)).decode()


def problema_password(password: str) -> str | None:
    """Perché una password nuova non va bene, o None se va bene."""
    if len(password) < CARATTERI_MINIMI_PASSWORD:
        return f"La password deve avere almeno {CARATTERI_MINIMI_PASSWORD} caratteri."
    if len(password.encode("utf-8")) > BYTE_MASSIMI_PASSWORD:
        return "La password è troppo lunga: al massimo 72 byte (circa 70 caratteri semplici)."
    if password.strip() != password:
        return "La password non può iniziare o finire con uno spazio."
    return None


def calcola_hash(password: str) -> str:
    """L'hash bcrypt di una password già controllata da `problema_password`."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(GIRI)).decode("ascii")


def verifica(password: str, hash_salvato: str | None) -> bool:
    """True se la password corrisponde all'hash. Non solleva: un hash rovinato è un no."""
    candidata = password.encode("utf-8")
    if len(candidata) > BYTE_MASSIMI_PASSWORD:
        bcrypt.checkpw(b"x", HASH_FITTIZIO.encode())  # stesso tempo di un tentativo vero
        return False
    try:
        return bcrypt.checkpw(candidata, (hash_salvato or HASH_FITTIZIO).encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return False
