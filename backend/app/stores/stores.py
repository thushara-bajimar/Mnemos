"""The five storage strategies used by Mnemos.

Every memory has one canonical row in the **structured store** (``memories``
table). The router then decides which *additional* stores index it:

=============  ==========================================  ==================================
Store          Implementation                              Best for
=============  ==========================================  ==================================
structured     SQLite ``memories`` table (subject/attr)    exact facts, filters, temporal validity
keyword        SQLite FTS5 (BM25, porter stemming)         queryable full-text keyword search
vector         embeddings as BLOBs + in-memory numpy index semantic / fuzzy similarity
graph          ``entities``/``edges``/``entity_mentions``  relationships, multi-hop lookups
file           one Markdown file per memory on disk        long procedures/documents, human-readable
=============  ==========================================  ==================================

Each store implements ``add``, ``remove`` and ``contains`` so deletion can be
verified store-by-store.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

import numpy as np

from ..core.embeddings import HashingEmbedder
from ..core.text import new_id, now_iso
from ..db import Database


# --------------------------------------------------------------------------
class StructuredStore:
    name = "structured"

    def __init__(self, db: Database):
        self.db = db

    def insert(self, rec: dict) -> None:
        cols = list(rec.keys())
        self.db.execute(
            f"INSERT INTO memories ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [json.dumps(v) if isinstance(v, (list, dict)) else v for v in rec.values()],
        )

    def update(self, memory_id: str, **fields) -> None:
        if not fields:
            return
        fields.setdefault("updated_at", now_iso())
        sets = ",".join(f"{k}=?" for k in fields)
        vals = [json.dumps(v) if isinstance(v, (list, dict)) else v for v in fields.values()]
        self.db.execute(f"UPDATE memories SET {sets} WHERE id=?", vals + [memory_id])

    def get(self, memory_id: str) -> dict | None:
        r = self.db.one("SELECT * FROM memories WHERE id=?", (memory_id,))
        return _decode(r) if r else None

    def find_fact(self, subject: str, attribute: str, statuses=("active", "conflicted", "pending_confirmation")) -> list[dict]:
        q = f"SELECT * FROM memories WHERE subject=? AND attribute=? AND status IN ({','.join('?' * len(statuses))}) ORDER BY created_at DESC"
        return [_decode(r) for r in self.db.query(q, (subject, attribute, *statuses))]

    def remove(self, memory_id: str) -> None:
        self.db.execute("DELETE FROM memories WHERE id=?", (memory_id,))

    def contains(self, memory_id: str) -> bool:
        return self.db.one("SELECT 1 AS x FROM memories WHERE id=?", (memory_id,)) is not None

    def search(self, terms: list[str], limit: int = 50) -> list[tuple[str, float]]:
        """Structured match on subject/attribute/value/entities columns."""
        if not terms:
            return []
        out: dict[str, float] = {}
        for t in terms[:8]:
            like = f"%{t}%"
            for r in self.db.query(
                "SELECT id, subject, attribute, value, entities FROM memories WHERE status IN ('active','conflicted') AND "
                "(subject LIKE ? OR attribute LIKE ? OR value LIKE ? OR entities LIKE ?) LIMIT ?",
                (like, like, like, like, limit),
            ):
                score = 0.0
                for col, w in (("subject", 1.0), ("attribute", 0.8), ("value", 0.6), ("entities", 0.5)):
                    if r[col] and t in str(r[col]).lower():
                        score += w
                out[r["id"]] = out.get(r["id"], 0.0) + score
        return sorted(out.items(), key=lambda x: -x[1])[:limit]


def _decode(r: dict) -> dict:
    for k in ("entities", "tags", "storage_routes"):
        if k in r and isinstance(r[k], str):
            try:
                r[k] = json.loads(r[k])
            except json.JSONDecodeError:
                r[k] = []
    return r


# --------------------------------------------------------------------------
_FTS_SAFE = re.compile(r"[^\w\s]")


class KeywordStore:
    """SQLite FTS5 full-text index with BM25 ranking (the *queryable* store)."""

    name = "keyword"

    def __init__(self, db: Database):
        self.db = db

    def add(self, memory_id: str, content: str, subject: str | None, tags: list[str]) -> None:
        self.remove(memory_id)
        self.db.execute(
            "INSERT INTO memories_fts (memory_id, content, subject, tags) VALUES (?,?,?,?)",
            (memory_id, content, subject or "", " ".join(tags)),
        )

    def remove(self, memory_id: str) -> None:
        self.db.execute("DELETE FROM memories_fts WHERE memory_id=?", (memory_id,))

    def contains(self, memory_id: str) -> bool:
        return self.db.one("SELECT 1 AS x FROM memories_fts WHERE memory_id=?", (memory_id,)) is not None

    def contains_text(self, text: str) -> bool:
        return self.db.one("SELECT 1 AS x FROM memories_fts WHERE content=?", (text,)) is not None

    def search(self, query: str, limit: int = 50) -> list[tuple[str, float]]:
        from ..core.text import STOPWORDS

        words = [w for w in _FTS_SAFE.sub(" ", query).split() if len(w) > 1 and w.lower() not in STOPWORDS]
        if not words:
            return []
        expr = " OR ".join(f'"{w}"' for w in words[:16])
        try:
            rows = self.db.query(
                "SELECT memory_id, bm25(memories_fts) AS s FROM memories_fts WHERE memories_fts MATCH ? ORDER BY s LIMIT ?",
                (expr, limit),
            )
        except Exception:
            return []
        # bm25() returns lower-is-better negative numbers; flip sign.
        return [(r["memory_id"], -float(r["s"])) for r in rows]


# --------------------------------------------------------------------------
class VectorStore:
    """Embeddings persisted in SQLite, searched with an in-memory numpy matrix."""

    name = "vector"

    def __init__(self, db: Database, embedder: HashingEmbedder):
        self.db = db
        self.embedder = embedder
        self._lock = threading.RLock()
        self._ids: list[str] = []
        self._matrix = np.zeros((0, embedder.dim), dtype=np.float32)
        self._load()

    def _load(self) -> None:
        rows = self.db.query("SELECT memory_id, embedding, dim FROM vectors")
        with self._lock:
            self._ids = [r["memory_id"] for r in rows if r["dim"] == self.embedder.dim]
            vecs = [np.frombuffer(r["embedding"], dtype=np.float32) for r in rows if r["dim"] == self.embedder.dim]
            self._matrix = np.vstack(vecs) if vecs else np.zeros((0, self.embedder.dim), dtype=np.float32)

    def add(self, memory_id: str, text: str) -> np.ndarray:
        v = self.embedder.embed(text)
        self.db.execute(
            "INSERT OR REPLACE INTO vectors (memory_id, dim, embedding, model) VALUES (?,?,?,?)",
            (memory_id, self.embedder.dim, v.tobytes(), self.embedder.name),
        )
        with self._lock:
            if memory_id in self._ids:
                self._matrix[self._ids.index(memory_id)] = v
            else:
                self._ids.append(memory_id)
                self._matrix = np.vstack([self._matrix, v[None, :]])
        return v

    def remove(self, memory_id: str) -> None:
        self.db.execute("DELETE FROM vectors WHERE memory_id=?", (memory_id,))
        with self._lock:
            if memory_id in self._ids:
                i = self._ids.index(memory_id)
                self._ids.pop(i)
                self._matrix = np.delete(self._matrix, i, axis=0)

    def contains(self, memory_id: str) -> bool:
        with self._lock:
            in_mem = memory_id in self._ids
        return in_mem or self.db.one("SELECT 1 AS x FROM vectors WHERE memory_id=?", (memory_id,)) is not None

    def search_vec(self, v: np.ndarray, limit: int = 50, allowed: set[str] | None = None) -> list[tuple[str, float]]:
        with self._lock:
            if not self._ids:
                return []
            sims = self._matrix @ v
            order = np.argsort(-sims)
            out = []
            for i in order:
                mid = self._ids[i]
                if allowed is not None and mid not in allowed:
                    continue
                out.append((mid, float(sims[i])))
                if len(out) >= limit:
                    break
            return out

    def search(self, query: str, limit: int = 50, allowed: set[str] | None = None) -> list[tuple[str, float]]:
        return self.search_vec(self.embedder.embed(query), limit, allowed)

    def size(self) -> int:
        return len(self._ids)


# --------------------------------------------------------------------------
class GraphStore:
    """Entities and typed relationships derived from memories."""

    name = "graph"

    def __init__(self, db: Database):
        self.db = db

    def _entity(self, name: str, kind: str = "thing") -> str:
        key = name.strip().lower()
        r = self.db.one("SELECT id FROM entities WHERE name=?", (key,))
        if r:
            return r["id"]
        eid = new_id("ent")
        self.db.execute("INSERT INTO entities (id, name, kind, created_at) VALUES (?,?,?,?)", (eid, key, kind, now_iso()))
        return eid

    def add(self, memory_id: str, entities: list[str], relation: tuple[str, str, str] | None) -> None:
        for e in entities:
            eid = self._entity(e)
            self.db.execute("INSERT OR IGNORE INTO entity_mentions (entity_id, memory_id) VALUES (?,?)", (eid, memory_id))
        if relation:
            s, rel, d = relation
            sid, did = self._entity(s, "entity"), self._entity(d, "entity")
            for eid in (sid, did):
                self.db.execute("INSERT OR IGNORE INTO entity_mentions (entity_id, memory_id) VALUES (?,?)", (eid, memory_id))
            self.db.execute(
                "INSERT INTO edges (id, src_entity, relation, dst_entity, memory_id, created_at) VALUES (?,?,?,?,?,?)",
                (new_id("edge"), sid, rel, did, memory_id, now_iso()),
            )

    def remove(self, memory_id: str) -> None:
        self.db.execute("DELETE FROM edges WHERE memory_id=?", (memory_id,))
        self.db.execute("DELETE FROM entity_mentions WHERE memory_id=?", (memory_id,))
        # garbage-collect orphan entities so deleted names do not linger
        self.db.execute(
            "DELETE FROM entities WHERE id NOT IN (SELECT entity_id FROM entity_mentions) "
            "AND id NOT IN (SELECT src_entity FROM edges) AND id NOT IN (SELECT dst_entity FROM edges)"
        )

    def contains(self, memory_id: str) -> bool:
        return (
            self.db.one("SELECT 1 AS x FROM edges WHERE memory_id=?", (memory_id,)) is not None
            or self.db.one("SELECT 1 AS x FROM entity_mentions WHERE memory_id=?", (memory_id,)) is not None
        )

    def memories_for_entities(self, names: list[str], hops: int = 1) -> list[tuple[str, float]]:
        if not names:
            return []
        keys = [n.lower() for n in names]
        ents = self.db.query(f"SELECT id FROM entities WHERE name IN ({','.join('?' * len(keys))})", keys)
        frontier = {e["id"] for e in ents}
        scores: dict[str, float] = {}
        seen = set(frontier)
        weight = 1.0
        for _ in range(hops + 1):
            if not frontier:
                break
            ph = ",".join("?" * len(frontier))
            for r in self.db.query(f"SELECT memory_id FROM entity_mentions WHERE entity_id IN ({ph})", list(frontier)):
                scores[r["memory_id"]] = scores.get(r["memory_id"], 0.0) + weight
            nxt = set()
            for r in self.db.query(
                f"SELECT src_entity, dst_entity FROM edges WHERE src_entity IN ({ph}) OR dst_entity IN ({ph})",
                list(frontier) * 2,
            ):
                nxt.update({r["src_entity"], r["dst_entity"]})
            frontier = nxt - seen
            seen |= nxt
            weight *= 0.5
        return sorted(scores.items(), key=lambda x: -x[1])

    def neighbourhood(self, name: str) -> dict:
        e = self.db.one("SELECT * FROM entities WHERE name=?", (name.lower(),))
        if not e:
            return {"entity": None, "edges": []}
        edges = self.db.query(
            "SELECT s.name AS src, e.relation, d.name AS dst, e.memory_id FROM edges e "
            "JOIN entities s ON s.id=e.src_entity JOIN entities d ON d.id=e.dst_entity "
            "WHERE e.src_entity=? OR e.dst_entity=?",
            (e["id"], e["id"]),
        )
        return {"entity": e, "edges": edges}

    def full_graph(self, limit: int = 300) -> dict:
        nodes = self.db.query("SELECT id, name, kind FROM entities LIMIT ?", (limit,))
        edges = self.db.query(
            "SELECT e.src_entity AS source, e.dst_entity AS target, e.relation, e.memory_id FROM edges e LIMIT ?", (limit,)
        )
        return {"nodes": nodes, "edges": edges}


# --------------------------------------------------------------------------
class FileStore:
    """Human-readable Markdown file per memory (procedures, long documents)."""

    name = "file"

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, memory_id: str) -> Path:
        return self.root / f"{memory_id}.md"

    def add(self, memory_id: str, rec: dict) -> str:
        p = self.path_for(memory_id)
        body = (
            f"---\nid: {memory_id}\ntype: {rec.get('memory_type')}\nstatus: {rec.get('status')}\n"
            f"created_at: {rec.get('created_at')}\nversion: {rec.get('version', 1)}\n---\n\n{rec.get('content','')}\n"
        )
        p.write_text(body, encoding="utf-8")
        return str(p)

    def read(self, memory_id: str) -> str | None:
        p = self.path_for(memory_id)
        return p.read_text(encoding="utf-8") if p.exists() else None

    def remove(self, memory_id: str) -> None:
        p = self.path_for(memory_id)
        if p.exists():
            # overwrite before unlinking (best-effort; SSD/OS caches may still retain blocks)
            size = p.stat().st_size
            with open(p, "r+b") as fh:
                fh.write(b"\0" * size)
            p.unlink()

    def contains(self, memory_id: str) -> bool:
        return self.path_for(memory_id).exists()

    def contains_text(self, text: str) -> list[str]:
        hits = []
        for p in self.root.glob("*.md"):
            try:
                if text in p.read_text(encoding="utf-8"):
                    hits.append(p.name)
            except OSError:
                continue
        return hits

    def search(self, terms: list[str], limit: int = 50) -> list[tuple[str, float]]:
        out = []
        for p in self.root.glob("*.md"):
            txt = p.read_text(encoding="utf-8").lower()
            s = sum(txt.count(t) for t in terms)
            if s:
                out.append((p.stem, float(s)))
        return sorted(out, key=lambda x: -x[1])[:limit]

    def disk_bytes(self) -> int:
        return sum(p.stat().st_size for p in self.root.glob("*.md"))
