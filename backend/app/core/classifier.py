"""Memory classification and fact extraction.

Deterministic, explainable rules classify a candidate into one of six memory
types and extract a ``(subject, attribute, value)`` triple when the text states
a fact, preference or relationship. Every rule that fires is recorded as a
human-readable *signal* so the UI can show *why* a classification was made.

Memory types
------------
episodic    – something that happened (meetings, events, decisions taken)
semantic    – a general/stable fact about the world, project or person
procedural  – how to do something (steps, commands, runbooks)
preference  – what someone likes/dislikes/wants
working     – short-lived task state ("currently", "for now", "this session")
relational  – relationships between entities ("A reports to B")
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .text import STOPWORDS, content_terms

MEMORY_TYPES = ["episodic", "semantic", "procedural", "preference", "working", "relational"]

FILLER = re.compile(
    r"^(?:\s*(ok(ay)?|k|thanks?( you)?|thx|ty|cool|nice|great|lol|haha+|hmm+|yes|no|yep|nope|sure|got it|"
    r"hi|hello|hey|bye|good (morning|night|evening)|sounds good|alright|right|wow|:\)|:\(|👍|🙂)[\s!.,?]*)+$",
    re.I,
)
SMALLTALK = re.compile(
    r"\b(how are you|nice weather|what'?s up|just saying|never mind|nvm|brb|lunch now|be right back)\b", re.I
)
HEDGE = re.compile(r"\b(maybe|perhaps|i think|i guess|probably|might|not sure|possibly|rumou?r|apparently|seems like)\b", re.I)
CHANGE = re.compile(
    r"\b(now|changed|change[sd]? to|moved|switched|no longer|instead|actually|updated?|correction|from now on|anymore|replaced)\b",
    re.I,
)
TEMPORAL_SHORT = [
    (re.compile(r"\b(for (the )?next (\d+) hours?)\b", re.I), "hours"),
    (re.compile(r"\b(this session|right now|for now|temporarily|currently|at the moment|today|tonight|this afternoon|this morning)\b", re.I), "session"),
    (re.compile(r"\b(until tomorrow|by tomorrow|this week)\b", re.I), "days"),
]
EPISODIC = re.compile(
    r"\b(yesterday|last (week|month|night|year)|on (monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"we (met|decided|agreed|discussed|shipped|launched|released)|happened|attended|visited|"
    r"meeting (with|on)|called|talked|went|incident|outage)\b",
    re.I,
)
PROCEDURAL = re.compile(
    r"(\bto [a-z]+[ ,].{0,60}\b(run|use|execute|click|open|type|call)\b|\bsteps?\b|\bfirst\b.*\bthen\b|\brun\b.{0,60}\bthen\b|"
    r"\bhow to\b|\brunbook\b|\bprocedure\b|^\s*(run|execute|install|deploy|use)\b|`[^`]+`|\bcommand\b)",
    re.I,
)
PREFERENCE = re.compile(
    r"\b(i|we|he|she|they|[A-Z][a-z]+)\s+(really\s+)?(prefer|prefers|like|likes|love|loves|hate|hates|dislike|dislikes|"
    r"enjoy|enjoys|want|wants|favou?rite)\b|\bfavou?rite\b|\bprefer(red|ence)?\b|\bdon'?t like\b|\bis allergic\b",
    re.I,
)
RELATIONAL = re.compile(
    r"\b(reports to|works with|is (the )?(manager|lead|owner|member|part|parent|child|sibling|friend|colleague) of|"
    r"belongs to|depends on|is owned by|manages|collaborates with|is married to|is a member of|is part of)\b",
    re.I,
)
WORKING = re.compile(
    r"\b(currently working on|i'?m working on|in progress|next step|todo|to-do|for now|this session|right now|scratch)\b",
    re.I,
)

# ---------------- fact extraction patterns (subject, attribute, value) ----------
FACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(?:my|our)\s+(?P<attr>[\w\s]{2,40}?)\s+(?:is|are)\s+(?:now\s+)?(?P<val>.+)$", re.I), "possessive"),
    (re.compile(r"^(?P<subj>[A-Z][\w\-\. ]{0,40}?)'s\s+(?P<attr>[\w\s]{2,40}?)\s+(?:is|are|was)\s+(?:now\s+)?(?P<val>.+)$"), "genitive"),
    (re.compile(r"^the\s+(?P<attr>[\w\s]{2,40}?)\s+(?:for|of)\s+(?P<subj>[\w\-\. ]{1,40}?)\s+(?:is|are|was)\s+(?:now\s+)?(?:changed to\s+|moved to\s+)?(?P<val>.+)$", re.I), "attr_of"),
    (re.compile(r"^(?P<subj>[\w\-\. ]{1,40}?)\s+(?P<attr>reports to|works with|depends on|belongs to|manages|is owned by|is part of|is a member of)\s+(?P<val>.+)$", re.I), "relation"),
    (re.compile(r"^(?P<subj>i|we|[A-Z][\w\-]*(?: [A-Z][\w\-]*)?)\s+(?:now\s+|really\s+|still\s+)?(?P<attr>prefers?|likes?|loves?|hates?|dislikes?|wants?|uses?|lives? in|is based in|works at|moved to|switched to)\s+(?P<val>.+)$", re.I), "verb"),
    (re.compile(r"^the\s+(?P<attr>[\w ]{2,30}?)\s+(?:is|are)\s+(?:now\s+)?(?P<val>.+)$", re.I), "the_attr"),
    (re.compile(r"^(?P<subj>[\w\-\. ]{1,40}?)\s+(?:is|are)\s+(?:now\s+)?(?:written in|built (?:with|on)|hosted on|using|scheduled for|due on|due|set to)\s+(?P<val>.+)$", re.I), "is_prop"),
]

VERB_ATTR = {
    "prefer": "preference", "prefers": "preference", "like": "preference", "likes": "preference",
    "love": "preference", "loves": "preference", "want": "preference", "wants": "preference",
    "hate": "dislike", "hates": "dislike", "dislike": "dislike", "dislikes": "dislike",
    "use": "uses", "uses": "uses", "lives in": "location", "live in": "location", "is based in": "location",
    "moved to": "location", "works at": "employer", "switched to": "uses",
}

ENTITY_RE = re.compile(r"\b([A-Z][a-zA-Z0-9]+(?:[ \-][A-Z][a-zA-Z0-9]+)*)\b")
COMMON_CAPS = {"I", "The", "A", "An", "We", "My", "Our", "It", "This", "That", "To", "First", "Then", "On",
               "In", "At", "For", "Use", "Run", "Remember", "Note", "Please", "Also", "Actually", "Today",
               "Yesterday", "Maybe", "Ignore", "From", "If", "When", "Always", "Never", "You", "He", "She", "They",
               "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Correction", "Now",
               "Steps", "Step", "Currently", "Our", "Its", "His", "Her", "Their", "So", "But", "And", "Or",
               "Apparently", "Probably", "Perhaps", "Install", "Execute", "Deploy", "Next", "Last", "Some"}


@dataclass
class Classification:
    memory_type: str
    type_scores: dict[str, float]
    signals: list[str] = field(default_factory=list)
    subject: str | None = None
    attribute: str | None = None
    value: str | None = None
    extraction: str = "none"
    entities: list[str] = field(default_factory=list)
    relation: tuple[str, str, str] | None = None
    is_filler: bool = False
    hedged: bool = False
    change_marker: bool = False
    temporal: str | None = None
    expires_in_hours: float | None = None
    informativeness: float = 0.0


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().strip(".!?,;:\"'")).strip()


def _norm_subject(s: str) -> str:
    s = _clean(s).lower()
    return {"i": "user", "me": "user", "my": "user", "we": "team", "our": "team", "us": "team"}.get(s, s)


def extract_entities(text: str) -> list[str]:
    ents: list[str] = []
    for m in ENTITY_RE.finditer(text):
        e = m.group(1)
        parts = [p for p in re.split(r"[ \-]", e) if p not in COMMON_CAPS]
        if not parts:
            continue
        e = " ".join(parts)
        if e.lower() in STOPWORDS or len(e) < 2:
            continue
        if e not in ents:
            ents.append(e)
    return ents[:12]


def extract_fact(text: str) -> tuple[str | None, str | None, str | None, str]:
    sent = _clean(re.split(r"(?<=[.!?])\s", text.strip())[0])
    sent = re.sub(r"^(actually|correction|update|note|fyi|remember( that)?|btw|so|also)[,:]?\s+", "", sent, flags=re.I)
    sent = re.sub(r"^(maybe|perhaps|probably|possibly|apparently|i think|i guess|i believe|rumou?r has it)[,:]?\s+(that\s+)?", "", sent, flags=re.I)
    sent = re.sub(r"^(?:as of|since|starting|from)\s+\w+[\w ,]{0,20}?,\s*", "", sent, flags=re.I)
    for pat, kind in FACT_PATTERNS:
        m = pat.match(sent)
        if not m:
            continue
        g = m.groupdict()
        val = _clean(g.get("val") or "")
        val = re.sub(r"\s+(now|anymore|instead|from now on)$", "", val, flags=re.I)
        val = re.sub(r"^(now\s+)", "", val, flags=re.I)
        if not val or len(val) > 120:
            continue
        if kind == "possessive":
            subj = "user" if sent.lower().startswith("my") else "team"
            attr = _clean(g["attr"]).lower()
        elif kind == "verb":
            subj = _norm_subject(g["subj"])
            verb = _clean(g["attr"]).lower()
            attr = VERB_ATTR.get(verb, verb)
        elif kind == "the_attr":
            subj = "general"
            attr = _clean(g["attr"]).lower()
        elif kind == "relation":
            subj = _norm_subject(g["subj"])
            attr = _clean(g["attr"]).lower()
        elif kind == "is_prop":
            subj = _norm_subject(g["subj"])
            low = sent.lower()
            attr = next((a for a in ["written in", "built with", "built on", "hosted on", "using",
                                       "scheduled for", "due on", "due", "set to"] if a in low), "property")
            attr = {"due on": "deadline", "due": "deadline", "scheduled for": "schedule", "built on": "built with",
                    "using": "uses"}.get(attr, attr)
        else:
            subj = _norm_subject(g.get("subj") or "user")
            attr = _clean(g["attr"]).lower()
        attr = re.sub(r"^(favou?rite)\s+", r"favorite ", attr)
        if subj in STOPWORDS and subj not in ("user", "team"):
            continue
        return subj, attr, val, kind
    return None, None, None, "none"


def classify(text: str, now: datetime | None = None) -> Classification:
    now = now or datetime.now(timezone.utc)
    t = text.strip()
    scores = {k: 0.0 for k in MEMORY_TYPES}
    signals: list[str] = []

    is_filler = bool(FILLER.match(t)) or (len(t) < 4)
    if SMALLTALK.search(t) and len(content_terms(t)) < 6:
        is_filler = True
    if is_filler:
        signals.append("filler/small-talk pattern matched")

    if EPISODIC.search(t):
        scores["episodic"] += 0.7
        signals.append("episodic cue (event/time reference)")
    if PROCEDURAL.search(t):
        scores["procedural"] += 0.75
        signals.append("procedural cue (steps/commands/how-to)")
    if PREFERENCE.search(t):
        scores["preference"] += 0.8
        signals.append("preference verb (prefer/like/favourite…)")
    if RELATIONAL.search(t):
        scores["relational"] += 0.85
        signals.append("relationship phrase between entities")
    if WORKING.search(t):
        scores["working"] += 0.7
        signals.append("working-memory cue (current task state)")

    subj, attr, val, kind = extract_fact(t)
    if kind != "none":
        signals.append(f"fact extracted via '{kind}' pattern: ({subj} | {attr} | {val})")
        if kind == "relation":
            scores["relational"] += 0.4
        elif attr in ("preference", "dislike") or (attr or "").startswith("favorite"):
            scores["preference"] += 0.4
        else:
            scores["semantic"] += 0.6
    if re.search(r"\b(is|are|has|have|was)\b", t, re.I) and not any(v > 0.6 for v in scores.values()):
        scores["semantic"] += 0.45
        signals.append("declarative statement (is/are/has)")
    if not any(scores.values()):
        scores["semantic"] = 0.3
        signals.append("no strong cue: default to semantic")

    temporal = None
    expires = None
    for pat, kind_t in TEMPORAL_SHORT:
        m = pat.search(t)
        if m:
            temporal = m.group(0)
            if kind_t == "hours":
                expires = float(m.group(3))
            elif kind_t == "session":
                expires = 8.0
            else:
                expires = 36.0
            signals.append(f"temporal validity cue: '{temporal}'")
            break
    if temporal and scores["working"] < 0.7 and not scores["episodic"]:
        scores["working"] += 0.5

    mem_type = max(scores, key=lambda k: scores[k])
    hedged = bool(HEDGE.search(t))
    if hedged:
        signals.append("hedging language lowers confidence")
    change = bool(CHANGE.search(t))
    if change:
        signals.append("change marker (now/moved/actually/no longer…)")

    entities = extract_entities(t)
    relation = None
    if kind == "relation" and subj and val:
        relation = (subj, attr or "related_to", _clean(val).lower())

    terms = content_terms(t)
    informativeness = 0.0 if is_filler else min(1.0, 0.15 + 0.07 * len(set(terms)) + (0.2 if kind != "none" else 0) + 0.05 * len(entities))

    total = sum(scores.values()) or 1.0
    return Classification(
        memory_type=mem_type,
        type_scores={k: round(v / total, 3) for k, v in scores.items()},
        signals=signals,
        subject=subj,
        attribute=attr,
        value=val,
        extraction=kind,
        entities=entities,
        relation=relation,
        is_filler=is_filler,
        hedged=hedged,
        change_marker=change,
        temporal=temporal,
        expires_in_hours=expires,
        informativeness=round(informativeness, 3),
    )


def expiry_from(hours: float | None, now: datetime | None = None) -> str | None:
    if hours is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (now + timedelta(hours=hours)).isoformat(timespec="seconds")
