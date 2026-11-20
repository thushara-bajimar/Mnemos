"""Token counting.

Uses the real ``cl100k_base`` BPE tokenizer from ``tiktoken`` when it is
installed and its vocabulary file is available (cached under
``backend/.cache/tiktoken``). Otherwise falls back to a clearly-labelled
heuristic estimate (~4 characters per token, word-aware).

Every response that reports a token count also reports which method produced
it (``tokenizer_name`` / ``is_estimate``) so results are never misrepresented.
"""
from __future__ import annotations

import math
import os
import re
from functools import lru_cache
from pathlib import Path

_CACHE = Path(__file__).resolve().parents[2] / ".cache" / "tiktoken"
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(_CACHE))

_encoder = None
TOKENIZER_NAME = "estimate:chars/4"
IS_ESTIMATE = True

if os.environ.get("MNEMOS_FORCE_ESTIMATE_TOKENIZER", "").lower() != "true":
    try:  # pragma: no cover - depends on environment
        import tiktoken

        _encoder = tiktoken.get_encoding("cl100k_base")
        TOKENIZER_NAME = "tiktoken:cl100k_base"
        IS_ESTIMATE = False
    except Exception:  # network unavailable, package missing, etc.
        _encoder = None

_WORD = re.compile(r"\w+|[^\w\s]")


def _estimate(text: str) -> int:
    if not text:
        return 0
    words = _WORD.findall(text)
    # blend of char-based and word-based heuristics; slightly conservative
    return max(1, math.ceil(max(len(text) / 4.0, len(words) * 0.75)))


@lru_cache(maxsize=20000)
def count_tokens(text: str) -> int:
    if not text:
        return 0
    if _encoder is not None:
        return len(_encoder.encode(text, disallowed_special=()))
    return _estimate(text)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Cut ``text`` so that it fits in ``max_tokens`` tokens."""
    if max_tokens <= 0:
        return ""
    if count_tokens(text) <= max_tokens:
        return text
    if _encoder is not None:
        ids = _encoder.encode(text, disallowed_special=())[: max(0, max_tokens - 1)]
        return _encoder.decode(ids) + "…"
    return text[: max(0, max_tokens * 4 - 1)] + "…"


def info() -> dict:
    return {"tokenizer": TOKENIZER_NAME, "is_estimate": IS_ESTIMATE}
