"""Local, dependency-free text embeddings.

Mnemos must run without paid services or large model downloads, so the default
embedder is a *feature-hashing* model: each text is mapped to a fixed-size
vector from

* stemmed content words (weight 1.0),
* word bigrams (0.6) — captures short phrases,
* character 4-grams inside words (0.25) — robust to typos/morphology,
* shared concept features (0.8) from ``text.CONCEPTS`` — limited synonymy.

Vectors are L2-normalised so cosine similarity is a dot product. This is a
*lexical-semantic* approximation, **not** a neural sentence encoder; the docs
state this limitation explicitly. If ``sentence-transformers`` is installed and
``MNEMOS_EMBEDDER=sentence-transformers`` is set, a neural model is used instead.
"""
from __future__ import annotations

import hashlib
import os

import numpy as np

from .text import WORD_TO_CONCEPT, content_terms, stem, tokenize


def _h(feature: str, dim: int) -> tuple[int, float]:
    d = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    v = int.from_bytes(d, "little")
    return v % dim, (1.0 if (v >> 63) & 1 else -1.0)


class HashingEmbedder:
    name = "hashing-ngram-v1"

    def __init__(self, dim: int = 512):
        self.dim = dim

    def embed(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        terms = content_terms(text)
        raw = tokenize(text)
        for t in terms:
            i, s = _h("w:" + t, self.dim)
            vec[i] += 1.0 * s
            for g in range(max(0, len(t) - 3)):
                i, s = _h("c:" + t[g : g + 4], self.dim)
                vec[i] += 0.25 * s
        for a, b in zip(terms, terms[1:]):
            i, s = _h(f"b:{a}_{b}", self.dim)
            vec[i] += 0.6 * s
        for t in raw:
            c = WORD_TO_CONCEPT.get(t) or WORD_TO_CONCEPT.get(stem(t))
            if c:
                i, s = _h("k:" + c, self.dim)
                vec[i] += 0.8 * s
        n = float(np.linalg.norm(vec))
        return vec / n if n > 0 else vec


class SentenceTransformerEmbedder:  # pragma: no cover - optional
    def __init__(self, model: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model)
        self.dim = self.model.get_sentence_embedding_dimension()
        self.name = f"st:{model}"

    def embed(self, text: str) -> np.ndarray:
        v = self.model.encode([text], normalize_embeddings=True)[0]
        return np.asarray(v, dtype=np.float32)


def make_embedder(dim: int = 512):
    if os.environ.get("MNEMOS_EMBEDDER") == "sentence-transformers":  # pragma: no cover
        try:
            return SentenceTransformerEmbedder()
        except Exception:
            pass
    return HashingEmbedder(dim)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))
