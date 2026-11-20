# Mnemos — Project Report

**Memory with Meaning. Context with Control.**

*Problem statement: Knowledge Brain — Memory That Knows What to Keep and When to Forget*

## 1. Problem

AI agents build up conversations, decisions, documents, tasks and preferences over time. The
memory systems behind them usually fall into one of two extremes.

* **Store everything.** Every message goes into a vector store. The store fills with filler,
  secrets and stale facts, contradictions get overwritten silently, and an injected sentence can
  later be retrieved and obeyed as if it were an instruction.
* **Send everything.** The whole history is pasted into the prompt. This wastes tokens, is still
  truncated, and drops older but important facts.

Neither approach can say where a fact came from, or prove that a deleted fact is really gone. The
memory is also usually private to one agent, so handing work to another agent loses context.

## 2. Objectives

1. Decide, for each piece of information, whether to **store, update, merge, keep temporarily,
   discard, ask for confirmation, or flag a conflict**, and explain why.
2. Classify memory into **episodic, semantic, procedural, preference, working and relational** types.
3. Route each memory to suitable storage (structured, keyword, vector, graph and file) and compare
   those strategies with measurements.
4. Track **provenance** and **history**; handle updates and contradictions without losing data.
5. Retrieve with ranking, filters and **abstention**; assemble context within a **token budget**.
6. **Forget** by id, topic, entity or source across every store, and **verify** the deletion.
7. Resist **false memories and poisoning**.
8. Serve **two or more distinct agents** from one memory and perform a **real task handover**.
9. Measure all of the above in an **evaluation lab** with genuine results.

## 3. Solution overview

Mnemos is a local-first memory service. It consists of:

* a **Python/FastAPI** backend with a SQLite-based multi-store engine;
* a **React/TypeScript** dashboard;
* three agent integrations, written in two languages.

It needs no paid AI service. Every incoming statement passes through a safety scan, a classifier,
the decision engine and a storage router. Every query passes through hybrid retrieval with
explicit answer statuses.

![System architecture](images/charts/architecture.png)

## 4. Implementation

### 4.1 Decision engine

The engine computes the following scores for each input:

* relevance, utility, confidence and durability;
* redundancy, from vector similarity;
* privacy risk and injection risk;
* source trust: user 0.90, document 0.75, agent 0.70, tool 0.60, web 0.40.

It then applies an ordered policy. Secrets and injection are discarded, followed by filler. PII is
redacted. Next come duplicates and corroboration (MERGE), then same-fact checks: UPDATE when there
is an explicit change marker, and FLAG_CONFLICT otherwise, with quarantine when a lower-trust
source tries to override. Short-lived information becomes TEMPORARY, low confidence becomes
NEEDS_CONFIRMATION, and everything else is stored. Every reason is logged and displayed.

![Decision Lab: every decision is explained](images/decision.png)

### 4.2 Storage routing

| Store | Implementation | Used for |
|---|---|---|
| Structured | SQLite `memories` table | Every memory: status, validity, facts |
| Keyword | SQLite FTS5 with BM25 | Every memory: queryable text search |
| Vector | Local hashing embeddings, numpy | Durable memories: semantic search, deduplication |
| Graph | Entity and edge tables | Relations and entity mentions |
| File | Markdown per memory | Procedures and long documents |

### 4.3 Provenance, updates and contradictions

Each observation adds a provenance row: source, agent, session, method, confidence and an input
hash. Versions are linked by `supersedes`, and derived memories by `derived_from`. Contradictions
open a conflict that can be resolved in the UI; nothing is silently overwritten.

![Contradiction & Update Center](images/conflicts.png)

### 4.4 Retrieval, abstention and token budgets

Retrieval fuses semantic (0.35), keyword (0.30), structured (0.20) and graph (0.15) scores. The
result is then weighted by confidence, importance, recency, status, task and query intent.

`ask()` returns one of `answered`, `conflicting`, `low_confidence`, `deleted`, `expired` or
`unknown`; it never invents an answer. Context assembly packs the best memories inside a hard
token budget, counted with the real `cl100k_base` tokenizer, and labels the records as *data, not
instructions*.

### 4.5 Forgetting

Deletion takes two phases: a plan with a confirmation token, then execution.

**Cascade.** The plan includes derived memories and older versions.

**Execution removes the memory from:**

* the structured, keyword, vector, graph and file stores;
* provenance, revisions, links and conflicts;
* task and handover copies (packages are re-sealed);
* agent logs and the cache.

**Verification** checks every store and also scans the raw database, WAL and file bytes. The audit
keeps only counts and salted term hashes, which lets Mnemos answer "deleted" without keeping the
data.

![Forgetting Center](images/forgetting.png)

### 4.6 Agents and handover

The three agent setups are:

* **Atlas**, an in-process Python SDK client;
* **Bolt**, which uses JSON tool calls only;
* **Relay**, an external Node.js process using REST.

All three share one memory. A handover package contains the task, progress, decisions,
constraints, unfinished steps, relevant memories with sources, a budgeted context, a token budget
and a SHA-256 checksum. The receiver validates the package, detects stale memories, executes the
remaining steps with memory evidence, and reports back.

![Task handover executed by Bolt](images/handover.png)

![Two agents sharing one memory](images/agents.png)

## 5. Evaluation methodology

* **53 scenarios** in 12 categories. Each runs on an isolated temporary database and checks the
  observed behaviour.
* **Context comparison.**
  * Data: a 1,430-turn synthetic conversation (12,437 tokens) with 24 gold facts, 6 of them later
    updated, and 24 questions.
  * Strategies: full history (sliding window), extractive summary and Mnemos selected memory.
  * Budgets: 500, 1,000, 2,000 and 5,000 tokens.
  * Metrics: answer support (the expected latest answer appears in the context) and stale risk.
* **Storage benchmark.**
  * Data: 220 memories and 63 labelled queries of five kinds.
  * Strategies: structured, keyword, vector, graph, file and hybrid.
  * Metrics: R-precision, Recall@5 and MRR; latency; bytes on disk; update correctness; logical and
    physical deletion.

All numbers below were produced by `POST /api/eval/run` and saved in
`docs/results/latest_eval.json`. The tokenizer was `{{TOKENIZER}}`.

## 6. Results

### 6.1 Scenarios

{{SCENARIO_SUMMARY}}

![Scenario pass rate by category](images/charts/scenarios.png)

### 6.2 Context strategies

{{CONTEXT_TABLE}}

![Answer support vs budget](images/charts/context_support.png)

![Tokens sent per question](images/charts/context_tokens.png)

### 6.3 Storage strategies

{{STORAGE_TABLE}}

![Retrieval quality by strategy](images/charts/storage_quality.png)

![Query latency by strategy](images/charts/storage_latency.png)

{{SECURE_DELETE}}

### 6.4 Tests

* Backend: **95 pytest tests passed**. These include integration tests against a live uvicorn
  server, the Node.js agent and the Python REST agent, and persistence across a server restart.
* Frontend: **4 vitest tests passed**.

### 6.5 Dashboard

![Evaluation Lab](images/evaluation.png)

![Storage Strategy Comparison](images/storage.png)

## 7. Discussion

* **Selective memory beats raw history.** Selected memory made every answer available at 500
  tokens. The sliding window reached only 75% answer support even at 5,000 tokens, because early
  facts fell out of the window. The summary was better than the window but still truncated, and at
  the largest budget it contained a stale value.
* **No single store is enough.** Vector search ranks paraphrases well, but it mis-ranks procedures
  and entity questions. Structured and graph search find the right entity but cannot rank within
  it. The hybrid achieved R-precision 0.976 and MRR 1.0, at the cost of about 4.6 ms per query and
  more disk space.
* **Forgetting needs more than a DELETE statement.** With SQLite's `secure_delete` off, deleted
  text remained in the file. Real forgetting also had to cover copies in tasks, handover packages
  and logs. The tests found two leaks of this kind during development, and both were fixed.

## 8. Limitations

* The rule-based classifier and fact extractor handle common English patterns only, with no
  coreference resolution.
* The local embeddings are lexical-semantic, not neural.
* Conflict detection only covers extracted facts (subject and attribute).
* The bundled agents are deterministic and rule-based; they do not call an LLM.
* Deletion cannot reach external backups, SSD remnants, or copies already taken by external agents.
* The evaluation data is synthetic and was written by the same authors as the rules, so the
  results are optimistic. Answer support is not the same as LLM answer accuracy.

## 9. Future scope

* An optional LLM extractor, keeping the rules as a fallback.
* Neural embeddings with an ANN index.
* Coreference resolution.
* Access control lists and encryption at rest.
* An MCP server built on the tool gateway.
* Evaluation on public long-term-memory benchmarks, with LLM-judged accuracy.

## 10. Conclusion

Mnemos meets the objectives with working, tested code. Specifically:

* it decides what to keep and why;
* it keeps history instead of overwriting it;
* it traces every fact to its source;
* it abstains rather than inventing answers;
* it fits context into strict token budgets;
* it forgets verifiably;
* it lets different agents share memory and hand work over.

The measurements show both the benefits and the costs of each design choice, and the limitations
are stated openly.
