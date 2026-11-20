"""Applies decisions to storage and manages the memory lifecycle.

Responsibilities: create / merge / update / conflict handling, provenance and
revision history, confirmation queue, conflict resolution, manual edits,
temporary-memory expiry, and lineage/trace queries.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..core.text import content_terms, new_id, now_iso, parse_iso, sha256
from .decision import Candidate, Decision, DecisionEngine

ACTIVE_STATES = ("active", "conflicted")


class MemoryService:
    def __init__(self, engine):
        self.e = engine
        self.db = engine.db
        self.structured = engine.structured
        self.decider = DecisionEngine(engine.settings, engine.structured, engine.vector)

    # ================================================================ ingest
    def ingest(self, cand: Candidate, dry_run: bool = False, now: datetime | None = None) -> dict:
        decision = self.decider.decide(cand, now)
        if dry_run:
            return {"decision": decision.to_dict(), "memory": None, "dry_run": True}
        did = self._log_decision(decision, cand)
        memory_id = None
        conflict_id = None
        a = decision.action
        if a == "STORE":
            memory_id = self._create(decision, cand, "active", did)
        elif a == "TEMPORARY":
            memory_id = self._create(decision, cand, "active", did, expires_at=decision.expires_at)
        elif a == "NEEDS_CONFIRMATION":
            memory_id = self._create(decision, cand, "pending_confirmation", did)
        elif a == "MERGE":
            memory_id = self._merge(decision.target_memory_id, cand, decision)
        elif a == "UPDATE":
            memory_id = self._update(decision.target_memory_id, cand, decision, did)
        elif a == "FLAG_CONFLICT":
            memory_id, conflict_id = self._flag_conflict(decision.target_memory_id, cand, decision, did)
        if memory_id:
            self.db.execute("UPDATE decisions SET memory_id=? WHERE id=?", (memory_id, did))
        self.e.invalidate_cache()
        return {
            "decision": decision.to_dict(),
            "decision_id": did,
            "memory": self.get(memory_id) if memory_id else None,
            "conflict_id": conflict_id,
            "dry_run": False,
        }

    def _log_decision(self, d: Decision, cand: Candidate) -> str:
        did = new_id("dec")
        keep_preview = d.action != "DISCARD" or self.e.settings.retain_discarded_preview
        preview = d.content[:160] if keep_preview and "secret_detected" not in d.flags else None
        self.db.execute(
            "INSERT INTO decisions (id, action, memory_type, preview, content_hash, scores, reasons, routes, flags, "
            "source_type, agent_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (did, d.action, d.memory_type, preview, sha256(cand.content), json.dumps(d.scores), json.dumps(d.reasons),
             json.dumps(d.routes), json.dumps(d.flags), cand.source_type, cand.agent_id, now_iso()),
        )
        return did

    def _create(self, d: Decision, cand: Candidate, status: str, decision_id: str, expires_at: str | None = None,
                version: int = 1, valid_from: str | None = None) -> str:
        mid = new_id("mem")
        ts = now_iso()
        c = d.classification
        rec = {
            "id": mid, "content": d.content, "memory_type": d.memory_type, "status": status,
            "subject": c.get("subject"), "attribute": c.get("attribute"), "value": c.get("value"),
            "entities": c.get("entities") or [], "tags": cand.tags or [],
            "importance": round(max(d.scores.get("utility", 0.5), cand.importance or 0), 3),
            "confidence": d.scores.get("confidence", 0.5), "source_trust": d.scores.get("source_trust", 0.5),
            "source_type": cand.source_type,
            "storage_routes": d.routes, "task_id": cand.task_id, "agent_id": cand.agent_id,
            "session_id": cand.session_id, "created_at": ts, "updated_at": ts, "valid_from": valid_from or ts,
            "expires_at": expires_at, "version": version, "decision_id": decision_id,
        }
        with self.db.transaction():
            self.structured.insert(rec)
            self._index(mid, rec, d)
            self._provenance(mid, cand, d)
            self._revision(mid, version, rec["content"], rec["value"], status, "create", "; ".join(d.reasons[-1:]), cand.agent_id or cand.source_type)
            for rid in d.related_ids:
                if rid != mid:
                    self._link(mid, rid, "related_to")
            for src in getattr(cand, "derived_from", None) or []:
                if self.structured.contains(src):
                    self._link(mid, src, "derived_from")
        return mid

    def _index(self, mid: str, rec: dict, d: Decision) -> None:
        if "keyword" in d.routes:
            self.e.keyword.add(mid, rec["content"], rec.get("subject"), rec.get("tags") or [])
        if "vector" in d.routes:
            self.e.vector.add(mid, rec["content"])
        if "graph" in d.routes:
            rel = d.classification.get("relation")
            self.e.graph.add(mid, d.classification.get("entities") or [], tuple(rel) if rel else None)
        if "file" in d.routes:
            path = self.e.files.add(mid, rec)
            self.structured.update(mid, file_path=path)

    def _unindex(self, mid: str) -> None:
        self.e.keyword.remove(mid)
        self.e.vector.remove(mid)
        self.e.graph.remove(mid)
        self.e.files.remove(mid)

    def _provenance(self, mid: str, cand: Candidate, d: Decision, method: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO provenance (id, memory_id, source_type, source_id, source_label, agent_id, session_id, "
            "extraction_method, confidence, excerpt_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (new_id("prov"), mid, cand.source_type, cand.source_id, cand.source_label, cand.agent_id, cand.session_id,
             method or f"rules:{d.classification.get('extraction') or 'none'}", d.scores.get("confidence", 0.5),
             sha256(cand.content), now_iso()),
        )

    def _revision(self, mid, version, content, value, status, change_type, reason, actor) -> None:
        self.db.execute(
            "INSERT INTO revisions (id, memory_id, version, content, value, status, change_type, reason, actor, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (new_id("rev"), mid, version, content, value, status, change_type, reason, actor, now_iso()),
        )

    def _link(self, a: str, b: str, rel: str) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO memory_links (from_id, to_id, relation, created_at) VALUES (?,?,?,?)",
            (a, b, rel, now_iso()),
        )

    # ------------------------------------------------------------ merge
    def _merge(self, target: str, cand: Candidate, d: Decision) -> str:
        m = self.structured.get(target)
        provs = self.db.query("SELECT source_type, source_id, agent_id FROM provenance WHERE memory_id=?", (target,))
        key = (cand.source_type, cand.source_id, cand.agent_id)
        distinct = all((p["source_type"], p["source_id"], p["agent_id"]) != key for p in provs)
        with self.db.transaction():
            self._provenance(target, cand, d, method="merge")
            if distinct:
                # independent corroboration raises confidence (noisy-OR, capped)
                conf = min(0.99, 1 - (1 - m["confidence"]) * (1 - 0.5 * d.scores.get("source_trust", 0.5)))
                self.structured.update(target, reinforcement=m["reinforcement"] + 1, confidence=round(conf, 3))
                note = "corroborated by an independent source → confidence raised"
            else:
                self.structured.update(target, updated_at=now_iso())
                note = "repeat from the same source → no confidence gain (anti-flooding)"
            d.reasons.append(note)
            self._revision(target, m["version"], m["content"], m.get("value"), m["status"], "merge", note,
                           cand.agent_id or cand.source_type)
        return target

    # ------------------------------------------------------------ update
    def _update(self, target: str, cand: Candidate, d: Decision, did: str) -> str:
        old = self.structured.get(target)
        ts = now_iso()
        with self.db.transaction():
            self.structured.update(target, status="superseded", valid_to=ts)
            self._revision(target, old["version"], old["content"], old.get("value"), "superseded", "superseded",
                           f"superseded by newer value '{d.classification.get('value')}'", cand.agent_id or cand.source_type)
            # superseded memories leave the semantic index so they are not retrieved as current
            self.e.vector.remove(target)
        new = self._create(d, cand, "active", did, version=old["version"] + 1, valid_from=ts)
        self._link(new, target, "supersedes")
        # close any open conflicts on the old memory
        self.db.execute(
            "UPDATE conflicts SET status='resolved', resolution='superseded_by_update', resolved_at=? "
            "WHERE status='open' AND (memory_a=? OR memory_b=?)",
            (ts, target, target),
        )
        return new

    # ------------------------------------------------------------ conflict
    def _flag_conflict(self, target: str, cand: Candidate, d: Decision, did: str) -> tuple[str, str]:
        kind = d.conflict_kind or "value_conflict"
        status = "quarantined" if kind == "low_trust_override" else "conflicted"
        new = self._create(d, cand, status, did)
        if kind == "value_conflict":
            self.structured.update(target, status="conflicted")
        old = self.structured.get(target)
        cid = new_id("cfl")
        expl = (
            f"'{old.get('subject')}' {old.get('attribute')}: existing value '{old.get('value')}' "
            f"(trust {old['source_trust']:.2f}) vs new value '{d.classification.get('value')}' "
            f"(trust {d.scores.get('source_trust', 0):.2f})"
        )
        self.db.execute(
            "INSERT INTO conflicts (id, memory_a, memory_b, subject, attribute, kind, status, explanation, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (cid, target, new, old.get("subject"), old.get("attribute"), kind, "open", expl, now_iso()),
        )
        self._link(new, target, "conflicts_with")
        return new, cid

    # ===================================================== confirmation
    def confirm(self, memory_id: str, approve: bool, actor: str = "user") -> dict:
        m = self.structured.get(memory_id)
        if not m or m["status"] not in ("pending_confirmation", "quarantined"):
            raise ValueError("memory is not awaiting confirmation")
        if approve:
            new_conf = max(m["confidence"], self.e.settings.confirmation_threshold + 0.25)
            self.structured.update(memory_id, status="active", confidence=round(min(new_conf, 0.95), 3))
            self._revision(memory_id, m["version"], m["content"], m.get("value"), "active", "confirmed",
                           f"confirmed by {actor}", actor)
            if "vector" in (m.get("storage_routes") or []):
                self.e.vector.add(memory_id, m["content"])
        else:
            self.e.forgetting.delete_ids([memory_id], scope="rejected", requested_by=actor)
        self.e.invalidate_cache()
        return {"memory_id": memory_id, "approved": approve}

    def resolve_conflict(self, conflict_id: str, resolution: str, actor: str = "user") -> dict:
        c = self.db.one("SELECT * FROM conflicts WHERE id=?", (conflict_id,))
        if not c:
            raise KeyError("conflict not found")
        if c["status"] != "open":
            raise ValueError("conflict already resolved")
        a, b = c["memory_a"], c["memory_b"]
        ts = now_iso()
        if resolution not in ("keep_a", "keep_b", "keep_both"):
            raise ValueError("resolution must be keep_a, keep_b or keep_both")
        if resolution == "keep_both":
            for mid in (a, b):
                if self.structured.contains(mid):
                    self.structured.update(mid, status="active")
        else:
            keep, drop = (a, b) if resolution == "keep_a" else (b, a)
            if self.structured.contains(keep):
                km = self.structured.get(keep)
                self.structured.update(keep, status="active")
                self._revision(keep, km["version"], km["content"], km.get("value"), "active", "conflict_resolved",
                               f"kept in conflict {conflict_id}", actor)
                if "vector" in (km.get("storage_routes") or []):
                    self.e.vector.add(keep, km["content"])
            if self.structured.contains(drop):
                dm = self.structured.get(drop)
                self.structured.update(drop, status="superseded", valid_to=ts)
                self._revision(drop, dm["version"], dm["content"], dm.get("value"), "superseded", "conflict_resolved",
                               f"rejected in conflict {conflict_id}", actor)
                self.e.vector.remove(drop)
                self._link(keep, drop, "supersedes")
        self.db.execute(
            "UPDATE conflicts SET status='resolved', resolution=?, resolved_at=? WHERE id=?", (resolution, ts, conflict_id)
        )
        self.e.invalidate_cache()
        return self.db.one("SELECT * FROM conflicts WHERE id=?", (conflict_id,))

    # ===================================================== manual edit
    def edit(self, memory_id: str, content: str, actor: str = "user", reason: str = "manual edit") -> dict:
        m = self.structured.get(memory_id)
        if not m:
            raise KeyError("memory not found")
        from ..core import safety
        from ..core.classifier import classify

        rep = safety.scan(content)
        if rep.secrets or rep.injection:
            raise ValueError("edit rejected: content contains secrets or instruction-like injection")
        cls = classify(rep.redacted_text)
        v = m["version"] + 1
        self.structured.update(memory_id, content=rep.redacted_text, version=v, subject=cls.subject or m["subject"],
                               attribute=cls.attribute or m["attribute"], value=cls.value or m["value"])
        self._revision(memory_id, v, rep.redacted_text, cls.value, m["status"], "edit", reason, actor)
        routes = m.get("storage_routes") or []
        if "keyword" in routes:
            self.e.keyword.add(memory_id, rep.redacted_text, cls.subject or m["subject"], m.get("tags") or [])
        if "vector" in routes and m["status"] == "active":
            self.e.vector.add(memory_id, rep.redacted_text)
        if "file" in routes:
            self.e.files.add(memory_id, {**m, "content": rep.redacted_text, "version": v})
        self.e.invalidate_cache()
        return self.get(memory_id)

    # ===================================================== expiry
    def expire_sweep(self, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        rows = self.db.query("SELECT id, content, expires_at FROM memories WHERE expires_at IS NOT NULL AND status='active'")
        expired = []
        for r in rows:
            exp = parse_iso(r["expires_at"])
            if exp and exp <= now:
                expired.append(r["id"])
                hashes = self.e.forgetting.term_hashes(r["content"])
                self._unindex(r["id"])
                # purge content but keep a minimal stub so retrieval can say "expired"
                # every field derived from the content is cleared, not only the text itself
                self.structured.update(r["id"], status="expired", content="[expired]", value=None, subject=None,
                                       attribute=None, entities=[], tags=[], file_path=None,
                                       valid_to=now.isoformat(timespec="seconds"))
                self.db.execute("DELETE FROM revisions WHERE memory_id=?", (r["id"],))
                self.db.execute("UPDATE decisions SET preview=NULL WHERE memory_id=?", (r["id"],))
                self.e.forgetting.audit("expiry", 1, ["structured", "keyword", "vector", "graph", "file"], True, hashes, "system")
        if expired:
            self.e.forgetting.compact()
            self.e.invalidate_cache()
        return {"expired": expired, "count": len(expired)}

    # ===================================================== read
    def get(self, memory_id: str | None, touch: bool = False) -> dict | None:
        if not memory_id:
            return None
        m = self.structured.get(memory_id)
        if not m:
            return None
        if touch:
            self.db.execute(
                "UPDATE memories SET access_count=access_count+1, last_accessed_at=? WHERE id=?", (now_iso(), memory_id)
            )
        return m

    def detail(self, memory_id: str) -> dict | None:
        m = self.get(memory_id)
        if not m:
            return None
        m["provenance"] = self.db.query("SELECT * FROM provenance WHERE memory_id=? ORDER BY created_at", (memory_id,))
        m["revisions"] = self.db.query("SELECT * FROM revisions WHERE memory_id=? ORDER BY created_at", (memory_id,))
        m["links"] = self.db.query(
            "SELECT * FROM memory_links WHERE from_id=? OR to_id=? ORDER BY created_at", (memory_id, memory_id)
        )
        m["decision"] = self._decision(m.get("decision_id"))
        m["conflicts"] = self.db.query(
            "SELECT * FROM conflicts WHERE memory_a=? OR memory_b=? ORDER BY created_at", (memory_id, memory_id)
        )
        m["file_content"] = self.e.files.read(memory_id)
        m["store_presence"] = self.e.forgetting.presence(memory_id)
        return m

    def _decision(self, did: str | None) -> dict | None:
        if not did:
            return None
        d = self.db.one("SELECT * FROM decisions WHERE id=?", (did,))
        if d:
            for k in ("scores", "reasons", "routes", "flags"):
                d[k] = json.loads(d[k])
        return d

    def list(self, status: str | None = None, memory_type: str | None = None, agent_id: str | None = None,
             source_type: str | None = None, q: str | None = None, task_id: str | None = None,
             limit: int = 100, offset: int = 0) -> dict:
        where, params = [], []
        for col, val in (("status", status), ("memory_type", memory_type), ("agent_id", agent_id),
                         ("source_type", source_type), ("task_id", task_id)):
            if val:
                where.append(f"{col}=?")
                params.append(val)
        if q:
            where.append("(content LIKE ? OR subject LIKE ? OR value LIKE ?)")
            params += [f"%{q}%"] * 3
        w = ("WHERE " + " AND ".join(where)) if where else ""
        total = self.db.one(f"SELECT COUNT(*) AS n FROM memories {w}", params)["n"]
        rows = self.db.query(f"SELECT * FROM memories {w} ORDER BY created_at DESC LIMIT ? OFFSET ?", params + [limit, offset])
        from ..stores.stores import _decode

        return {"total": total, "items": [_decode(r) for r in rows]}

    def lineage(self, memory_id: str) -> list[dict]:
        """Follow supersedes links in both directions → ordered version chain."""
        chain_ids = [memory_id]
        cur = memory_id
        while True:  # older versions
            r = self.db.one("SELECT to_id FROM memory_links WHERE from_id=? AND relation='supersedes'", (cur,))
            if not r or r["to_id"] in chain_ids:
                break
            chain_ids.insert(0, r["to_id"])
            cur = r["to_id"]
        cur = memory_id
        while True:  # newer versions
            r = self.db.one("SELECT from_id FROM memory_links WHERE to_id=? AND relation='supersedes'", (cur,))
            if not r or r["from_id"] in chain_ids:
                break
            chain_ids.append(r["from_id"])
            cur = r["from_id"]
        return [m for m in (self.get(i) for i in chain_ids) if m]

    def trace(self, memory_id: str) -> dict:
        m = self.detail(memory_id)
        if not m:
            raise KeyError("memory not found")
        parents = self.db.query("SELECT to_id FROM memory_links WHERE from_id=? AND relation='derived_from'", (memory_id,))
        children = self.db.query("SELECT from_id FROM memory_links WHERE to_id=? AND relation='derived_from'", (memory_id,))
        return {
            "memory": m,
            "origin": m["provenance"][0] if m["provenance"] else None,
            "corroborations": m["provenance"][1:],
            "derived_from": [self.get(r["to_id"]) for r in parents],
            "derived_memories": [self.get(r["from_id"]) for r in children],
            "lineage": self.lineage(memory_id),
            "explanation": self._explain(m),
        }

    def _explain(self, m: dict) -> list[str]:
        out = []
        o = m["provenance"][0] if m["provenance"] else None
        if o:
            out.append(
                f"Originated from a {o['source_type']} source"
                + (f" '{o['source_label']}'" if o.get("source_label") else "")
                + (f" via agent {o['agent_id']}" if o.get("agent_id") else "")
                + (f" in session {o['session_id']}" if o.get("session_id") else "")
                + f" at {o['created_at']}, extracted by {o['extraction_method']}."
            )
        if len(m["provenance"]) > 1:
            out.append(f"Corroborated/merged {len(m['provenance']) - 1} additional time(s).")
        if m.get("decision"):
            out.append(f"Decision: {m['decision']['action']} — " + "; ".join(m["decision"]["reasons"][-2:]))
        out.append(f"Stored in: {', '.join(m.get('storage_routes') or [])}.")
        if m["status"] != "active":
            out.append(f"Current status: {m['status']}.")
        return out

    def term_overlap_terms(self, text: str) -> list[str]:
        return sorted(set(content_terms(text)))
