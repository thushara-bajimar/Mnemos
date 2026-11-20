"""FastAPI application exposing the Mnemos REST API.

Run:  uvicorn app.main:app --reload --port 8000   (from the backend/ folder)
Docs: http://localhost:8000/docs (OpenAPI / Swagger UI)
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import shutil

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.schemas import (AskIn, BatchIn, ChatIn, CompareIn, ConfirmIn, ContextIn, EditIn, EvalIn, ForgetExecIn,
                          ForgetPlanIn, HandoverIn, MemoryIn, RegisterAgentIn, ResetIn, ResolveIn, SearchIn,
                          SettingsIn, TaskIn, ToolIn, WorkIn)
from .config import Settings
from .core.router import ROUTE_DESCRIPTIONS
from .engine import Mnemos
from .services.agents import TOOLS
from .services.decision import Candidate

logging.basicConfig(level=os.environ.get("MNEMOS_LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("mnemos.api")

_engine: Mnemos | None = None


def get_engine() -> Mnemos:
    global _engine
    if _engine is None:
        _engine = Mnemos(Settings())
    return _engine


def set_engine(e: Mnemos | None) -> None:
    """Used by tests to inject an isolated engine."""
    global _engine
    _engine = e


app = FastAPI(
    title="Mnemos API",
    version="1.0.0",
    description="Memory with Meaning. Context with Control. — a memory system for AI agents that decides what to "
                "keep, how to store it, what to retrieve, and when to forget.",
)
app.add_middleware(
    CORSMiddleware, allow_origins=Settings().cors_origins, allow_methods=["*"], allow_headers=["*"],
)


@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    key = os.environ.get("MNEMOS_API_KEY")
    if key and request.url.path.startswith("/api") and request.url.path != "/api/health" and request.method != "OPTIONS":
        if not secrets.compare_digest(request.headers.get("x-api-key", ""), key):
            return JSONResponse({"detail": "missing or invalid X-API-Key"}, status_code=401)
    return await call_next(request)


@app.exception_handler(ValueError)
async def _value_error(_, exc: ValueError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(KeyError)
async def _key_error(_, exc: KeyError):
    return JSONResponse({"detail": str(exc).strip("'\"")}, status_code=404)


@app.exception_handler(PermissionError)
async def _perm_error(_, exc: PermissionError):
    return JSONResponse({"detail": str(exc)}, status_code=403)


def _cand(m: MemoryIn) -> Candidate:
    return Candidate(**m.model_dump())


E = Depends(get_engine)

# ------------------------------------------------------------------ system


@app.get("/api/health", tags=["system"])
def health(e: Mnemos = E):
    return {"status": "ok", "memories": e.db.one("SELECT COUNT(*) n FROM memories")["n"]}


@app.get("/api/stats", tags=["system"])
def stats(e: Mnemos = E):
    return e.stats()


@app.get("/api/settings", tags=["system"])
def get_settings(e: Mnemos = E):
    return {"settings": e.settings.public_dict(), "routes": ROUTE_DESCRIPTIONS, **{"tokenizer": e.stats()["tokenizer"]},
            "embedder": e.embedder.name}


@app.put("/api/settings", tags=["system"])
def put_settings(body: SettingsIn, e: Mnemos = E):
    return {"settings": e.update_settings(body.values)}


@app.post("/api/admin/seed", tags=["system"])
def seed(e: Mnemos = E):
    from .evaluation.demo_data import seed_demo

    return seed_demo(e)


@app.post("/api/admin/reset", tags=["system"])
def reset(body: ResetIn, e: Mnemos = E):
    """Delete ALL local data (database + files). Requires {"confirm": "RESET"}."""
    settings = e.settings
    e.close()
    for p in [settings.db_path, f"{settings.db_path}-wal", f"{settings.db_path}-shm"]:
        if os.path.exists(p):
            os.remove(p)
    shutil.rmtree(settings.files_dir, ignore_errors=True)
    set_engine(Mnemos(settings))
    return {"reset": True}


# ------------------------------------------------------------------ memories


@app.post("/api/decide", tags=["memory"])
def decide(body: MemoryIn, e: Mnemos = E):
    """Dry-run the decision engine: nothing is stored."""
    return e.memory.ingest(_cand(body), dry_run=True)


@app.post("/api/memories", tags=["memory"])
def create_memory(body: MemoryIn, dry_run: bool = False, e: Mnemos = E):
    return e.memory.ingest(_cand(body), dry_run=dry_run)


@app.post("/api/memories/batch", tags=["memory"])
def create_batch(body: BatchIn, e: Mnemos = E):
    out = [e.memory.ingest(_cand(m)) for m in body.items]
    return {"results": out, "actions": [o["decision"]["action"] for o in out]}


@app.get("/api/memories", tags=["memory"])
def list_memories(status: str | None = None, memory_type: str | None = None, agent_id: str | None = None,
                  source_type: str | None = None, q: str | None = None, task_id: str | None = None,
                  limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), e: Mnemos = E):
    return e.memory.list(status, memory_type, agent_id, source_type, q, task_id, limit, offset)


@app.get("/api/memories/{memory_id}", tags=["memory"])
def get_memory(memory_id: str, e: Mnemos = E):
    m = e.memory.detail(memory_id)
    if not m:
        raise HTTPException(404, "memory not found (it may never have existed, or was deleted)")
    return m


@app.put("/api/memories/{memory_id}", tags=["memory"])
def edit_memory(memory_id: str, body: EditIn, e: Mnemos = E):
    return e.memory.edit(memory_id, body.content, body.actor, body.reason)


@app.get("/api/memories/{memory_id}/trace", tags=["provenance"])
def trace(memory_id: str, e: Mnemos = E):
    return e.memory.trace(memory_id)


@app.get("/api/memories/{memory_id}/history", tags=["provenance"])
def history(memory_id: str, e: Mnemos = E):
    if not e.structured.contains(memory_id):
        raise HTTPException(404, "memory not found")
    return {"lineage": e.memory.lineage(memory_id),
            "revisions": e.db.query("SELECT * FROM revisions WHERE memory_id=? ORDER BY created_at", (memory_id,))}


@app.post("/api/memories/{memory_id}/confirm", tags=["memory"])
def confirm(memory_id: str, body: ConfirmIn, e: Mnemos = E):
    return e.memory.confirm(memory_id, body.approve, body.actor)


@app.get("/api/decisions", tags=["memory"])
def decisions(limit: int = Query(100, ge=1, le=500), action: str | None = None, e: Mnemos = E):
    sql = "SELECT * FROM decisions" + (" WHERE action=?" if action else "") + " ORDER BY created_at DESC, rowid DESC LIMIT ?"
    rows = e.db.query(sql, ([action] if action else []) + [limit])
    for r in rows:
        for k in ("scores", "reasons", "routes", "flags"):
            r[k] = json.loads(r[k])
    return rows


@app.get("/api/graph", tags=["memory"])
def graph(entity: str | None = None, e: Mnemos = E):
    return e.graph.neighbourhood(entity) if entity else e.graph.full_graph()


# ------------------------------------------------------------------ retrieval


@app.post("/api/search", tags=["retrieval"])
def search(body: SearchIn, e: Mnemos = E):
    return e.retriever.search(body.query, body.mode, body.limit, body.memory_types, body.agent_id, body.task_id,
                              body.source_types, body.min_confidence, body.include_inactive)


@app.post("/api/ask", tags=["retrieval"])
def ask(body: AskIn, e: Mnemos = E):
    return e.retriever.ask(body.question, body.task_id)


@app.post("/api/context", tags=["retrieval"])
def context(body: ContextIn, e: Mnemos = E):
    return e.retriever.assemble(body.query, body.budget, body.task_id, body.mode, body.memory_types, body.compact)


@app.post("/api/context/compare", tags=["retrieval"])
def context_compare(body: CompareIn, e: Mnemos = E):
    from .evaluation.context_compare import compare_live

    return compare_live(e, body.query, body.budgets)


# ------------------------------------------------------------------ conflicts


@app.get("/api/conflicts", tags=["conflicts"])
def conflicts(status: str | None = None, e: Mnemos = E):
    sql = "SELECT * FROM conflicts" + (" WHERE status=?" if status else "") + " ORDER BY created_at DESC"
    rows = e.db.query(sql, [status] if status else [])
    for r in rows:
        r["a"] = e.structured.get(r["memory_a"])
        r["b"] = e.structured.get(r["memory_b"])
    return rows


@app.post("/api/conflicts/{conflict_id}/resolve", tags=["conflicts"])
def resolve(conflict_id: str, body: ResolveIn, e: Mnemos = E):
    return e.memory.resolve_conflict(conflict_id, body.resolution, body.actor)


@app.get("/api/pending", tags=["conflicts"])
def pending(e: Mnemos = E):
    return e.memory.list(status="pending_confirmation")["items"] + e.memory.list(status="quarantined")["items"]


@app.get("/api/updates", tags=["conflicts"])
def updates(limit: int = 50, e: Mnemos = E):
    """Recent supersede links (fact updates) with old/new values."""
    rows = e.db.query("SELECT * FROM memory_links WHERE relation='supersedes' ORDER BY created_at DESC LIMIT ?", (limit,))
    return [{"new": e.structured.get(r["from_id"]), "old": e.structured.get(r["to_id"]), "at": r["created_at"]} for r in rows]


# ------------------------------------------------------------------ forgetting


@app.post("/api/forget/plan", tags=["forgetting"])
def forget_plan(body: ForgetPlanIn, e: Mnemos = E):
    return e.forgetting.plan(body.scope, body.value, body.include_derived)


@app.post("/api/forget/execute", tags=["forgetting"])
def forget_execute(body: ForgetExecIn, e: Mnemos = E):
    return e.forgetting.execute(body.confirm_token, body.requested_by)


@app.get("/api/forget/verify/{memory_id}", tags=["forgetting"])
def forget_verify(memory_id: str, e: Mnemos = E):
    return e.forgetting.verify([memory_id])


@app.get("/api/forget/audit", tags=["forgetting"])
def forget_audit(e: Mnemos = E):
    return e.forgetting.audit_log()


@app.post("/api/maintenance/expire", tags=["forgetting"])
def expire(e: Mnemos = E):
    return e.memory.expire_sweep()


# ------------------------------------------------------------------ agents


@app.get("/api/agents", tags=["agents"])
def agents(e: Mnemos = E):
    return e.agents.list_agents()


@app.post("/api/agents/register", tags=["agents"])
def register_agent(body: RegisterAgentIn, e: Mnemos = E):
    return e.agents.register_external(body.agent_id, body.name, body.integration)


@app.get("/api/agents/log", tags=["agents"])
def agent_log(agent_id: str | None = None, task_id: str | None = None, limit: int = 100, e: Mnemos = E):
    return e.agents.get_log(agent_id, task_id, limit)


@app.post("/api/agents/{agent_id}/chat", tags=["agents"])
def agent_chat(agent_id: str, body: ChatIn, e: Mnemos = E):
    if agent_id == "atlas":
        return e.agents.atlas.chat(body.message, body.task_id)
    if agent_id == "bolt":
        return e.agents.bolt.chat(body.message, body.task_id)
    raise HTTPException(404, "built-in agents are 'atlas' and 'bolt'; external agents use /api/tools/invoke")


@app.get("/api/tools", tags=["agents"])
def tools():
    return TOOLS


@app.post("/api/tools/invoke", tags=["agents"])
def tools_invoke(body: ToolIn, e: Mnemos = E):
    if not e.db.one("SELECT 1 x FROM agents WHERE id=?", (body.agent_id,)):
        raise HTTPException(403, "unknown agent — register it first via /api/agents/register")
    return e.agents.gateway.invoke(body.agent_id, body.tool, body.args)


@app.get("/api/tasks", tags=["agents"])
def tasks(e: Mnemos = E):
    return e.agents.list_tasks()


@app.post("/api/tasks", tags=["agents"])
def create_task(body: TaskIn, e: Mnemos = E):
    return e.agents.atlas.plan(body.title, body.goal, body.steps, body.constraints)


@app.get("/api/tasks/{task_id}", tags=["agents"])
def get_task(task_id: str, e: Mnemos = E):
    return e.agents.get_task(task_id)


@app.post("/api/tasks/{task_id}/work", tags=["agents"])
def atlas_work(task_id: str, body: WorkIn, e: Mnemos = E):
    return e.agents.atlas.work(task_id, body.max_steps)


@app.get("/api/handovers", tags=["handover"])
def handovers(e: Mnemos = E):
    return e.agents.list_handovers()


@app.post("/api/handovers", tags=["handover"])
def create_handover(body: HandoverIn, e: Mnemos = E):
    return e.agents.create_handover(body.task_id, body.from_agent, body.to_agent, body.token_budget, body.notes)


@app.get("/api/handovers/{handover_id}", tags=["handover"])
def get_handover(handover_id: str, e: Mnemos = E):
    return e.agents.get_handover(handover_id)


@app.post("/api/handovers/{handover_id}/run", tags=["handover"])
def run_handover(handover_id: str, e: Mnemos = E):
    """Let Bolt accept the handover and execute the unfinished steps."""
    h = e.agents.get_handover(handover_id)
    if h["to_agent"] != "bolt":
        raise HTTPException(400, f"handover is addressed to '{h['to_agent']}'; that agent must run it itself")
    return e.agents.bolt.run_handover(handover_id)


@app.post("/api/demo/handover", tags=["handover"])
def demo_handover(budget: int = Query(1000, ge=200, le=20000), e: Mnemos = E):
    return e.agents.run_demo(budget)


# ------------------------------------------------------------------ evaluation


@app.post("/api/eval/run", tags=["evaluation"])
def eval_run(body: EvalIn, e: Mnemos = E):
    from .evaluation.runner import run_suite

    return run_suite(e, body.suite)


@app.get("/api/eval/runs", tags=["evaluation"])
def eval_runs(e: Mnemos = E):
    rows = e.db.query("SELECT id, kind, summary, created_at FROM eval_runs ORDER BY created_at DESC LIMIT 50")
    for r in rows:
        r["summary"] = json.loads(r["summary"])
    return rows


@app.get("/api/eval/runs/{run_id}", tags=["evaluation"])
def eval_run_get(run_id: str, e: Mnemos = E):
    r = e.db.one("SELECT * FROM eval_runs WHERE id=?", (run_id,))
    if not r:
        raise HTTPException(404, "run not found")
    r["summary"] = json.loads(r["summary"])
    r["details"] = json.loads(r["details"])
    return r


@app.get("/api/eval/latest", tags=["evaluation"])
def eval_latest(kind: str = "all", e: Mnemos = E):
    r = e.db.one("SELECT * FROM eval_runs WHERE kind=? ORDER BY created_at DESC LIMIT 1", (kind,))
    if not r:
        return None
    r["summary"] = json.loads(r["summary"])
    r["details"] = json.loads(r["details"])
    return r
