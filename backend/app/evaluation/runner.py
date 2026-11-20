"""Runs the evaluation suites and persists results in ``eval_runs``."""
from __future__ import annotations

import json
import shutil
import tempfile
import time
import traceback
from pathlib import Path

from ..core.text import new_id, now_iso
from ..core.tokenizer import info as tok_info


def run_scenarios() -> dict:
    from ..config import Settings
    from ..engine import Mnemos
    from .scenarios import SCENARIOS

    rows = []
    for sc in SCENARIOS:
        tmp = tempfile.mkdtemp(prefix=f"mnemos_sc_{sc['id']}_")
        e = Mnemos(Settings(data_dir=Path(tmp)))
        t0 = time.perf_counter()
        try:
            passed, evidence = sc["fn"](e)
            err = None
        except Exception as ex:  # a crash is a failure, recorded honestly
            passed, evidence, err = False, "", f"{type(ex).__name__}: {ex}"
            traceback.print_exc()
        ms = (time.perf_counter() - t0) * 1000
        try:
            e.close()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
        rows.append({"id": sc["id"], "category": sc["category"], "title": sc["title"], "passed": bool(passed),
                     "evidence": str(evidence)[:400], "error": err, "ms": round(ms, 1)})
    cats: dict[str, dict] = {}
    for r in rows:
        c = cats.setdefault(r["category"], {"passed": 0, "total": 0})
        c["total"] += 1
        c["passed"] += r["passed"]
    return {"total": len(rows), "passed": sum(r["passed"] for r in rows), "by_category": cats, "rows": rows}


def run_suite(engine, suite: str = "all") -> dict:
    from .context_compare import compare_synthetic
    from .storage_bench import run_storage_benchmark

    t0 = time.perf_counter()
    details: dict = {"tokenizer": tok_info()}
    if suite in ("scenarios", "all"):
        details["scenarios"] = run_scenarios()
    if suite in ("storage", "all"):
        details["storage"] = run_storage_benchmark()
    if suite in ("context", "all"):
        details["context"] = compare_synthetic()
    summary = {"suite": suite, "duration_s": round(time.perf_counter() - t0, 2)}
    if "scenarios" in details:
        s = details["scenarios"]
        summary["scenarios_passed"] = s["passed"]
        summary["scenarios_total"] = s["total"]
    if "storage" in details:
        best = max(details["storage"]["rows"], key=lambda r: r["mrr"])
        summary["best_mrr_strategy"] = best["strategy"]
    if "context" in details:
        sel = [r for r in details["context"]["rows"] if r["strategy"] == "selected"]
        summary["selected_answer_support_at_500"] = next((r["answer_support"] for r in sel if r["budget"] == 500), None)
    rid = new_id("eval")
    engine.db.execute("INSERT INTO eval_runs (id, kind, summary, details, created_at) VALUES (?,?,?,?,?)",
                      (rid, suite, json.dumps(summary), json.dumps(details, default=str), now_iso()))
    return {"id": rid, "kind": suite, "summary": summary, "details": details, "created_at": now_iso()}
