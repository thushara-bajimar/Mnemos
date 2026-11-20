"""Minimal Python REST agent — shows how any external process can use Mnemos.

    python agents/python_rest_agent.py "What is the deadline for Project Orion?"

Env: MNEMOS_URL (default http://127.0.0.1:8000), MNEMOS_API_KEY (optional).
"""
from __future__ import annotations

import json
import os
import sys

import httpx

BASE = os.environ.get("MNEMOS_URL", "http://127.0.0.1:8000")
HEADERS = {"x-api-key": os.environ["MNEMOS_API_KEY"]} if os.environ.get("MNEMOS_API_KEY") else {}


def tool(client: httpx.Client, name: str, **args):
    r = client.post("/api/tools/invoke", json={"agent_id": "py-rest", "tool": name, "args": args})
    r.raise_for_status()
    return r.json()


def main() -> None:
    q = sys.argv[1] if len(sys.argv) > 1 else "What is the deadline for Project Orion?"
    with httpx.Client(base_url=BASE, headers=HEADERS, timeout=30) as c:
        c.post("/api/agents/register", json={"agent_id": "py-rest", "name": "Python REST agent", "integration": "REST (httpx)"})
        print(json.dumps(tool(c, "memory.ask", question=q), indent=2))


if __name__ == "__main__":
    main()
