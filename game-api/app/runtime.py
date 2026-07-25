"""Orchestration des parties : connexions WebSocket, manches, timer, révélation.

Autorité serveur (brief §4.2) : le serveur est seul détenteur du mot cible, du
compteur de manches et du buffer de propositions de la manche en cours. Aucune
information exploitable ne transite avant révélation.

La boucle de jeu (timers asyncio) est locale au process ; l'état sérialisable est
persisté via le Store (mémoire ou Redis). La carte de percentiles reste en mémoire
de process, par partie.
"""
from __future__ import annotations

import asyncio
import logging
import time

from fastapi import WebSocket

from . import config
from .codes import new_player_id, new_room_code
from .scoring import (apply_round_scores, compute_ranking, round_has_winner, score_round)
from .semantic_client import SemanticClient
from .store import Store

log = logging.getLogger("game.runtime")

MAX_PLAYERS = 12


def now_ms() -> int:
    return int(time.time() * 1000)


class RoomRuntime:
    """État de process (non persistant) d'une partie : verrou, carte, timers, conns."""
    def __init__(self):
        self.lock = asyncio.Lock()
        self.pmap: dict[str, float] = {}
        self.timer_task: asyncio.Task | None = None
        self.advance_task: asyncio.Task | None = None


class ConnectionManager:
    def __init__(self):
        # code -> { WebSocket: playerId }
        self.conns: dict[str, dict[WebSocket, str]] = {}

    def bind(self, code: str, ws: WebSocket, player_id: str) -> None:
        self.conns.setdefault(code, {})[ws] = player_id

    def unbind(self, code: str, ws: WebSocket) -> str | None:
        pid = self.conns.get(code, {}).pop(ws, None)
        if code in self.conns and not self.conns[code]:
            self.conns.pop(code, None)
        return pid

    def player_still_connected(self, code: str, player_id: str) -> bool:
        return player_id in (self.conns.get(code, {}) or {}).values()

    async def broadcast(self, code: str, message: dict) -> None:
        for ws in list(self.conns.get(code, {})):
            try:
                await ws.send_json(message)
            except Exception:
                self.conns.get(code, {}).pop(ws, None)

    async def send(self, ws: WebSocket, message: dict) -> None:
        try:
            await ws.send_json(message)
        except Exception:
            pass


# --------------------------------------------------------------- sérialisation
def is_active(state: dict, pid: str) -> bool:
    """Un joueur actif propose des mots (tout le monde sauf le maître du mot)."""
    return pid != state.get("wordSetterId")


def players_public(state: dict) -> list[dict]:
    out = []
    for p in state["players"].values():
        out.append({
            "id": p["id"], "pseudo": p["pseudo"], "score": round(p.get("score", 0.0), 4),
            "connected": p.get("connected", False),
            "isHost": p["id"] == state.get("hostId"),
            "isSetter": p["id"] == state.get("wordSetterId"),
        })
    return out


def public_state(state: dict) -> dict:
    """Instantané destiné au client. Le mot cible n'apparaît que si FINISHED."""
    return {
        "code": state["code"],
        "mode": state["mode"],
        "level": state["level"],
        "status": state["status"],
        "currentRound": state["currentRound"],
        "totalRounds": state["totalRounds"],
        "hostId": state.get("hostId"),
        "wordSetterId": state.get("wordSetterId"),
        "hasTarget": bool(state.get("targetWord")),
        "players": players_public(state),
        "history": state.get("history", []),
        "ranking": compute_ranking(state["players"]),
        "roundDeadline": state.get("roundDeadline"),
        # jamais avant FINISHED (brief §2.6, §4.2) :
        "targetWord": state["targetWord"] if state["status"] == "FINISHED" else None,
    }


class GameManager:
    def __init__(self, store: Store, semantic: SemanticClient):
        self.store = store
        self.semantic = semantic
        self.cm = ConnectionManager()
        self._runtimes: dict[str, RoomRuntime] = {}

    def runtime(self, code: str) -> RoomRuntime:
        return self._runtimes.setdefault(code, RoomRuntime())

    # ------------------------------------------------------------- création
    async def create_room(self, mode: str, level: str) -> str:
        mode = mode.upper()
        level = level.upper()
        if mode not in ("SYSTEM", "PLAYER"):
            raise ValueError("mode invalide")
        if level not in config.ROUNDS_BY_LEVEL:
            raise ValueError("niveau invalide")
        for _ in range(20):
            code = new_room_code()
            if not await self.store.exists(code):
                break
        else:
            raise RuntimeError("impossible de générer un code unique")
        state = {
            "code": code, "mode": mode, "level": level,
            "totalRounds": config.ROUNDS_BY_LEVEL[level], "currentRound": 0,
            "status": "LOBBY", "targetWord": None, "wordSetterId": None, "hostId": None,
            "players": {}, "roundBuffer": {}, "history": [], "roundDeadline": None,
        }
        await self.store.create(state)
        log.info("Salon %s créé (mode=%s niveau=%s)", code, mode, level)
        return code

    # --------------------------------------------------------------- join
    async def on_join(self, code: str, ws: WebSocket, pseudo: str, player_id: str | None):
        rt = self.runtime(code)
        async with rt.lock:
            state = await self.store.get(code)
            if state is None:
                await self.cm.send(ws, {"type": "error", "message": "Salon introuvable."})
                return None

            # Reconnexion d'un joueur connu.
            if player_id and player_id in state["players"]:
                state["players"][player_id]["connected"] = True
                self.cm.bind(code, ws, player_id)
                await self.store.save(state)
                await self.cm.send(ws, {"type": "joined", "playerId": player_id,
                                        "isHost": player_id == state["hostId"]})
                await self.cm.send(ws, {"type": "state", "state": public_state(state)})
                await self.cm.broadcast(code, {"type": "lobbyUpdate", **self._lobby(state)})
                return player_id

            # Nouveau joueur : uniquement en LOBBY.
            if state["status"] != "LOBBY":
                await self.cm.send(ws, {"type": "error",
                                        "message": "La partie a déjà commencé."})
                return None
            if len(state["players"]) >= MAX_PLAYERS:
                await self.cm.send(ws, {"type": "error", "message": "Salon complet."})
                return None
            pseudo = (pseudo or "Joueur").strip()[:24] or "Joueur"
            pid = new_player_id()
            state["players"][pid] = {"id": pid, "pseudo": pseudo, "score": 0.0,
                                     "connected": True}
            if state["hostId"] is None:
                state["hostId"] = pid
            self.cm.bind(code, ws, pid)
            await self.store.save(state)
            await self.cm.send(ws, {"type": "joined", "playerId": pid,
                                    "isHost": pid == state["hostId"]})
            await self.cm.send(ws, {"type": "state", "state": public_state(state)})
            await self.cm.broadcast(code, {"type": "lobbyUpdate", **self._lobby(state)})
            log.info("Salon %s : %s rejoint (%s)", code, pseudo, pid)
            return pid

    def _lobby(self, state: dict) -> dict:
        return {"players": players_public(state), "mode": state["mode"],
                "level": state["level"], "status": state["status"],
                "hostId": state.get("hostId"), "wordSetterId": state.get("wordSetterId"),
                "hasTarget": bool(state.get("targetWord")),
                "totalRounds": state["totalRounds"]}

    # ------------------------------------------------------ set target word
    async def on_set_target(self, code: str, pid: str, word: str):
        rt = self.runtime(code)
        async with rt.lock:
            state = await self.store.get(code)
            if state is None or state["status"] != "LOBBY":
                return await self._err(code, pid, "Action impossible maintenant.")
            if state["mode"] != "PLAYER":
                return await self._err(code, pid, "Mot cible imposé uniquement en mode PLAYER.")
            if pid != state["hostId"]:
                return await self._err(code, pid, "Seul l'hôte définit le mot cible.")
            res = await self.semantic.validate_target(word)
            if not res.get("ok"):
                # Mot invalide -> partie non lancée, message explicite (brief §2.1).
                return await self._err(code, pid, res.get("reason", "Mot cible invalide."))
            state["targetWord"] = res["word"]
            state["wordSetterId"] = pid
            await self.store.save(state)
            await self._send_pid(code, pid, {"type": "targetSet", "ok": True})
            await self.cm.broadcast(code, {"type": "lobbyUpdate", **self._lobby(state)})

    # ----------------------------------------------------------- start game
    async def on_start(self, code: str, pid: str):
        rt = self.runtime(code)
        async with rt.lock:
            state = await self.store.get(code)
            if state is None or state["status"] != "LOBBY":
                return await self._err(code, pid, "La partie ne peut pas démarrer.")
            if pid != state["hostId"]:
                return await self._err(code, pid, "Seul l'hôte peut lancer la partie.")
            if len(state["players"]) < 2:
                return await self._err(code, pid, "Il faut au moins 2 joueurs.")
            if state["mode"] == "PLAYER" and not state.get("targetWord"):
                return await self._err(code, pid, "Définissez d'abord le mot cible.")
            active = [p for p in state["players"] if is_active(state, p)]
            if len(active) < 1:
                return await self._err(code, pid, "Aucun joueur pour deviner.")

            # Choix / préparation du mot cible.
            if state["mode"] == "SYSTEM":
                state["targetWord"] = await self.semantic.random_word(state["level"])
            try:
                rt.pmap = await self.semantic.percentiles(state["targetWord"])
            except Exception as e:
                log.exception("Échec calcul percentiles")
                return await self._err(code, pid, "Erreur moteur sémantique.")

            state["status"] = "RUNNING"
            state["currentRound"] = 0
            await self.store.save(state)
            await self.cm.broadcast(code, {"type": "gameStarted",
                                           "totalRounds": state["totalRounds"],
                                           "level": state["level"], "mode": state["mode"]})
            log.info("Salon %s : partie lancée, cible cachée prête (%d mots)",
                     code, len(rt.pmap))
            await self._start_round(code, state, rt)

    async def _start_round(self, code: str, state: dict, rt: RoomRuntime):
        """Ouvre une manche (verrou déjà tenu par l'appelant)."""
        state["currentRound"] += 1
        state["status"] = "RUNNING"
        state["roundBuffer"] = {}
        deadline = now_ms() + config.ROUND_SECONDS * 1000
        state["roundDeadline"] = deadline
        await self.store.save(state)
        round_no = state["currentRound"]
        await self.cm.broadcast(code, {"type": "roundStarted", "round": round_no,
                                       "totalRounds": state["totalRounds"],
                                       "deadline": deadline,
                                       "durationSeconds": config.ROUND_SECONDS})
        rt.timer_task = asyncio.create_task(self._round_timer(code, round_no))

    async def _round_timer(self, code: str, round_no: int):
        try:
            await asyncio.sleep(config.ROUND_SECONDS)
        except asyncio.CancelledError:
            return
        rt = self.runtime(code)
        async with rt.lock:
            state = await self.store.get(code)
            if (state and state["status"] == "RUNNING"
                    and state["currentRound"] == round_no):
                await self._reveal_locked(code, state, rt)

    # -------------------------------------------------------- submit guess
    async def on_submit(self, code: str, pid: str, word: str):
        rt = self.runtime(code)
        async with rt.lock:
            state = await self.store.get(code)
            if state is None or state["status"] != "RUNNING":
                return await self._err(code, pid, "Aucune manche en cours.")
            if state["roundDeadline"] and now_ms() > state["roundDeadline"]:
                return await self._err(code, pid, "Temps écoulé pour cette manche.")
            if not is_active(state, pid):
                return await self._err(code, pid, "Le maître du mot ne propose pas.")
            if pid in state["roundBuffer"]:
                return await self._err(code, pid, "Vous avez déjà proposé cette manche.")

            res = await self.semantic.normalize(word)
            if not res.get("ok"):
                # Hors vocabulaire / nom propre : proposition NON consommée (brief §3.3).
                return await self._err(code, pid, res.get("reason", "Mot inconnu."))

            w = res["word"]
            pct = float(rt.pmap.get(w, 0.0))
            is_target = (w == state["targetWord"])
            # Bufferisé côté serveur, AUCUNE diffusion avant révélation (brief §2.2).
            state["roundBuffer"][pid] = {"word": w, "percentile": pct, "isTarget": is_target}
            await self.store.save(state)
            # Accusé au seul proposant : mot retenu, SANS le score (aveugle).
            await self._send_pid(code, pid, {"type": "guessAccepted",
                                             "round": state["currentRound"], "word": w})

            # Révélation anticipée si tous les joueurs actifs connectés ont proposé.
            active_connected = [p["id"] for p in state["players"].values()
                                if p.get("connected") and is_active(state, p["id"])]
            if active_connected and all(a in state["roundBuffer"] for a in active_connected):
                if rt.timer_task and rt.timer_task is not asyncio.current_task():
                    rt.timer_task.cancel()
                await self._reveal_locked(code, state, rt)

    # --------------------------------------------------------- reveal round
    async def _reveal_locked(self, code: str, state: dict, rt: RoomRuntime):
        """Révèle la manche (verrou tenu). Applique le scoring, diffuse, enchaîne."""
        if state["status"] != "RUNNING":
            return
        state["status"] = "REVEALING"
        state["roundDeadline"] = None
        round_no = state["currentRound"]

        entries = []
        for pid, g in state["roundBuffer"].items():
            player = state["players"].get(pid, {})
            entries.append({"playerId": pid, "pseudo": player.get("pseudo", "?"),
                            "word": g["word"], "percentile": round(g["percentile"], 2),
                            "isTarget": g["isTarget"]})
        # Ordre d'affichage : meilleur pourcentage en tête.
        entries.sort(key=lambda e: e["percentile"], reverse=True)

        round_points = score_round(
            [{"playerId": e["playerId"], "percentile": e["percentile"],
              "isTarget": e["isTarget"]} for e in entries])
        apply_round_scores(state["players"], round_points)

        for e in entries:
            e["roundPoints"] = round(round_points.get(e["playerId"], 0.0), 4)
            state["history"].append({"round": round_no, "playerId": e["playerId"],
                                     "pseudo": e["pseudo"], "word": e["word"],
                                     "percentile": e["percentile"], "isTarget": e["isTarget"]})
        state["roundBuffer"] = {}
        has_winner = round_has_winner(entries)
        await self.store.save(state)

        await self.cm.broadcast(code, {
            "type": "roundRevealed", "round": round_no,
            "totalRounds": state["totalRounds"], "entries": entries,
            "hasWinner": has_winner,
            "players": players_public(state),
            "ranking": compute_ranking(state["players"]),
        })
        log.info("Salon %s : manche %d révélée (%d propositions, gagnant=%s)",
                 code, round_no, len(entries), has_winner)

        if has_winner or round_no >= state["totalRounds"]:
            await self._finish(code, state)
        else:
            rt.advance_task = asyncio.create_task(self._advance_after_pause(code, round_no))

    async def _advance_after_pause(self, code: str, prev_round: int):
        try:
            await asyncio.sleep(config.REVEAL_PAUSE_SECONDS)
        except asyncio.CancelledError:
            return
        rt = self.runtime(code)
        async with rt.lock:
            state = await self.store.get(code)
            if (state and state["status"] == "REVEALING"
                    and state["currentRound"] == prev_round):
                await self._start_round(code, state, rt)

    async def _finish(self, code: str, state: dict):
        state["status"] = "FINISHED"
        state["roundDeadline"] = None
        await self.store.save(state)
        await self.cm.broadcast(code, {
            "type": "gameFinished", "targetWord": state["targetWord"],
            "ranking": compute_ranking(state["players"]),
            "history": state["history"], "totalRounds": state["totalRounds"],
        })
        log.info("Salon %s : partie terminée, cible='%s'", code, state["targetWord"])

    # -------------------------------------------------------- disconnect
    async def on_disconnect(self, code: str, ws: WebSocket):
        pid = self.cm.unbind(code, ws)
        if not pid:
            return
        rt = self.runtime(code)
        async with rt.lock:
            state = await self.store.get(code)
            if state is None or pid not in state["players"]:
                return
            # Déconnecté seulement si plus aucune socket de ce joueur.
            if not self.cm.player_still_connected(code, pid):
                state["players"][pid]["connected"] = False
                await self.store.save(state)
                await self.cm.broadcast(code, {"type": "lobbyUpdate", **self._lobby(state)})
                log.info("Salon %s : joueur %s déconnecté (partie continue)", code, pid)

    # ------------------------------------------------------------- helpers
    async def _err(self, code: str, pid: str, message: str):
        await self._send_pid(code, pid, {"type": "error", "message": message})

    async def _send_pid(self, code: str, pid: str, message: dict):
        for ws, bound in list(self.cm.conns.get(code, {}).items()):
            if bound == pid:
                await self.cm.send(ws, message)
