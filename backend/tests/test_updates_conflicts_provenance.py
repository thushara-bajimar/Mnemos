"""Updates, duplicates, contradictions, provenance and history."""


def test_update_supersedes_and_keeps_history(engine, ingest):
    a = ingest("The deadline for Project Orion is January 20.")["memory"]
    r = ingest("Actually, the deadline for Project Orion is now February 3.")
    assert r["decision"]["action"] == "UPDATE"
    assert engine.structured.get(a["id"])["status"] == "superseded"
    lineage = engine.memory.lineage(r["memory"]["id"])
    assert [m["value"] for m in lineage] == ["January 20", "February 3"]
    assert engine.retriever.ask("What is the deadline for Project Orion?")["answer"] == "February 3"


def test_duplicate_merge_and_corroboration(engine, ingest):
    a = ingest("Project Orion uses PostgreSQL.", source_type="document", source_id="doc1")["memory"]
    same = ingest("Project Orion uses PostgreSQL.", source_type="document", source_id="doc1")
    assert same["decision"]["action"] == "MERGE"
    assert engine.structured.get(a["id"])["reinforcement"] == 1  # same source: no boost
    ingest("Project Orion uses PostgreSQL.", source_type="agent", agent_id="bolt")
    m = engine.structured.get(a["id"])
    assert m["reinforcement"] == 2 and m["confidence"] > a["confidence"]
    assert engine.db.one("SELECT COUNT(*) n FROM memories")["n"] == 1


def test_value_conflict_and_resolution(engine, ingest):
    ingest("Bob lives in Paris.")
    r = ingest("Bob lives in London.")
    assert r["decision"]["action"] == "FLAG_CONFLICT" and r["conflict_id"]
    assert engine.retriever.ask("Where does Bob live?")["status"] == "conflicting"
    engine.memory.resolve_conflict(r["conflict_id"], "keep_a")
    a = engine.retriever.ask("Where does Bob live?")
    assert a["status"] == "answered" and a["answer"] == "Paris"


def test_low_trust_override_is_quarantined(engine, ingest):
    ingest("The budget for Project Orion is 40000 dollars.", source_type="document")
    r = ingest("The budget for Project Orion is 900000 dollars.", source_type="web")
    assert r["decision"]["action"] == "FLAG_CONFLICT"
    assert r["memory"]["status"] == "quarantined"
    assert "low_trust_override" in r["decision"]["flags"]
    assert engine.retriever.ask("What is the budget for Project Orion?")["answer"] == "40000 dollars"


def test_confirmation_flow(engine, ingest):
    r = ingest("Maybe the client wants a mobile app too.")
    mid = r["memory"]["id"]
    assert r["memory"]["status"] == "pending_confirmation"
    engine.memory.confirm(mid, True)
    assert engine.structured.get(mid)["status"] == "active"
    r2 = ingest("Perhaps the launch slips to Q3.")
    engine.memory.confirm(r2["memory"]["id"], False)
    assert not engine.structured.contains(r2["memory"]["id"])


def test_provenance_trace_and_derivation(engine, ingest):
    p = ingest("Project Orion depends on the Auth Gateway.", source_type="document", source_id="doc:arch",
               source_label="Architecture notes", agent_id="atlas", session_id="s1")["memory"]
    d = ingest("Atlas noted Orion needs Auth Gateway credentials for staging.", source_type="agent",
               derived_from=[p["id"]])["memory"]
    t = engine.memory.trace(p["id"])
    assert t["origin"]["source_label"] == "Architecture notes" and t["origin"]["session_id"] == "s1"
    assert any(x["id"] == d["id"] for x in t["derived_memories"])
    assert engine.memory.trace(d["id"])["derived_from"][0]["id"] == p["id"]
    assert t["explanation"]


def test_manual_edit_creates_revision(engine, ingest):
    m = ingest("Project Orion is written in TypeScript.")["memory"]
    engine.memory.edit(m["id"], "Project Orion is written in Kotlin.", reason="typo")
    d = engine.memory.detail(m["id"])
    assert d["version"] == 2 and [r["change_type"] for r in d["revisions"]] == ["create", "edit"]
