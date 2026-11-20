"""Deletion across all stores, cascades, verification, audit and expiry."""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest


def _raw(engine) -> bytes:
    engine.forgetting.compact()
    out = b""
    for p in [str(engine.settings.db_path), f"{engine.settings.db_path}-wal"]:
        if os.path.exists(p):
            out += open(p, "rb").read()
    return out


def test_delete_by_id_clears_every_store(engine, ingest):
    m = ingest("To rotate the Orion signing key ZEBRA42, first revoke the old key, then run the rotate script.")["memory"]
    assert {"file", "vector", "graph"} <= set(m["storage_routes"])
    engine.retriever.search("rotate signing key")  # populate cache
    out = engine.forgetting.delete_ids([m["id"]])
    v = out["verification"]
    assert v["all_clear"] and v["logical_clear"] and not v["physical_residue"]
    assert not any(engine.forgetting.presence(m["id"]).values())
    assert b"ZEBRA42" not in _raw(engine)


def test_two_phase_deletion_requires_token(engine, ingest):
    ingest("Project Nova is written in Rust.")
    plan = engine.forgetting.plan("topic", "Project Nova")
    assert plan["count"] == 1 and plan["confirm_token"]
    with pytest.raises(ValueError):
        engine.forgetting.execute("bogus-token-123")
    assert engine.forgetting.execute(plan["confirm_token"])["count"] == 1
    with pytest.raises(ValueError):  # tokens are single-use
        engine.forgetting.execute(plan["confirm_token"])


def test_delete_by_entity_cascades_to_derived(engine, ingest):
    p = ingest("Kemi lives in Accra.")["memory"]
    d = ingest("Atlas booked the onsite in Accra for the visitor.", source_type="agent", derived_from=[p["id"]])["memory"]
    plan = engine.forgetting.plan("entity", "Kemi")
    cascaded = [i for i in plan["items"] if i["cascade"]]
    assert any(i["id"] == d["id"] for i in cascaded)
    out = engine.forgetting.execute(plan["confirm_token"])
    assert set(out["deleted"]) >= {p["id"], d["id"]}


def test_delete_by_source(engine, ingest):
    ingest("Project Lyra is written in Go.", session_id="sA")
    ingest("Project Lyra uses Redis.", session_id="sA")
    keep = ingest("Project Lyra has three engineers.", session_id="sB")["memory"]
    out = engine.forgetting.execute(engine.forgetting.plan("source", "sA")["confirm_token"])
    assert out["count"] == 2 and engine.structured.contains(keep["id"])


def test_deleted_vs_unknown_vs_expired(engine, ingest):
    m = ingest("Lars is allergic to peanuts.")["memory"]
    engine.forgetting.delete_ids([m["id"]])
    assert engine.retriever.ask("Is Lars allergic to peanuts?")["status"] == "deleted"
    assert engine.retriever.ask("What is the capital of Mars?")["status"] == "unknown"
    ingest("I am currently debugging the flaky upload test for now.")
    engine.memory.expire_sweep(datetime.now(timezone.utc) + timedelta(days=2))
    assert engine.retriever.ask("What am I currently debugging in the upload test?")["status"] == "expired"


def test_audit_keeps_no_content(engine, ingest):
    m = ingest("The vault codename for Project Cobalt is NIGHTJAR.")["memory"]
    engine.forgetting.delete_ids([m["id"]], requested_by="tester")
    audit = engine.db.query("SELECT * FROM deletion_audit")
    assert len(audit) == 1 and "NIGHTJAR" not in json.dumps(audit) and "Cobalt" not in json.dumps(audit)
    assert engine.db.one("SELECT preview FROM decisions")["preview"] is None


def test_deletion_redacts_handover_snapshots(engine, ingest):
    m = ingest("Project Orion is written in TypeScript.")["memory"]
    t = engine.agents.atlas.plan("Orion", "Project Orion TypeScript", steps=["review"])
    h = engine.agents.create_handover(t["id"], "atlas", "bolt", 1000)
    assert any(x["id"] == m["id"] for x in h["package"]["relevant_memories"])
    engine.forgetting.delete_ids([m["id"]])
    pkg = engine.agents.get_handover(h["id"])["package"]
    assert "written in TypeScript" not in json.dumps(pkg)


def test_expiry_purges_content(engine, ingest):
    m = ingest("Today the office wifi code is BLUEFALCON.")["memory"]
    assert m["expires_at"]
    engine.memory.expire_sweep(datetime.now(timezone.utc) + timedelta(days=3))
    row = engine.structured.get(m["id"])
    assert row["status"] == "expired" and row["content"] == "[expired]" and row["entities"] == []
    assert b"BLUEFALCON" not in _raw(engine)
