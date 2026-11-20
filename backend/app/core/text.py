"""Small text-processing helpers shared by the classifier, embedder and retriever."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

STOPWORDS = set(
    """a an the and or but if then else of to in on at by for with about as is are was were be been being
    it its this that these those i me my we our you your he she they them their his her what which who whom
    whose when where why how do does did done have has had having not no yes so too very can could should would
    will shall may might must just also than into from up down out over under again further once there here
    all any both each few more most other some such only own same s t don now please tell know remember""".split()
)

# Lightweight concept groups. Words in a group are mapped to a shared concept
# feature by the embedder, giving limited synonym-awareness without a neural model.
CONCEPTS: dict[str, list[str]] = {
    "database": ["database", "db", "postgres", "postgresql", "mysql", "sqlite", "sql", "datastore", "mongodb"],
    "deadline": ["deadline", "due", "duedate", "cutoff", "deliver", "delivery", "launch", "release"],
    "prefer": ["prefer", "preference", "like", "likes", "favorite", "favourite", "love", "enjoy", "want"],
    "meeting": ["meeting", "meet", "call", "sync", "standup", "discussion", "met"],
    "deploy": ["deploy", "deployment", "ship", "release", "rollout", "publish"],
    "language": ["language", "python", "typescript", "javascript", "java", "rust", "go", "golang"],
    "location": ["location", "city", "live", "lives", "based", "moved", "relocated", "office", "home"],
    "manager": ["manager", "boss", "lead", "reports", "supervisor", "head"],
    "budget": ["budget", "cost", "price", "spend", "money", "dollars", "usd", "funding"],
    "bug": ["bug", "issue", "error", "defect", "crash", "failure", "incident"],
    "test": ["test", "tests", "testing", "pytest", "qa", "verify"],
    "food": ["food", "diet", "vegetarian", "vegan", "allergy", "allergic", "eat", "meal"],
    "schedule": ["schedule", "time", "morning", "evening", "monday", "tuesday", "wednesday", "thursday",
                  "friday", "weekend", "timezone"],
    "frontend": ["frontend", "ui", "react", "interface", "dashboard", "css", "tailwind"],
    "backend": ["backend", "api", "server", "fastapi", "endpoint", "service"],
    "security": ["security", "auth", "authentication", "password", "token", "encryption", "secret"],
    "customer": ["customer", "client", "user", "account", "buyer"],
    "color": ["color", "colour", "theme", "dark", "light"],
}
WORD_TO_CONCEPT = {w: c for c, ws in CONCEPTS.items() for w in ws}

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_\-\.]*[a-z0-9]|[a-z0-9]")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def stem(word: str) -> str:
    """Very small suffix stripper (Porter-lite)."""
    for suf in ("ingly", "edly", "ing", "ies", "ied", "ed", "es", "ly", "s"):
        if len(word) > len(suf) + 2 and word.endswith(suf):
            if suf in ("ies", "ied"):
                return word[: -len(suf)] + "y"
            return word[: -len(suf)]
    return word


def content_terms(text: str) -> list[str]:
    return [stem(t) for t in tokenize(text) if t not in STOPWORDS and len(t) > 1]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def new_id(prefix: str) -> str:
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:12]}"
