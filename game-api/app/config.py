"""Configuration du game-api."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent

# URL du semantic-api (validation lexicale + percentiles + tirage).
SEMANTIC_API_URL = os.getenv("SEMANTIC_API_URL", "http://127.0.0.1:8100")

# Store d'état : Redis si REDIS_URL est défini, sinon mémoire de process.
REDIS_URL = os.getenv("REDIS_URL")  # ex. redis://localhost:6379/0
STATE_TTL = int(os.getenv("STATE_TTL", str(24 * 3600)))  # 24 h (brief §4)

# Durée d'une manche, en secondes (brief §2.2).
ROUND_SECONDS = int(os.getenv("ROUND_SECONDS", "25"))
# Pause d'affichage de la révélation avant la manche suivante.
REVEAL_PAUSE_SECONDS = float(os.getenv("REVEAL_PAUSE_SECONDS", "4"))

# Nombre de manches par niveau (brief §2.3).
ROUNDS_BY_LEVEL = {"FACILE": 10, "NORMAL": 6, "DIFFICILE": 3}

# Répertoire du client PWA servi en statique (build « no-build »).
CLIENT_DIR = Path(os.getenv("CLIENT_DIR", str(REPO_DIR / "client")))

# URL publique de base pour les QR codes (lien de salon). Ex. https://jeu.exemple.fr
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")

HOST = os.getenv("GAME_HOST", "0.0.0.0")
PORT = int(os.getenv("GAME_PORT", "8000"))
