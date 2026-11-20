# API Documentation

* **Base URL:** `http://localhost:8000`. Interactive OpenAPI (Swagger) docs are at `/docs`, and the raw schema is at `/openapi.json`.
* **Format:** all bodies are JSON.
* **Authentication:** if `MNEMOS_API_KEY` is set, every `/api/*` route except `/api/health` needs the header `X-API-Key: <key>`. Without it the server returns 401.

**Errors** come back as `{"detail": "..."}`:

| Code | Meaning |
|---|---|
| 400 | Invalid value or operation |
| 401 | Missing or wrong API key |
| 403 | Not permitted, or agent not registered |
| 404 | Not found |
| 422 | Request failed schema validation |

## System

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness check and memory count |
| GET | `/api/stats` | Counts by status, type, decision, source and route; conflicts; deletions; storage bytes; tokenizer and embedder |
| GET | `/api/settings` | Current settings, route descriptions, tokenizer |
| PUT | `/api/settings` | `{"values": {"abstain_threshold": 0.25, ...}}`. Only tunable keys are accepted; values are validated and persisted |
| POST | `/api/admin/seed` | Ingest 26 synthetic demo statements through the decision engine |
| POST | `/api/admin/reset` | `{"confirm": "RESET"}`. Deletes all local data |

## Memory

| Method | Path | Description |
|---|---|---|
| POST | `/api/decide` | Dry run: returns the decision without storing anything |
| POST | `/api/memories?dry_run=false` | Ingest one candidate (body schema below) |
| POST | `/api/memories/batch` | `{"items": [MemoryIn, ...]}`, up to 200 items |
| GET | `/api/memories` | Filters: `status`, `memory_type`, `agent_id`, `source_type`, `task_id`, `q`, `limit`, `offset` |
| GET | `/api/memories/{id}` | Detail: provenance, revisions, links, decision, conflicts, file copy, store presence |
| PUT | `/api/memories/{id}` | `{"content", "reason", "actor"}`. Manual edit; creates a revision and re-indexes |
| POST | `/api/memories/{id}/confirm` | `{"approve": true\|false}`. Approve a pending or quarantined memory, or reject it (rejection deletes it) |
| GET | `/api/memories/{id}/trace` | Origin, corroborations, parents, derived memories, lineage, explanation |
| GET | `/api/memories/{id}/history` | Version lineage and revisions |
| GET | `/api/decisions?action=&limit=` | Decision log |
| GET | `/api/graph?entity=` | Full graph, or one entity's neighbourhood |

**MemoryIn** (the body for `POST /api/memories`):

```json
{
  "content": "The deadline for Project Orion is January 20.",
  "source_type": "user | agent | document | tool | web | system | unknown",
  "source_id": "doc:plan", "source_label": "Q1 plan", "agent_id": "atlas", "session_id": "s1",
  "task_id": "task_x", "tags": ["orion"], "confidence": 0.8, "ttl_hours": 4,
  "memory_type": "semantic", "importance": 0.7, "derived_from": ["mem_..."]
}
```

Only `content` is required.

**Response:**

```json
{
  "decision": {
    "action": "STORE", "memory_type": "semantic", "content": "...",
    "scores": {"relevance": 0.73, "utility": 0.77, "confidence": 0.9, "durability": 0.8, "redundancy": 0.0,
               "privacy_risk": 0.0, "injection_risk": 0.0, "source_trust": 0.9},
    "reasons": ["classified as semantic ...", "source 'user' has trust 0.90", "relevant (0.73), durable (0.80), confident (0.90) → store"],
    "flags": [], "routes": ["structured", "keyword", "vector", "graph"], "route_reasons": ["..."],
    "classification": {"subject": "project orion", "attribute": "deadline", "value": "January 20", "entities": ["Project Orion", "January"], "signals": ["..."]},
    "target_memory_id": null, "expires_at": null
  },
  "decision_id": "dec_...", "memory": { "...": "the stored row" }, "conflict_id": null, "dry_run": false
}
```

## Retrieval

| Method | Path | Body |
|---|---|---|
| POST | `/api/search` | `{"query", "mode": "hybrid\|keyword\|semantic\|structured\|graph", "limit", "memory_types", "agent_id", "task_id", "source_types", "min_confidence", "include_inactive"}` |
| POST | `/api/ask` | `{"question", "task_id"?}` → `status`: answered, conflicting, low_confidence, deleted, expired or unknown |
| POST | `/api/context` | `{"query", "budget": 50–20000, "task_id"?, "mode"?, "memory_types"?, "compact"?}` → context, tokens_used, included, excluded, tokenizer |
| POST | `/api/context/compare` | `{"query", "budgets": [500, 1000, 2000, 5000]}` → full_dump vs summary vs selected on live memory |

Example:

```bash
curl -s localhost:8000/api/ask -H 'content-type: application/json' \
     -d '{"question":"What is the deadline for Project Orion?"}'
# {"status":"answered","answer":"February 3","memory_id":"mem_…","confidence":0.9,"sources":[…],"explanation":"…"}
```

## Conflicts and updates

| Method | Path | Description |
|---|---|---|
| GET | `/api/conflicts?status=open\|resolved` | Conflicts, with both memories attached |
| POST | `/api/conflicts/{id}/resolve` | `{"resolution": "keep_a\|keep_b\|keep_both"}` |
| GET | `/api/pending` | Memories that are pending confirmation or quarantined |
| GET | `/api/updates` | Recent supersede events (old value → new value) |

## Forgetting

| Method | Path | Description |
|---|---|---|
| POST | `/api/forget/plan` | `{"scope": "id\|topic\|entity\|source", "value", "include_derived": true}` → items and `confirm_token` |
| POST | `/api/forget/execute` | `{"confirm_token"}` → deleted ids, verification (logical and physical), audit_id |
| GET | `/api/forget/verify/{id}` | Re-verify that an id is absent from every store |
| GET | `/api/forget/audit` | Content-free deletion audit |
| POST | `/api/maintenance/expire` | Run the temporary-memory expiry sweep |

## Agents, tasks and handover

| Method | Path | Description |
|---|---|---|
| GET | `/api/agents` | Registered agents, with memories written and actions taken |
| POST | `/api/agents/register` | `{"agent_id", "name", "integration"}` |
| GET | `/api/agents/log?agent_id=&task_id=` | Redacted activity log |
| POST | `/api/agents/{atlas\|bolt}/chat` | `{"message", "task_id"?}`. A message ending in `?` is treated as a question; anything else is stored as memory |
| GET | `/api/tools` | Tool catalogue |
| POST | `/api/tools/invoke` | `{"agent_id", "tool", "args"}` (see [AGENT_INTEROPERABILITY.md](AGENT_INTEROPERABILITY.md)) |
| GET / POST | `/api/tasks` | List tasks, or have Atlas plan one: `{"title", "goal", "steps"?, "constraints"?}` |
| GET | `/api/tasks/{id}` | Task detail |
| POST | `/api/tasks/{id}/work` | `{"max_steps"}`. Atlas completes research steps |
| GET / POST | `/api/handovers` | List handovers, or create one: `{"task_id", "from_agent", "to_agent", "token_budget", "notes"}` |
| GET | `/api/handovers/{id}` | Package, status, result |
| POST | `/api/handovers/{id}/run` | Bolt accepts and executes (only for handovers addressed to Bolt) |
| POST | `/api/demo/handover?budget=1000` | End-to-end demo: seed, plan, work, hand over, execute, recall |

## Evaluation

| Method | Path | Description |
|---|---|---|
| POST | `/api/eval/run` | `{"suite": "scenarios\|storage\|context\|all"}`. Runs on isolated temporary databases and stores the result |
| GET | `/api/eval/runs` | Run summaries |
| GET | `/api/eval/runs/{id}` | Full details |
| GET | `/api/eval/latest?kind=all` | Latest run of a given kind |
