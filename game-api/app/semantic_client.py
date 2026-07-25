"""Client HTTP asynchrone vers le semantic-api."""
from __future__ import annotations

import httpx

from . import config


class SemanticClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or config.SEMANTIC_API_URL).rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def close(self):
        await self._client.aclose()

    async def health(self) -> dict:
        r = await self._client.get("/health")
        r.raise_for_status()
        return r.json()

    async def normalize(self, text: str) -> dict:
        """Valide/normalise une proposition. Renvoie {ok, word?|reason?}."""
        r = await self._client.post("/normalize", json={"text": text})
        r.raise_for_status()
        return r.json()

    async def validate_target(self, text: str) -> dict:
        r = await self._client.post("/validate-target", json={"text": text})
        r.raise_for_status()
        return r.json()

    async def percentiles(self, target: str) -> dict[str, float]:
        """Carte complète {mot: percentile} de la cible (mise en cache par la partie)."""
        r = await self._client.post("/percentiles", json={"target": target})
        r.raise_for_status()
        return r.json()["percentiles"]

    async def random_word(self, level: str) -> str:
        r = await self._client.get("/random-word", params={"level": level})
        r.raise_for_status()
        return r.json()["word"]
