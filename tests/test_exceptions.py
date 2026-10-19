"""Test della gerarchia delle eccezioni (M1-T4).

La gerarchia è una promessa fatta al resto del progetto: chiunque scriva
`except BeeWatchError` deve intercettare *tutti* gli errori previsti. Questi
test verificano che la promessa regga anche dopo future aggiunte.
"""

from __future__ import annotations

import pytest

from beewatch.exceptions import (
    BeeWatchError,
    ConfigError,
    DatabaseError,
    ETLError,
    LLMError,
    ModelError,
    ValidationError,
)

SOTTOCLASSI = (ConfigError, DatabaseError, ValidationError, ETLError, ModelError, LLMError)


@pytest.mark.parametrize("eccezione", SOTTOCLASSI)
def test_ogni_eccezione_discende_dalla_radice(eccezione: type[BeeWatchError]) -> None:
    assert issubclass(eccezione, BeeWatchError)


@pytest.mark.parametrize("eccezione", SOTTOCLASSI)
def test_una_sola_except_le_cattura_tutte(eccezione: type[BeeWatchError]) -> None:
    """È il caso d'uso reale: la UI scrive `except BeeWatchError` e basta."""
    with pytest.raises(BeeWatchError):
        raise eccezione("qualcosa è andato storto")


def test_il_messaggio_arriva_intatto() -> None:
    """Il messaggio finisce sotto gli occhi dell'utente: non va alterato."""
    messaggio = "Impossibile connettersi al database."
    with pytest.raises(DatabaseError) as info:
        raise DatabaseError(messaggio)
    assert str(info.value) == messaggio


def test_validation_error_porta_il_campo() -> None:
    """Il form deve poter evidenziare la casella sbagliata, non tutta la pagina."""
    with pytest.raises(ValidationError) as info:
        raise ValidationError("Il peso non può essere negativo.", campo="peso_kg")
    assert info.value.campo == "peso_kg"


def test_validation_error_senza_campo() -> None:
    """Il campo è facoltativo: non tutti gli errori riguardano una casella."""
    assert ValidationError("dato non valido").campo is None


def test_le_eccezioni_non_catturano_i_bug() -> None:
    """`except BeeWatchError` non deve nascondere un errore di programmazione."""
    with pytest.raises(ZeroDivisionError):
        try:
            _ = 1 / 0
        except BeeWatchError:  # pragma: no cover - non deve mai entrarci
            pytest.fail("un bug è stato scambiato per un errore di dominio")
