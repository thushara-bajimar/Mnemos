"""Context-strategy comparison: full history vs. summary vs. selected memory.

A deterministic synthetic conversation (seeded RNG) mixes 24 *gold facts*
(6 of which are later updated) with small talk, filler and distractor
statements. 24 questions have ground-truth answers (the *latest* value).

Strategies, each evaluated at budgets 500 / 1,000 / 2,000 / 5,000 tokens:

* **full_history** – the raw transcript. If it exceeds the budget, the most
  recent turns that fit are kept (a sliding window, as a real agent would do).
* **summary** – a rule-based extractive summary (filler dropped, statements
  compressed to extracted facts where possible), then truncated to the budget
  keeping the most recent lines.
* **selected** – Mnemos: the transcript is ingested through the decision engine
  once; each question then receives a hybrid-retrieved, budgeted context.

Metrics (all measured, nothing estimated except where the tokenizer says so):

* ``answer_support`` – fraction of questions whose expected (latest) answer
  string appears in the context. A *necessary* condition for a downstream LLM
  to answer correctly; it is **not** an LLM accuracy measurement.
* ``stale_risk`` – fraction of contexts that contain an outdated value of the
  asked fact (could mislead a model).
* ``avg_tokens`` – mean tokens actually sent per question.
* ``latency_ms`` – mean time to build the context.
"""
from __future__ import annotations

import random
import tempfile
import time
from pathlib import Path

from ..core.classifier import classify
from ..core.tokenizer import count_tokens, info as tok_info

PEOPLE = ["Ana", "Ben", "Chen", "Dara", "Eli", "Farah", "Gus", "Hana"]
CITIES = ["Lisbon", "Oslo", "Nairobi", "Lima", "Hanoi", "Dublin", "Quito", "Perth", "Tunis", "Riga"]
PROJECTS = ["Atlas", "Borealis", "Cobalt", "Delta", "Ember", "Falcon"]
LANGS = ["Rust", "Go", "Kotlin", "Python", "Elixir", "Scala"]
DATES = ["March 3", "April 9", "May 21", "June 14", "July 2", "August 30", "September 8", "October 12"]
DBS = ["PostgreSQL", "MySQL", "MongoDB", "SQLite", "Cassandra", "Redis"]

FILLER = ["ok", "thanks!", "lol", "sounds good", "hmm", "cool", "got it", "nice weather today, how are you",
          "brb, lunch now", "haha yes", "sure", "alright"]
ACTORS = ["Ivo", "Jun", "Kemi", "Lars", "Mina", "Noor", "Omar", "Pia", "Raj", "Sven"]
ACTIONS = ["reviewed", "refactored", "commented on", "tested", "documented", "demoed", "paired on", "estimated",
           "triaged", "renamed"]
THINGS = ["the login page", "the search filter", "the export button", "the onboarding email", "the audit log",
          "the settings panel", "the CSV importer", "the billing widget", "the help center", "the sidebar layout",
          "the retry logic", "the dark theme", "the cache warmer", "the release notes", "the error banner"]
WHEN = ["on Monday", "on Tuesday", "this afternoon", "after standup", "before lunch", "last sprint", "during the demo",
        "in the retro", "over the weekend", "on Thursday"]
SMALLTALK = ["I watched a documentary about whales last night.", "The coffee machine on the third floor is broken again.",
             "Someone left an umbrella in the meeting room.", "The quarterly all-hands has a pizza lunch.",
             "There is a new bakery near the station.", "The parking garage closes early on Sundays."]


def build_dataset(seed: int = 7, n_noise: int = 1400):
    """Return (turns, qa). Deterministic for a given seed."""
    rng = random.Random(seed)
    facts = []
    for i, p in enumerate(PEOPLE):
        c1, c2 = rng.sample(CITIES, 2)
        facts.append({"key": p, "stmt": f"{p} lives in {c1}.", "q": f"Where does {p} live?", "a": c1,
                      "upd": f"Actually, {p} moved to {c2} now." if i < 3 else None, "a2": c2 if i < 3 else None})
    for i, pr in enumerate(PROJECTS):
        d1, d2 = rng.sample(DATES, 2)
        facts.append({"key": pr, "stmt": f"The deadline for Project {pr} is {d1}.", "q": f"What is the deadline for Project {pr}?",
                      "a": d1, "upd": f"Correction: the deadline for Project {pr} is now {d2}." if i < 3 else None,
                      "a2": d2 if i < 3 else None})
        facts.append({"key": pr, "stmt": f"Project {pr} is written in {LANGS[i]}.", "q": f"What language is Project {pr} written in?",
                      "a": LANGS[i], "upd": None, "a2": None})
    for i, pr in enumerate(PROJECTS[:4]):
        facts.append({"key": pr, "stmt": f"Project {pr} uses {DBS[i]} as its database.", "q": f"Which database does Project {pr} use?",
                      "a": DBS[i], "upd": None, "a2": None})
    facts = facts[:24]
    turns: list[str] = []
    for _ in range(n_noise):
        r = rng.random()
        if r < 0.45:
            turns.append(rng.choice(FILLER))
        elif r < 0.55:
            turns.append(rng.choice(SMALLTALK))
        else:
            turns.append(f"{rng.choice(ACTORS)} {rng.choice(ACTIONS)} {rng.choice(THINGS)} {rng.choice(WHEN)}.")
    positions = sorted(rng.sample(range(len(turns)), len(facts)))
    for off, (pos, f) in enumerate(zip(positions, facts)):
        turns.insert(pos + off, f["stmt"])
    for f in facts:
        if f["upd"]:
            turns.insert(rng.randint(len(turns) * 3 // 4, len(turns)), f["upd"])
    qa = [{"q": f["q"], "key": f["key"], "answer": f["a2"] or f["a"], "stale": f["a"] if f["a2"] else None} for f in facts]
    return turns, qa


def _fit_recent(lines: list[str], budget: int) -> str:
    out: list[str] = []
    used = 0
    for line in reversed(lines):
        t = count_tokens(line) + 1
        if used + t > budget:
            break
        out.append(line)
        used += t
    return "\n".join(reversed(out))


def summarize(turns: list[str]) -> list[str]:
    lines = []
    for t in turns:
        c = classify(t)
        if c.is_filler or c.informativeness < 0.3:
            continue
        if c.subject and c.attribute and c.value:
            lines.append(f"{c.subject} {c.attribute}: {c.value}")
        else:
            lines.append(t)
    return list(dict.fromkeys(lines))


def _score(ctx: str, qa: dict) -> tuple[bool, bool]:
    low = ctx.lower()
    supported = qa["answer"].lower() in low
    # stale = an outdated value of *this* fact appears on a line about the same subject
    stale = bool(qa["stale"]) and any(qa["stale"].lower() in ln and qa["key"].lower() in ln for ln in low.splitlines())
    return supported, stale


def compare_synthetic(budgets=(500, 1000, 2000, 5000), seed: int = 7) -> dict:
    from ..config import Settings
    from ..engine import Mnemos
    from ..services.decision import Candidate

    turns, qa = build_dataset(seed)
    transcript = [f"user: {t}" for t in turns]
    full_tokens = count_tokens("\n".join(transcript))
    summary_lines = summarize(turns)
    summary_tokens = count_tokens("\n".join(summary_lines))

    tmp = tempfile.mkdtemp(prefix="mnemos_ctx_")
    eng = Mnemos(Settings(data_dir=Path(tmp)))
    t0 = time.perf_counter()
    actions: dict[str, int] = {}
    for t in turns:
        a = eng.memory.ingest(Candidate(content=t, source_type="user", session_id="bench"))["decision"]["action"]
        actions[a] = actions.get(a, 0) + 1
    ingest_ms = (time.perf_counter() - t0) * 1000

    rows = []
    for b in budgets:
        for strat in ("full_history", "summary", "selected"):
            sup = stale = 0
            toks = []
            lat = []
            for item in qa:
                s0 = time.perf_counter()
                if strat == "full_history":
                    ctx = _fit_recent(transcript, b)
                elif strat == "summary":
                    ctx = _fit_recent(summary_lines, b)
                else:
                    eng.invalidate_cache()  # measure real retrieval latency, not cache hits
                    ctx = eng.retriever.assemble(item["q"], budget=b)["context"]
                lat.append((time.perf_counter() - s0) * 1000)
                toks.append(count_tokens(ctx))
                s, st = _score(ctx, item)
                sup += s
                stale += st
            n = len(qa)
            rows.append({
                "strategy": strat, "budget": b, "answer_support": round(sup / n, 3), "stale_risk": round(stale / n, 3),
                "avg_tokens": round(sum(toks) / n, 1), "max_tokens": max(toks), "within_budget": max(toks) <= b,
                "latency_ms": round(sum(lat) / n, 3),
            })
    stored = eng.db.one("SELECT COUNT(*) n FROM memories WHERE status='active'")["n"]
    eng.close()
    return {
        "dataset": {"turns": len(turns), "questions": len(qa), "gold_facts": 24, "updated_facts": 6, "seed": seed,
                    "full_history_tokens": full_tokens, "summary_tokens": summary_tokens,
                    "mnemos_active_memories": stored, "mnemos_ingest_ms": round(ingest_ms, 1),
                    "mnemos_decisions": actions},
        "rows": rows, **tok_info(),
        "note": "answer_support = expected latest answer string present in context (necessary, not sufficient, "
                "for a model to answer). No LLM was called.",
    }


def compare_live(engine, query: str, budgets: list[int]) -> dict:
    """Compare strategies on the *live* memory store for an arbitrary query.

    Mnemos does not retain raw conversation history (privacy by design), so the
    'full' baseline here is a dump of every active memory, and 'summary' is
    their compact fact form — both truncated to the budget like the selected
    strategy.
    """
    mems = engine.db.query("SELECT * FROM memories WHERE status IN ('active','conflicted') ORDER BY created_at")
    full_lines = [f"- {m['content']}" for m in mems]
    summ_lines = [f"- {m['subject']} {m['attribute']}: {m['value']}" if m["subject"] and m["value"] else f"- {m['content'][:120]}"
                  for m in mems]
    from ..core.text import content_terms

    qterms = set(content_terms(query))

    def cov(ctx: str) -> float:
        if not qterms:
            return 0.0
        cterms = set(content_terms(ctx))
        return round(len(qterms & cterms) / len(qterms), 3)

    out = []
    for b in budgets:
        for name, lines in (("full_dump", full_lines), ("summary", summ_lines)):
            t0 = time.perf_counter()
            ctx = _fit_recent(lines, b)
            out.append({"strategy": name, "budget": b, "tokens": count_tokens(ctx), "items": ctx.count("\n- ") + (1 if ctx else 0),
                        "query_term_coverage": cov(ctx), "latency_ms": round((time.perf_counter() - t0) * 1000, 3)})
        r = engine.retriever.assemble(query, budget=b)
        out.append({"strategy": "selected", "budget": b, "tokens": r["tokens_used"], "items": len(r["included"]),
                    "query_term_coverage": cov(r["context"]), "latency_ms": r["latency_ms"]})
    return {"query": query, "rows": out, "total_active_memories": len(mems),
            "full_dump_tokens": count_tokens("\n".join(full_lines)), **tok_info()}
