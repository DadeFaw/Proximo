#!/usr/bin/env python
"""Élagage hors-ligne d'un modèle d'embeddings français (brief §3.1, §9.1).

À exécuter UNE fois. Prend un modèle word2vec/FastText français entraîné sur
corpus français (type frWac, ou cc.fr.300 de fastText), le réduit aux ~80 000
lemmes de contenu les plus fréquents (noms, verbes, adjectifs, adverbes ; hors
noms propres), et produit un artefact binaire chargé directement au démarrage
du semantic-api :

    artifact/
      vectors.npy   float32 (N, dim)   matrice des vecteurs
      words.json    list[str]          lemmes, alignés sur les lignes de la matrice
      ranks.npy     int64 (N,)         rang de fréquence (petit = fréquent)
      meta.json     infos de production

On passe ainsi de plusieurs Go à ~100 Mo. Le filtrage POS n'est PAS refait au boot.

Exemples
--------
  # fastText cc.fr.300 (binaire Facebook)
  python prune_model.py --model cc.fr.300.bin --format fasttext --out artifact

  # frWac word2vec binaire
  python prune_model.py --model frWac_200_cbow.bin --format word2vec-bin --out artifact

Dépendances : pip install gensim spacy ; python -m spacy download fr_core_news_md
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

import numpy as np

CONTENT_POS = {"NOUN", "VERB", "ADJ", "ADV"}


def strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def load_keyed_vectors(model_path: str, fmt: str):
    """Charge un modèle et renvoie un gensim KeyedVectors (vocab ordonné par fréquence)."""
    from gensim.models import KeyedVectors
    if fmt == "fasttext":
        from gensim.models.fasttext import load_facebook_vectors
        return load_facebook_vectors(model_path)
    if fmt == "word2vec-bin":
        return KeyedVectors.load_word2vec_format(model_path, binary=True)
    if fmt == "word2vec-txt":
        return KeyedVectors.load_word2vec_format(model_path, binary=False)
    if fmt == "gensim":
        return KeyedVectors.load(model_path)
    raise ValueError(f"Format inconnu : {fmt}")


def is_candidate(word: str, min_len: int) -> bool:
    return word.isalpha() and word == word.lower() and len(word) >= min_len


def main() -> int:
    ap = argparse.ArgumentParser(description="Élagage d'un modèle d'embeddings FR.")
    ap.add_argument("--model", required=True, help="Chemin du modèle d'embeddings")
    ap.add_argument("--format", default="word2vec-bin",
                    choices=["fasttext", "word2vec-bin", "word2vec-txt", "gensim"])
    ap.add_argument("--out", default="artifact", help="Dossier de sortie de l'artefact")
    ap.add_argument("--limit", type=int, default=80000, help="Nb max de lemmes retenus")
    ap.add_argument("--min-len", type=int, default=3)
    ap.add_argument("--spacy", default="fr_core_news_md", help="Modèle spaCy (POS/lemmes)")
    ap.add_argument("--lemmas-only", action="store_true", default=True,
                    help="Ne garder que les mots déjà en forme canonique (lemme)")
    ap.add_argument("--keep-inflected", dest="lemmas_only", action="store_false")
    ap.add_argument("--scan", type=int, default=400000,
                    help="Nb de mots (par fréquence) examinés avant filtrage")
    args = ap.parse_args()

    print(f"[1/4] Chargement du modèle {args.model} ({args.format})…", flush=True)
    kv = load_keyed_vectors(args.model, args.format)
    vocab = list(kv.index_to_key)[: args.scan]  # déjà trié par fréquence décroissante
    print(f"      {len(kv.index_to_key)} vecteurs, {len(vocab)} examinés, dim={kv.vector_size}")

    print(f"[2/4] Pré-filtrage lexical…", flush=True)
    candidates = [w for w in vocab if is_candidate(w, args.min_len)]
    print(f"      {len(candidates)} candidats alpha/minuscule/len>={args.min_len}")

    print(f"[3/4] Filtrage POS via spaCy '{args.spacy}' (noms/verbes/adj/adv, hors propres)…",
          flush=True)
    import spacy
    nlp = spacy.load(args.spacy, disable=["parser", "ner"])
    kept_words: list[str] = []
    kept_rank: list[int] = []
    seen_deaccent: set[str] = set()
    for rank, (w, doc) in enumerate(zip(candidates, nlp.pipe(candidates, batch_size=2000))):
        if not len(doc):
            continue
        tok = doc[0]
        if tok.pos_ not in CONTENT_POS or tok.pos_ == "PROPN" or tok.is_stop:
            continue
        if args.lemmas_only and (tok.lemma_ or w).lower() != w:
            continue
        key = strip_accents(w)
        if key in seen_deaccent:      # évite doublons désaccentués
            continue
        seen_deaccent.add(key)
        kept_words.append(w)
        kept_rank.append(rank)
        if len(kept_words) >= args.limit:
            break
    print(f"      {len(kept_words)} lemmes retenus")

    print(f"[4/4] Écriture de l'artefact dans {args.out}…", flush=True)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    matrix = np.vstack([kv[w] for w in kept_words]).astype(np.float32)
    np.save(out / "vectors.npy", matrix)
    (out / "words.json").write_text(json.dumps(kept_words, ensure_ascii=False), encoding="utf-8")
    np.save(out / "ranks.npy", np.array(kept_rank, dtype=np.int64))
    (out / "meta.json").write_text(json.dumps({
        "source_model": args.model, "format": args.format,
        "count": len(kept_words), "dim": int(kv.vector_size),
        "spacy_model": args.spacy, "lemmas_only": args.lemmas_only,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    size_mb = matrix.nbytes / 1e6
    print(f"      OK — {len(kept_words)} mots × {kv.vector_size}d, matrice ≈ {size_mb:.0f} Mo")
    print("Terminé. Lancez le semantic-api avec ARTIFACT_DIR pointant sur ce dossier.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
