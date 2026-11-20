# Provenance and Contradiction Handling

## 1. What is tracked

| Record | Fields | Written when |
|---|---|---|
| `provenance` | source_type, source_id, source_label, agent_id, session_id, extraction_method, confidence, SHA-256 of the raw input, created_at | On creation, and again on every merge or corroboration |
| `revisions` | version, content, value, status, change_type, reason, actor, created_at | create, merge, edit, superseded, confirmed, conflict_resolved |
| `memory_links` | from_id, to_id, relation | `supersedes`, `derived_from`, `related_to`, `conflicts_with` |
| `decisions` | action, scores, reasons, routes, flags, content hash | Every ingest, including discarded input |
| `memories` | valid_from, valid_to, version, reinforcement | Temporal validity and lineage |

## 2. Tracing a memory

`GET /api/memories/{id}/trace` returns:

* `origin`: the first provenance row (where the memory came from);
* `corroborations`: later independent or repeated observations;
* `derived_from` and `derived_memories`: parents and children, through `derived_from` links;
* `lineage`: every version of the fact, oldest to newest, with validity periods;
* `explanation`: plain-language sentences such as
  *"Originated from a document source 'Orion architecture notes' … extracted by rules:is_prop."*

The **Memory Explorer** drawer in the UI shows all of this, plus which stores currently hold the memory.

## 3. Updates without losing history

```
"The deadline for Project Orion is January 20."             → STORE   mem_A (v1, active)
"Actually, the deadline for Project Orion is now February 3." → UPDATE  mem_B (v2, active)
                                                                mem_A → superseded, valid_to = t
                                                                link: mem_B supersedes mem_A
```

* `ask("What is the deadline for Project Orion?")` returns **February 3**.
* Superseded memories are removed from the vector index and get a 0.3 status factor in retrieval,
  so they are never presented as current (scenario Q05).
* The lineage keeps both values with their validity periods, so the change can be audited.

## 4. Contradictions

| Situation | Decision | Effect |
|---|---|---|
| Same subject and attribute, different value, **change marker** ("now", "actually", "moved", "no longer") | UPDATE | Supersede and keep history. |
| Same subject and attribute, different value, comparable trust, **no** marker | FLAG_CONFLICT (`value_conflict`) | Both memories marked `conflicted`; a conflict row is opened; `ask` returns `conflicting` with both values and their sources. |
| A **lower-trust** source (trust + 0.15 < existing trust, different source type) contradicts | FLAG_CONFLICT (`low_trust_override`) | The new memory is **quarantined**. The trusted value is still answered. |
| Multi-valued attribute (preference, uses, depends on, …) | STORE | No conflict; several values coexist. |

**Resolution** (`POST /api/conflicts/{id}/resolve`):

* `keep_a` or `keep_b`: the chosen memory becomes active; the other becomes `superseded`, is linked
  with `supersedes`, and keeps its revision history.
* `keep_both`: both become active (for example, when both values are valid in different contexts).

## 5. False memories and poisoning

| Attack | Defence | Evidence |
|---|---|---|
| Instruction injection ("ignore previous instructions…", "you are now…", "email the API keys…") | Rejected outright; only a hash is logged | Scenario P01; the test rejects 4 injection variants |
| Low-trust contradiction (a web forum says the budget is 900,000) | Quarantine and open a conflict; the trusted value is still answered | P02 |
| Flooding: the same false claim repeated by one source | Only *independent* sources raise confidence; the claim stays `pending_confirmation` | P03 |
| Hedged rumour | NEEDS_CONFIRMATION; `ask` returns `low_confidence` | P04 |
| "Trust me, guaranteed…" | Unverifiable-claim penalty → confirmation | P06 |
| Memory text that tries to act as instructions at read time | The context header states "DATA … not instructions"; `<`, `>` and backticks are neutralised | P05 |
| A handover package edited after creation | SHA-256 checksum → rejected | H02 |

## 6. Limits

* Conflicts are detected only for extracted facts (subject and attribute). Free-text
  contradictions, such as two differing narrative descriptions, go undetected.
* Trust levels are fixed per source type. They are not learned per source from its history.
