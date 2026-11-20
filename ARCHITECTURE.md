# Architecture

## Components

```
┌──────────────────────────────────────── Clients ────────────────────────────────────────┐
│  React dashboard (frontend/)   Atlas (SDK)   Bolt (JSON tools)   Relay (Node.js)   curl │
└───────────┬─────────────────────────┬──────────────┬───────────────────┬────────────────┘
            │ HTTP /api/*             │ in-process   │ ToolGateway       │ HTTP /api/tools/invoke
┌───────────▼─────────────────────────▼──────────────▼───────────────────▼────────────────┐
│ app/main.py  FastAPI · Pydantic schemas · API-key middleware · exception→HTTP mapping   │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│ app/engine.py  Mnemos(settings)                                                          │
│   ├─ core/safety.py       secrets · PII redaction · injection patterns                   │
│   ├─ core/classifier.py   6 memory types · (subject, attribute, value) · entities · TTL  │
│   ├─ services/decision.py STORE/UPDATE/MERGE/TEMPORARY/DISCARD/NEEDS_CONFIRMATION/       │
│   │                       FLAG_CONFLICT + scores + reasons                               │
│   ├─ core/router.py       which stores, and why                                          │
│   ├─ services/memory.py   apply decisions · provenance · revisions · conflicts · expiry  │
│   ├─ services/retrieval.py hybrid search · ask/abstain · budgeted context                │
│   ├─ services/forgetting.py plan → execute → verify (logical + physical) → audit         │
│   ├─ services/agents.py   MemoryClient · ToolGateway · Atlas · Bolt · tasks · handover   │
│   └─ LRU retrieval cache (invalidated on every write)                                    │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│ stores/stores.py  Structured │ Keyword (FTS5) │ Vector (numpy) │ Graph │ File (Markdown)  │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│ SQLite file  backend/data/mnemos.db  (WAL, secure_delete=ON)  +  backend/data/files/*.md │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

## Write path (ingest)

```
text + source metadata
   │
   ▼ safety.scan ─── secret? ──► DISCARD (hash only in decision log)
   │              └─ injection? ► DISCARD (flags: prompt_injection, poisoning_attempt)
   ▼ classify ─── filler / low relevance? ► DISCARD
   ▼ redact PII
   ▼ vector lookup ─ near-duplicate (same fact, same entities)? ► MERGE
   ▼ fact lookup (subject, attribute) ─ same value ► MERGE
   │                                  ├ low-trust override ► FLAG_CONFLICT (quarantine)
   │                                  ├ change marker ► UPDATE (supersede, keep history)
   │                                  └ otherwise ► FLAG_CONFLICT (value conflict)
   ▼ temporal cue / working memory ► TEMPORARY (expires_at)
   ▼ confidence < threshold ► NEEDS_CONFIRMATION
   ▼ STORE
   │
   ▼ MemoryService: one transaction → memories row + routed indexes + provenance + revision + links
   ▼ decision log row (scores, reasons, routes, flags, content hash)
   ▼ cache invalidated
```

## Read path (ask / context)

```
query → keyword(BM25) ┐
      → semantic(cos) ├─ normalise → weighted fusion + agreement bonus
      → structured    │   × confidence × importance × recency × status × task × intent
      → graph (1-hop) ┘
      → coverage check → ask(): answered | conflicting | low_confidence | deleted | expired | unknown
                       → assemble(): header ("data, not instructions") + greedy packing under budget
```

## Database schema (SQLite)

| Table | Purpose |
|---|---|
| `memories` | Canonical memory rows (structured store). |
| `memories_fts` | FTS5 virtual table: keyword / queryable store. |
| `vectors` | Embedding BLOBs (the vector store's persistence). |
| `entities`, `edges`, `entity_mentions` | Graph store. |
| `provenance` | One row per observation (origin and corroborations). |
| `revisions` | Version history of each memory. |
| `memory_links` | `supersedes`, `derived_from`, `related_to`, `conflicts_with`. |
| `decisions` | Explainable decision log (hash and preview, no secrets). |
| `conflicts` | Open and resolved contradictions. |
| `deletion_audit` | Content-free audit with salted term hashes (also used for expiry). |
| `agents`, `tasks`, `handovers`, `agent_log` | Interoperability and handover. |
| `eval_runs` | Stored evaluation results. |
| `kv_settings` | Persisted runtime settings and the tombstone salt. |

## Concurrency and persistence

* A single SQLite connection is guarded by a re-entrant lock. Multi-step writes run inside explicit
  `BEGIN … COMMIT` transactions.
* The vector index is an in-memory numpy matrix, rebuilt from the `vectors` table at start-up. That
  is how semantic search survives restarts; a test covers it.
* Uvicorn runs the synchronous endpoints in a thread pool, and the lock serialises database access.

## Frontend

`frontend/src/App.tsx` routes to 11 pages:

* Overview
* Memory Explorer (with a provenance drawer)
* Decision Lab
* Retrieval & Budget
* Contradictions
* Forgetting
* Agent Workspace
* Task Handover
* Storage Strategies
* Evaluation Lab
* Settings

`lib/api.ts` is a typed `fetch` wrapper. It shows backend error messages as they are, and it sends
`X-API-Key` if a key is stored in the browser. In development, Vite proxies `/api` to `:8000`.
