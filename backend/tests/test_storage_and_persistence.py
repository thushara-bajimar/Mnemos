"""Storage routing, multi-store indexing and persistence across restarts."""
from app.config import Settings
from app.engine import Mnemos


def test_routing_by_type(engine, ingest):
    fact = ingest("The office is closed on public holidays.")["memory"]
    assert {"structured", "keyword", "vector"} <= set(fact["storage_routes"]) and "file" not in fact["storage_routes"]
    rel = ingest("Priya reports to Marcus.")["memory"]
    assert "graph" in rel["storage_routes"] and engine.graph.contains(rel["id"])
    proc = ingest("To deploy Orion, first run migrations, then restart the pods.")["memory"]
    assert "file" in proc["storage_routes"] and engine.files.contains(proc["id"])
    tmp = ingest("Right now I am reviewing pull request 42.")["memory"]
    assert "vector" not in tmp["storage_routes"] and not engine.vector.contains(tmp["id"])


def test_every_route_is_really_indexed(engine, ingest):
    m = ingest("Priya reports to Marcus on the platform team.")["memory"]
    p = engine.forgetting.presence(m["id"])
    for store in m["storage_routes"]:
        assert p[store], f"{store} should contain the memory"


def test_memory_survives_restart(tmp_path):
    from app.services.decision import Candidate

    s = Settings(data_dir=tmp_path / "persist")
    e1 = Mnemos(s)
    mid = e1.memory.ingest(Candidate(content="Project Orion is written in TypeScript."))["memory"]["id"]
    e1.close()
    e2 = Mnemos(Settings(data_dir=tmp_path / "persist"))
    assert e2.structured.contains(mid)
    assert e2.vector.contains(mid)  # in-memory vector index rebuilt from SQLite
    assert e2.retriever.ask("What language is Project Orion written in?")["answer"] == "TypeScript"
    e2.close()


def test_settings_override_persists(tmp_path):
    s = Settings(data_dir=tmp_path / "cfg")
    e1 = Mnemos(s)
    e1.update_settings({"abstain_threshold": 0.3})
    e1.close()
    e2 = Mnemos(Settings(data_dir=tmp_path / "cfg"))
    assert e2.settings.abstain_threshold == 0.3
    e2.close()
