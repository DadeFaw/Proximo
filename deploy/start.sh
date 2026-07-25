#!/usr/bin/env sh
# Démarre les deux services dans le conteneur : semantic-api en interne (:8100),
# puis game-api en façade sur le port fourni par l'hébergeur ($PORT).
set -e
PORT="${PORT:-8000}"

echo "[start] semantic-api interne sur :8100…"
( cd /app/semantic-api && exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8100 ) &

echo "[start] attente du moteur sémantique…"
python - <<'PY'
import time, urllib.request, sys
for _ in range(150):
    try:
        urllib.request.urlopen("http://127.0.0.1:8100/health", timeout=3)
        print("[start] semantic-api prêt"); sys.exit(0)
    except Exception:
        time.sleep(2)
print("[start] semantic-api n'a pas démarré"); sys.exit(1)
PY

echo "[start] game-api public sur :$PORT (sert la PWA + WebSocket)…"
cd /app/game-api
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
