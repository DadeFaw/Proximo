"""Tests des règles de scoring et d'égalité (brief §2.5). Exécutable directement :
    python game-api/tests/test_scoring.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.scoring import (apply_round_scores, compute_ranking, round_has_winner, score_round)


def approx(a, b, eps=1e-6):
    return abs(a - b) < eps


def test_single_finder():
    entries = [{"playerId": "a", "percentile": 100.0, "isTarget": True},
               {"playerId": "b", "percentile": 40.0, "isTarget": False}]
    pts = score_round(entries)
    assert pts["a"] == 1.0 and pts["b"] == 0.0
    assert round_has_winner(entries)


def test_multiple_finders_all_score():
    # Plusieurs joueurs trouvent -> 1 point chacun, aucune priorité au premier.
    entries = [{"playerId": "a", "percentile": 100.0, "isTarget": True},
               {"playerId": "b", "percentile": 100.0, "isTarget": True}]
    pts = score_round(entries)
    assert pts["a"] == 1.0 and pts["b"] == 1.0


def test_no_finder_best_gets_half():
    # 62 % -> 0,31 point (exemple du brief).
    entries = [{"playerId": "a", "percentile": 62.0, "isTarget": False},
               {"playerId": "b", "percentile": 30.0, "isTarget": False}]
    pts = score_round(entries)
    assert approx(pts["a"], 0.31), pts
    assert pts["b"] == 0.0


def test_tie_best_percentile_duplicated():
    # Deux joueurs à égalité au meilleur pourcentage -> chacun 50 %.
    entries = [{"playerId": "a", "percentile": 80.0, "isTarget": False},
               {"playerId": "b", "percentile": 80.0, "isTarget": False},
               {"playerId": "c", "percentile": 10.0, "isTarget": False}]
    pts = score_round(entries)
    assert approx(pts["a"], 0.40) and approx(pts["b"], 0.40)
    assert pts["c"] == 0.0


def test_same_word_both_score():
    # Deux joueurs proposent le même mot -> même percentile -> tous deux marquent.
    entries = [{"playerId": "a", "word": "chien", "percentile": 73.5, "isTarget": False},
               {"playerId": "b", "word": "chien", "percentile": 73.5, "isTarget": False}]
    pts = score_round(entries)
    assert approx(pts["a"], pts["b"]) and pts["a"] > 0


def test_empty_round():
    assert score_round([]) == {}


def test_ranking_ties_shared_rank():
    players = {
        "a": {"id": "a", "pseudo": "Al", "score": 2.0},
        "b": {"id": "b", "pseudo": "Bo", "score": 2.0},
        "c": {"id": "c", "pseudo": "Ci", "score": 0.5},
    }
    r = compute_ranking(players)
    assert r[0]["rank"] == 1 and r[1]["rank"] == 1  # égalité -> rang partagé
    assert r[2]["rank"] == 3
    assert r[0]["score"] == 2.0


def test_cumulative():
    players = {"a": {"id": "a", "pseudo": "Al", "score": 0.0}}
    apply_round_scores(players, {"a": 0.31})
    apply_round_scores(players, {"a": 1.0})
    assert approx(players["a"]["score"], 1.31)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests réussis")
    sys.exit(1 if failed else 0)
