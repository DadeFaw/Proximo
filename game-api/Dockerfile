# game-api — contexte de build : racine du dépôt
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1

COPY game-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt redis

COPY game-api/app ./app
COPY client /client

ENV CLIENT_DIR=/client SEMANTIC_API_URL=http://semantic-api:8100 \
    GAME_HOST=0.0.0.0 GAME_PORT=8000
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
