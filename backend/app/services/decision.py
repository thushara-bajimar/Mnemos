"""Memory decision engine.

Given an incoming candidate (text + source metadata) it returns one of::

    STORE | UPDATE | MERGE | TEMPORARY | DISCARD | NEEDS_CONFIRMATION | FLAG_CONFLICT

together with numeric scores (relevance, utility, confidence, durability,
redundancy, privacy_risk, injection_risk, source_trust), the classification,
the storage routes, and a list of human-readable reasons. The engine is
*pure* with respect to storage: it only reads existing memories; applying
the decision is done by :class:`~app.services.memory.MemoryService`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from ..core import safety
from ..core.classifier import Classification, classify, expiry_from
from ..core.router import route
from ..core.text import normalize

SOURCE_TRUST = {
    "system": 0.95,
    "user": 0.9,
    "document": 0.75,
    "agent": 0.7,
    "tool": 0.6,
    "web": 0.4,
    "unknown": 0.3,
}

DURABILITY = {
    "procedural": 0.9, "preference": 0.85, "semantic": 0.8, "relational": 0.8, "episodic": 0.6, "working": 0.2,
}

# attributes that can legitimately have several values at once
MULTI_VALUED = {"preference", "dislike", "uses", "works with", "depends on", "manages", "is a member of",
                "is part of", "likes", "loves", "wants", "built with"}

ACTIONS = ["STORE", "UPDATE", "MERGE", "TEMPORARY", "DISCARD", "NEEDS_CONFIRMATION", "FLAG_CONFLICT"]


@dataclass
class Candidate:
    content: str
    source_type: str = "user"
    source_id: str | None = None
    source_label: str | None = None
    agent_id: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    tags: list[str] = field(default_factory=list)
    confidence: float | None = None       # optional caller-supplied confidence
    ttl_hours: float | None = None         # explicit expiry request
    memory_type: str | None = None         # optional override
    importance: float | None = None
    derived_from: list[str] = field(default_factory=list)  # ids this memory was derived from


@dataclass
class Decision:
    action: str
    memory_type: str
    content: str                       # content to store (redacted)
    scores: dict[str, float]
    reasons: list[str]
    flags: list[str]
    routes: list[str]
    route_reasons: list[str]
    classification: dict
    target_memory_id: str | None = None
    expires_at: str | None = None
    conflict_kind: str | None = None
    related_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class DecisionEngine:
    def __init__(self, settings, structured, vector):
        self.settings = settings
        self.structured = structured
        self.vector = vector

    def decide(self, cand: Candidate, now: datetime | None = None) -> Decision:
        now = now or datetime.now(timezone.utc)
        s = self.settings
        text = cand.content.strip()
        reasons: list[str] = []
        flags: list[str] = []
        rep = safety.scan(text)
        cls: Classification = classify(text, now)
        if cand.memory_type:
            reasons.append(f"memory type overridden by caller: {cand.memory_type}")
            cls.memory_type = cand.memory_type
        trust = SOURCE_TRUST.get(cand.source_type, SOURCE_TRUST["unknown"])

        def result(action: str, **kw) -> Decision:
            temporary = action == "TEMPORARY"
            routes, rreasons = ([], []) if action == "DISCARD" else route(cls, rep.redacted_text, temporary)
            return Decision(
                action=action,
                memory_type=cls.memory_type,
                content=rep.redacted_text,
                scores={k: round(v, 3) for k, v in scores.items()},
                reasons=reasons,
                flags=flags,
                routes=routes,
                route_reasons=rreasons,
                classification={
                    "type_scores": cls.type_scores,
                    "signals": cls.signals,
                    "subject": cls.subject,
                    "attribute": cls.attribute,
                    "value": cls.value,
                    "extraction": cls.extraction,
                    "entities": cls.entities,
                    "relation": list(cls.relation) if cls.relation else None,
                    "temporal": cls.temporal,
                },
                **kw,
            )

        # ---------------- scores ---------------------------------------
        type_strength = max(cls.type_scores.values()) if cls.type_scores else 0.0
        relevance = cls.informativeness * (0.6 + 0.4 * type_strength)
        if cand.importance is not None:
            relevance = max(relevance, cand.importance)
        confidence = trust
        if cls.hedged:
            confidence *= 0.55
        if rep.unverifiable:
            confidence *= 0.6
            flags.append("unverifiable_claim")
        if cand.confidence is not None:
            confidence = min(confidence, cand.confidence) if cand.confidence < confidence else (confidence + cand.confidence) / 2
        durability = DURABILITY.get(cls.memory_type, 0.6)
        if cls.temporal:
            durability = min(durability, 0.15)
        utility = 0.5 * relevance + 0.3 * durability + 0.2 * (1.0 if cls.extraction != "none" else 0.4)
        scores = {
            "relevance": relevance, "utility": utility, "confidence": confidence, "durability": durability,
            "redundancy": 0.0, "privacy_risk": rep.privacy_risk, "injection_risk": rep.injection_risk,
            "source_trust": trust,
        }
        reasons.append(f"classified as {cls.memory_type} (type scores {cls.type_scores})")
        reasons.append(f"source '{cand.source_type}' has trust {trust:.2f}")

        # ---------------- 1. hard safety rejections --------------------
        if rep.secrets:
            flags.append("secret_detected")
            reasons.append(f"contains secret material ({', '.join(rep.secrets)}): secrets are never stored")
            return result("DISCARD")
        if rep.injection:
            flags.append("prompt_injection")
            flags.append("poisoning_attempt")
            reasons.append(
                f"instruction-like/injection content detected ({', '.join(rep.injection)}): memory is data, "
                "not instructions — rejected to prevent memory poisoning"
            )
            return result("DISCARD")

        # ---------------- 2. relevance filter --------------------------
        if cls.is_filler:
            reasons.append("filler / small talk carries no durable information")
            return result("DISCARD")
        if relevance < s.min_relevance:
            reasons.append(f"relevance {relevance:.2f} below threshold {s.min_relevance:.2f}")
            return result("DISCARD")

        if rep.pii:
            flags.append("pii_redacted")
            reasons.append(f"personal data redacted before storage: {', '.join(rep.pii)}")

        # ---------------- 3. redundancy (exact / near duplicate) ------
        sims = self.vector.search(rep.redacted_text, limit=5)
        top = None
        for mid, sim in sims:
            m = self.structured.get(mid)
            if m and m["status"] in ("active", "conflicted", "pending_confirmation"):
                top = (m, sim)
                break
        if top:
            scores["redundancy"] = max(0.0, top[1])
        if top and (top[1] >= s.duplicate_threshold or normalize(top[0]["content"]) == normalize(rep.redacted_text)):
            m = top[0]
            same_fact = not (cls.subject and m.get("subject") == cls.subject and m.get("attribute") == cls.attribute
                             and normalize(m.get("value") or "") != normalize(cls.value or ""))
            if same_fact:
                reasons.append(f"near-duplicate of {m['id']} (similarity {top[1]:.2f} ≥ {s.duplicate_threshold}) → reinforce instead of duplicating")
                return result("MERGE", target_memory_id=m["id"])

        # ---------------- 4. fact update / contradiction -------------
        if cls.subject and cls.attribute and cls.value and cls.attribute not in MULTI_VALUED:
            existing = self.structured.find_fact(cls.subject, cls.attribute)
            for old in existing:
                if normalize(old.get("value") or "") == normalize(cls.value):
                    reasons.append(f"same fact already stored as {old['id']} → merge/reinforce")
                    return result("MERGE", target_memory_id=old["id"])
            if existing:
                old = existing[0]
                reasons.append(
                    f"existing fact {old['id']}: ({cls.subject} | {cls.attribute} | {old.get('value')}) differs from new value '{cls.value}'"
                )
                if trust + 0.15 < float(old["source_trust"]) and not (cand.source_type == old.get("source_type")):
                    flags.append("low_trust_override")
                    flags.append("possible_false_memory")
                    reasons.append(
                        f"lower-trust source ({trust:.2f}) contradicts higher-trust memory ({old['source_trust']:.2f}) → quarantined, conflict flagged"
                    )
                    return result("FLAG_CONFLICT", target_memory_id=old["id"], conflict_kind="low_trust_override")
                if cls.change_marker:
                    reasons.append("explicit change marker → supersede old value (old version kept in history)")
                    return result("UPDATE", target_memory_id=old["id"])
                reasons.append("no change marker and comparable trust → ambiguous contradiction, flagged for resolution")
                return result("FLAG_CONFLICT", target_memory_id=old["id"], conflict_kind="value_conflict")

        related = [mid for mid, sim in sims if s.merge_threshold <= sim < s.duplicate_threshold][:3]

        # ---------------- 5. temporary memory -------------------------
        hours = cand.ttl_hours or cls.expires_in_hours
        if hours is None and cls.memory_type == "working":
            hours = s.default_temporary_hours
        if hours is not None:
            reasons.append(f"short-lived information → TEMPORARY, expires in {hours:g}h")
            return result("TEMPORARY", expires_at=expiry_from(hours, now), related_ids=related)

        # ---------------- 6. confidence gate --------------------------
        if confidence < s.confirmation_threshold:
            reasons.append(f"confidence {confidence:.2f} below {s.confirmation_threshold:.2f} → needs confirmation before use")
            return result("NEEDS_CONFIRMATION", related_ids=related)

        reasons.append(f"relevant ({relevance:.2f}), durable ({durability:.2f}), confident ({confidence:.2f}) → store")
        return result("STORE", related_ids=related)
