# semantic-api — contexte de build : racine du dépôt
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1

COPY semantic-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && python -m spacy download fr_core_news_md

COPY semantic-api/app ./app
COPY semantic-api/prune_model.py .

# Pré-construit le cache du lexique (POS/lemmes) pour un démarrage rapide.
RUN python -c "from app.engine import load_engine; load_engine()"

ENV SEMANTIC_HOST=0.0.0.0 SEMANTIC_PORT=8100
EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
