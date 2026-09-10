"""Tests for MCP HTTP server API key middleware.

Tests that:
- Requests without X-API-Key → 401
- Requests with wrong key → 401
- Requests with valid key → pass through (200 or MCP-level response)
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import bcrypt
import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from mm.mcp.auth import ApiKeyMiddleware


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user_store(tmp_path: Path, raw_key: str) -> Path:
    """Create a minimal user data dir with a bcrypt api_key.hash."""
    user_dir = tmp_path / "users" / "rob"
    user_dir.mkdir(parents=True)
    hashed = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()
    (user_dir / "api_key.hash").write_text(hashed)
    return tmp_path


def _make_app(data_root: Path) -> ApiKeyMiddleware:
    """Minimal Starlette app behind the middleware."""
    async def ok(request):
        return JSONResponse({"status": "ok"})

    inner = Starlette(routes=[Route("/mcp", ok), Route("/", ok)])
    wrapped = ApiKeyMiddleware(inner)
    # Patch middleware env
    wrapped._data_root = data_root
    wrapped._user_id = "rob"
    wrapped._hash = None  # force reload from disk
    return wrapped


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestApiKeyMiddleware:
    VALID_KEY = "mm_sk_testkey1234567890abcdef"

    @pytest.fixture()
    def client(self, tmp_path):
        data_root = _make_user_store(tmp_path, self.VALID_KEY)
        app = _make_app(data_root)
        return TestClient(app, raise_server_exceptions=True)

    def test_no_key_returns_401(self, client):
        resp = client.get("/mcp")
        assert resp.status_code == 401
        assert "Unauthorized" in resp.json()["detail"]

    def test_wrong_key_returns_401(self, client):
        resp = client.get("/mcp", headers={"X-API-Key": "mm_sk_wrongkeyXXXXXXXXXXXXXXXX"})
        assert resp.status_code == 401

    def test_invalid_prefix_returns_401(self, client):
        resp = client.get("/mcp", headers={"X-API-Key": "notavalidkey"})
        assert resp.status_code == 401

    def test_valid_key_passes_through(self, client):
        resp = client.get("/mcp", headers={"X-API-Key": self.VALID_KEY})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_valid_key_on_root_passes(self, client):
        resp = client.get("/", headers={"X-API-Key": self.VALID_KEY})
        assert resp.status_code == 200

    def test_no_hash_file_returns_401(self, tmp_path):
        """If the hash file doesn't exist yet, all requests should be rejected."""
        # Don't create the hash file
        (tmp_path / "users" / "rob").mkdir(parents=True)
        app = _make_app(tmp_path)
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/mcp", headers={"X-API-Key": self.VALID_KEY})
        assert resp.status_code == 401
