"""Schémas d'échange (Pydantic) du semantic-api."""
from __future__ import annotations

from pydantic import BaseModel, Field


class NormalizeRequest(BaseModel):
    text: str = Field(..., description="Proposition brute saisie par le joueur")


class NormalizeResponse(BaseModel):
    ok: bool
    word: str | None = None          # lemme canonique retenu dans le vocabulaire
    reason: str | None = None        # message explicite en cas de rejet
    is_proper_noun: bool = False


class ValidateTargetRequest(BaseModel):
    text: str


class ValidateTargetResponse(BaseModel):
    ok: bool
    word: str | None = None
    reason: str | None = None


class PercentilesRequest(BaseModel):
    target: str = Field(..., description="Mot cible déjà normalisé (présent au vocabulaire)")


class PercentilesResponse(BaseModel):
    target: str
    count: int
    # {mot: percentile in [0,100]} — la carte complète, mise en cache par le game-api.
    percentiles: dict[str, float]


class ScoreRequest(BaseModel):
    target: str
    word: str


class ScoreResponse(BaseModel):
    ok: bool
    word: str | None = None
    percentile: float | None = None
    is_target: bool = False
    reason: str | None = None


class RandomWordResponse(BaseModel):
    word: str
    level: str


class HealthResponse(BaseModel):
    status: str
    engine: str
    model: str
    vocab_size: int
    dim: int
