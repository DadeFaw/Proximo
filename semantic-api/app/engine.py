"""Moteur sémantique : lexique élagué en RAM, calcul de percentiles, validation.

Deux sources de vecteurs, une seule logique :

  * ArtifactEngine   — matrice numpy + index produits hors-ligne par prune_model.py
                       (voie « frWac / cc.fr.300 → 80 000 lemmes » du brief §3.1).
  * SpacyVectorEngine — vecteurs 300d embarqués dans le modèle spaCy fr_core_news_md
                       (voie par défaut : un seul téléchargement, tourne immédiatement).

Dans les deux cas, spaCy fournit la lemmatisation et la détection des noms propres
(brief §3.3). Le lexique retenu (mots + POS + rangs de fréquence) est mis en cache
disque pour ne pas refaire le filtrage POS à chaque démarrage.
"""
from __future__ import annotations

import json
import logging
import random
import time
import unicodedata
from pathlib import Path

import numpy as np

from . import config

log = logging.getLogger("semantic.engine")

# Étiquettes POS (Universal POS) considérées comme « mots de contenu » (brief §3.1).
CONTENT_POS = {"NOUN", "VERB", "ADJ", "ADV"}
CACHE_VERSION = 5
_VOWELS = set("aeiouyàâäéèêëïîôöùûü")


def strip_accents(s: str) -> str:
    """Retourne une clé désaccentuée en minuscules (brief §3.3, seconde tentative)."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


class SemanticEngine:
    """Contient le lexique en RAM et expose normalisation / percentiles / tirage.

    Attributs clés :
      words   : list[str]              lemmes du lexique, dans l'ordre des lignes de `matrix`
      matrix  : np.ndarray (N, dim)    vecteurs L2-normalisés (float32)
      pos     : list[str]              POS dominante estimée par mot
      ranks   : np.ndarray (N,)        rang de fréquence (petit = fréquent)
    """

    def __init__(self, nlp, words, matrix, pos, ranks, source, model_name, is_lemma=None):
        self.nlp = nlp
        self.words: list[str] = list(words)
        self.matrix: np.ndarray = matrix.astype(np.float32, copy=False)
        self.pos: list[str] = list(pos)
        self.ranks: np.ndarray = np.asarray(ranks)
        # True si le mot est déjà sa forme canonique (lemme) — sert au tirage des cibles.
        self.is_lemma: list[bool] = (list(is_lemma) if is_lemma is not None
                                     else [True] * len(self.words))
        self.source = source
        self.model_name = model_name
        self.dim = int(self.matrix.shape[1])

        self.word2idx: dict[str, int] = {w: i for i, w in enumerate(self.words)}
        # Index désaccentué -> mot canonique (première occurrence conservée).
        self.deaccent2word: dict[str, str] = {}
        for w in self.words:
            self.deaccent2word.setdefault(strip_accents(w), w)

        # Pools de tirage par niveau (uniquement des noms communs), pré-calculés.
        self._level_pools = self._build_level_pools()
        # Petit cache LRU-léger des cartes de percentiles (utile pour /score en test).
        self._pct_cache: dict[str, dict[str, float]] = {}
        log.info(
            "Moteur '%s' prêt : %d mots, dim=%d (facile=%d normal=%d difficile=%d)",
            source, len(self.words), self.dim,
            *(len(self._level_pools[k]) for k in ("FACILE", "NORMAL", "DIFFICILE")),
        )

    # ------------------------------------------------------------------ tirage
    def _build_level_pools(self) -> dict[str, list[str]]:
        """Bande le lexique par fréquence et ne garde que des noms pour le tirage.

        La concrétude n'étant pas disponible sans ressource dédiée, on l'approxime
        par la fréquence : mots fréquents ≈ concrets/courants, mots rares ≈ abstraits.
        """
        # Cibles = noms communs en forme canonique (on écarte les pluriels/fléchis).
        nouns = [i for i, p in enumerate(self.pos) if p == "NOUN" and self.is_lemma[i]]
        if len(nouns) < 30:  # garde-fou si le POS-tagging a échoué
            nouns = [i for i, p in enumerate(self.pos) if p == "NOUN"] or list(range(len(self.words)))
        nouns.sort(key=lambda i: self.ranks[i])  # du plus fréquent au plus rare
        n = len(nouns)
        facile = nouns[: max(1, int(n * 0.25))]
        normal = nouns[int(n * 0.25): max(1, int(n * 0.60))]
        # On écarte les 5 % les plus rares (souvent du bruit / hapax).
        difficile = nouns[int(n * 0.60): max(1, int(n * 0.95))]
        return {
            "FACILE": [self.words[i] for i in facile],
            "NORMAL": [self.words[i] for i in normal] or [self.words[i] for i in facile],
            "DIFFICILE": [self.words[i] for i in difficile] or [self.words[i] for i in normal],
        }

    def random_word(self, level: str) -> str:
        pool = self._level_pools.get(level.upper(), self._level_pools["NORMAL"])
        return random.choice(pool)

    # ---------------------------------------------------------- normalisation
    def _lemmatize(self, text: str):
        """Retourne (lemme_min, pos, is_propn, surface_min) pour la 1re unité utile."""
        doc = self.nlp(text.strip())
        chosen = None
        for tok in doc:
            if tok.is_space or tok.is_punct:
                continue
            if chosen is None:
                chosen = tok
            if tok.is_alpha and not tok.is_stop:
                chosen = tok
                break
        if chosen is None:
            return None
        lemma = (chosen.lemma_ or chosen.text).lower().strip()
        surface = chosen.text.lower().strip()
        return lemma, chosen.pos_, chosen.pos_ == "PROPN", surface

    def _lookup(self, candidates: list[str]) -> str | None:
        """Cherche successivement chaque candidat, puis sa forme désaccentuée."""
        for c in candidates:
            if c in self.word2idx:
                return c
        for c in candidates:
            w = self.deaccent2word.get(strip_accents(c))
            if w is not None:
                return w
        return None

    def normalize(self, text: str) -> dict:
        """Pipeline du brief §3.3. Ne renvoie JAMAIS 0 pour un hors-vocabulaire :
        renvoie un rejet explicite, à charge de l'appelant de ne pas consommer la
        proposition."""
        if not text or not text.strip():
            return {"ok": False, "reason": "Proposition vide."}
        parsed = self._lemmatize(text)
        if parsed is None:
            return {"ok": False, "reason": "mot inconnu du dictionnaire"}
        lemma, pos, is_propn, surface = parsed
        if is_propn:
            return {"ok": False, "is_proper_noun": True,
                    "reason": "Les noms propres ne sont pas acceptés."}
        found = self._lookup([lemma, surface])
        if found is None:
            return {"ok": False, "reason": "mot inconnu du dictionnaire"}
        return {"ok": True, "word": found, "is_proper_noun": False}

    def validate_target(self, text: str) -> dict:
        """Validation d'un mot cible saisi en mode PLAYER (brief §2.1) :
        présent au vocabulaire, nom commun, non nom propre."""
        if not text or not text.strip():
            return {"ok": False, "reason": "Mot cible vide."}
        parsed = self._lemmatize(text)
        if parsed is None:
            return {"ok": False, "reason": "Mot cible introuvable dans le dictionnaire."}
        lemma, pos, is_propn, surface = parsed
        if is_propn:
            return {"ok": False, "reason": "Un nom propre ne peut pas être le mot cible."}
        found = self._lookup([lemma, surface])
        if found is None:
            return {"ok": False,
                    "reason": "Mot cible absent du vocabulaire d'embeddings."}
        # On exige un nom commun pour le mot cible.
        idx = self.word2idx[found]
        if self.pos[idx] not in ("NOUN", "ADJ"):
            return {"ok": False,
                    "reason": "Le mot cible doit être un nom commun."}
        return {"ok": True, "word": found}

    # -------------------------------------------------------------- percentiles
    def percentile_map(self, target: str) -> dict[str, float]:
        """Carte {mot: percentile in [0,100]} du `target` contre tout le lexique.

        Brief §3.2 : cosinus normalisé sur [0,1] puis rang percentile (distribution
        étalée). Calculé une seule fois par partie ; ~10 ms pour 20–80k × 300."""
        if target not in self.word2idx:
            raise KeyError(target)
        if target in self._pct_cache:
            return self._pct_cache[target]
        t0 = time.perf_counter()
        tvec = self.matrix[self.word2idx[target]]
        sims = self.matrix @ tvec            # cosinus dans [-1, 1] (matrice normalisée)
        # Rang percentile : part des mots de similarité <= la similarité courante.
        order = np.argsort(sims, kind="stable")
        ranks = np.empty(len(sims), dtype=np.float64)
        ranks[order] = np.arange(len(sims))
        pct = ranks / max(1, len(sims) - 1) * 100.0   # cible (sim max) -> 100.0
        result = {w: round(float(pct[i]), 2) for i, w in enumerate(self.words)}
        self._pct_cache[target] = result
        if len(self._pct_cache) > 64:        # borne mémoire
            self._pct_cache.pop(next(iter(self._pct_cache)))
        log.debug("percentile_map(%s) en %.1f ms", target, (time.perf_counter() - t0) * 1e3)
        return result

    def score(self, target: str, word: str) -> dict:
        """Normalise `word` puis renvoie son percentile via la carte du `target`."""
        norm = self.normalize(word)
        if not norm["ok"]:
            return norm
        w = norm["word"]
        pmap = self.percentile_map(target)
        return {"ok": True, "word": w,
                "percentile": pmap.get(w, 0.0),
                "is_target": w == target}


# --------------------------------------------------------------------- chargement
def _valid_token_string(s: str) -> bool:
    if not (s.isalpha() and s == s.lower() and len(s) >= config.MIN_WORD_LEN):
        return False
    # Filtre anti-bruit de corpus (tokens type « somour », « dordinateur ») :
    if not any(c in _VOWELS for c in s):        # aucun voyelle -> rejet
        return False
    for i in range(len(s) - 2):                 # 3 lettres identiques consécutives
        if s[i] == s[i + 1] == s[i + 2]:
            return False
    return True


def _tag_words(nlp, words: list[str]) -> tuple[list[str], list[bool]]:
    """Estime POS + forme canonique de chaque mot isolé (une passe, mise en cache).

    Retourne (pos, is_lemma) où is_lemma[i] est True si words[i] est déjà son lemme
    (utile pour ne tirer que des cibles au singulier)."""
    pos: list[str] = []
    is_lemma: list[bool] = []
    for w, doc in zip(words, nlp.pipe(words, batch_size=1000)):
        if len(doc):
            pos.append(doc[0].pos_)
            is_lemma.append((doc[0].lemma_ or w).lower() == w)
        else:
            pos.append("X")
            is_lemma.append(True)
    return pos, is_lemma


def _cache_path(model_name: str, source: str) -> Path:
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return config.CACHE_DIR / f"lexicon_{source}_{model_name}_v{CACHE_VERSION}.npz"


def _load_from_cache(path: Path):
    if not path.exists():
        return None
    try:
        data = np.load(path, allow_pickle=True)
        return (list(data["words"]), data["matrix"], list(data["pos"]),
                data["ranks"], list(data["is_lemma"]))
    except Exception as e:  # cache corrompu -> on rebâtit
        log.warning("Cache lexique illisible (%s), reconstruction.", e)
        return None


def _save_cache(path: Path, words, matrix, pos, ranks, is_lemma):
    np.savez_compressed(path, words=np.array(words, dtype=object),
                        matrix=matrix.astype(np.float32),
                        pos=np.array(pos, dtype=object), ranks=np.asarray(ranks),
                        is_lemma=np.array(is_lemma, dtype=bool))


def _normalize_rows(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (mat / norms).astype(np.float32)


def _load_spacy(model_name: str):
    import spacy
    try:
        # parser/ner inutiles ici (on ne fait que lemmatisation + POS) : gain RAM/CPU,
        # utile pour tenir dans les petits plans d'hébergement (~512 Mo).
        return spacy.load(model_name, exclude=["parser", "ner"])
    except OSError as e:
        raise RuntimeError(
            f"Modèle spaCy '{model_name}' introuvable. Installez-le :\n"
            f"    python -m spacy download {model_name}"
        ) from e


def build_spacy_vector_engine(model_name: str) -> SemanticEngine:
    nlp = _load_spacy(model_name)
    if nlp.vocab.vectors.shape[0] == 0:
        raise RuntimeError(
            f"Le modèle '{model_name}' ne contient pas de vecteurs de mots. "
            "Utilisez fr_core_news_md ou fr_core_news_lg, ou un artefact élagué."
        )
    cache = _cache_path(model_name, "spacy")
    cached = _load_from_cache(cache)
    if cached:
        words, matrix, pos, ranks, is_lemma = cached
        return SemanticEngine(nlp, words, matrix, pos, ranks, "spacy", model_name, is_lemma)

    log.info("Construction du lexique depuis les vecteurs spaCy (une fois)…")
    vectors = nlp.vocab.vectors
    # Les modèles spaCy *_md élaguent leurs vecteurs (prune_vectors) : des milliers de
    # clés sont remappées sur un petit nombre de lignes réelles, créant des vecteurs
    # dupliqués. On ne conserve donc qu'UN mot par ligne unique : le plus fréquent.
    row_best: dict[int, tuple[int, str]] = {}
    for key, row in vectors.key2row.items():
        s = nlp.vocab.strings[key]
        if not _valid_token_string(s):
            continue
        lex = nlp.vocab[s]
        if lex.is_stop:
            continue
        rank = lex.rank if lex.rank >= 0 else np.iinfo(np.int64).max
        cur = row_best.get(row)
        if cur is None or rank < cur[0]:
            row_best[row] = (rank, s)

    items = sorted(row_best.items(), key=lambda kv: kv[1][0])   # tri par fréquence
    if len(items) > config.MAX_LEXICON:
        items = items[: config.MAX_LEXICON]
    rows = [row for row, _ in items]
    words = [w for _, (_, w) in items]
    ranks = np.array([r for _, (r, _) in items], dtype=np.int64)
    matrix = _normalize_rows(np.asarray(vectors.data)[rows])
    pos, is_lemma = _tag_words(nlp, words)
    _save_cache(cache, words, matrix, pos, ranks, is_lemma)
    return SemanticEngine(nlp, words, matrix, pos, ranks, "spacy", model_name, is_lemma)


def build_artifact_engine(artifact_dir: Path, model_name: str) -> SemanticEngine:
    """Charge un artefact élagué : words.json + vectors.npy (+ ranks.npy optionnel)."""
    words = json.loads((artifact_dir / "words.json").read_text(encoding="utf-8"))
    matrix = np.load(artifact_dir / "vectors.npy")
    matrix = _normalize_rows(matrix)
    ranks_file = artifact_dir / "ranks.npy"
    ranks = np.load(ranks_file) if ranks_file.exists() else np.arange(len(words))
    nlp = _load_spacy(model_name)  # uniquement pour la lemmatisation / POS

    cache = _cache_path(model_name, "artifact")
    cached = _load_from_cache(cache)
    if cached and len(cached[0]) == len(words):
        _, _, pos, _, is_lemma = cached
    else:
        log.info("Tagging POS/lemmes de l'artefact (une fois)…")
        pos, is_lemma = _tag_words(nlp, words)
        _save_cache(cache, words, matrix, pos, ranks, is_lemma)
    return SemanticEngine(nlp, words, matrix, pos, ranks, "artifact", model_name, is_lemma)


def load_engine() -> SemanticEngine:
    """Factory : artefact élagué s'il existe, sinon vecteurs spaCy."""
    artifact_dir = Path(config.ARTIFACT_DIR)
    if (artifact_dir / "vectors.npy").exists() and (artifact_dir / "words.json").exists():
        log.info("Artefact élagué détecté dans %s", artifact_dir)
        return build_artifact_engine(artifact_dir, config.SPACY_MODEL)
    log.info("Aucun artefact : utilisation des vecteurs spaCy '%s'.", config.SPACY_MODEL)
    return build_spacy_vector_engine(config.SPACY_MODEL)
