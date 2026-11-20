"""The evaluation lab itself: scenarios, storage benchmark, context comparison."""
from app.evaluation.context_compare import build_dataset, compare_synthetic
from app.evaluation.runner import run_scenarios
from app.evaluation.scenarios import SCENARIOS
from app.evaluation.storage_bench import build_corpus, run_storage_benchmark


def test_at_least_30_scenarios_across_categories():
    assert len(SCENARIOS) >= 30
    assert len({s["category"] for s in SCENARIOS}) >= 10
    assert len({s["id"] for s in SCENARIOS}) == len(SCENARIOS)


def test_scenarios_run():
    r = run_scenarios()
    failed = [(x["id"], x["evidence"], x["error"]) for x in r["rows"] if not x["passed"]]
    assert not failed, failed


def test_datasets_are_deterministic():
    assert build_dataset(7) == build_dataset(7)
    assert build_corpus(11) == build_corpus(11)


def test_storage_benchmark_measures_all_strategies():
    r = run_storage_benchmark()
    names = {x["strategy"] for x in r["rows"]}
    assert names == {"structured", "keyword", "vector", "graph", "file", "hybrid"}
    for x in r["rows"]:
        assert 0 <= x["r_precision"] <= 1 and x["storage_bytes"] > 0 and x["delete_logical"]
    assert r["secure_delete_demo"]["secure_delete_on"]["token_found_in_file_after_delete"] is False


def test_context_comparison_respects_budgets():
    r = compare_synthetic(budgets=(500, 1000))
    assert r["dataset"]["full_history_tokens"] > 5000
    for row in r["rows"]:
        assert row["within_budget"], row
    sel = {x["budget"]: x for x in r["rows"] if x["strategy"] == "selected"}
    full = {x["budget"]: x for x in r["rows"] if x["strategy"] == "full_history"}
    assert sel[500]["answer_support"] >= full[500]["answer_support"]
