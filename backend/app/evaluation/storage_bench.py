"""Storage-strategy benchmark.

Six strategies are run on the same synthetic, labelled corpus (fictional data),
each in its own temporary directory:

* ``structured``  – SQLite table of (subject, attribute, value); LIKE matching on columns
* ``keyword``     – SQLite FTS5 with BM25 ranking (queryable full-text store)
* ``vector``      – local hashing embeddings + cosine similarity (numpy)
* ``graph``       – entity/edge tables; entity lookup + 1-hop expansion
* ``file``        – append-only JSONL file; linear scan with term overlap
* ``hybrid``      – the full Mnemos engine (decision engine + all stores + fusion)

Measured per strategy: R-precision, Recall@5, MRR, mean insert latency, mean
and p95 query latency, storage bytes on disk, update latency and update
correctness, and deletion verification (logical: the item is no longer
retrievable; physical: its unique token is absent from the raw bytes on disk).
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path

import numpy as np

from ..core.classifier import classify
from ..core.embeddings import HashingEmbedder
from ..core.text import STOPWORDS, content_terms

PEOPLE = ["Ana", "Ben", "Chen", "Dara", "Eli", "Farah", "Gus", "Hana", "Ivo", "Jun", "Kemi", "Lars"]
MANAGERS = ["Marcus", "Nadia", "Oscar"]
CITIES = ["Lisbon", "Oslo", "Nairobi", "Lima", "Hanoi", "Dublin", "Quito", "Perth", "Tunis", "Riga", "Accra", "Porto"]
TEAMS = ["platform", "payments", "search", "mobile"]
PROJECTS = ["Atlas", "Borealis", "Cobalt", "Delta", "Ember", "Falcon"]
LANGS = ["Rust", "Go", "Kotlin", "Python", "Elixir", "Scala"]
DBS = ["PostgreSQL", "MySQL", "MongoDB", "SQLite", "Cassandra", "Redis"]
DATES = ["March 3", "April 9", "May 21", "June 14", "July 2", "August 30"]


def build_corpus(seed: int = 11):
    rng = random.Random(seed)
    items: list[tuple[str, str]] = []
    queries: list[dict] = []

    def add(text: str) -> str:
        i = f"d{len(items):03d}"
        items.append((i, text))
        return i

    for idx, p in enumerate(PEOPLE):
        city = CITIES[idx]
        a = add(f"{p} lives in {city}.")
        m = MANAGERS[idx % 3]
        r = add(f"{p} reports to {m}.")
        t = add(f"{p} works on the {TEAMS[idx % 4]} team.")
        queries.append({"q": f"Where does {p} live?", "rel": [a], "kind": "exact"})
        queries.append({"q": f"Which city is {p} based in?", "rel": [a], "kind": "paraphrase"})
        queries.append({"q": f"Who is {p}'s manager?", "rel": [r], "kind": "paraphrase"})
        _ = t
    for m in MANAGERS:
        rel = [i for i, txt in items if txt.endswith(f"reports to {m}.")]
        queries.append({"q": f"Who reports to {m}?", "rel": rel, "kind": "relational"})
    for idx, pr in enumerate(PROJECTS):
        l = add(f"Project {pr} is written in {LANGS[idx]}.")
        d = add(f"Project {pr} uses {DBS[idx]} as its database.")
        dl = add(f"The deadline for Project {pr} is {DATES[idx]}.")
        pc = add(f"To release Project {pr}, first run the test suite, then tag the build, then deploy to staging.")
        queries.append({"q": f"What is the deadline for Project {pr}?", "rel": [dl], "kind": "exact"})
        queries.append({"q": f"Which datastore backs Project {pr}?", "rel": [d], "kind": "paraphrase"})
        queries.append({"q": f"How do I release Project {pr}?", "rel": [pc], "kind": "procedural"})
        queries.append({"q": f"Tell me everything about Project {pr}", "rel": [l, d, dl, pc], "kind": "entity"})
    for i in range(160):
        p = rng.choice(PEOPLE)
        add(f"{p} {rng.choice(['reviewed', 'tested', 'documented', 'demoed'])} the "
            f"{rng.choice(['login page', 'search filter', 'export button', 'audit log', 'help center', 'release notes', 'deploy script'])} "
            f"for Project {rng.choice(PROJECTS)} {rng.choice(['on Monday', 'after standup', 'last sprint', 'on Thursday'])}.")
    return items, queries


# ---------------------------------------------------------------- strategies
def _sqlite(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(path), isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA secure_delete=ON")
    return c


def _terms(q: str) -> list[str]:
    return [t for t in content_terms(q) if t not in STOPWORDS]


class Structured:
    name = "structured"

    def __init__(self, d: Path):
        self.c = _sqlite(d / "s.db")
        self.c.execute("CREATE TABLE f (id TEXT PRIMARY KEY, subject TEXT, attribute TEXT, value TEXT, content TEXT)")

    def add(self, i, text):
        cl = classify(text)
        subj = cl.subject or (cl.entities[0].lower() if cl.entities else None)
        self.c.execute("INSERT OR REPLACE INTO f VALUES (?,?,?,?,?)", (i, subj, cl.attribute, cl.value, text))

    def search(self, q, k=5):
        ents = [e.lower() for e in classify(q).entities]
        terms = _terms(q) + ents
        scores: dict[str, float] = {}
        for t in terms:
            for row in self.c.execute("SELECT id, subject, attribute, value FROM f WHERE subject LIKE ? OR attribute LIKE ? OR value LIKE ?",
                                      (f"%{t}%",) * 3):
                s = (2 if row[1] and t in row[1] else 0) + (1 if row[2] and t in row[2] else 0) + (0.5 if row[3] and t in row[3].lower() else 0)
                scores[row[0]] = scores.get(row[0], 0) + s
        return [i for i, _ in sorted(scores.items(), key=lambda x: -x[1])[:k]]

    def update(self, i, text):
        self.add(i, text)

    def delete(self, i):
        self.c.execute("DELETE FROM f WHERE id=?", (i,))

    def flush(self):
        self.c.execute("PRAGMA wal_checkpoint(TRUNCATE)")


class Keyword:
    name = "keyword"

    def __init__(self, d: Path):
        self.c = _sqlite(d / "k.db")
        self.c.execute("CREATE VIRTUAL TABLE f USING fts5(id UNINDEXED, content, tokenize='porter unicode61')")

    def add(self, i, text):
        self.c.execute("INSERT INTO f (id, content) VALUES (?,?)", (i, text))

    def search(self, q, k=5):
        w = [x for x in "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in q).split()
             if x.lower() not in STOPWORDS and len(x) > 1]
        if not w:
            return []
        expr = " OR ".join(f'"{x}"' for x in w)
        return [r[0] for r in self.c.execute("SELECT id FROM f WHERE f MATCH ? ORDER BY bm25(f) LIMIT ?", (expr, k))]

    def update(self, i, text):
        self.delete(i)
        self.add(i, text)

    def delete(self, i):
        self.c.execute("DELETE FROM f WHERE id=?", (i,))

    def flush(self):
        self.c.execute("INSERT INTO f(f) VALUES('optimize')")
        self.c.execute("PRAGMA wal_checkpoint(TRUNCATE)")


class Vector:
    name = "vector"

    def __init__(self, d: Path):
        self.c = _sqlite(d / "v.db")
        self.c.execute("CREATE TABLE v (id TEXT PRIMARY KEY, emb BLOB, content TEXT)")
        self.emb = HashingEmbedder(512)
        self.ids: list[str] = []
        self.m = np.zeros((0, 512), dtype=np.float32)

    def add(self, i, text):
        v = self.emb.embed(text)
        self.c.execute("INSERT OR REPLACE INTO v VALUES (?,?,?)", (i, v.tobytes(), text))
        if i in self.ids:
            self.m[self.ids.index(i)] = v
        else:
            self.ids.append(i)
            self.m = np.vstack([self.m, v[None, :]])

    def search(self, q, k=5):
        if not self.ids:
            return []
        s = self.m @ self.emb.embed(q)
        return [self.ids[j] for j in np.argsort(-s)[:k]]

    def update(self, i, text):
        self.add(i, text)

    def delete(self, i):
        self.c.execute("DELETE FROM v WHERE id=?", (i,))
        if i in self.ids:
            j = self.ids.index(i)
            self.ids.pop(j)
            self.m = np.delete(self.m, j, axis=0)

    def flush(self):
        self.c.execute("PRAGMA wal_checkpoint(TRUNCATE)")


class Graph:
    name = "graph"

    def __init__(self, d: Path):
        self.c = _sqlite(d / "g.db")
        self.c.executescript(
            "CREATE TABLE m (id TEXT PRIMARY KEY, content TEXT);"
            "CREATE TABLE mention (ent TEXT, mid TEXT);"
            "CREATE TABLE edge (src TEXT, rel TEXT, dst TEXT, mid TEXT);")

    def add(self, i, text):
        cl = classify(text)
        self.c.execute("INSERT OR REPLACE INTO m VALUES (?,?)", (i, text))
        for e in cl.entities:
            self.c.execute("INSERT INTO mention VALUES (?,?)", (e.lower(), i))
        if cl.relation:
            s, r, d = cl.relation
            self.c.execute("INSERT INTO edge VALUES (?,?,?,?)", (s, r, d, i))

    def search(self, q, k=5):
        ents = [e.lower() for e in classify(q).entities] or [t for t in _terms(q) if len(t) > 3]
        scores: dict[str, float] = {}
        for e in ents:
            for (mid,) in self.c.execute("SELECT mid FROM mention WHERE ent=?", (e,)):
                scores[mid] = scores.get(mid, 0) + 1
            for (mid,) in self.c.execute("SELECT mid FROM edge WHERE src=? OR dst=?", (e, e)):
                scores[mid] = scores.get(mid, 0) + 1.5
        return [i for i, _ in sorted(scores.items(), key=lambda x: -x[1])[:k]]

    def update(self, i, text):
        self.delete(i)
        self.add(i, text)

    def delete(self, i):
        for t in ("m",):
            self.c.execute(f"DELETE FROM {t} WHERE id=?", (i,))
        self.c.execute("DELETE FROM mention WHERE mid=?", (i,))
        self.c.execute("DELETE FROM edge WHERE mid=?", (i,))

    def flush(self):
        self.c.execute("PRAGMA wal_checkpoint(TRUNCATE)")


class FileJSONL:
    name = "file"

    def __init__(self, d: Path):
        self.p = d / "memories.jsonl"
        self.p.write_text("", encoding="utf-8")

    def add(self, i, text):
        with open(self.p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": i, "content": text}) + "\n")

    def _rows(self):
        with open(self.p, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh if x.strip()]

    def search(self, q, k=5):
        qt = set(_terms(q))
        scored = []
        for r in self._rows():
            ov = len(qt & set(content_terms(r["content"])))
            if ov:
                scored.append((r["id"], ov))
        return [i for i, _ in sorted(scored, key=lambda x: -x[1])[:k]]

    def _rewrite(self, rows):
        self.p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def update(self, i, text):
        self._rewrite([r if r["id"] != i else {"id": i, "content": text} for r in self._rows()])

    def delete(self, i):
        self._rewrite([r for r in self._rows() if r["id"] != i])

    def flush(self):
        pass


class Hybrid:
    name = "hybrid"

    def __init__(self, d: Path):
        from ..config import Settings
        from ..engine import Mnemos

        self.e = Mnemos(Settings(data_dir=d))
        self.map: dict[str, str] = {}
        self.rev: dict[str, str] = {}

    def add(self, i, text):
        from ..services.decision import Candidate

        r = self.e.memory.ingest(Candidate(content=text, source_type="document", source_id="bench"))
        if r["memory"]:
            self.map[r["memory"]["id"]] = i
            self.rev[i] = r["memory"]["id"]

    def search(self, q, k=5):
        self.e.invalidate_cache()
        res = self.e.retriever.search(q, limit=k)["results"]
        return [self.map.get(r["id"], r["id"]) for r in res]

    def update(self, i, text):
        from ..services.decision import Candidate

        r = self.e.memory.ingest(Candidate(content=f"Actually, {text.rstrip('.')} now.", source_type="document",
                                           source_id="bench"))
        if r["memory"]:
            self.map[r["memory"]["id"]] = i
            self.rev[i] = r["memory"]["id"]

    def delete(self, i):
        mid = self.rev.get(i)
        if mid:
            self.e.forgetting.delete_ids(self.e.forgetting.select("id", mid), requested_by="bench")

    def flush(self):
        self.e.forgetting.compact()


STRATEGIES = [Structured, Keyword, Vector, Graph, FileJSONL, Hybrid]


def _dir_bytes(d: Path) -> int:
    return sum(p.stat().st_size for p in d.rglob("*") if p.is_file())


def _raw_contains(d: Path, token: str) -> bool:
    b = token.encode()
    for p in d.rglob("*"):
        if p.is_file():
            try:
                if b in p.read_bytes():
                    return True
            except OSError:
                continue
    return False


def run_storage_benchmark(seed: int = 11) -> dict:
    items, queries = build_corpus(seed)
    rows = []
    per_kind: dict[str, dict[str, list[float]]] = {}
    for cls in STRATEGIES:
        d = Path(tempfile.mkdtemp(prefix=f"mnemos_bench_{cls.name}_"))
        s = cls(d)
        t0 = time.perf_counter()
        for i, text in items:
            s.add(i, text)
        insert_ms = (time.perf_counter() - t0) * 1000 / len(items)
        s.flush()
        storage = _dir_bytes(d)
        rp, rec5, mrr, lat = [], [], [], []
        for qd in queries:
            q0 = time.perf_counter()
            got = s.search(qd["q"], 5)
            lat.append((time.perf_counter() - q0) * 1000)
            rel = set(qd["rel"])
            k = len(rel)
            rp.append(len(set(got[:k]) & rel) / k)
            rec5.append(len(set(got[:5]) & rel) / k)
            rr = 0.0
            for rank, g in enumerate(got, 1):
                if g in rel:
                    rr = 1 / rank
                    break
            mrr.append(rr)
            per_kind.setdefault(cls.name, {}).setdefault(qd["kind"], []).append(rec5[-1])
        # update: move Ana to a new city, verify top-1 for the question returns the updated item text
        u0 = time.perf_counter()
        s.update("d000", "Ana lives in Zanzibar.")
        update_ms = (time.perf_counter() - u0) * 1000
        top = s.search("Where does Ana live?", 1)
        update_ok = bool(top) and top[0] == "d000"
        # deletion: add a unique-token memory, delete it, verify logical + physical absence
        token = "QZX7741"
        s.add("dzz", f"The vault code name is {token} for Project Cobalt.")
        s.flush()
        s.delete("dzz")
        s.flush()
        logical = "dzz" not in s.search(f"vault code name {token}", 10)
        physical = not _raw_contains(d, token)
        if isinstance(s, Hybrid):
            s.e.close()
        rows.append({
            "strategy": cls.name, "r_precision": round(statistics.mean(rp), 3), "recall_at_5": round(statistics.mean(rec5), 3),
            "mrr": round(statistics.mean(mrr), 3), "insert_ms": round(insert_ms, 3),
            "query_ms_mean": round(statistics.mean(lat), 3), "query_ms_p95": round(sorted(lat)[int(len(lat) * 0.95) - 1], 3),
            "storage_bytes": storage, "update_ms": round(update_ms, 3), "update_correct": update_ok,
            "delete_logical": logical, "delete_physical": physical,
        })
    by_kind = {name: {k: round(statistics.mean(v), 3) for k, v in kinds.items()} for name, kinds in per_kind.items()}
    return {"corpus": {"items": len(items), "queries": len(queries), "seed": seed,
                       "query_kinds": sorted({q["kind"] for q in queries})},
            "rows": rows, "recall_by_query_kind": by_kind, "secure_delete_demo": secure_delete_demo()}


def secure_delete_demo() -> dict:
    """Show why ``PRAGMA secure_delete`` matters: deleted text can survive in free pages."""
    out = {}
    for flag in ("OFF", "ON"):
        d = Path(tempfile.mkdtemp(prefix=f"mnemos_sd_{flag}_"))
        c = sqlite3.connect(str(d / "x.db"), isolation_level=None)
        c.execute(f"PRAGMA secure_delete={flag}")
        c.execute("CREATE TABLE t (x TEXT)")
        c.execute("INSERT INTO t VALUES (?)", ("secret-note SDTOKEN4242 " + "pad " * 50,))
        c.execute("DELETE FROM t")
        c.close()
        out[f"secure_delete_{flag.lower()}"] = {"token_found_in_file_after_delete": b"SDTOKEN4242" in (d / "x.db").read_bytes()}
    return out
