"""Store d'état de partie éphémère (brief §4, §5).

Deux implémentations derrière une interface commune :
  * InMemoryStore — dict de process, par défaut (aucune dépendance).
  * RedisStore    — JSON par clé `game:{code}`, TTL 24 h, pour un déploiement
                    multi-instances ou survivant aux redémarrages.

L'état stocké est strictement sérialisable (cf. modèle §5). La carte de
percentiles et les timers asyncio restent, eux, en mémoire de process
(orchestration de la boucle de jeu, cf. runtime.py).
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod

from . import config


class Store(ABC):
    @abstractmethod
    async def create(self, state: dict) -> None: ...
    @abstractmethod
    async def get(self, code: str) -> dict | None: ...
    @abstractmethod
    async def save(self, state: dict) -> None: ...
    @abstractmethod
    async def delete(self, code: str) -> None: ...

    async def exists(self, code: str) -> bool:
        return (await self.get(code)) is not None

    async def close(self) -> None:  # pragma: no cover - surcharge optionnelle
        return None


class InMemoryStore(Store):
    def __init__(self):
        self._games: dict[str, dict] = {}

    async def create(self, state: dict) -> None:
        self._games[state["code"]] = state

    async def get(self, code: str) -> dict | None:
        return self._games.get(code)

    async def save(self, state: dict) -> None:
        self._games[state["code"]] = state

    async def delete(self, code: str) -> None:
        self._games.pop(code, None)


class RedisStore(Store):
    def __init__(self, url: str, ttl: int = config.STATE_TTL):
        import redis.asyncio as redis  # import paresseux : dépendance optionnelle
        self._r = redis.from_url(url, encoding="utf-8", decode_responses=True)
        self._ttl = ttl

    @staticmethod
    def _key(code: str) -> str:
        return f"game:{code}"

    async def create(self, state: dict) -> None:
        await self.save(state)

    async def get(self, code: str) -> dict | None:
        raw = await self._r.get(self._key(code))
        return json.loads(raw) if raw else None

    async def save(self, state: dict) -> None:
        await self._r.set(self._key(state["code"]), json.dumps(state, ensure_ascii=False),
                          ex=self._ttl)

    async def delete(self, code: str) -> None:
        await self._r.delete(self._key(code))

    async def close(self) -> None:
        await self._r.aclose()


def build_store() -> Store:
    if config.REDIS_URL:
        return RedisStore(config.REDIS_URL)
    return InMemoryStore()
