"""Test d'intégration bout-en-bout via WebSocket (brief §7).

Prérequis : semantic-api (8100) et game-api (8000) démarrés.
Joue une partie SYSTEM/DIFFICILE (3 manches) à 2 joueurs et vérifie :
  - le mot cible n'apparaît jamais avant gameFinished ;
  - aucune proposition adverse n'est visible avant la révélation (aveugle) ;
  - un mot hors-vocabulaire est rejeté sans consommer le tour ;
  - les deux joueurs sont bien présents dans chaque révélation, avec scores ;
  - le niveau DIFFICILE applique 3 manches.
Puis une partie PLAYER : mot cible invalide refusé, mot valide accepté.
"""
import asyncio
import json
import sys

import httpx
import websockets

BASE = "http://127.0.0.1:8000"
WS = "ws://127.0.0.1:8000/ws/"
leaks: list = []


def check_leak(cid, m):
    if m.get("type") != "gameFinished":
        if m.get("targetWord"):
            leaks.append(("targetWord_avant_fin", cid, m.get("type")))
        if m.get("type") == "state" and (m.get("state") or {}).get("targetWord"):
            leaks.append(("state_target_leak", cid, m))


class Client:
    def __init__(self, cid, ws):
        self.cid = cid
        self.ws = ws
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
                # une erreur inattendue interrompt le test
                raise AssertionError(f"[{self.cid}] erreur serveur : {m['message']}")


def ok(cond, label):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        globals()["_failures"] += 1


_failures = 0


async def play_system():
    global _failures
    print("\n=== Partie SYSTEM / DIFFICILE (3 manches, 2 joueurs) ===")
    async with httpx.AsyncClient() as h:
        r = await h.post(f"{BASE}/api/rooms", json={"mode": "SYSTEM", "level": "DIFFICILE"})
        code = r.json()["code"]
    print("  salon:", code)

    async with websockets.connect(WS + code) as wa, websockets.connect(WS + code) as wb:
        A, B = Client("A", wa), Client("B", wb)
        await A.send("join", pseudo="Alice")
        ja = await A.wait("joined"); pidA = ja["playerId"]
        ok(ja["isHost"], "A est hôte")
        await A.wait("state")
        await B.send("join", pseudo="Bob")
        jb = await B.wait("joined"); pidB = jb["playerId"]
        ok(not jb["isHost"], "B n'est pas hôte")

        await A.send("startGame")
        gsa = await A.wait("gameStarted")
        await B.wait("gameStarted")
        ok(gsa["totalRounds"] == 3, "DIFFICILE => 3 manches")

        guesses = [("chat", "maison"), ("route", "arbre"), ("musique", "table")]
        rounds_seen = 0
        finished = None
        for i in range(3):
            ra = await A.wait("roundStarted")
            await B.wait("roundStarted")
            rounds_seen += 1
            ok("deadline" in ra, f"manche {ra['round']} a une deadline")

            if i == 0:
                # mot hors-vocabulaire -> rejet sans consommer le tour
                await A.send("submitGuess", word="wxcvbqztn")
                err = await A.wait("error")
                ok("inconnu" in err["message"].lower() or "propre" in err["message"].lower(),
                   "mot invalide rejeté avec message explicite")

            ga, gb = guesses[i]
            await A.send("submitGuess", word=ga)
            acc = await A.wait("guessAccepted")
            ok("percentile" not in acc, "guessAccepted ne divulgue pas le score (aveugle)")
            # B ne doit PAS avoir reçu la révélation de CETTE manche avant d'avoir proposé,
            # ni le mot de A d'aucune manière.
            b_leaked = any(m.get("type") == "roundRevealed" and m.get("round") == ra["round"]
                           for m in B.msgs)
            b_saw_word = any(ga in json.dumps(m, ensure_ascii=False)
                             for m in B.msgs if m.get("type") != "roundRevealed")
            ok(not b_leaked and not b_saw_word, "B n'a rien reçu de la manche avant révélation (aveugle)")
            await B.send("submitGuess", word=gb)
            await B.wait("guessAccepted")

            rev = await A.wait("roundRevealed")
            await B.wait("roundRevealed")
            words = {e["word"] for e in rev["entries"]}
            ok(len(rev["entries"]) == 2, f"manche {rev['round']} : 2 propositions révélées")
            ok(all("percentile" in e for e in rev["entries"]), "scores présents à la révélation")

            if rev["hasWinner"] or rev["round"] == 3:
                finished = await A.wait("gameFinished")
                await B.wait("gameFinished")
                break

        ok(finished is not None, "partie terminée")
        ok(finished.get("targetWord"), f"mot cible révélé à la fin : {finished.get('targetWord')!r}")
        ok(len(finished["ranking"]) == 2, "classement final à 2 joueurs")
        print("  cible:", finished["targetWord"], "| classement:",
              [(p["pseudo"], p["score"]) for p in finished["ranking"]])


async def play_player_mode():
    print("\n=== Partie PLAYER : validation du mot cible ===")
    async with httpx.AsyncClient() as h:
        r = await h.post(f"{BASE}/api/rooms", json={"mode": "PLAYER", "level": "FACILE"})
        code = r.json()["code"]
    async with websockets.connect(WS + code) as wa, websockets.connect(WS + code) as wb:
        A, B = Client("A", wa), Client("B", wb)
        await A.send("join", pseudo="Hote"); await A.wait("joined"); await A.wait("state")
        await B.send("join", pseudo="Bob"); await B.wait("joined")
        # mot cible invalide (nom propre)
        await A.send("setTargetWord", word="Zorglub")
        e1 = await A.wait("error")
        ok(True, f"mot cible invalide refusé : {e1['message']!r}")
        # mot cible valide
        await A.send("setTargetWord", word="horizon")
        ts = await A.wait("targetSet", "error")
        ok(ts["type"] == "targetSet", "mot cible valide accepté")
        # On attend le lobbyUpdate consécutif au setTargetWord (hasTarget devient vrai).
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
    if leaks:
        _failures += len(leaks)
    print(f"\nRésultat : {'ÉCHEC' if _failures else 'SUCCÈS'} ({_failures} échec(s))")
    sys.exit(1 if _failures else 0)


if __name__ == "__main__":
    asyncio.run(main())
