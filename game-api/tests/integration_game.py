"""Test d'intégration bout-en-bout via WebSocket (flux mis à jour).

Prérequis : semantic-api (8100) et game-api (8000) démarrés.
Vérifie :
  - thème : la cible est bien tirée dans le thème choisi (ANIMAUX) ;
  - le mot cible n'apparaît jamais avant gameFinished ;
  - aveugle : aucune proposition adverse avant révélation ;
  - un mot hors-vocabulaire est rejeté sans consommer le tour ;
  - LES SCORES SONT MASQUÉS pendant la partie (score=None), révélés seulement à la fin ;
  - l'hôte doit lancer chaque manche suivante (nextRound) — pas d'auto-avance ;
  - toutes les propositions + leur % s'affichent à la révélation.
Puis une partie PLAYER : mot cible invalide refusé, mot valide accepté.
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "semantic-api"))
from app.themes import THEMES  # noqa: E402  (depuis semantic-api)

BASE = "http://127.0.0.1:8000"
WS = "ws://127.0.0.1:8000/ws/"
leaks: list = []
_failures = 0


def check_leak(cid, m):
    if m.get("type") != "gameFinished":
        if m.get("targetWord"):
            leaks.append(("targetWord_avant_fin", cid, m.get("type")))
        # scores jamais divulgués avant la fin
        for p in (m.get("players") or []):
            if p.get("score") is not None:
                leaks.append(("score_avant_fin", cid, m.get("type")))


class Client:
    def __init__(self, cid, ws):
        self.cid, self.ws = cid, ws
        self.q: asyncio.Queue = asyncio.Queue()
        self.msgs: list = []
        self.task = asyncio.create_task(self._read())

    async def _read(self):
        try:
            async for raw in self.ws:
                m = json.loads(raw)
                check_leak(self.cid, m)
                self.msgs.append(m)
                await self.q.put(m)
        except Exception:
            pass

    async def send(self, type_, **kw):
        await self.ws.send(json.dumps({"type": type_, **kw}))

    async def wait(self, *types, timeout=30):
        while True:
            m = await asyncio.wait_for(self.q.get(), timeout)
            if m["type"] in types:
                return m
            if m["type"] == "error" and "error" not in types:
                raise AssertionError(f"[{self.cid}] erreur serveur : {m['message']}")


def ok(cond, label):
    global _failures
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        _failures += 1


async def play_system():
    print("\n=== Partie SYSTEM / DIFFICILE / thème ANIMAUX (2 joueurs) ===")
    async with httpx.AsyncClient() as h:
        r = await h.post(f"{BASE}/api/rooms",
                         json={"mode": "SYSTEM", "level": "DIFFICILE", "theme": "ANIMAUX"})
        code = r.json()["code"]
    print("  salon:", code)

    async with websockets.connect(WS + code) as wa, websockets.connect(WS + code) as wb:
        A, B = Client("A", wa), Client("B", wb)
        await A.send("join", pseudo="Alice"); ja = await A.wait("joined")
        ok(ja["isHost"], "A est hôte"); await A.wait("state")
        await B.send("join", pseudo="Bob"); jb = await B.wait("joined")
        ok(not jb["isHost"], "B n'est pas hôte")

        await A.send("startGame")
        gsa = await A.wait("gameStarted"); await B.wait("gameStarted")
        ok(gsa["totalRounds"] == 3, "DIFFICILE => 3 manches")

        guesses = [("chat", "maison"), ("route", "arbre"), ("musique", "table")]
        finished = None
        for i in range(3):
            ra = await A.wait("roundStarted"); await B.wait("roundStarted")
            ok("deadline" in ra, f"manche {ra['round']} : deadline présente")

            if i == 0:
                await A.send("submitGuess", word="wxcvbqztn")
                err = await A.wait("error")
                ok("inconnu" in err["message"].lower() or "propre" in err["message"].lower(),
                   "mot invalide rejeté sans consommer le tour")

            ga, gb = guesses[i]
            await A.send("submitGuess", word=ga)
            acc = await A.wait("guessAccepted")
            ok("percentile" not in acc, "guessAccepted sans score (aveugle)")
            await B.send("submitGuess", word=gb); await B.wait("guessAccepted")

            rev = await A.wait("roundRevealed"); await B.wait("roundRevealed")
            ok(len(rev["entries"]) == 2, f"manche {rev['round']} : 2 propositions révélées")
            ok(all("percentile" in e for e in rev["entries"]), "chaque proposition a son %")
            ok("ranking" not in rev, "pas de classement diffusé pendant la partie")
            ok(all("roundPoints" not in e for e in rev["entries"]), "pas de points diffusés")
            ok(all(p.get("score") is None for p in rev.get("players", [])),
               "scores masqués dans la révélation")

            # Sans action de l'hôte, la manche suivante NE démarre PAS (avance manuelle).
            try:
                await B.wait("roundStarted", "gameFinished", timeout=2)
                ok(False, "avance manuelle : rien ne doit démarrer sans l'hôte")
            except asyncio.TimeoutError:
                ok(True, "avance manuelle : la partie attend l'hôte")

            await A.send("nextRound")
            if rev["gameOver"]:
                finished = await A.wait("gameFinished"); await B.wait("gameFinished")
                break

        ok(finished is not None, "partie terminée après action de l'hôte")
        target = finished.get("targetWord")
        ok(target in THEMES["ANIMAUX"]["words"], f"cible tirée dans le thème ANIMAUX : {target!r}")
        ranking = finished["ranking"]
        ok(all(p["score"] is not None for p in ranking), "scores révélés dans le classement final")
        print("  cible:", target, "| classement final:",
              [(p["pseudo"], p["score"]) for p in ranking])


async def play_player_mode():
    print("\n=== Partie PLAYER : validation du mot cible ===")
    async with httpx.AsyncClient() as h:
        r = await h.post(f"{BASE}/api/rooms", json={"mode": "PLAYER", "level": "FACILE"})
        code = r.json()["code"]
    async with websockets.connect(WS + code) as wa, websockets.connect(WS + code) as wb:
        A, B = Client("A", wa), Client("B", wb)
        await A.send("join", pseudo="Hote"); await A.wait("joined"); await A.wait("state")
        await B.send("join", pseudo="Bob"); await B.wait("joined")
        await A.send("setTargetWord", word="Zorglub")
        e1 = await A.wait("error")
        ok(True, f"mot cible invalide refusé : {e1['message']!r}")
        await A.send("setTargetWord", word="horizon")
        ts = await A.wait("targetSet", "error")
        ok(ts["type"] == "targetSet", "mot cible valide accepté")
        lob = None
        for _ in range(5):
            lob = await B.wait("lobbyUpdate")
            if lob.get("hasTarget"):
                break
        ok(lob.get("hasTarget") is True, "les joueurs voient qu'un mot est défini (sans le mot)")
        ok("targetWord" not in lob, "le mot cible n'est pas diffusé au lobby")


async def main():
    global _failures
    await play_system()
    await play_player_mode()
    print("\n--- fuites détectées:", leaks if leaks else "aucune", "---")
    _failures += len(leaks)
    print(f"\nRésultat : {'ÉCHEC' if _failures else 'SUCCÈS'} ({_failures} échec(s))")
    sys.exit(1 if _failures else 0)


if __name__ == "__main__":
    asyncio.run(main())
