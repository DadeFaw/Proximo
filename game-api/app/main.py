"""game-api — FastAPI + WebSocket (brief §4, §6).

Expose :
  * REST : création de salon, infos salon, QR code, santé.
  * WebSocket /ws/{code} : join, leave, setTargetWord, startGame, submitGuess
    (client -> serveur) ; lobbyUpdate, gameStarted, roundStarted, roundRevealed,
    gameFinished, error (serveur -> clients).
  * Sert le client PWA en statique.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import segno
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .runtime import GameManager
from .semantic_client import SemanticClient
from .store import build_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("game.api")

manager: GameManager | None = None
_semantic: SemanticClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global manager, _semantic
    store = build_store()
    _semantic = SemanticClient()
    manager = GameManager(store, _semantic)
    try:
        info = await _semantic.health()
        log.info("semantic-api OK : %s (%d mots, dim %d)",
                 info.get("engine"), info.get("vocab_size"), info.get("dim"))
    except Exception as e:
        log.warning("semantic-api injoignable au démarrage (%s). "
                    "Vérifiez SEMANTIC_API_URL=%s", e, config.SEMANTIC_API_URL)
    yield
    await _semantic.close()
    await store.close()


app = FastAPI(title="game-api", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


def mgr() -> GameManager:
    if manager is None:
        raise HTTPException(503, "Service non initialisé.")
    return manager


class CreateRoomRequest(BaseModel):
    mode: str = Field(..., pattern="^(SYSTEM|PLAYER|system|player)$")
    level: str = Field(..., pattern="^(FACILE|NORMAL|DIFFICILE|facile|normal|difficile)$")
    theme: str | None = None


class CreateRoomResponse(BaseModel):
    code: str


# ---------------------------------------------------------------------- REST
@app.get("/api/health")
async def health():
    out = {"status": "ok", "semantic": None}
    try:
        out["semantic"] = await _semantic.health()
    except Exception as e:
        out["status"] = "degraded"
        out["semantic_error"] = str(e)
    return out


@app.get("/api/config")
async def get_config():
    return {"roundSeconds": config.ROUND_SECONDS, "roundsByLevel": config.ROUNDS_BY_LEVEL}


@app.post("/api/rooms", response_model=CreateRoomResponse)
async def create_room(req: CreateRoomRequest):
    try:
        code = await mgr().create_room(req.mode, req.level, req.theme)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return CreateRoomResponse(code=code)


@app.get("/api/themes")
async def get_themes():
    """Liste des thèmes de mots cibles (proxy du semantic-api)."""
    try:
        return {"themes": await _semantic.themes()}
    except Exception as e:
        raise HTTPException(503, f"semantic-api injoignable : {e}")


@app.get("/api/rooms/{code}")
async def room_info(code: str):
    state = await mgr().store.get(code.upper())
    if state is None:
        raise HTTPException(404, "Salon introuvable.")
    return {"exists": True, "code": state["code"], "status": state["status"],
            "mode": state["mode"], "level": state["level"],
            "players": len(state["players"]), "totalRounds": state["totalRounds"]}


def _join_url(request: Request, code: str) -> str:
    base = config.PUBLIC_BASE_URL.rstrip("/") if config.PUBLIC_BASE_URL else str(request.base_url).rstrip("/")
    return f"{base}/?code={code}"


@app.get("/api/rooms/{code}/join-url")
async def join_url(code: str, request: Request):
    if await mgr().store.get(code.upper()) is None:
        raise HTTPException(404, "Salon introuvable.")
    return {"url": _join_url(request, code.upper())}


@app.get("/api/rooms/{code}/qr.svg")
async def room_qr(code: str, request: Request):
    """QR code (SVG) pointant vers le lien de salon (brief §4.1)."""
    code = code.upper()
    if await mgr().store.get(code) is None:
        raise HTTPException(404, "Salon introuvable.")
    qr = segno.make(_join_url(request, code), error="m")
    svg = qr.svg_inline(scale=6, border=2, dark="#0f172a", light="#ffffff")
    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ WebSocket
@app.websocket("/ws/{code}")
async def ws_endpoint(ws: WebSocket, code: str):
    code = code.upper()
    await ws.accept()
    gm = mgr()
    player_id: str | None = None
    try:
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")

            if mtype == "join":
                player_id = await gm.on_join(code, ws, msg.get("pseudo", ""),
                                             msg.get("playerId"))
                continue

            if player_id is None:
                await ws.send_json({"type": "error",
                                    "message": "Envoyez d'abord un message 'join'."})
                continue

            if mtype == "setTargetWord":
                await gm.on_set_target(code, player_id, msg.get("word", ""))
            elif mtype == "startGame":
                await gm.on_start(code, player_id)
            elif mtype == "submitGuess":
                await gm.on_submit(code, player_id, msg.get("word", ""))
            elif mtype == "nextRound":
                await gm.on_next_round(code, player_id)
            elif mtype == "leave":
                break
            else:
                await ws.send_json({"type": "error", "message": f"Type inconnu : {mtype}"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.exception("Erreur WS : %s", e)
    finally:
        await gm.on_disconnect(code, ws)


# ---------------------------------------------------- client PWA (statique)
if config.CLIENT_DIR.exists():
    app.mount("/", StaticFiles(directory=str(config.CLIENT_DIR), html=True), name="client")
else:  # pragma: no cover
    log.warning("Répertoire client introuvable : %s", config.CLIENT_DIR)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=False)
