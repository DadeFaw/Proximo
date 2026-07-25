#!/usr/bin/env bash
# Lance semantic-api (8100) puis game-api (8000) en local, sous Linux/macOS.
# Prérequis (une fois) :
#   python -m venv .venv && . .venv/bin/activate
#   pip install -r semantic-api/requirements.txt -r game-api/requirements.txt
#   python -m spacy download fr_core_news_md
set -euo pipefail
cd "$(dirname "$0")"
PY="${PY:-python}"
export PYTHONUTF8=1

echo "Démarrage du semantic-api (8100)…"
( cd semantic-api && "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8100 ) &
SEM_PID=$!
trap 'echo "Arrêt…"; kill $SEM_PID 2>/dev/null || true' EXIT

echo "Attente du moteur sémantique…"
for i in $(seq 1 120); do
  if curl -sf http://127.0.0.1:8100/health >/dev/null 2>&1; then echo "prêt."; break; fi
  sleep 2
done

echo "Démarrage du game-api (8000) — ouvrez http://127.0.0.1:8000"
export SEMANTIC_API_URL="http://127.0.0.1:8100"
cd game-api && "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
