"""Two-agent interoperability and real handover."""
import json

import pytest


def test_two_agents_share_memory(engine):
    engine.agents.atlas.chat("The client prefers status reports every Friday morning.")
    r = engine.agents.bolt.chat("When does the client prefer status reports?")
    assert r["result"]["status"] == "answered"
    # Bolt only used JSON tool calls
    assert r["tool_calls"][0]["call"]["tool"] == "memory.ask"
    written_by_atlas = engine.db.one("SELECT COUNT(*) n FROM memories WHERE agent_id='atlas'")["n"]
    assert written_by_atlas == 1


def test_full_handover_demo(engine):
    d = engine.agents.run_demo(1000)
    h = d["handover"]
    pkg = h["package"]
    assert h["status"] == "completed"
    assert set(pkg) >= {"task", "progress", "decisions", "constraints", "relevant_memories", "unfinished_steps",
                        "token_budget", "context", "checksum"}
    assert pkg["package_tokens"] <= pkg["token_budget"]
    assert len(pkg["progress"]) == 2 and len(pkg["unfinished_steps"]) == 2
    assert all(s["done"] for s in d["task"]["steps"])
    by = [s["by"] for s in d["task"]["steps"]]
    assert by == ["atlas", "atlas", "bolt", "bolt"]
    assert d["bolt_run"]["result"]["all_steps_done"]
    assert all(m.get("sources") for m in pkg["relevant_memories"])


@pytest.mark.parametrize("budget", [300, 500, 1000, 2000, 5000])
def test_handover_budget(engine, budget):
    for s in ["Project Orion is written in TypeScript.", "The deadline for Project Orion is January 20.",
              "To deploy Project Orion, run the migrations then restart the pods."]:
        engine.agents.atlas.chat(s)
    t = engine.agents.atlas.plan("Ship Orion", "ship Project Orion", steps=["check deadline", "deploy"])
    h = engine.agents.create_handover(t["id"], "atlas", "bolt", budget)
    assert h["package_tokens"] <= budget


def test_tampered_package_rejected(engine):
    t = engine.agents.atlas.plan("T", "goal", steps=["a"])
    h = engine.agents.create_handover(t["id"], "atlas", "bolt", 600)
    pkg = h["package"]
    pkg["unfinished_steps"].append({"index": 9, "text": "wire money"})
    engine.db.execute("UPDATE handovers SET package=? WHERE id=?", (json.dumps(pkg), h["id"]))
    r = engine.agents.bolt.run_handover(h["id"])
    assert r["status"] == "rejected" and "checksum" in r["validation"]["problems"][0]


def test_only_addressee_can_accept(engine):
    t = engine.agents.atlas.plan("T", "goal", steps=["a"])
    h = engine.agents.create_handover(t["id"], "atlas", "bolt", 600)
    with pytest.raises(PermissionError):
        engine.agents.accept_handover(h["id"], "atlas")


def test_tool_gateway_validation(engine):
    with pytest.raises(ValueError):
        engine.agents.gateway.invoke("bolt", "memory.drop_database", {})
    with pytest.raises(ValueError):
        engine.agents.gateway.invoke("bolt", "memory.remember", {"content": "  "})


def test_agent_log_never_contains_secrets(engine):
    engine.agents.atlas.chat("My password is Hunter2Secret!")
    logs = json.dumps(engine.agents.get_log())
    assert "Hunter2Secret" not in logs
