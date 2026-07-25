# Image « tout-en-un » : semantic-api (interne) + game-api (public) dans un seul
# conteneur, pour un déploiement cloud en un seul service (Render, Railway, Fly…).
# Store en mémoire (une seule instance) — aucune dépendance Redis requise.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PIP_NO_CACHE_DIR=1

# Dépendances des deux services + modèle français (vecteurs + lemmatisation).
COPY semantic-api/requirements.txt /tmp/req-sem.txt
COPY game-api/requirements.txt /tmp/req-game.txt
RUN pip install -r /tmp/req-sem.txt -r /tmp/req-game.txt \
 && python -m spacy download fr_core_news_md

# Code + client PWA.
COPY semantic-api /app/semantic-api
COPY game-api /app/game-api
COPY client /app/client
COPY deploy/start.sh /app/start.sh

# Pré-construit le cache du lexique (POS/lemmes) => démarrage rapide au boot.
RUN chmod +x /app/start.sh \
 && cd /app/semantic-api && python -c "from app.engine import load_engine; load_engine()"

# game-api appelle semantic-api en local dans le conteneur ; il sert aussi la PWA.
ENV SEMANTIC_API_URL=http://127.0.0.1:8100 \
    CLIENT_DIR=/app/client \
    PORT=8000
EXPOSE 8000
CMD ["/app/start.sh"]
