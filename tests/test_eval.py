"""Tests for mm/eval/runner.py — parameterized eval suite."""
from __future__ import annotations

import json

import pytest
import responses as rsps_lib

from mm.eval.runner import (
    ABSENT_TOPIC_QUERY,
    EvalResult,
    EvalRunner,
    ScenarioResult,
    print_results,
    run_all,
)

BASE = "http://testserver:8000"

# ------------------------------------------------------------------ #
# Fixtures / helpers
# ------------------------------------------------------------------ #


def make_runner() -> EvalRunner:
    return EvalRunner(api_url=BASE, api_key="mm_sk_test")


def query_ok(answer: str = "Some answer.", sources: list | None = None, warnings: list | None = None) -> dict:
    return {
        "answer": answer,
        "sources": sources if sources is not None else [
            {"path": "docs/page.md", "domain": "work", "updated": "2026-01-01T00:00:00"}
        ],
        "staleness_warnings": warnings or [],
    }


def domains_ok(domains: list | None = None) -> dict:
    if domains is None:
        domains = [{"id": "work", "label": "Work", "page_count": 3, "staleness_threshold_days": 30}]
    return {"domains": domains}


def pages_ok(pages: list | None = None) -> dict:
    import datetime
    if pages is None:
        recent = (datetime.datetime.utcnow() - datetime.timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
        pages = [
            {"id": "docs/page.md", "title": "My Page", "domain": "work", "updated_at": recent}
        ]
    return {"pages": pages}


# ------------------------------------------------------------------ #
# Unit tests — ScenarioResult & EvalResult
# ------------------------------------------------------------------ #


def test_scenario_result_to_dict():
    r = ScenarioResult("S1", "Within-domain retrieval", True, "All good")
    d = r.to_dict()
    assert d == {"id": "S1", "name": "Within-domain retrieval", "passed": True, "reason": "All good"}


def test_eval_result_score():
    results = [ScenarioResult(f"S{i}", f"Scenario {i}", i < 7, "") for i in range(1, 10)]
    er = EvalResult(passed=6, failed=3, total=9, score="6/9", results=results)
    d = er.to_dict()
    assert d["score"] == "6/9"
    assert d["passed"] == 6
    assert len(d["results"]) == 9


# ------------------------------------------------------------------ #
# S1 — Within-domain retrieval
# ------------------------------------------------------------------ #


@rsps_lib.activate
def test_s1_pass():
    rsps_lib.add(rsps_lib.GET, f"{BASE}/domains", json=domains_ok())
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json=query_ok())
    runner = make_runner()
    result = runner.s1_within_domain_retrieval()
    assert result.passed, result.reason


@rsps_lib.activate
def test_s1_fail_no_domains():
    rsps_lib.add(rsps_lib.GET, f"{BASE}/domains", json={"domains": []})
    runner = make_runner()
    result = runner.s1_within_domain_retrieval()
    assert not result.passed
    assert "No domains" in result.reason


@rsps_lib.activate
def test_s1_fail_no_sources():
    rsps_lib.add(rsps_lib.GET, f"{BASE}/domains", json=domains_ok())
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query",
                 json={"answer": "This information is not in your context library.", "sources": [], "staleness_warnings": []})
    runner = make_runner()
    result = runner.s1_within_domain_retrieval()
    assert not result.passed


# ------------------------------------------------------------------ #
# S2 — Cross-domain synthesis
# ------------------------------------------------------------------ #


@rsps_lib.activate
def test_s2_pass():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json=query_ok(sources=[
        {"path": "a.md", "domain": "work", "updated": "2026-01-01"},
        {"path": "b.md", "domain": "personal", "updated": "2026-01-01"},
    ]))
    result = make_runner().s2_cross_domain_synthesis()
    assert result.passed, result.reason
    assert "2 domains" in result.reason


@rsps_lib.activate
def test_s2_fail_single_domain():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json=query_ok(sources=[
        {"path": "a.md", "domain": "work", "updated": "2026-01-01"},
    ]))
    result = make_runner().s2_cross_domain_synthesis()
    assert not result.passed


@rsps_lib.activate
def test_s2_fail_no_sources():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json=query_ok(sources=[]))
    result = make_runner().s2_cross_domain_synthesis()
    assert not result.passed


# ------------------------------------------------------------------ #
# S3 — Temporal awareness
# ------------------------------------------------------------------ #


@rsps_lib.activate
def test_s3_pass():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json=query_ok())
    result = make_runner().s3_temporal_awareness()
    assert result.passed


@rsps_lib.activate
def test_s3_fail_empty_answer():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json={"answer": "", "sources": [], "staleness_warnings": []})
    result = make_runner().s3_temporal_awareness()
    assert not result.passed


# ------------------------------------------------------------------ #
# S4 — Staleness detection
# ------------------------------------------------------------------ #


@rsps_lib.activate
def test_s4_pass_fresh_page():
    rsps_lib.add(rsps_lib.GET, f"{BASE}/pages", json=pages_ok())
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json=query_ok())
    result = make_runner().s4_staleness_detection()
    assert result.passed  # fresh page → correct to NOT warn


@rsps_lib.activate
def test_s4_pass_old_page_with_warning():
    rsps_lib.add(rsps_lib.GET, f"{BASE}/pages", json=pages_ok(pages=[
        {"id": "old.md", "title": "Old Page", "domain": "work", "updated_at": "2020-01-01T00:00:00"}
    ]))
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json=query_ok(warnings=["old.md is 2362 days old (threshold: 30)"]))
    result = make_runner().s4_staleness_detection()
    assert result.passed, result.reason


@rsps_lib.activate
def test_s4_fail_old_page_no_warning():
    rsps_lib.add(rsps_lib.GET, f"{BASE}/pages", json=pages_ok(pages=[
        {"id": "old.md", "title": "Old Page", "domain": "work", "updated_at": "2020-01-01T00:00:00"}
    ]))
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json=query_ok(warnings=[]))
    result = make_runner().s4_staleness_detection()
    assert not result.passed


@rsps_lib.activate
def test_s4_fail_no_pages():
    rsps_lib.add(rsps_lib.GET, f"{BASE}/pages", json={"pages": []})
    result = make_runner().s4_staleness_detection()
    assert not result.passed


# ------------------------------------------------------------------ #
# S5 — Knowledge boundary
# ------------------------------------------------------------------ #


@rsps_lib.activate
def test_s5_pass_says_not_in_library():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query",
                 json={"answer": "This information is not in your context library.", "sources": [], "staleness_warnings": []})
    result = make_runner().s5_knowledge_boundary()
    assert result.passed, result.reason


@rsps_lib.activate
def test_s5_fail_returns_sources():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json=query_ok(
        answer="Mars capital is Olympus.", sources=[{"path": "mars.md", "domain": "space", "updated": "2026-01-01"}]
    ))
    result = make_runner().s5_knowledge_boundary()
    assert not result.passed
    assert "fabrication" in result.reason.lower()


@rsps_lib.activate
def test_s5_fail_no_disclaimer():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query",
                 json={"answer": "The capital of Mars is Olympus Mons.", "sources": [], "staleness_warnings": []})
    result = make_runner().s5_knowledge_boundary()
    assert not result.passed


# ------------------------------------------------------------------ #
# S6 — Auth boundary
# ------------------------------------------------------------------ #


@rsps_lib.activate
def test_s6_pass_401():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", status=401,
                 json={"detail": "Unauthorized"})
    result = make_runner().s6_auth_boundary()
    assert result.passed, result.reason
    assert "401" in result.reason


@rsps_lib.activate
def test_s6_fail_200():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", status=200, json=query_ok())
    result = make_runner().s6_auth_boundary()
    assert not result.passed
    assert "Expected 401" in result.reason


@rsps_lib.activate
def test_s6_fail_403():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", status=403, json={"detail": "Forbidden"})
    result = make_runner().s6_auth_boundary()
    assert not result.passed


# ------------------------------------------------------------------ #
# S7 — Source provenance
# ------------------------------------------------------------------ #


@rsps_lib.activate
def test_s7_pass_all_fields():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json=query_ok(sources=[
        {"path": "docs/a.md", "domain": "work", "updated": "2026-01-01"}
    ]))
    result = make_runner().s7_source_provenance()
    assert result.passed, result.reason


@rsps_lib.activate
def test_s7_pass_no_sources_empty_library():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json={"answer": "Nothing.", "sources": [], "staleness_warnings": []})
    result = make_runner().s7_source_provenance()
    assert result.passed  # empty library → inconclusive → pass


@rsps_lib.activate
def test_s7_fail_missing_field():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json=query_ok(sources=[
        {"path": "docs/a.md", "domain": "", "updated": "2026-01-01"}  # missing domain
    ]))
    result = make_runner().s7_source_provenance()
    assert not result.passed
    assert "domain" in result.reason


# ------------------------------------------------------------------ #
# S8 — Cross-domain insight
# ------------------------------------------------------------------ #


@rsps_lib.activate
def test_s8_pass_multiple_sources():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json=query_ok(sources=[
        {"path": "a.md", "domain": "work", "updated": "2026-01-01"},
        {"path": "b.md", "domain": "personal", "updated": "2026-01-01"},
    ]))
    result = make_runner().s8_cross_domain_insight()
    assert result.passed, result.reason


@rsps_lib.activate
def test_s8_fail_single_source():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json=query_ok(sources=[
        {"path": "a.md", "domain": "work", "updated": "2026-01-01"}
    ]))
    result = make_runner().s8_cross_domain_insight()
    assert not result.passed


@rsps_lib.activate
def test_s8_fail_no_sources():
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json={"answer": "Nothing.", "sources": [], "staleness_warnings": []})
    result = make_runner().s8_cross_domain_insight()
    assert not result.passed


# ------------------------------------------------------------------ #
# S9 — Connector ingestion
# ------------------------------------------------------------------ #


@rsps_lib.activate
def test_s9_pass_has_pages():
    rsps_lib.add(rsps_lib.GET, f"{BASE}/pages", json=pages_ok())
    result = make_runner().s9_connector_ingestion()
    assert result.passed, result.reason
    assert "1 page" in result.reason


@rsps_lib.activate
def test_s9_fail_no_pages():
    rsps_lib.add(rsps_lib.GET, f"{BASE}/pages", json={"pages": []})
    result = make_runner().s9_connector_ingestion()
    assert not result.passed


# ------------------------------------------------------------------ #
# run_all() integration
# ------------------------------------------------------------------ #


@rsps_lib.activate
def test_run_all_returns_eval_result():
    # S1
    rsps_lib.add(rsps_lib.GET, f"{BASE}/domains", json=domains_ok())
    # S2, S3, S7, S8 (query calls)
    for _ in range(6):
        rsps_lib.add(rsps_lib.POST, f"{BASE}/query", json=query_ok(sources=[
            {"path": "a.md", "domain": "work", "updated": "2026-01-01"},
            {"path": "b.md", "domain": "personal", "updated": "2026-01-01"},
        ]))
    # S4 pages
    rsps_lib.add(rsps_lib.GET, f"{BASE}/pages", json=pages_ok())
    # S5 query (not-in-library answer)
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query",
                 json={"answer": "This information is not in your context library.", "sources": [], "staleness_warnings": []})
    # S6 auth boundary
    rsps_lib.add(rsps_lib.POST, f"{BASE}/query", status=401, json={"detail": "Unauthorized"})
    # S9 pages
    rsps_lib.add(rsps_lib.GET, f"{BASE}/pages", json=pages_ok())

    result = run_all(api_url=BASE, api_key="mm_sk_test")
    assert isinstance(result, EvalResult)
    assert result.total == 9
    assert result.passed + result.failed == 9
    assert "/" in result.score


# ------------------------------------------------------------------ #
# Output format
# ------------------------------------------------------------------ #


def test_json_output(capsys):
    results = [ScenarioResult(f"S{i}", f"Scenario {i}", True, "ok") for i in range(1, 10)]
    er = EvalResult(passed=9, failed=0, total=9, score="9/9", results=results)
    print_results(er, output="json")
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["score"] == "9/9"
    assert data["passed"] == 9
    assert len(data["results"]) == 9


def test_text_output(capsys):
    results = [ScenarioResult(f"S{i}", f"Scenario {i}", True, "ok") for i in range(1, 10)]
    er = EvalResult(passed=9, failed=0, total=9, score="9/9", results=results)
    print_results(er, output="text")
    captured = capsys.readouterr()
    assert "9/9" in captured.out
    assert "PASS" in captured.out


def test_warning_banner_below_threshold(capsys):
    results = [ScenarioResult(f"S{i}", f"Scenario {i}", i <= 6, "reason") for i in range(1, 10)]
    er = EvalResult(passed=6, failed=3, total=9, score="6/9", results=results)
    print_results(er, output="text")
    captured = capsys.readouterr()
    assert "WARNING" in captured.out


def test_no_warning_banner_at_threshold(capsys):
    results = [ScenarioResult(f"S{i}", f"Scenario {i}", True, "ok") for i in range(1, 10)]
    er = EvalResult(passed=7, failed=2, total=9, score="7/9", results=results)
    print_results(er, output="text")
    captured = capsys.readouterr()
    assert "WARNING" not in captured.out
