# Testing and Evaluation

## 1. Automated tests

Run them with:

```bash
cd backend  && python -m pytest -q
cd frontend && npm test
```

**Latest result:**

* Backend: **95 passed** in about 23 s (pytest 9.2, Python 3.14.6, Windows 11).
* Frontend: **4 passed** (vitest 2.1.2, jsdom).
* The frontend type-check (`tsc -b`) and production build (`vite build`) succeed.

| File | Tests | What it proves |
|---|---|---|
| `test_classification_and_decisions.py` | 23 | Six memory types; fact triples; filler; secret, PII and injection scanning; every decision action; dry run stores nothing; templated text about different entities is not merged |
| `test_storage_and_persistence.py` | 4 | Routing per type; every routed store really holds the memory; **restart persistence**, including the vector index; settings persistence |
| `test_updates_conflicts_provenance.py` | 7 | Supersede with lineage; merge vs corroboration; conflict and resolution; low-trust quarantine; confirmation flow; trace and derivation; edit revisions |
| `test_retrieval_budget_integrity.py` | 22 | Answers, including paraphrases; procedural intent; abstention; 5 search modes; result explanations; budgets of 100, 500, 1,000, 2,000 and 5,000; data framing; 4 injection variants; anti-flooding; cache invalidation |
| `test_forgetting.py` | 8 | Deletion from every store, plus a raw-byte check; two-phase single-use tokens; entity cascade; source scope; deleted vs unknown vs expired; content-free audit; handover redaction; expiry purge |
| `test_agents_handover.py` | 11 | Shared memory between Atlas and Bolt; full handover; package budget at 300–5,000; tampered package rejected; addressee enforced; gateway validation; agent logs never contain secrets |
| `test_api.py` | 12 | Every endpoint group, validation errors (422/400), API-key guard (401), seed, settings, the evaluation endpoint |
| `test_integration_server.py` | 3 | **A real uvicorn process**: persistence across a server restart; a Python REST agent; a **Node.js agent** sharing memory and completing a handover over HTTP |
| `test_evaluation.py` | 5 | At least 30 scenarios across at least 10 categories, all passing; deterministic datasets; storage benchmark sanity; context budgets respected |
| `frontend/src/App.test.tsx` | 4 | Overview renders API data; Decision Lab dry-run flow; API error surfacing; message when the backend is unreachable |

### Failures found and fixed during development

Every one of these was a real bug, caught by the tests or the benchmark before the final commit:

1. Stop words leaked into FTS queries, so "What is the capital of Mars?" was answered with an unrelated fact. **Fix:** filter stop words, and add a query-coverage requirement before `ask()` may answer.
2. Templated runbooks for different projects (cosine ≈ 0.90) were merged as duplicates. **Fix:** deduplication now also requires the same entity set.
3. Procedural queries ranked runbooks below work notes. **Fix:** query-intent type priors, and graph routing for every durable memory that names entities.
4. Expiry purged `content` but left the extracted entities, so the expired secret was still in the database bytes (scenario T04). **Fix:** clear every content-derived field.
5. Deleted memory text survived inside task constraints copied into handover packages. **Fix:** scrub tasks, packages and agent logs, and re-seal packages.
6. Agent logs stored chat messages verbatim, including a password. **Fix:** redact log messages and data recursively.

## 2. Evaluation lab

You can run the evaluation lab from the UI (**Evaluation Lab → Run everything**), through
`POST /api/eval/run {"suite": "all"}`, or through pytest. Every run uses fresh temporary databases.
The latest full run is saved in [docs/results/latest_eval.json](docs/results/latest_eval.json).

### 2.1 Scenarios: 53 of 53 passed

| Category | Passed | Examples |
|---|---|---|
| retention | 5/5 | Preference recall; fact triple; runbook routed to the file store; relationship routed to the graph; episodic decision |
| rejection | 5/5 | Filler; small talk; password absent from raw DB bytes; API key; email redaction |
| temporary | 4/4 | "For now" expires and is reported as expired; explicit TTL; not vector-indexed; content purged from disk |
| updates | 7/7 | Supersede with history; latest value answered; same-source merge without a confidence gain; corroboration raises confidence; conflict flagged; resolution; multi-valued preferences |
| integrity | 6/6 | Injection rejected; low-trust quarantine; flooding; hedged rumour; data framing; unverifiable claims |
| retrieval | 5/5 | Abstention; paraphrase; task-aware ranking; source filter; superseded values not treated as current |
| provenance | 3/3 | Origin trace; derived links; every decision explained and logged |
| forgetting | 7/7 | By id, entity (cascade) and source; "deleted" status; physical absence; token required; superseded versions forgotten too |
| handover | 6/6 | Full Atlas → Bolt run; tamper rejected; budget respected; stale memories flagged; wrong agent refused; shared memory |
| token_budget | 2/2 | Never exceeds the budget; a larger budget includes at least as many memories |
| persistence | 1/1 | Engine restart |
| routing | 2/2 | Plain facts are not sent to the file store; long documents are |

### 2.2 Context strategies (full history vs summary vs selected memory)

**Dataset.** The synthetic conversation is deterministic (seed 7):

* 1,430 turns, 12,437 tokens with `cl100k_base`;
* 24 gold facts, 6 of which are later updated;
* 628 filler turns, 123 small-talk turns and 649 distractor work notes.

The 24 questions are scored against the **latest** value of each fact.

**Metrics:**

* **answer support:** the expected answer string appears in the context;
* **stale risk:** an outdated value appears on a line about the same subject;
* **average tokens** sent per question;
* **latency.**

| Budget | Strategy | Answer support | Stale risk | Avg tokens | Latency ms |
|---|---|---|---|---|---|
| 500 | full history (recent window) | 0.125 | 0.000 | 467 | 0.02 |
| 500 | extractive summary | 0.167 | 0.000 | 456 | 0.02 |
| 500 | **Mnemos selected** | **1.000** | 0.000 | **404** | 3.6 |
| 1,000 | full history | 0.250 | 0.000 | 934 | 0.02 |
| 1,000 | summary | 0.458 | 0.000 | 908 | 0.02 |
| 1,000 | **selected** | **1.000** | 0.000 | 546 | 3.6 |
| 2,000 | full history | 0.500 | 0.000 | 1,872 | 0.05 |
| 2,000 | summary | 0.667 | 0.000 | 1,824 | 0.05 |
| 2,000 | **selected** | **1.000** | 0.000 | 546 | 3.2 |
| 5,000 | full history | 0.750 | 0.000 | 4,682 | 0.13 |
| 5,000 | summary | 0.833 | 0.083 | 4,552 | 0.11 |
| 5,000 | **selected** | **1.000** | 0.000 | 546 | 3.4 |

While processing the transcript, Mnemos discarded 628 turns, merged 130, stored 604, made 62
temporary and applied 6 updates. All 6 updates were correctly detected as supersessions, which is
why the selected context never contained stale values.

### 2.3 Storage strategies

**Corpus:** 220 synthetic memories (seed 11). 63 labelled queries: 18 exact, 30 paraphrase,
3 relational, 6 procedural, 6 entity ("tell me everything about X").

| Strategy | R-precision | Recall@5 | MRR | Insert ms | Query ms mean / p95 | Disk | Update ms | Update correct | Delete logical / physical |
|---|---|---|---|---|---|---|---|---|---|
| structured | 0.619 | 1.000 | 0.786 | 0.52 | 0.27 / 0.41 | 64 KB | 2.1 | ✖ | ✔ / ✔ |
| keyword (FTS5) | 0.595 | 0.929 | 0.775 | 0.42 | 0.09 / 0.19 | 104 KB | 1.6 | ✔ | ✔ / ✔ |
| vector | 0.821 | 0.937 | 0.897 | 0.61 | 0.06 / 0.11 | 924 KB | 1.0 | ✔ | ✔ / ✔ |
| graph | 0.333 | 1.000 | 0.627 | 1.16 | 0.12 / 0.18 | 80 KB | 3.3 | ✖ | ✔ / ✔ |
| file (JSONL) | 0.714 | 1.000 | 0.857 | 0.29 | 2.96 / 3.92 | 18 KB | 1.5 | ✔ | ✔ / ✔ |
| **hybrid (Mnemos)** | **0.976** | **0.976** | **1.000** | 2.53 | 4.60 / 6.38 | 1.56 MB | 6.6 | ✔ | ✔ / ✔ |

**Recall@5 by query kind:**

* keyword is weak on procedural (0.50) and entity (0.75) queries;
* vector is weak on procedural (0.67) and entity (0.67) queries;
* hybrid scores 1.0 on every kind except entity (0.75).

**"Update correct"** means that after Ana's city changes, the top-1 result for "Where does Ana
live?" is the updated record. Structured and graph search tie with Ana's other records, so they
fail this check.

**Secure-delete check:** with `secure_delete` OFF, the deleted token was **still in the file**;
with it ON, the token was **gone**.

## 3. Threats to validity

* **Author bias.** The scenarios, corpora and rules were written by the same team. The intent
  priors and concept groups suit this vocabulary, so expect lower numbers on real conversations.
* **Synthetic, templated English.** No coreference, typos, sarcasm or multilingual input.
* **Answer support is not answer accuracy.** No LLM was asked to answer from the contexts.
* **Small scale.** 220–1,430 items. The numpy brute-force vector search and the SQLite LIKE
  queries would need ANN indexes at millions of items.
* **Single machine.** Latency was measured on one Windows 11 laptop and will vary.
* **Hybrid storage overhead** includes the SQLite WAL and all indexes, so it is an upper bound for
  this corpus.
