# Forgetting and Privacy

## 1. Privacy by design: what is never kept

| Data | Handling |
|---|---|
| Secrets (passwords, API keys, private keys, card numbers, bearer tokens) | Rejected. The decision log keeps only a SHA-256 hash and the flag `secret_detected`; no preview. |
| PII (emails, phone numbers) | Redacted to `[REDACTED_EMAIL]` or `[REDACTED_PHONE]` before any storage. |
| Discarded input | Hash only. The preview is off by default (`retain_discarded_preview=false`). |
| Raw conversations | Not retained. Only extracted memories are stored. Agent logs pass through the same redaction. |
| Provenance | Stores a hash of the raw input, not the input itself. |

## 2. Deletion scopes

| Scope | Selects |
|---|---|
| `id` | The given memory ids (comma-separated). |
| `topic` | Memories matching a free-text topic (hybrid score ≥ 0.35, or a keyword hit). |
| `entity` | Memories mentioning an entity, found through the graph and through text/subject/entity columns. |
| `source` | Memories whose provenance has that source_id, agent_id, session_id or source_label. |

With `include_derived` (the default), the plan also includes **derived memories**, followed
recursively through `derived_from` links, and **older versions**, followed through `supersedes`
links. Forgetting a fact therefore also forgets its earlier values.

## 3. Two-phase protocol

```
POST /api/forget/plan    {scope, value, include_derived}
   → {count, items[ {id, content preview, status, cascade, stores-currently-holding} ], confirm_token}
POST /api/forget/execute {confirm_token}       # single use, valid for 10 minutes
   → {deleted[], verification{all_clear, logical_clear, physical_residue[], per_memory{...}}, audit_id}
```

## 4. What is removed

For each memory id:

* the `memories` row (structured store) and the `memories_fts` row (keyword store);
* the `vectors` row and its in-memory numpy index row (vector store);
* `edges` and `entity_mentions`, plus any entities left orphaned (graph store);
* the Markdown file, which is overwritten with zeros and then unlinked (file store);
* `provenance`, `revisions` (these contain old content), `memory_links` and `conflicts`;
* the decision log preview and its memory reference;
* copies in **task** constraints, decisions and step notes;
* copies in **handover packages**: the memory is replaced by `{"content": "[deleted]"}`; affected
  constraints and decisions are redacted; the context is invalidated if it quoted the memory; and
  the package is re-sealed with a new checksum and a `redactions` entry;
* **agent-log** messages that quote the memory;
* the **retrieval cache**, which is cleared.

After deletion, Mnemos runs `INSERT INTO memories_fts(memories_fts) VALUES('optimize')`, which
merges FTS segments, and `PRAGMA wal_checkpoint(TRUNCATE)`. With `PRAGMA secure_delete=ON`, freed
pages are zeroed.

## 5. Verification

* **Logical:** presence checks across structured, keyword, vector, graph, file, provenance,
  revisions, links, handovers and the cache. Every one must report false.
* **Physical:** the raw bytes of `mnemos.db`, `mnemos.db-wal` and every memory file are scanned for
  the first 60 characters of each deleted content version.
* `all_clear` is true only if both checks pass. Tests F01 and F05, and
  `test_delete_by_id_clears_every_store`, confirm that a unique token is gone from the raw bytes.

The storage benchmark also shows why `secure_delete` matters. With it **OFF**, deleted text was
still found in the SQLite file; with it **ON**, the text was not found.

## 6. Audit trail (privacy-safe)

The `deletion_audit` table holds: id, scope, deleted_count, stores, verified, requested_by,
created_at and `term_hashes`.

`term_hashes` are salted SHA-256 hashes (truncated) of the deleted content's stemmed terms. They
allow `ask()` to answer **"deleted"** rather than "unknown" when someone asks about forgotten
information, without keeping the information itself. The salt is random for each installation.

## 7. Expiry

Temporary memories get an `expires_at`. `POST /api/maintenance/expire`, or the Overview button,
runs the expiry sweep. For each expired memory it:

* unindexes it from the keyword, vector, graph and file stores;
* replaces the content with `[expired]` and clears the subject, attribute, value, entities and tags;
* deletes its revisions and decision preview;
* writes an `expiry` audit entry with term hashes.

`ask()` then reports **expired**. Scenario T04 verifies with a raw-byte scan that the content is
gone from disk.

## 8. Backup and recovery limitations

* **Backups and copies** of `backend/data/` made outside Mnemos (manual copies, cloud sync, system
  backups) are not touched by deletion. To meet a deletion request, those must be rotated or purged
  separately.
* **SSD and OS level:** zero-overwriting a file does not guarantee physical erasure on SSDs (wear
  levelling) or journaling file systems. Use full-disk encryption.
* **Recovery:** forgotten memories cannot be recovered from Mnemos, by design; there is no recycle bin.
* **Term hashes:** an attacker with database access could test guessed words against the salted
  hashes, which confirms a guess but reveals nothing beyond it. Turn off tombstone answers if this
  matters for you (future option).
* **External copies:** text that an external agent already copied into its own storage or logs
  cannot be recalled.
* **Reset:** `POST /api/admin/reset` with `{"confirm": "RESET"}` deletes the entire local database
  and all files.
