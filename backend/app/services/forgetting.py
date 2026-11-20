"""Forgetting: cascading deletion, cross-store verification and privacy-safe audit.

Deletion scopes
---------------
* ``id``      – explicit memory ids
* ``topic``   – memories matching a free-text topic (hybrid search, threshold)
* ``entity``  – memories mentioning an entity (graph + text match)
* ``source``  – memories whose provenance came from a source id / agent / session

Two-phase protocol: ``plan()`` returns exactly what would be deleted (including
cascaded derived memories) plus a short-lived confirmation token; ``execute()``
requires that token. This prevents accidental bulk deletion.

What gets removed for every memory
----------------------------------
structured row, FTS5 row, vector row + in-memory index entry, graph mentions and
edges (+ orphan entities), Markdown file (zero-overwritten, then unlinked),
provenance, revisions (they contain old content), memory links, conflicts,
decision previews, handover package snapshots (redacted in place) and the
retrieval cache. The audit row keeps only counts, store names and salted
hashes of content terms — never content.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time

from ..core.text import content_terms, new_id, now_iso

STORES = ["structured", "keyword", "vector", "graph", "file", "provenance", "revisions", "links", "handovers"]


class ForgettingService:
    def __init__(self, engine):
        self.e = engine
        self.db = engine.db
        self._plans: dict[str, tuple[float, list[str], str]] = {}
        r = self.db.one("SELECT value FROM kv_settings WHERE key='tombstone_salt'")
        if r:
            self.salt = r["value"]
        else:
            self.salt = secrets.token_hex(16)
            self.db.execute("INSERT INTO kv_settings (key, value) VALUES ('tombstone_salt', ?)", (self.salt,))

    # ----------------------------------------------------------- hashing
    def _h(self, term: str) -> str:
        return hashlib.sha256((self.salt + term).encode()).hexdigest()[:16]

    def term_hashes(self, text: str) -> list[str]:
        return sorted({self._h(t) for t in content_terms(text)})

    def tombstone_match(self, query: str) -> dict | None:
        """Does the query look like it is asking about something deleted/expired?"""
        qh = {self._h(t) for t in content_terms(query)}
        if not qh:
            return None
        best = None
        for r in self.db.query("SELECT scope, term_hashes, created_at FROM deletion_audit ORDER BY created_at DESC LIMIT 500"):
            hs = set(json.loads(r["term_hashes"]))
            if not hs:
                continue
            overlap = len(qh & hs) / len(qh)
            if overlap >= 0.6 and (best is None or overlap > best["overlap"]):
                best = {"scope": r["scope"], "overlap": round(overlap, 2), "at": r["created_at"]}
        return best

    # ----------------------------------------------------------- selection
    def select(self, scope: str, value: str, include_derived: bool = True) -> list[str]:
        ids: list[str] = []
        if scope == "id":
            ids = [v.strip() for v in value.split(",") if v.strip() and self.e.structured.contains(v.strip())]
        elif scope == "topic":
            res = self.e.retriever.search(value, limit=50, include_inactive=True, min_score=0.0)
            ids = [r["id"] for r in res["results"] if r["score"] >= 0.35 or r["matched"].get("keyword")]
        elif scope == "entity":
            ids = [m for m, _ in self.e.graph.memories_for_entities([value], hops=0)]
            like = f"%{value}%"
            ids += [r["id"] for r in self.db.query(
                "SELECT id FROM memories WHERE content LIKE ? OR subject LIKE ? OR entities LIKE ?", (like, like, like))]
        elif scope == "source":
            ids = [r["memory_id"] for r in self.db.query(
                "SELECT DISTINCT memory_id FROM provenance WHERE source_id=? OR agent_id=? OR session_id=? OR source_label=?",
                (value, value, value, value))]
        else:
            raise ValueError("scope must be id, topic, entity or source")
        ids = list(dict.fromkeys(i for i in ids if self.e.structured.contains(i)))
        if include_derived:
            ids = self._with_derived(ids)
        return ids

    def _with_derived(self, ids: list[str]) -> list[str]:
        out = list(ids)
        frontier = list(ids)
        while frontier:
            ph = ",".join("?" * len(frontier))
            kids = [r["from_id"] for r in self.db.query(
                f"SELECT from_id FROM memory_links WHERE relation IN ('derived_from','merged_into') AND to_id IN ({ph})", frontier)]
            # older versions of a forgotten fact are forgotten too (they hold the same information)
            kids += [r["to_id"] for r in self.db.query(
                f"SELECT to_id FROM memory_links WHERE relation='supersedes' AND from_id IN ({ph})", frontier)]
            frontier = [k for k in dict.fromkeys(kids) if k not in out and self.e.structured.contains(k)]
            out += frontier
        return out

    # ----------------------------------------------------------- plan/execute
    def plan(self, scope: str, value: str, include_derived: bool = True) -> dict:
        ids = self.select(scope, value, include_derived)
        direct = set(self.select(scope, value, False)) if include_derived else set(ids)
        token = secrets.token_urlsafe(12)
        self._plans[token] = (time.time() + 600, ids, scope)
        items = []
        for i in ids:
            m = self.e.structured.get(i)
            items.append({
                "id": i, "content": m["content"][:140], "memory_type": m["memory_type"], "status": m["status"],
                "cascade": i not in direct, "stores": self.presence(i),
            })
        return {"scope": scope, "value": value, "count": len(ids), "items": items, "confirm_token": token,
                "expires_in_s": 600}

    def execute(self, token: str, requested_by: str = "user") -> dict:
        p = self._plans.pop(token, None)
        if not p or p[0] < time.time():
            raise ValueError("invalid or expired confirmation token — create a new deletion plan")
        return self.delete_ids(p[1], scope=p[2], requested_by=requested_by)

    def delete_ids(self, ids: list[str], scope: str = "id", requested_by: str = "user") -> dict:
        hashes: set[str] = set()
        all_fps: list[str] = []
        for mid in ids:
            m = self.e.structured.get(mid)
            if not m:
                continue
            hashes.update(self.term_hashes(m["content"]))
            fingerprints = [m["content"]]
            for rv in self.db.query("SELECT content FROM revisions WHERE memory_id=?", (mid,)):
                fingerprints.append(rv["content"])
            with self.db.transaction():
                self.e.keyword.remove(mid)
                self.e.vector.remove(mid)
                self.e.graph.remove(mid)
                self.db.execute("DELETE FROM provenance WHERE memory_id=?", (mid,))
                self.db.execute("DELETE FROM revisions WHERE memory_id=?", (mid,))
                self.db.execute("DELETE FROM memory_links WHERE from_id=? OR to_id=?", (mid, mid))
                self.db.execute("DELETE FROM conflicts WHERE memory_a=? OR memory_b=?", (mid, mid))
                self.db.execute("UPDATE decisions SET preview=NULL, memory_id=NULL WHERE memory_id=?", (mid,))
                self.e.structured.remove(mid)
            self.e.files.remove(mid)
            self._redact_handovers(mid, fingerprints)
            all_fps += fingerprints
        self.compact()
        self.e.invalidate_cache()
        verification = self.verify(ids, all_fps)
        audit_id = self.audit(scope, len(ids), STORES, verification["all_clear"], sorted(hashes), requested_by)
        return {"deleted": ids, "count": len(ids), "verification": verification, "audit_id": audit_id}

    def _redact_handovers(self, mid: str, fingerprints: list[str]) -> None:
        """Scrub copies of a deleted memory from tasks, handover packages and agent logs."""
        needles = [mid] + [f[:40] for f in fingerprints if f and len(f) >= 12]
        RED = "[redacted: deleted memory]"

        def hit(text: str) -> bool:
            return any(n in text for n in needles)

        def scrub_list(xs: list) -> list:
            out = []
            for x in xs:
                if isinstance(x, str):
                    out.append(RED if hit(x) else x)
                elif isinstance(x, dict):
                    out.append({k: (RED if isinstance(v, str) and hit(v) and k in ("note", "text") else v) for k, v in x.items()})
                else:
                    out.append(x)
            return out

        like = [f"%{n}%" for n in needles]
        cond = " OR ".join(["{col} LIKE ?"] * len(like))
        # tasks: constraints / decisions / step notes
        for t in self.db.query(f"SELECT id, steps, constraints, decisions FROM tasks WHERE {cond.format(col='constraints')} "
                               f"OR {cond.format(col='decisions')} OR {cond.format(col='steps')}", like * 3):
            self.db.execute("UPDATE tasks SET steps=?, constraints=?, decisions=? WHERE id=?",
                            (json.dumps(scrub_list(json.loads(t["steps"]))), json.dumps(scrub_list(json.loads(t["constraints"]))),
                             json.dumps(scrub_list(json.loads(t["decisions"]))), t["id"]))
        # handover packages: snapshot replaced, then re-sealed (authorised redaction, recorded in the package)
        from .agents import _checksum

        for h in self.db.query(f"SELECT id, package FROM handovers WHERE {cond.format(col='package')}", like):
            pkg = json.loads(h["package"])
            pkg["relevant_memories"] = [
                x if x.get("id") != mid else {"id": mid, "content": "[deleted]", "deleted": True}
                for x in pkg.get("relevant_memories", [])
            ]
            for k in ("constraints", "decisions", "progress"):
                pkg[k] = scrub_list(pkg.get(k, []))
            if hit(pkg.get("context", "")):
                pkg["context"] = "[context invalidated: a referenced memory was deleted]"
            pkg["redactions"] = pkg.get("redactions", []) + [{"memory_id": mid, "at": now_iso(), "reason": "forgetting"}]
            pkg["checksum"] = _checksum(pkg)
            self.db.execute("UPDATE handovers SET package=?, checksum=? WHERE id=?", (json.dumps(pkg), pkg["checksum"], h["id"]))
        # agent logs: drop message/data text that quotes the memory
        for r in self.db.query(f"SELECT id FROM agent_log WHERE {cond.format(col='message')} OR {cond.format(col='data')}", like * 2):
            self.db.execute("UPDATE agent_log SET message=?, data='{}' WHERE id=?", (RED, r["id"]))

    # ----------------------------------------------------------- verify
    def presence(self, mid: str) -> dict:
        return {
            "structured": self.e.structured.contains(mid),
            "keyword": self.e.keyword.contains(mid),
            "vector": self.e.vector.contains(mid),
            "graph": self.e.graph.contains(mid),
            "file": self.e.files.contains(mid),
            "provenance": self.db.one("SELECT 1 AS x FROM provenance WHERE memory_id=?", (mid,)) is not None,
            "revisions": self.db.one("SELECT 1 AS x FROM revisions WHERE memory_id=?", (mid,)) is not None,
            "links": self.db.one("SELECT 1 AS x FROM memory_links WHERE from_id=? OR to_id=?", (mid, mid)) is not None,
            "handovers": self.db.one(
                "SELECT 1 AS x FROM handovers WHERE package LIKE ? AND package NOT LIKE ?",
                (f'%"id": "{mid}", "content"%', f'%"id": "{mid}", "content": "[deleted]"%'),
            ) is not None,
            "cache": self.e.cache_contains(mid),
        }

    def compact(self) -> None:
        """Merge FTS5 segments and checkpoint the WAL so deleted bytes are physically overwritten."""
        try:
            self.db.execute("INSERT INTO memories_fts(memories_fts) VALUES('optimize')")
            self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:  # pragma: no cover - best effort
            pass

    def physical_scan(self, fingerprints: list[str]) -> list[str]:
        """Search the raw database/WAL bytes and memory files for remnants of deleted content."""
        import os

        fps = [f[:60].encode("utf-8") for f in fingerprints if f and len(f) >= 12 and f != "[expired]"]
        if not fps:
            return []
        found = []
        paths = [str(self.e.settings.db_path), f"{self.e.settings.db_path}-wal"]
        for p in paths:
            if os.path.exists(p):
                with open(p, "rb") as fh:
                    blob = fh.read()
                for f in fps:
                    if f in blob:
                        found.append(f"{os.path.basename(p)}: '{f[:24].decode(errors='ignore')}…'")
        for f in fps:
            for name in self.e.files.contains_text(f.decode("utf-8", errors="ignore")):
                found.append(f"file {name}")
        return found

    def verify(self, ids: list[str], fingerprints: list[str] | None = None) -> dict:
        per = {}
        clear = True
        for mid in ids:
            pres = self.presence(mid)
            leftovers = [k for k, v in pres.items() if v]
            per[mid] = {"remaining_in": leftovers, "clear": not leftovers}
            clear = clear and not leftovers
        residue = self.physical_scan(fingerprints or [])
        return {"all_clear": clear and not residue, "logical_clear": clear, "physical_residue": residue,
                "physical_scan": bool(fingerprints), "checked_stores": STORES + ["cache"], "per_memory": per,
                "checked_at": now_iso()}

    def audit(self, scope: str, count: int, stores: list[str], verified: bool, hashes: list[str], by: str) -> str:
        aid = new_id("del")
        self.db.execute(
            "INSERT INTO deletion_audit (id, scope, deleted_count, stores, verified, term_hashes, requested_by, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (aid, scope, count, json.dumps(stores), int(verified), json.dumps(hashes), by, now_iso()),
        )
        return aid

    def audit_log(self, limit: int = 100) -> list[dict]:
        rows = self.db.query(
            "SELECT id, scope, deleted_count, stores, verified, requested_by, created_at FROM deletion_audit "
            "ORDER BY created_at DESC LIMIT ?", (limit,))
        for r in rows:
            r["stores"] = json.loads(r["stores"])
            r["verified"] = bool(r["verified"])
        return rows
