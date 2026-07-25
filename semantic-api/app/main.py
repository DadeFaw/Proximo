"""semantic-api — service FastAPI isolé (brief §4).

Porte le lexique élagué en RAM et expose :
  * validation lexicale des propositions et des mots cibles ;
  * la carte de percentiles d'une cible (calculée une fois par partie) ;
  * le tirage d'un mot cible par niveau.

Ce service ne connaît rien des salons ni des parties : il est stateless et
scalable indépendamment du game-api.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .engine import SemanticEngine, load_engine
from .schemas import (
    HealthResponse, NormalizeRequest, NormalizeResponse, PercentilesRequest,
    PercentilesResponse, RandomWordResponse, ScoreRequest, ScoreResponse,
    ValidateTargetRequest, ValidateTargetResponse,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("semantic.api")

LEVELS = {"FACILE", "NORMAL", "DIFFICILE"}
_engine: SemanticEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine
    log.info("Chargement du moteur sémantique…")
    _engine = load_engine()
    yield
    _engine = None


app = FastAPI(title="semantic-api", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


def engine() -> SemanticEngine:
    if _engine is None:
        raise HTTPException(503, "Moteur sémantique non chargé.")
    return _engine


@app.get("/health", response_model=HealthResponse)
def health():
    e = engine()
    return HealthResponse(status="ok", engine=e.source, model=e.model_name,
                          vocab_size=len(e.words), dim=e.dim)


@app.post("/normalize", response_model=NormalizeResponse)
def normalize(req: NormalizeRequest):
    """Normalise/valide une proposition (lemmatisation, vocabulaire, nom propre)."""
    return NormalizeResponse(**engine().normalize(req.text))


@app.post("/validate-target", response_model=ValidateTargetResponse)
def validate_target(req: ValidateTargetRequest):
    """Valide un mot cible saisi (mode PLAYER) : vocab + nom commun + non propre."""
    return ValidateTargetResponse(**engine().validate_target(req.text))


@app.post("/percentiles", response_model=PercentilesResponse)
def percentiles(req: PercentilesRequest):
    """Carte {mot: percentile} de la cible contre tout le lexique (une fois/partie)."""
    e = engine()
    if req.target not in e.word2idx:
        raise HTTPException(422, f"Cible '{req.target}' absente du vocabulaire.")
    pmap = e.percentile_map(req.target)
    return PercentilesResponse(target=req.target, count=len(pmap), percentiles=pmap)


@app.post("/score", response_model=ScoreResponse)
def score(req: ScoreRequest):
    """Normalise `word` et renvoie son percentile face à `target` (utilitaire/test)."""
    e = engine()
    if req.target not in e.word2idx:
        raise HTTPException(422, f"Cible '{req.target}' absente du vocabulaire.")
    return ScoreResponse(**e.score(req.target, req.word))


@app.get("/random-word", response_model=RandomWordResponse)
def random_word(level: str = Query("NORMAL")):
    """Tire un mot cible dans le lexique filtré par niveau (mode SYSTEM)."""
    lvl = level.upper()
    if lvl not in LEVELS:
        raise HTTPException(422, f"Niveau inconnu : {level}")
    return RandomWordResponse(word=engine().random_word(lvl), level=lvl)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=False)
