"""Scoring et classement — fonctions pures (brief §2.5, §2.6).

Règle des égalités : une égalité n'est JAMAIS départagée, elle est dupliquée.
"""
from __future__ import annotations


def score_round(entries: list[dict]) -> dict[str, float]:
    """Points attribués pour UNE manche, par joueur.

    entries : [{playerId, word, percentile (0..100), isTarget}]

    * Un ou plusieurs joueurs trouvent la cible  -> 1 point chacun (aucune priorité
      au premier arrivé : les manches sont simultanées et en aveugle).
    * Personne ne trouve -> le(s) joueur(s) au meilleur pourcentage reçoi(ven)t
      50 % de ce pourcentage (ex. 62 % -> 0,31 point), à égalité dupliquée.
    * Les autres joueurs marquent 0 sur la manche.
    """
    points: dict[str, float] = {e["playerId"]: 0.0 for e in entries}
    if not entries:
        return points

    finders = [e for e in entries if e.get("isTarget")]
    if finders:
        for e in finders:
            points[e["playerId"]] = 1.0
        return points

    best = max(e["percentile"] for e in entries)
    for e in entries:
        if e["percentile"] == best:
            points[e["playerId"]] = round(0.5 * best / 100.0, 4)
    return points


def apply_round_scores(players: dict[str, dict], round_points: dict[str, float]) -> None:
    """Ajoute au cumul de chaque joueur (mutation en place)."""
    for pid, pts in round_points.items():
        if pid in players:
            players[pid]["score"] = round(players[pid].get("score", 0.0) + pts, 4)


def round_has_winner(entries: list[dict]) -> bool:
    """Vrai si au moins un joueur a trouvé la cible dans la manche (fin immédiate)."""
    return any(e.get("isTarget") for e in entries)


def compute_ranking(players: dict[str, dict]) -> list[dict]:
    """Classement au cumul, décroissant. Égalités partagées (rangs 1,2,2,4)."""
    ordered = sorted(players.values(),
                     key=lambda p: (-p.get("score", 0.0), p.get("pseudo", "").lower()))
    ranking: list[dict] = []
    prev_score = None
    rank = 0
    for i, p in enumerate(ordered, start=1):
        score = round(p.get("score", 0.0), 4)
        if prev_score is None or score != prev_score:
            rank = i
            prev_score = score
        ranking.append({
            "playerId": p["id"],
            "pseudo": p["pseudo"],
            "score": score,
            "rank": rank,
            "connected": p.get("connected", False),
        })
    return ranking
