# Mnemos — Technical Documentation

**Memory with Meaning. Context with Control.**
Version 1.0 · Problem statement: *Knowledge Brain — Memory That Knows What to Keep and When to Forget*

---

## 1. Introduction

### 1.1 Problem

AI agents build up conversations, decisions, documents, tasks and preferences over time. Simple
memory designs, such as "append everything to a vector store" or "resend the whole history", fail
in predictable ways:

* **Irrelevant storage:** small talk and filler pollute retrieval.
* **Stale and contradictory facts:** old values are returned as if they were still true, and
  conflicting values are silently overwritten.
* **Poor retrieval:** keyword-only search misses paraphrases, and vector-only search misses exact
  facts and relationships.
* **Token waste:** whole histories are sent to the model and still miss the facts that matter.
* **No provenance:** nobody can tell where a "fact" came from.
* **Unreliable forgetting:** deleted data survives in indexes, caches, files and free database pages.
* **Poisoning:** injected instructions or repeated false claims become trusted "memory".
* **No interoperability:** each agent keeps its own private memory, and handing work over loses context.

### 1.2 Objectives

Mnemos decides **what to remember, how to store it, what to retrieve, when to update or reject it,
how to verify its source and how to forget it properly**. It persists across restarts, serves
several distinct agent setups at once, supports real task handover between agents, and measures
its own memory quality and token efficiency.

### 1.3 Design principles

1. **Explainability first.** Every decision, route, ranking and deletion carries human-readable reasons.
2. **Local-first, no paid dependencies.** SQLite, numpy and a local tokenizer are enough.
3. **Memory is data, never instructions.** The system rejects instruction-like input and frames retrieved context as data.
4. **Never silently overwrite.** Updates keep history and contradictions are surfaced.
5. **Honest measurement.** Benchmarks run on real code, estimates are labelled, and limitations are documented.

---

## 2. System architecture

```
 ┌──────────────────────────── Agents / clients ────────────────────────────┐
 │ Atlas (in-process SDK)  Bolt (JSON tool calls)  Relay (Node.js REST)  UI  │
 └───────────────┬───────────────────┬───────────────────┬──────────────────┘
                 │                   │                   │
         MemoryClient          ToolGateway  ◄── POST /api/tools/invoke
                 │                   │                   │
 ┌───────────────▼───────────────────▼───────────────────▼──────────────────┐
 │                         FastAPI application (app/main.py)                 │
 │   validation (Pydantic) · API-key guard · error mapping · CORS            │
 ├───────────────────────────────────────────────────────────────────────────┤
 │                          Mnemos engine (app/engine.py)                    │
 │  safety.scan → classifier.classify → DecisionEngine.decide → router.route │
 │  MemoryService · Retriever · ForgettingService · AgentService · cache     │
 ├───────────────────────────────────────────────────────────────────────────┤
 │ StructuredStore │ KeywordStore │ VectorStore │ GraphStore │ FileStore     │
 │ memories table  │ FTS5 + BM25  │ BLOB+numpy  │ entities/  │ Markdown per  │
 │ + provenance,   │              │ in-memory   │ edges      │ memory        │
 │ revisions, ...  │              │ matrix      │            │               │
 └────────────────────────── SQLite file (WAL, secure_delete) + data/files ──┘
```

### 2.1 Technology stack

| Layer | Technology | Why |
|---|---|---|
| API | Python 3, FastAPI, Pydantic v2, Uvicorn | Typed validation and automatic OpenAPI docs. |
| Storage | SQLite (WAL, FTS5, `secure_delete=ON`) | Zero-ops, transactional, ships with Python. |
| Vectors | numpy matrix plus SQLite BLOB persistence | Fast exact cosine search at this scale, with no server. |
| Tokenizer | `tiktoken` `cl100k_base`, with a labelled fallback estimator | Real token counts for budgets. |
| Frontend | React 18, Vite 5, TypeScript, Tailwind CSS 3, Recharts 2 | Typed, fast and responsive. |
| Tests | pytest, FastAPI TestClient, uvicorn subprocess, vitest + jsdom | Unit, API, integration and UI coverage. |
| PDFs | ReportLab and matplotlib | Generated from the Markdown documentation and the measured results. |

### 2.2 Source layout

| Path | Responsibility |
|---|---|
| `backend/app/config.py` | Settings from `MNEMOS_*` environment variables; runtime-tunable thresholds. |
| `backend/app/db.py` | SQLite schema and the thread-safe connection wrapper. |
| `backend/app/engine.py` | Wires the stores and services together; LRU retrieval cache; statistics. |
| `backend/app/core/` | `tokenizer`, `embeddings`, `text`, `classifier`, `safety`, `router`. |
| `backend/app/stores/stores.py` | The five storage strategies. |
| `backend/app/services/` | `decision`, `memory`, `retrieval`, `forgetting`, `agents`. |
| `backend/app/evaluation/` | `scenarios`, `storage_bench`, `context_compare`, `runner`, `demo_data`. |
| `backend/app/main.py` | REST API. |
| `frontend/src/` | Dashboard: 11 pages and shared components. |
| `agents/` | External Node.js and Python REST agents. |

---

## 3. Memory model

### 3.1 Memory types

| Type | Meaning | Example | Typical durability |
|---|---|---|---|
| episodic | Something that happened | "Yesterday we decided to freeze features." | 0.60 |
| semantic | A stable fact | "Project Orion is written in TypeScript." | 0.80 |
| procedural | How to do something | "To deploy, first run migrations, then …" | 0.90 |
| preference | Likes, dislikes and wishes | "I prefer dark mode." | 0.85 |
| working | Short-lived task state | "I'm currently debugging the login bug." | 0.20 |
| relational | A relationship between entities | "Priya reports to Marcus." | 0.80 |

The classifier (`core/classifier.py`) scores every type with regular-expression cue families:
event and time cues, step and command cues, preference verbs, relationship phrases, working-state
cues, and declarative statements. It then normalises the scores. Every cue that fires is recorded
as a *signal*, which the Decision Lab displays.

### 3.2 Fact extraction

A small set of ordered patterns extracts a `(subject, attribute, value)` triple. Examples:

| Input | Pattern | Triple |
|---|---|---|
| "My favorite color is blue" | possessive | (user, favorite color, blue) |
| "The deadline for Project Orion is March 3" | attr_of | (project orion, deadline, March 3) |
| "Priya reports to Marcus" | relation | (priya, reports to, Marcus) |
| "I moved to Berlin" | verb | (user, location, Berlin) |
| "Project Orion is written in Rust" | is_prop | (project orion, written in, Rust) |

Hedging prefixes ("maybe", "I think") and discourse markers ("actually", "correction") are stripped
before matching, but their presence is recorded: hedging lowers confidence, and a change marker
allows an UPDATE. Verbs are normalised, so "lives in" and "moved to" both map to `location`. This
lets a move be recognised as an update of the same attribute.

### 3.3 The memory record

The canonical row in the `memories` table holds: id, content (redacted), type, status, subject,
attribute, value, entities, tags, importance, confidence, source_trust, source_type, reinforcement
count, storage_routes, task, agent, session, created_at and updated_at, `valid_from` and `valid_to`
(temporal validity), expires_at, last access and access count, version, file path, and the id of
the decision that created it.

Statuses: `active`, `superseded`, `conflicted`, `quarantined`, `pending_confirmation`, `expired`.
Deleted memories have no row at all; only a content-free audit entry remains.

---

## 4. The decision engine

`services/decision.py` turns a `Candidate` into a `Decision`. A candidate consists of the content
plus source type, source id and label, agent, session, task, tags, optional confidence, TTL, type
override and `derived_from`. The engine only *reads* storage; `MemoryService` applies the decision.

### 4.1 Scores

| Score | Computation |
|---|---|
| source_trust | system 0.95, user 0.90, document 0.75, agent 0.70, tool 0.60, web 0.40, unknown 0.30 |
| relevance | informativeness × (0.6 + 0.4 × strongest type score). Informativeness grows with the number of distinct content terms, an extracted fact and named entities. |
| confidence | trust × 0.55 if hedged × 0.6 if the claim is unverifiable ("trust me", "guaranteed"), optionally blended with a caller-supplied confidence. |
| durability | the type's prior, capped at 0.15 when a temporal cue is present |
| utility | 0.5·relevance + 0.3·durability + 0.2·(1 if a fact was extracted else 0.4) |
| redundancy | highest cosine similarity to an existing live memory |
| privacy_risk | 1.0 if a secret is present, otherwise 0.35 per PII category |
| injection_risk | 0.6 per injection pattern |

### 4.2 Decision order

1. **Secrets** (passwords, API keys, private keys, card numbers, bearer tokens) → `DISCARD`.
2. **Injection or poisoning patterns** (override instructions, role hijack, system prompt,
   exfiltration, dangerous commands, "always approve/transfer…", script tags) → `DISCARD`, with
   the flags `prompt_injection` and `poisoning_attempt`.
3. **Filler or small talk**, or relevance below `min_relevance` (0.30) → `DISCARD`.
4. **PII** (email, phone) is redacted, flagged `pii_redacted`, and processing continues.
5. **Near-duplicate** (cosine ≥ `duplicate_threshold`, 0.90, or identical normalised text) with
   the same fact and the same entity set → `MERGE`. *The entity check exists because templated
   sentences about different projects are about 0.90 similar but are not duplicates; the
   benchmark revealed this and it was fixed.*
6. **Same subject and attribute, different value**, for single-valued attributes:
   * same value → `MERGE`;
   * the new source's trust + 0.15 < the existing memory's trust, and the source type differs →
     `FLAG_CONFLICT` (kind `low_trust_override`); the new memory is **quarantined**;
   * an explicit change marker ("now", "actually", "moved", "no longer", …) → `UPDATE`;
   * otherwise → `FLAG_CONFLICT` (kind `value_conflict`); both memories become `conflicted`.
   Multi-valued attributes (preference, uses, depends on, …) never conflict.
7. **Temporal cue or working memory** → `TEMPORARY`, with an expiry. "for the next N hours" → N h;
   "today", "for now", "currently" → 8 h; "until tomorrow" or "this week" → 36 h; working memory
   with no cue → `default_temporary_hours` (24 h); an explicit TTL wins over all of these.
8. **Confidence below `confirmation_threshold`** (0.55) → `NEEDS_CONFIRMATION`. The memory is
   stored as `pending_confirmation` and is never used as a confident answer.
9. Otherwise → `STORE`.

### 4.3 Applying decisions (`services/memory.py`)

| Action | Effect |
|---|---|
| STORE / TEMPORARY / NEEDS_CONFIRMATION | Inside a single transaction: insert the canonical row, index it in the routed stores, write a provenance row and revision v1, and add `related_to` and `derived_from` links. |
| MERGE | Add a provenance row. If the source is *independent* (a different source type, id or agent), apply a noisy-OR confidence boost `1-(1-c)(1-0.5·trust)` and increment reinforcement. A repeat from the same source changes nothing (anti-flooding). |
| UPDATE | Mark the old memory `superseded` with `valid_to = now` and remove it from the vector index. Create a new memory with version + 1 and the link `new supersedes old`. Resolve any open conflicts on the old memory. |
| FLAG_CONFLICT | Create the new memory as `conflicted` or `quarantined`, mark the old one `conflicted` (for a value conflict), open a `conflicts` row with an explanation, and add a `conflicts_with` link. |

Every decision is written to the `decisions` table with its scores, reasons, routes, flags and a
SHA-256 hash of the input. A text preview is kept only for non-discarded input, and never when a
secret was detected.

---

## 5. Storage routing and strategies

### 5.1 Routing rules (`core/router.py`)

| Store | Routed when |
|---|---|
| structured | Always. This is the canonical record with status, validity and provenance. |
| keyword | Always, for queryable full-text search. |
| vector | The memory is durable (not temporary). Working memory is kept out of the long-term semantic index. |
| graph | An explicit relation was extracted, or the memory names entities (unless it is temporary). |
| file | The memory is procedural, or the content is longer than 400 characters (treated as a document). |

The route reasons are stored with the decision and shown in the UI.

### 5.2 Strategy implementations

| Strategy | Implementation | Strong for | Weak for |
|---|---|---|---|
| Structured | `memories` table with an index on (subject, attribute); LIKE matching on columns | Exact facts, filters, validity, status | Paraphrases |
| Keyword (queryable) | SQLite FTS5, porter stemming, BM25 | Rare terms; explainable | Synonyms |
| Vector | 512-dimension feature-hashing embeddings; numpy matrix; persisted as BLOBs | Paraphrases, deduplication | Exactness; larger index; must re-embed |
| Graph | `entities`, `edges`, `entity_mentions`; 1-hop expansion | Relationships, "everything about X" | Ranking within an entity |
| File | Markdown with YAML front-matter per memory | Long runbooks; human-readable; portable | Linear scan; rewrite on update |

**Embeddings.** `core/embeddings.py` hashes the following features into 512 dimensions with
signed hashing:

* stemmed content words (weight 1.0);
* word bigrams (0.6);
* character 4-grams (0.25);
* concept features from a small synonym table (0.8), for example database ↔ postgres ↔ sql.

Vectors are L2-normalised. This is a *lexical-semantic* approximation, **not** a neural encoder.
Setting `MNEMOS_EMBEDDER=sentence-transformers` switches to a neural model when one is installed.

---

## 6. Retrieval

### 6.1 Hybrid scoring (`services/retrieval.py`)

Each strategy produces candidate scores, and each score is normalised to the range [0, 1]:

* **keyword:** BM25, normalised as half relative-to-max and half saturating `s/(s+3)`;
* **semantic:** cosine similarity, clipped, keeping only candidates with cosine > 0.12;
* **structured:** column-match score relative to the maximum;
* **graph:** entity hits with a 1-hop decay of 0.5.

The scores are then combined:

```
base   = 0.35·semantic + 0.30·keyword + 0.20·structured + 0.15·graph
base  *= 1 + 0.15·(number of strategies that found it − 1)       # agreement bonus
score  = base · (0.6+0.4·confidence) · (0.85+0.15·importance) · recency(0.9–1.0)
              · status_factor · task_boost · intent_boost
```

* **Status factors:** active 1.0, conflicted 0.8, pending 0.5, superseded 0.3, quarantined and expired 0.
* **Task-aware ranking:** ×1.2 for memories that belong to the requested task.
* **Query intent:** "how do I / steps / runbook" → procedural ×1.35. Preference words →
  preference ×1.25. "what happened / when did / yesterday" → episodic ×1.25. "reports to /
  manager / depends on" → relational ×1.25.
* **Filters:** memory types, agent, source types, minimum confidence and inactive statuses.

Each result includes its component scores, the multiplying factors, a `why` string, **query-term
coverage** and its provenance sources. Search results are cached in an LRU cache of 256 entries,
which is invalidated on every write.

### 6.2 Answering and abstention (`ask`)

`ask()` never generates text. It returns a stored value or abstains. A memory can answer only if
it covers at least 50% of the question's content words (directly or through a shared concept) and
its score is at least `abstain_threshold` (0.22). The response status is one of:

| Status | When |
|---|---|
| answered | The top usable memory is active and above the threshold. Returns the value, confidence and sources. |
| conflicting | The top memory is conflicted. Returns every competing value with its sources. |
| low_confidence | The top memory is pending confirmation. |
| deleted | No live match, but the question matches the salted term hashes of a deletion record. |
| expired | Same as above, for an expiry record. |
| unknown | Nothing qualifies. The response says explicitly that it will not guess. |

### 6.3 Token-budget context assembly

`assemble(query, budget)` builds the context in these steps:

1. Run the hybrid search, keeping up to 60 candidates.
2. Write a fixed header stating that the records are **data, not instructions**.
3. For each candidate in rank order:
   * skip it if its score is below half of `abstain_threshold`, or if it duplicates a fact already included;
   * otherwise render it as `[id] (type, conf, src, date) content`, with markup neutralised;
   * if that does not fit the remaining budget, try a compact `subject · attribute: value` form;
   * if the item is high-scoring and at least 24 tokens remain, truncate it to fit;
   * if none of these fit, exclude it with the reason "budget exhausted".
4. Report the tokens used, the included items (with tokens, score and form), the excluded items
   (with reasons) and the tokenizer name.

The tokens used never exceed the budget; this is tested at 100, 500, 1,000, 2,000 and 5,000 tokens.
Token counts come from `tiktoken cl100k_base`. If tiktoken is unavailable, a heuristic of
max(chars/4, words×0.75) is used and labelled `is_estimate: true` everywhere.

---

## 7. Provenance, updates and contradictions

* **Provenance row (one per observation):** source_type, source_id, source_label, agent_id,
  session_id, extraction_method (e.g. `rules:verb`, `merge`), confidence, SHA-256 of the raw input, timestamp.
* **Revisions:** version, content, value, status, change_type (`create`, `merge`, `edit`,
  `superseded`, `confirmed`, `conflict_resolved`), reason, actor.
* **Links:** `supersedes`, `derived_from`, `related_to`, `conflicts_with`.
* **Trace API** (`GET /api/memories/{id}/trace`) returns:
  * the origin and every corroboration;
  * parents and derived memories;
  * the full version lineage, built by following `supersedes` links in both directions;
  * the stored decision;
  * a natural-language explanation.
* **Temporal validity:** `valid_from` and `valid_to` record the period during which a value was
  current, so superseded facts can still be audited.
* **Conflict resolution:** `keep_a`, `keep_b` or `keep_both`. The rejected side becomes
  `superseded`, is linked, and keeps its history.

**False memories and poisoning.** Mnemos has five layers of defence:

1. Injection patterns are rejected.
2. Trust-weighted contradiction handling quarantines low-trust overrides.
3. Anti-flooding: only independent sources raise confidence.
4. Hedged or unverifiable claims go to confirmation.
5. Retrieved context is labelled and escaped as data.

---

## 8. Forgetting and privacy

### 8.1 Deletion protocol (`services/forgetting.py`)

1. **Plan** (`POST /api/forget/plan`) selects memories by `id`, `topic` (hybrid match), `entity`
   (graph and text) or `source` (source id, agent, session or label). With cascade enabled, it adds
   **derived memories** and **older superseded versions**. It returns every item with the stores
   that currently hold it, plus a single-use confirmation token valid for 10 minutes.
2. **Execute** (`POST /api/forget/execute`) with the token removes the following for each memory:
   * the structured row, the FTS row, the vector row and its in-memory index entry;
   * graph mentions and edges, and any entities left orphaned;
   * provenance, revisions and links;
   * conflicts, and the decision preview;
   * the Markdown file, which is zero-overwritten and then unlinked;
   * copies inside task constraints, decisions and notes;
   * copies inside handover packages, which are redacted and re-sealed with a new checksum and a
     `redactions` note;
   * agent-log text that quotes the memory;
   * the retrieval cache.

   It then runs an FTS5 `optimize` and `PRAGMA wal_checkpoint(TRUNCATE)`.
3. **Verify** checks for any remaining presence in 9 stores plus the cache. It also scans the raw
   bytes of the database, the WAL and the memory files for the first 60 characters of every
   deleted content version. The result is `all_clear` only if both the logical and the physical
   checks pass.
4. **Audit** records the scope, count, stores, verification result, requester and **salted term
   hashes** of the deleted content. It stores no text. The hashes let Mnemos answer "this was
   deleted" without retaining the content.

### 8.2 Expiry

`expire_sweep()` handles temporary memories that have passed their expiry. It removes them from
all indexes and purges the content and every derived field (subject, attribute, value, entities,
tags), leaving a `[expired]` stub. It also deletes their revisions and records an `expiry` audit
entry.

### 8.3 Other privacy measures

* **SQLite `secure_delete=ON`.** The benchmark shows that, without it, deleted text remains in the
  database file; with it, the text is gone.
* **Secrets** are never stored, and **PII** is redacted before storage.
* **Discarded input** is reduced to a hash; the preview is off by default.
* **Agent logs** are redacted through the same safety layer.
* Raw conversations are **not retained**; only the extracted memories are.

**Limitations.** Deletion does not reach:

* backups or copies of the data made outside Mnemos;
* blocks retained by SSD wear-levelling or OS caches (use full-disk encryption);
* data an external agent has already copied elsewhere.

In addition, salted term hashes could be dictionary-tested by an attacker with access to the database.

---

## 9. Agent interoperability and handover

| Agent | Implementation | Integration path |
|---|---|---|
| **Atlas** (planner/researcher) | `AtlasAgent` | In-process Python SDK (`MemoryClient`) |
| **Bolt** (executor) | `BoltAgent` | Serialises JSON `{tool, args}` messages → `ToolGateway` (the same gateway behind `POST /api/tools/invoke`) |
| **Relay** (external) | `agents/node_agent.mjs` | Separate Node.js process using HTTP REST only |
| Python REST agent | `agents/python_rest_agent.py` | Separate Python process using httpx |

**Tools:** `memory.remember`, `memory.search`, `memory.ask`, `memory.context`, `memory.provenance`,
`task.get`, `task.complete_step`, `handover.get`, `handover.accept`, `handover.complete`.
Unknown tools and unregistered agents are rejected.

**Handover package** (stored in `handovers`, JSON):

* package_version, handover_id, task (id, title, goal), from_agent and to_agent;
* progress (the steps already done, with who did them and notes), decisions and constraints;
* unfinished_steps;
* relevant_memories (id, content, type, confidence, status, score and up to two sources);
* a budgeted context string, token_budget, package_tokens, notes and the policy statement;
* a SHA-256 checksum of the canonical JSON.

To respect the budget, the creator drops the lowest-ranked memories first and then shrinks the
context until the whole JSON package fits.

**Accept** verifies four things:

* the addressee is the accepting agent;
* the checksum matches, so a package changed after creation is rejected;
* the status is valid;
* the package is within its budget.

It also re-checks every referenced memory and reports any that have since been deleted or
superseded as stale. The receiving agent then executes the unfinished steps. For each step it asks
memory, gathers evidence, writes a progress memory linked to its evidence with `derived_from`, and
completes the step. Finally it completes the handover with a result report.

---

## 10. API

FastAPI serves interactive OpenAPI documentation at `/docs`. The main groups are:

* **system:** health, stats, settings, seed, reset;
* **memory:** create, batch, decide, list, detail, edit, confirm, decisions, graph;
* **provenance:** trace, history;
* **retrieval:** search, ask, context, compare;
* **conflicts:** list, resolve, pending, updates;
* **forgetting:** plan, execute, verify, audit, expire;
* **agents:** list, register, log, chat, tools, tasks, work;
* **handover:** create, list, get, run, demo;
* **evaluation:** run, runs, latest.

[API_DOCUMENTATION.md](API_DOCUMENTATION.md) documents each endpoint.

**Errors:** 400 for invalid values (`ValueError`), 403 for permission problems and unknown agents,
404 for missing resources, 422 for schema validation failures, and 401 for a missing or wrong API key.

---

## 11. Security

| Threat | Mitigation |
|---|---|
| Unauthorized access | Optional `MNEMOS_API_KEY` (constant-time comparison); CORS limited to localhost by default; the server binds to localhost by default. |
| Prompt injection or poisoning | Pattern rejection; trust-weighted quarantine; anti-flooding; confirmation gate; data framing and escaping of retrieved context. |
| Sensitive data retention | Secret rejection; PII redaction; hashed decision log; redacted agent logs; secure_delete; verified deletion. |
| Unsafe deletion | Two-phase plan and token; single-use tokens with a 10-minute expiry; resetting all data requires typing `RESET`. |
| Handover tampering | SHA-256 checksum; addressee check; budget check; stale-memory detection. |
| Malformed input | Pydantic schemas with length limits; tool-argument validation; parameterised SQL everywhere; FTS queries sanitised. |
| Secrets in source | None. Configuration comes only from the environment; `.env` is git-ignored and `.env.example` is provided. |

---

## 12. Testing

| Suite | Count | Covers |
|---|---|---|
| `test_classification_and_decisions.py` | 23 | Types, triples, filler, safety scan, all 7 decision actions, dry run, entity-aware dedup |
| `test_storage_and_persistence.py` | 4 | Routing, real indexing, restart persistence, settings persistence |
| `test_updates_conflicts_provenance.py` | 7 | Update and lineage, merge and corroboration, conflict and resolution, quarantine, confirmation, trace, edit |
| `test_retrieval_budget_integrity.py` | 22 | Answers, intent, abstention, 5 modes, explanations, budgets ×5, data framing, injection, flooding, cache |
| `test_forgetting.py` | 8 | Every store, two-phase token, entity cascade, source scope, deleted/unknown/expired, audit, handover redaction, expiry purge |
| `test_agents_handover.py` | 11 | Shared memory, full handover, budget ×5, tamper rejection, addressee, gateway validation, log redaction |
| `test_api.py` | 12 | All endpoint groups, validation, API-key guard |
| `test_integration_server.py` | 3 | Real uvicorn: restart persistence, Python REST agent, Node.js agent including a handover |
| `test_evaluation.py` | 5 | ≥30 scenarios, determinism, benchmark sanity, context budgets |
| Frontend `App.test.tsx` | 4 | Overview rendering from the API, Decision Lab flow, API error handling |

**Result: 95 backend tests and 4 frontend tests passed** (pytest 9.2, Python 3.14; vitest 2.1).

---

## 13. Evaluation

### 13.1 Method

* **Scenarios (53, 12 categories):** each runs on a fresh temporary engine and checks the observed
  behaviour.
* **Storage benchmark:**
  * Corpus: 220 synthetic memories and 63 labelled queries of five kinds (exact, paraphrase,
    relational, procedural, entity).
  * Six strategies, each in its own directory.
  * Metrics: R-precision, Recall@5 and MRR; insert latency and query latency (mean and p95);
    bytes on disk; update latency and correctness; logical and physical deletion.
* **Context comparison:**
  * A deterministic synthetic conversation of 1,430 turns and 12,437 tokens: 628 filler turns,
    123 small-talk turns, 649 distractor work notes, and 24 gold facts, 6 of which are later updated.
  * 24 questions whose ground truth is the *latest* value.
  * Strategies: a sliding window of the full history; an extractive summary truncated to the
    budget; Mnemos selected memory.
  * Budgets: 500, 1,000, 2,000 and 5,000 tokens.
  * **Answer support:** the expected answer appears in the context. This is a necessary condition
    for a model to answer correctly; no LLM is called.
  * **Stale risk:** an outdated value of the same subject appears in the context.

### 13.2 Results (measured; tokenizer `tiktoken:cl100k_base`)

**Scenarios: 53 of 53 passed.** By category: retention 5/5, rejection 5/5, temporary 4/4,
updates 7/7, integrity 6/6, retrieval 5/5, provenance 3/3, forgetting 7/7, handover 6/6,
token_budget 2/2, persistence 1/1, routing 2/2.

**Context strategies.** Each cell gives answer support and the average tokens sent.

| Budget | Full history (window) | Extractive summary | Mnemos selected |
|---|---|---|---|
| 500 | 0.125 · 467 | 0.167 · 456 | **1.000 · 404** |
| 1,000 | 0.250 · 934 | 0.458 · 908 | **1.000 · 546** |
| 2,000 | 0.500 · 1,872 | 0.667 · 1,824 | **1.000 · 546** |
| 5,000 | 0.750 · 4,682 | 0.833 · 4,552 (stale risk 0.083) | **1.000 · 546** |

Selected memory reached full answer support with roughly 11× fewer tokens than the 5,000-token
window. It stopped adding context once nothing relevant remained. Its context latency was 3–4 ms
per question; the baselines took less than 0.2 ms.

**Storage strategies** (220 memories, 63 queries):

| Strategy | R-prec | Recall@5 | MRR | Query ms (mean) | Bytes | Update correct | Delete (logical/physical) |
|---|---|---|---|---|---|---|---|
| structured | 0.619 | 1.000 | 0.786 | 0.27 | 64 KB | no | yes / yes |
| keyword (FTS5) | 0.595 | 0.929 | 0.775 | 0.09 | 104 KB | yes | yes / yes |
| vector | 0.821 | 0.937 | 0.897 | 0.06 | 924 KB | yes | yes / yes |
| graph | 0.333 | 1.000 | 0.627 | 0.12 | 80 KB | no | yes / yes |
| file (JSONL) | 0.714 | 1.000 | 0.857 | 2.96 | 18 KB | yes | yes / yes |
| **hybrid (Mnemos)** | **0.976** | **0.976** | **1.000** | 4.60 | 1.56 MB | yes | yes / yes |

*Secure-delete check:* with `secure_delete` OFF, the deleted token was **found** in the database
file; with it ON, the token was **not found**.

### 13.3 Interpretation and caveats

* Hybrid fusion gives the best ranking, at the cost of more latency and storage. That trade-off is
  acceptable at agent scale, since a few milliseconds is negligible next to LLM latency.
* Structured and graph search have high Recall@5 but low precision. They find the right entity but
  cannot rank within it, which is why the hybrid combines them with other signals.
* The same author wrote the corpus, the scenarios and the rules, so the results carry optimistic
  bias. They show that the specified behaviour works on clean templated English; they say nothing
  about accuracy on messy real conversations.
* Synthetic answer support is not end-to-end question-answering accuracy.

---

## 14. Limitations

1. The rule-based classifier and extractor cover common English patterns only. They do not
   resolve coreference ("she", "it") or handle multi-sentence facts well.
2. The local embeddings are lexical-semantic and will miss deep paraphrases.
3. Conflict detection works only on facts with an extracted subject and attribute; contradictions
   in free text go undetected.
4. The bundled agents are deterministic. Their step "execution" means grounding the step in memory
   and recording progress, not performing real-world actions.
5. Single-node SQLite: the system is not designed for multi-writer, distributed deployment.
6. The forgetting limits listed in §8.

## 15. Future scope

* An optional LLM extractor and classifier, keeping the rules as the safe fallback.
* A neural embedding model and an ANN index (FAISS or sqlite-vec) for larger corpora.
* Coreference resolution and multi-sentence fact extraction.
* Per-user and per-agent access control lists and encryption at rest.
* An MCP (Model Context Protocol) server exposing the tool gateway.
* Evaluation on public long-term-memory benchmarks, with LLM-judged answer accuracy.

## 16. Conclusion

Mnemos shows that a memory layer can be **selective, explainable, verifiable and frugal**:

* it rejects noise and attacks;
* it keeps history instead of overwriting it;
* it says "I don't know" instead of guessing;
* it proves that deletions happened;
* it lets different agents share memory and hand over work;
* it delivers the needed facts in a fraction of the tokens a raw history would use.
