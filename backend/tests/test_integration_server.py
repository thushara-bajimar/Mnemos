"""Integration tests against a real uvicorn server process.

Proves cross-process interoperability: a Node.js agent and a Python REST
agent use the same persistent memory, a handover addressed to the Node.js
agent is completed by it, and memory persists across a server restart.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _start(data_dir: Path, port: int) -> subprocess.Popen:
    env = {**os.environ, "MNEMOS_DATA_DIR": str(data_dir), "PYTHONIOENCODING": "utf-8"}
    env.pop("MNEMOS_API_KEY", None)
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
                         cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1).status_code == 200:
                return p
        except httpx.HTTPError:
            time.sleep(0.15)
    p.kill()
    raise RuntimeError("server did not start: " + p.stderr.read().decode(errors="ignore")[-2000:])


@pytest.fixture
def server(tmp_path):
    port = _free_port()
    proc = _start(tmp_path / "live", port)
    yield {"url": f"http://127.0.0.1:{port}", "port": port, "data": tmp_path / "live", "proc": proc}
    proc.terminate()
    proc.wait(timeout=10)


def test_persistence_across_server_restart(tmp_path):
    port = _free_port()
    p = _start(tmp_path / "restart", port)
    url = f"http://127.0.0.1:{port}"
    mid = httpx.post(f"{url}/api/memories", json={"content": "Project Orion is written in TypeScript."}).json()["memory"]["id"]
    p.terminate()
    p.wait(timeout=10)
    p2 = _start(tmp_path / "restart", port)
    try:
        assert httpx.get(f"{url}/api/memories/{mid}").status_code == 200
        a = httpx.post(f"{url}/api/ask", json={"question": "What language is Project Orion written in?"}).json()
        assert a["answer"] == "TypeScript"
    finally:
        p2.terminate()
        p2.wait(timeout=10)


def test_python_rest_agent(server):
    httpx.post(f"{server['url']}/api/memories", json={"content": "The deadline for Project Orion is January 20."})
    out = subprocess.run([sys.executable, str(ROOT / "agents" / "python_rest_agent.py"),
                          "What is the deadline for Project Orion?"],
                         env={**os.environ, "MNEMOS_URL": server["url"]}, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["answer"] == "January 20"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_node_agent_shares_memory_and_completes_handover(server):
    url = server["url"]
    env = {**os.environ, "MNEMOS_URL": url}
    node = shutil.which("node")
    demo = subprocess.run([node, str(ROOT / "agents" / "node_agent.mjs"), "demo"], env=env, capture_output=True,
                          text=True, timeout=60)
    assert demo.returncode == 0, demo.stderr
    d = json.loads(demo.stdout)
    assert d["remember"]["action"] == "STORE"
    assert d["ask"]["status"] == "answered"
    assert d["injection"]["action"] == "DISCARD"
    # the memory written by the Node agent is visible to the built-in Python agent (Bolt)
    r = httpx.post(f"{url}/api/agents/bolt/chat", json={"message": "Which region does the Orion staging cluster run in?"}).json()
    assert "eu-west" in r["reply"]
    # Atlas hands a task over to the Node.js agent, which completes it over HTTP
    t = httpx.post(f"{url}/api/tasks", json={"title": "Verify staging", "goal": "verify Orion staging cluster",
                                            "steps": ["Check the staging region", "Report status"]}).json()
    h = httpx.post(f"{url}/api/handovers", json={"task_id": t["id"], "from_agent": "atlas", "to_agent": "relay",
                                                "token_budget": 800}).json()
    out = subprocess.run([node, str(ROOT / "agents" / "node_agent.mjs"), "handover", h["id"]], env=env,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["status"] == "completed"
    assert httpx.get(f"{url}/api/tasks/{t['id']}").json()["status"] == "done"
    assert httpx.get(f"{url}/api/handovers/{h['id']}").json()["status"] == "completed"
