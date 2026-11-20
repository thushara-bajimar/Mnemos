"""SQLite connection management and schema.

A single SQLite file holds the structured store, the FTS5 keyword index,
the vector store (embeddings as BLOBs), the graph (entities/edges),
provenance, revisions, conflicts, deletion audit, agents, tasks and
handovers. The file-based store lives next to it on disk.

``PRAGMA secure_delete=ON`` makes SQLite overwrite deleted content with
zeros so forgotten memories do not linger in free pages of the database file.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    status TEXT NOT NULL,              -- active|superseded|expired|conflicted|quarantined|pending_confirmation
    subject TEXT,
    attribute TEXT,
    value TEXT,
    entities TEXT NOT NULL DEFAULT '[]',   -- JSON list
    tags TEXT NOT NULL DEFAULT '[]',       -- JSON list
    importance REAL NOT NULL DEFAULT 0.5,
    confidence REAL NOT NULL DEFAULT 0.5,
    source_trust REAL NOT NULL DEFAULT 0.5,
    source_type TEXT,
    reinforcement INTEGER NOT NULL DEFAULT 1,
    storage_routes TEXT NOT NULL DEFAULT '[]',
    task_id TEXT,
    agent_id TEXT,
    session_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    expires_at TEXT,
    last_accessed_at TEXT,
    access_count INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    file_path TEXT,
    decision_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_mem_status ON memories(status);
CREATE INDEX IF NOT EXISTS idx_mem_subject ON memories(subject, attribute);
CREATE INDEX IF NOT EXISTS idx_mem_type ON memories(memory_type);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    memory_id UNINDEXED, content, subject, tags, tokenize='porter unicode61'
);

CREATE TABLE IF NOT EXISTS vectors (
    memory_id TEXT PRIMARY KEY,
    dim INTEGER NOT NULL,
    embedding BLOB NOT NULL,
    model TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL DEFAULT 'thing',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    src_entity TEXT NOT NULL,
    relation TEXT NOT NULL,
    dst_entity TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_edges_mem ON edges(memory_id);
CREATE TABLE IF NOT EXISTS entity_mentions (
    entity_id TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    PRIMARY KEY (entity_id, memory_id)
);

CREATE TABLE IF NOT EXISTS provenance (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT,
    source_label TEXT,
    agent_id TEXT,
    session_id TEXT,
    extraction_method TEXT NOT NULL,
    confidence REAL NOT NULL,
    excerpt_hash TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prov_mem ON provenance(memory_id);
CREATE INDEX IF NOT EXISTS idx_prov_src ON provenance(source_id);

CREATE TABLE IF NOT EXISTS revisions (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    value TEXT,
    status TEXT NOT NULL,
    change_type TEXT NOT NULL,
    reason TEXT,
    actor TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rev_mem ON revisions(memory_id);

CREATE TABLE IF NOT EXISTS memory_links (
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    relation TEXT NOT NULL,          -- derived_from|supersedes|merged_into|conflicts_with
    created_at TEXT NOT NULL,
    PRIMARY KEY (from_id, to_id, relation)
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    memory_type TEXT,
    memory_id TEXT,
    preview TEXT,                    -- redacted, truncated; NULL for discarded input by default
    content_hash TEXT NOT NULL,
    scores TEXT NOT NULL,
    reasons TEXT NOT NULL,
    routes TEXT NOT NULL DEFAULT '[]',
    flags TEXT NOT NULL DEFAULT '[]',
    source_type TEXT,
    agent_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conflicts (
    id TEXT PRIMARY KEY,
    memory_a TEXT NOT NULL,
    memory_b TEXT NOT NULL,
    subject TEXT,
    attribute TEXT,
    kind TEXT NOT NULL,              -- value_conflict|poisoning|low_trust_override
    status TEXT NOT NULL,            -- open|resolved
    resolution TEXT,
    explanation TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS deletion_audit (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,             -- id|topic|entity|source|expiry
    deleted_count INTEGER NOT NULL,
    stores TEXT NOT NULL,
    verified INTEGER NOT NULL,
    term_hashes TEXT NOT NULL,       -- salted hashes only, never content
    requested_by TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    description TEXT,
    integration TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    goal TEXT,
    owner_agent TEXT,
    status TEXT NOT NULL,
    steps TEXT NOT NULL DEFAULT '[]',     -- JSON list of {text, done, by}
    constraints TEXT NOT NULL DEFAULT '[]',
    decisions TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS handovers (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    status TEXT NOT NULL,            -- pending|accepted|completed|rejected
    package TEXT NOT NULL,           -- JSON handover package
    checksum TEXT NOT NULL,
    token_budget INTEGER NOT NULL,
    package_tokens INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    accepted_at TEXT,
    completed_at TEXT,
    result TEXT
);

CREATE TABLE IF NOT EXISTS agent_log (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    task_id TEXT,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kv_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:
    """Thread-safe wrapper around a single SQLite connection."""

    def __init__(self, path: Path | str):
        self.path = str(path)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA secure_delete=ON")
        self.conn.executescript(SCHEMA)

    # -- helpers -------------------------------------------------------
    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, params)

    def executemany(self, sql: str, seq) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.executemany(sql, seq)

    def query(self, sql: str, params: tuple | list = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple | list = ()) -> dict | None:
        with self._lock:
            r = self.conn.execute(sql, params).fetchone()
            return dict(r) if r else None

    def transaction(self):
        return _Tx(self)

    def close(self) -> None:
        with self._lock:
            self.conn.close()


class _Tx:
    def __init__(self, db: Database):
        self.db = db

    def __enter__(self):
        self.db._lock.acquire()
        self.db.conn.execute("BEGIN")
        return self.db

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.db.conn.execute("COMMIT")
            else:
                self.db.conn.execute("ROLLBACK")
        finally:
            self.db._lock.release()
        return False
