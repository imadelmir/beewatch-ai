"""L'indicatore di robustezza della password sotto il campo di Registrati (mockup)."""

from __future__ import annotations

import pytest

from beewatch.sicurezza import FORZA_DEBOLE, FORZA_MEDIA, FORZA_ROBUSTA, forza_password


@pytest.mark.parametrize(
    ("password", "attesa"),
    [
        ("", (0, FORZA_DEBOLE)),
        ("corta", (0, FORZA_DEBOLE)),  # sotto le regole: debole, qualunque cosa contenga
        (" con-spazio-davanti", (0, FORZA_DEBOLE)),
        ("abcdefgh", (1, FORZA_DEBOLE)),
        ("abcdefgh1", (2, FORZA_MEDIA)),
        ("abcdefghilmn", (2, FORZA_MEDIA)),
        ("Abcdefgh1", (3, FORZA_ROBUSTA)),
        ("favo-di-miele", (3, FORZA_ROBUSTA)),
        ("Favo-di-miele-2026", (4, FORZA_ROBUSTA)),
    ],
)
def test_la_robustezza_della_password(password, attesa):
    assert forza_password(password) == attesa
