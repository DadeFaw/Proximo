"""Test de ressenti sémantique — à lancer avant tout le reste (brief §9.2)."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine import load_engine

t0 = time.perf_counter()
eng = load_engine()
print(f"Chargé en {time.perf_counter()-t0:.1f}s | vocab={len(eng.words)} dim={eng.dim} source={eng.source}")

for target in ["chat", "voiture", "amour", "montagne", "ordinateur"]:
    if target not in eng.word2idx:
        print(f"\n[{target}] absent du lexique"); continue
    pmap = eng.percentile_map(target)
    top = sorted(pmap.items(), key=lambda kv: kv[1], reverse=True)[:8]
    print(f"\n[cible={target}] top voisins :")
    for w, p in top:
        print(f"   {p:6.2f}%  {w}")

print("\n-- distribution des percentiles pour quelques mots face à 'chat' --")
pmap = eng.percentile_map("chat")
for w in ["chien", "félin", "animal", "souris", "table", "démocratie", "avion"]:
    print(f"   {w:12s} -> {pmap.get(w, 'absent')}")

print("\n-- normalisation --")
for t in ["Chats", "manger", "PARIS", "qwxz", "les voitures", "félins"]:
    print(f"   {t!r:16s} -> {eng.normalize(t)}")

print("\n-- tirage par niveau --")
for lvl in ["FACILE", "NORMAL", "DIFFICILE"]:
    print(f"   {lvl:10s} -> {[eng.random_word(lvl) for _ in range(6)]}")
