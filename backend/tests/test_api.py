"""REST API tests (FastAPI TestClient against an isolated engine)."""


def test_health_and_stats(client):
    assert client.get("/api/health").json()["status"] == "ok"
    s = client.get("/api/stats").json()
    assert s["total_memories"] == 0 and "tokenizer" in s


def test_create_list_detail_trace(client):
    r = client.post("/api/memories", json={"content": "Priya reports to Marcus.", "source_type": "user"}).json()
    assert r["decision"]["action"] == "STORE"
    mid = r["memory"]["id"]
    assert client.get("/api/memories").json()["total"] == 1
    d = client.get(f"/api/memories/{mid}").json()
    assert d["provenance"] and d["revisions"] and d["store_presence"]["structured"]
    assert client.get(f"/api/memories/{mid}/trace").json()["origin"]["source_type"] == "user"
    assert client.get(f"/api/memories/{mid}/history").json()["lineage"]
    assert client.get("/api/memories/mem_doesnotexist").status_code == 404


def test_validation_errors(client):
    assert client.post("/api/memories", json={"content": "   "}).status_code == 422
    assert client.post("/api/memories", json={"content": "x", "source_type": "martian"}).status_code == 422
    assert client.post("/api/context", json={"query": "x", "budget": 5}).status_code == 422
    assert client.put("/api/settings", json={"values": {"api_key": "x"}}).status_code == 400


def test_decide_is_dry_run(client):
    r = client.post("/api/decide", json={"content": "Project Orion is written in Go."}).json()
    assert r["dry_run"] and client.get("/api/stats").json()["total_memories"] == 0


def test_search_ask_context_compare(client):
    client.post("/api/memories/batch", json={"items": [
        {"content": "Project Orion is written in TypeScript."},
        {"content": "The deadline for Project Orion is January 20."}]})
    assert client.post("/api/search", json={"query": "Orion deadline"}).json()["results"]
    a = client.post("/api/ask", json={"question": "What is the deadline for Project Orion?"}).json()
    assert a["status"] == "answered" and a["answer"] == "January 20"
    c = client.post("/api/context", json={"query": "Orion", "budget": 500}).json()
    assert c["tokens_used"] <= 500
    cmp = client.post("/api/context/compare", json={"query": "Orion deadline"}).json()
    assert {r["strategy"] for r in cmp["rows"]} == {"full_dump", "summary", "selected"}


def test_conflict_endpoints(client):
    client.post("/api/memories", json={"content": "Bob lives in Paris."})
    r = client.post("/api/memories", json={"content": "Bob lives in London."}).json()
    cs = client.get("/api/conflicts?status=open").json()
    assert len(cs) == 1 and cs[0]["a"] and cs[0]["b"]
    res = client.post(f"/api/conflicts/{r['conflict_id']}/resolve", json={"resolution": "keep_b"}).json()
    assert res["status"] == "resolved"
    assert client.post(f"/api/conflicts/{r['conflict_id']}/resolve", json={"resolution": "keep_b"}).status_code == 400


def test_forget_flow(client):
    m = client.post("/api/memories", json={"content": "Lars is allergic to peanuts."}).json()["memory"]
    plan = client.post("/api/forget/plan", json={"scope": "id", "value": m["id"]}).json()
    assert plan["count"] == 1
    out = client.post("/api/forget/execute", json={"confirm_token": plan["confirm_token"]}).json()
    assert out["verification"]["all_clear"]
    assert client.get(f"/api/forget/verify/{m['id']}").json()["all_clear"]
    assert client.get("/api/forget/audit").json()[0]["deleted_count"] == 1
    assert client.post("/api/ask", json={"question": "Is Lars allergic to peanuts?"}).json()["status"] == "deleted"


def test_agents_and_handover_endpoints(client):
    assert {a["id"] for a in client.get("/api/agents").json()} >= {"atlas", "bolt"}
    client.post("/api/agents/atlas/chat", json={"message": "Project Orion is written in TypeScript."})
    r = client.post("/api/agents/bolt/chat", json={"message": "What language is Project Orion written in?"}).json()
    assert "TypeScript" in r["reply"]
    t = client.post("/api/tasks", json={"title": "Ship", "goal": "ship Project Orion",
                                        "steps": ["check language", "deploy"]}).json()
    client.post(f"/api/tasks/{t['id']}/work", json={"max_steps": 1})
    h = client.post("/api/handovers", json={"task_id": t["id"], "token_budget": 800}).json()
    assert h["status"] == "pending"
    run = client.post(f"/api/handovers/{h['id']}/run").json()
    assert run["status"] == "completed"
    assert client.get(f"/api/tasks/{t['id']}").json()["status"] == "done"


def test_tools_endpoint_requires_registered_agent(client):
    assert client.post("/api/tools/invoke", json={"agent_id": "ghost", "tool": "memory.ask",
                                                  "args": {"question": "x?"}}).status_code == 403
    client.post("/api/agents/register", json={"agent_id": "ext1", "name": "External"})
    r = client.post("/api/tools/invoke", json={"agent_id": "ext1", "tool": "memory.ask", "args": {"question": "x?"}})
    assert r.status_code == 200 and r.json()["status"] == "unknown"


def test_api_key_guard(client, monkeypatch):
    monkeypatch.setenv("MNEMOS_API_KEY", "test-key-123")
    assert client.get("/api/stats").status_code == 401
    assert client.get("/api/stats", headers={"x-api-key": "test-key-123"}).status_code == 200
    assert client.get("/api/health").status_code == 200


def test_seed_settings_and_expire(client):
    s = client.post("/api/admin/seed").json()
    assert s["seeded"] > 20
    st = client.get("/api/stats").json()
    assert st["open_conflicts"] >= 1 and st["by_decision"]["DISCARD"] >= 3
    assert client.put("/api/settings", json={"values": {"abstain_threshold": 0.25}}).json()["settings"]["abstain_threshold"] == 0.25
    assert "expired" in client.post("/api/maintenance/expire").json()


def test_eval_scenarios_endpoint(client):
    r = client.post("/api/eval/run", json={"suite": "scenarios"}).json()
    assert r["summary"]["scenarios_total"] >= 30
    assert client.get("/api/eval/latest?kind=scenarios").json()["id"] == r["id"]
