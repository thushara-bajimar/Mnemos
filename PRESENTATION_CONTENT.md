# Mnemos: Presentation Content (11 slides)

All numbers on these slides come from `docs/results/latest_eval.json`, the measured run of the
evaluation lab. Visuals reference files in `docs/images/`.

---

## Slide 1: Title

**Mnemos**
*Memory with Meaning. Context with Control.*

Knowledge Brain: memory that knows what to keep and when to forget.

* A local-first memory layer for AI agents, built with FastAPI, SQLite and React.
* **Visual:** the logo mark "M", with a faint background screenshot of `docs/images/overview.png`.

**Speaker note:** "Agents remember too much, too little, or the wrong things. Mnemos decides, and it can explain every decision."

---

## Slide 2: The problem

Agent memory today fails in eight ways:

| Failure | Consequence |
|---|---|
| Stores everything | Noise, secrets and small talk end up in memory |
| Silent overwrite | Contradictions lost, stale facts served |
| Weak retrieval | Misses paraphrases or exact facts |
| Whole-history prompts | Token waste, and still truncated |
| No provenance | "Where did this come from?" has no answer |
| Fake forgetting | Data survives in indexes, files and free pages |
| Poisoning | Injected text becomes trusted "memory" |
| Siloed agents | Handover loses context |

**Visual:** eight icons in a 4×2 grid.

---

## Slide 3: Motivation and existing limitations

* Plain vector stores have no notion of truth, time, trust or deletion.
* Summaries compress, but they lose detail and keep outdated values.
* Full-history windows forget early facts once the window slides past them.
* **Measured on our dataset:** a 500-token window of the history contained the answer for only **12.5%** of questions.

**Visual:** a small line chart (`docs/images/charts/context_support.png`) with the grey and orange lines highlighted.

---

## Slide 4: Proposed solution

Mnemos asks six questions of every piece of information:

1. **Keep it?** STORE · TEMPORARY · DISCARD
2. **What is it?** episodic · semantic · procedural · preference · working · relational
3. **Where should it live?** structured · keyword · vector · graph · file
4. **Is it new, a repeat or a contradiction?** UPDATE · MERGE · FLAG_CONFLICT · NEEDS_CONFIRMATION
5. **What does this task need, within N tokens?** hybrid retrieval and budgeted context
6. **How do we prove it's gone?** verified forgetting

**Visual:** six numbered chips arranged in a circle.

---

## Slide 5: Architecture

* Three agents (Atlas: Python SDK; Bolt: JSON tools; Relay: Node.js REST) and the dashboard all call one FastAPI API and ToolGateway.
* The pipeline: safety scan → classifier → decision engine → router.
* Services: MemoryService · Retriever · ForgettingService.
* Five stores in one SQLite file (WAL, `secure_delete`), plus Markdown files.

**Visual:** `docs/images/charts/architecture.png`, full width.

---

## Slide 6: The memory decision mechanism

* **Scores:** relevance, utility, confidence, durability, redundancy, privacy risk, injection risk, source trust (user 0.9 … web 0.4).
* **Ordered policy:** secrets/injection → DISCARD; filler → DISCARD; duplicate → MERGE; same fact with a change marker → UPDATE; contradiction → FLAG_CONFLICT (low-trust source → quarantine); time cue → TEMPORARY; low confidence → NEEDS_CONFIRMATION; otherwise → STORE.
* **Examples from the live demo:**
  * "ok thanks!" → DISCARD
  * "My password is …" → DISCARD (secret)
  * "Actually, the deadline is now Feb 3" → UPDATE
  * Web: "budget is 900000" → FLAG_CONFLICT (quarantined)

**Visual:** `docs/images/decision.png`, cropped to the scores and reasons panel.

---

## Slide 7: Storage and provenance

* Five functional strategies, each benchmarked on 220 memories and 63 labelled queries:

| Strategy | R-precision | MRR | Query ms |
|---|---|---|---|
| keyword (FTS5) | 0.595 | 0.775 | 0.09 |
| vector | 0.821 | 0.897 | 0.06 |
| graph | 0.333 | 0.627 | 0.12 |
| **hybrid (Mnemos)** | **0.976** | **1.000** | 4.60 |

* Provenance on every memory: source, agent, session, method, confidence, versions (`supersedes`), derived memories (`derived_from`).

**Visual:** `docs/images/charts/storage_quality.png`, with a small inset of the provenance drawer from `docs/images/explorer.png`.

---

## Slide 8: Retrieval and token efficiency

* Hybrid score: 0.35 semantic + 0.30 keyword + 0.20 structured + 0.15 graph, multiplied by confidence, importance, recency, status, task and intent.
* Every answer has a status: **answered · conflicting · low_confidence · deleted · expired · unknown**. Mnemos never guesses.
* Context is assembled inside a hard budget, counted with the real `cl100k_base` tokenizer.
* **Result** (1,430-turn conversation of 12,437 tokens; 24 questions):

| Budget | Full history | Summary | **Mnemos** |
|---|---|---|---|
| 500 | 12.5% | 16.7% | **100%** (404 tokens) |
| 5,000 | 75% | 83% | **100%** (546 tokens) |

**Visual:** `docs/images/charts/context_tokens.png`.

---

## Slide 9: Forgetting and privacy

* Two-phase deletion: plan → confirm token → execute → verify → audit.
* Scopes: id, topic, entity or source; cascades to derived memories and older versions.
* Removed from five stores, provenance, revisions, links, task and handover copies, logs and the cache.
* Verification checks every store **and scans the raw database, WAL and file bytes**.
* Finding: with SQLite `secure_delete` OFF, deleted text **survived in the file**; with it ON, it was gone.
* The audit keeps counts and salted hashes only, so Mnemos can still answer "this was deleted".

**Visual:** `docs/images/forgetting.png`.

---

## Slide 10: Agent interoperability and handover

* Atlas (in-process SDK), Bolt (JSON tool calls only) and Relay (separate Node.js process over REST) share one memory.
* The handover package holds the task, progress, decisions, constraints, unfinished steps, memories with sources, a budgeted context, a token budget and a SHA-256 checksum.
* **Live demo result:** handover completed at 993 of 1,000 tokens. Steps were done by Atlas, Atlas, Bolt, Bolt. Bolt then recalled "December 15" from shared memory.
* A tampered package is rejected; deleted memories are flagged as stale.

**Visual:** `docs/images/handover.png` beside `docs/images/agents.png`.

---

## Slide 11: Results, limitations and conclusion

**Results**

* 53 of 53 evaluation scenarios passed (12 categories).
* 95 backend tests and 4 frontend tests pass, including a live server with the Node.js agent.
* 100% answer support at 500 tokens, versus 12.5% for a history window.

**Honest limitations**

* Rule-based extraction (English patterns, no coreference).
* Lexical-semantic embeddings, not a neural model.
* Synthetic evaluation written by the same authors as the rules.
* Deterministic agents.
* Deletion cannot reach external backups.

**Next steps:** LLM extractor with a rules fallback, neural embeddings with an ANN index, an MCP server, and public benchmarks.

**Conclusion:** memory that is selective, explainable, verifiable and frugal.

**Visual:** `docs/images/evaluation.png`, faded.
