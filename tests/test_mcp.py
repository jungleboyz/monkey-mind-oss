"""Tests for CL-T7: MCP server tools."""
from __future__ import annotations

import datetime
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _make_store(tmp_path: Path, user_id: str = "testuser"):
    from mm.core.store import UserStore
    store = UserStore(tmp_path, user_id)
    store.init()
    return store


def _insert_page(store, page_id: str, domain: str, title: str, updated_at: str, threshold: int = 30):
    con = sqlite3.connect(store.db_path)
    con.execute(
        "INSERT OR REPLACE INTO pages (id, domain, type, title, source, updated_at, staleness_threshold_days) "
        "VALUES (?, ?, 'note', ?, 'manual', ?, ?)",
        (page_id, domain, title, updated_at, threshold),
    )
    con.commit()
    con.close()


# ------------------------------------------------------------------ #
# query_context
# ------------------------------------------------------------------ #

class TestQueryContext:
    def test_returns_mcp_format(self, tmp_path):
        store = _make_store(tmp_path)
        mock_result = {
            "answer": "You should focus on your health.",
            "sources": [{"path": "domains/health/summary.md", "domain": "health", "updated": "2026-08-01"}],
            "staleness_warnings": [],
        }

        with patch("mm.mcp.server._get_store", return_value=store), \
             patch("mm.api.query.QueryEngine.retrieve", return_value=[{"text": "ctx", "metadata": {}, "distance": 0.1}]), \
             patch("mm.api.query.QueryEngine.synthesise", return_value=mock_result):
            from mm.mcp.server import query_context
            result = query_context("what should I focus on")

        assert "content" in result
        assert result["content"][0]["type"] == "text"
        assert "health" in result["content"][0]["text"]
        assert len(result["sources"]) == 1
        assert result["staleness_warnings"] == []

    def test_empty_library_returns_not_in_repo(self, tmp_path):
        store = _make_store(tmp_path)
        empty_result = {
            "answer": "This information is not in your context library.",
            "sources": [],
            "staleness_warnings": [],
        }

        with patch("mm.mcp.server._get_store", return_value=store), \
             patch("mm.api.query.QueryEngine.retrieve", return_value=[]), \
             patch("mm.api.query.QueryEngine.synthesise", return_value=empty_result):
            from mm.mcp.server import query_context
            result = query_context("capital of mars")

        assert "not in your context library" in result["content"][0]["text"]
        assert result["sources"] == []


# ------------------------------------------------------------------ #
# list_domains
# ------------------------------------------------------------------ #

class TestListDomains:
    def test_returns_all_domains(self, tmp_path):
        store = _make_store(tmp_path)
        _insert_page(store, "domains/health/p1.md", "health", "Health Page", "2026-08-01")
        _insert_page(store, "domains/professional/p1.md", "professional", "Work Page", "2026-08-01")

        with patch("mm.mcp.server._get_store", return_value=store):
            from mm.mcp.server import list_domains
            result = list_domains()

        data = json.loads(result["content"][0]["text"])
        ids = [d["id"] for d in data["domains"]]
        assert "health" in ids
        assert "professional" in ids

    def test_page_counts_correct(self, tmp_path):
        store = _make_store(tmp_path)
        _insert_page(store, "domains/health/p1.md", "health", "Page 1", "2026-08-01")
        _insert_page(store, "domains/health/p2.md", "health", "Page 2", "2026-08-01")

        with patch("mm.mcp.server._get_store", return_value=store):
            from mm.mcp.server import list_domains
            result = list_domains()

        data = json.loads(result["content"][0]["text"])
        health = next(d for d in data["domains"] if d["id"] == "health")
        assert health["page_count"] == 2


# ------------------------------------------------------------------ #
# get_page
# ------------------------------------------------------------------ #

class TestGetPage:
    def test_existing_page_returned(self, tmp_path):
        store = _make_store(tmp_path)
        _insert_page(store, "domains/health/summary.md", "health", "Health Summary", "2026-08-01")

        with patch("mm.mcp.server._get_store", return_value=store):
            from mm.mcp.server import get_page
            result = get_page("domains/health/summary.md")

        data = json.loads(result["content"][0]["text"])
        assert data["metadata"]["id"] == "domains/health/summary.md"
        assert data["metadata"]["domain"] == "health"

    def test_missing_page_returns_not_found(self, tmp_path):
        store = _make_store(tmp_path)

        with patch("mm.mcp.server._get_store", return_value=store):
            from mm.mcp.server import get_page
            result = get_page("domains/nonexistent/page.md")

        assert "not found" in result["content"][0]["text"].lower()


# ------------------------------------------------------------------ #
# search_pages
# ------------------------------------------------------------------ #

class TestSearchPages:
    def test_finds_by_title(self, tmp_path):
        store = _make_store(tmp_path)
        _insert_page(store, "domains/health/exercise.md", "health", "Exercise Log", "2026-08-01")
        _insert_page(store, "domains/professional/cv.md", "professional", "CV Summary", "2026-08-01")

        with patch("mm.mcp.server._get_store", return_value=store):
            from mm.mcp.server import search_pages
            result = search_pages("Exercise")

        data = json.loads(result["content"][0]["text"])
        assert data["count"] == 1
        assert data["pages"][0]["id"] == "domains/health/exercise.md"

    def test_domain_filter(self, tmp_path):
        store = _make_store(tmp_path)
        _insert_page(store, "domains/health/log.md", "health", "Log", "2026-08-01")
        _insert_page(store, "domains/professional/log.md", "professional", "Log", "2026-08-01")

        with patch("mm.mcp.server._get_store", return_value=store):
            from mm.mcp.server import search_pages
            result = search_pages("Log", domain="health")

        data = json.loads(result["content"][0]["text"])
        assert data["count"] == 1
        assert data["pages"][0]["domain"] == "health"

    def test_no_results(self, tmp_path):
        store = _make_store(tmp_path)

        with patch("mm.mcp.server._get_store", return_value=store):
            from mm.mcp.server import search_pages
            result = search_pages("zzznomatch")

        data = json.loads(result["content"][0]["text"])
        assert data["count"] == 0


# ------------------------------------------------------------------ #
# get_staleness_report
# ------------------------------------------------------------------ #

class TestGetStalenessReport:
    def test_stale_pages_flagged(self, tmp_path):
        store = _make_store(tmp_path)
        old_date = (datetime.datetime.utcnow() - datetime.timedelta(days=60)).isoformat()
        _insert_page(store, "domains/health/old.md", "health", "Old Page", old_date, threshold=30)

        with patch("mm.mcp.server._get_store", return_value=store):
            from mm.mcp.server import get_staleness_report
            result = get_staleness_report()

        data = json.loads(result["content"][0]["text"])
        assert data["count"] == 1
        assert data["stale_pages"][0]["id"] == "domains/health/old.md"
        assert len(result["staleness_warnings"]) == 1

    def test_fresh_pages_not_flagged(self, tmp_path):
        store = _make_store(tmp_path)
        fresh_date = (datetime.datetime.utcnow() - datetime.timedelta(days=5)).isoformat()
        _insert_page(store, "domains/health/fresh.md", "health", "Fresh Page", fresh_date, threshold=30)

        with patch("mm.mcp.server._get_store", return_value=store):
            from mm.mcp.server import get_staleness_report
            result = get_staleness_report()

        data = json.loads(result["content"][0]["text"])
        assert data["count"] == 0

    def test_domain_filter(self, tmp_path):
        store = _make_store(tmp_path)
        old_date = (datetime.datetime.utcnow() - datetime.timedelta(days=60)).isoformat()
        _insert_page(store, "domains/health/old.md", "health", "Old Health", old_date, threshold=30)
        _insert_page(store, "domains/professional/old.md", "professional", "Old Work", old_date, threshold=30)

        with patch("mm.mcp.server._get_store", return_value=store):
            from mm.mcp.server import get_staleness_report
            result = get_staleness_report(domain="health")

        data = json.loads(result["content"][0]["text"])
        assert data["count"] == 1
        assert data["stale_pages"][0]["domain"] == "health"
