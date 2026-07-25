"""Génération des codes de salon et des identifiants joueurs."""
from __future__ import annotations

import secrets

# Alphabet sans caractères ambigus (0/O, 1/I/L) pour la saisie/lecture d'un QR.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def new_room_code(length: int = 6) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def new_player_id() -> str:
    return secrets.token_hex(8)
