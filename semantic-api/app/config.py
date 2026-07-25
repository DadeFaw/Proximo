"""Configuration du service semantic-api.

Toutes les valeurs sont surchargeables par variables d'environnement, ce qui
permet de basculer entre le moteur spaCy (par défaut, léger) et un artefact
élagué produit hors-ligne (cf. prune_model.py) sans toucher au code.
"""
from __future__ import annotations

import os
from pathlib import Path

# Répertoire de base du service (…/semantic-api)
BASE_DIR = Path(__file__).resolve().parent.parent

# Modèle spaCy français : fournit lemmatisation, POS et (pour *_md/_lg) vecteurs.
SPACY_MODEL = os.getenv("SPACY_MODEL", "fr_core_news_md")

# Chemin optionnel vers un artefact élagué (dossier produit par prune_model.py).
# S'il est présent et valide, il prime sur les vecteurs embarqués dans spaCy.
ARTIFACT_DIR = os.getenv("ARTIFACT_DIR", str(BASE_DIR / "artifact"))

# Cache du lexique construit (matrice + POS + rangs), pour éviter de refaire le
# filtrage POS coûteux à chaque démarrage (cf. brief §3.1 : « une fois, hors ligne »).
CACHE_DIR = Path(os.getenv("CACHE_DIR", str(BASE_DIR / ".cache")))

# Taille cible du lexique retenu (le brief vise ~80 000 lemmes pour frWac/cc.fr.300 ;
# le modèle spaCy _md en contient nettement moins, on garde donc tout ce qui est valide).
MAX_LEXICON = int(os.getenv("MAX_LEXICON", "80000"))

# Longueur minimale d'un lemme retenu dans le lexique.
MIN_WORD_LEN = int(os.getenv("MIN_WORD_LEN", "3"))

HOST = os.getenv("SEMANTIC_HOST", "0.0.0.0")
PORT = int(os.getenv("SEMANTIC_PORT", "8100"))
