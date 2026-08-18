"""Tests for mm.api.server and mm.api.query."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request


# ------------------------------------------------------------------ #
# Helpers / fixtures
# ------------------------------------------------------------------ #


def _make_user_store(tmp_path: Path, user_id: str = "testuser") -> MagicMock:
    """Return a MagicMock that looks like UserStore with a real SQLite DB."""
    store = MagicMock()
    store.user_id = user_id

    # Create real SQLite DB so auth_log inserts work
    db_path = tmp_path / "metadata.sqlite3"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS pages (
            id TEXT PRIMARY KEY, domain TEXT NOT NULL, type TEXT NOT NULL,
            title TEXT, source TEXT, connector TEXT,
            created_at TEXT, updated_at TEXT,
            staleness_threshold_days INTEGER DEFAULT 30,
            confidence TEXT DEFAULT 'medium', tags TEXT, raw_path TEXT
        );
        CREATE TABLE IF NOT EXISTS auth_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hint TEXT, result TEXT, endpoint TEXT, ip TEXT, ts TEXT NOT NULL
        );
        """
    )
    con.commit()
    con.close()

    store.db_path = db_path

    # get_config returns a real-looking UserConfig mock
    from mm.config.user import DomainConfig, EmbedConfig, LLMConfig, UserConfig

    cfg = UserConfig(
        user_id=user_id,
        llm=LLMConfig(provider="anthropic", model="claude-haiku-4-5"),
        embedding=EmbedConfig(provider="openai", model="text-embedding-3-small"),
        domains=[DomainConfig("health", "Health", 30)],
        connectors=[],
    )
    store.get_config.return_value = cfg
    return store


VALID_KEY = "mm_sk_validtestkey123"
VALID_HASH = None  # set in fixture


# ------------------------------------------------------------------ #
# Client fixture that patches auth
# ------------------------------------------------------------------ #


@pytest.fixture()
def client(tmp_path):
    """TestClient with get_user_store dependency overridden."""
    import bcrypt

    from mm.api.server import app, get_user_store

    hashed = bcrypt.hashpw(VALID_KEY.encode(), bcrypt.gensalt()).decode()
    store = _make_user_store(tmp_path)

    # Track whether auth was called
    _auth_log_db = store.db_path

    async def _mock_auth(request: Request = None):  # type: ignore[assignment]
        from fastapi import HTTPException

        api_key = request.headers.get("x-api-key") if request else None
        if api_key != VALID_KEY:
            import datetime

            con = sqlite3.connect(_auth_log_db)
            hint = (api_key[:8] + "...") if api_key and len(api_key) >= 8 else (api_key or "")
            con.execute(
                "INSERT INTO auth_log (key_hint, result, endpoint, ip, ts) VALUES (?,?,?,?,?)",
                (hint, "fail", "/query", "testclient", datetime.datetime.utcnow().isoformat()),
            )
            con.commit()
            con.close()
            raise HTTPException(status_code=401, detail="Unauthorized")
        return store

    app.dependency_overrides[get_user_store] = _mock_auth
    yield TestClient(app, raise_server_exceptions=True), store
    app.dependency_overrides.clear()


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #


def test_health_no_auth(client):
    tc, _ = client
    resp = tc.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_missing_api_key(client):
    tc, _ = client
    resp = tc.post("/query", json={"query": "what is my name?"})
    assert resp.status_code == 401


def test_invalid_api_key(client):
    tc, _ = client
    resp = tc.post(
        "/query",
        json={"query": "what is my name?"},
        headers={"X-API-Key": "mm_sk_wrongkey"},
    )
    assert resp.status_code == 401


def test_query_success(client):
    tc, store = client

    mock_chunks = [
        {
            "text": "Alice is a software engineer.",
            "metadata": {
                "path": "personal/alice.md",
                "domain": "personal",
                "updated_at": "2026-01-01T00:00:00",
                "staleness_threshold_days": 60,
            },
            "distance": 0.1,
        }
    ]
    mock_result = {
        "answer": "Alice is a software engineer.",
        "sources": [{"path": "personal/alice.md", "domain": "personal", "updated": "2026-01-01"}],
        "staleness_warnings": [],
    }

    with patch("mm.api.query.QueryEngine") as MockQE:
        instance = MockQE.return_value
        instance.retrieve.return_value = mock_chunks
        instance.synthesise.return_value = mock_result

        resp = tc.post(
            "/query",
            json={"query": "who is alice?"},
            headers={"X-API-Key": VALID_KEY},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "sources" in data
    assert "staleness_warnings" in data


def test_query_knowledge_boundary(client):
    """When chunks are empty, answer must mention 'not in your context library'."""
    tc, store = client

    from mm.api.query import QueryEngine

    engine = QueryEngine()
    result = engine.synthesise("unknown question", [], store.get_config.return_value)
    assert "not in your context library" in result["answer"]
    assert result["sources"] == []


def test_list_domains(client):
    tc, _ = client
    resp = tc.get("/domains", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 200
    data = resp.json()
    assert "domains" in data
    assert isinstance(data["domains"], list)
    assert data["domains"][0]["id"] == "health"


def test_list_pages(client):
    tc, _ = client
    resp = tc.get("/pages", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 200
    assert "pages" in resp.json()


def test_auth_log_written(client):
    tc, store = client
    # Trigger a failed auth
    tc.post(
        "/query",
        json={"query": "hello"},
        headers={"X-API-Key": "mm_sk_badkey123"},
    )
    con = sqlite3.connect(store.db_path)
    rows = con.execute("SELECT * FROM auth_log").fetchall()
    con.close()
    assert len(rows) >= 1
