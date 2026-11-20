"""Storage routing: decide which stores index a memory, and explain why."""
from __future__ import annotations

from .classifier import Classification

ROUTE_DESCRIPTIONS = {
    "structured": "Canonical SQLite row: exact subject/attribute/value lookups, filters, temporal validity, status.",
    "keyword": "SQLite FTS5 index (BM25): queryable keyword search with stemming.",
    "vector": "Embedding in the vector store: fuzzy/semantic similarity search and duplicate detection.",
    "graph": "Entities + typed edges: relationship and multi-hop queries.",
    "file": "Markdown file on disk: long procedures/documents kept human-readable and portable.",
}

LONG_CONTENT_CHARS = 400


def route(cls: Classification, content: str, temporary: bool) -> tuple[list[str], list[str]]:
    routes = ["structured", "keyword"]
    reasons = [
        "structured: every memory gets a canonical row (status, provenance, validity)",
        "keyword: every memory is full-text indexed for queryable search",
    ]
    if not temporary:
        routes.append("vector")
        reasons.append("vector: durable memory → indexed for semantic retrieval and dedup")
    else:
        reasons.append("vector skipped: temporary/working memory would pollute the long-term semantic index")
    if cls.relation or (cls.entities and not temporary):
        routes.append("graph")
        reasons.append(
            "graph: " + ("explicit relationship " + " → ".join(cls.relation) if cls.relation else f"entities {cls.entities[:4]}")
        )
    if cls.memory_type == "procedural" or len(content) > LONG_CONTENT_CHARS:
        routes.append("file")
        reasons.append(
            "file: procedural knowledge kept as a readable runbook"
            if cls.memory_type == "procedural"
            else f"file: long content ({len(content)} chars) stored as a document"
        )
    return routes, reasons
