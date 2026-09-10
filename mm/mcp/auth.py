"""API key middleware for the Monkey Mind MCP HTTP server.

Checks the X-API-Key header on every incoming request.
The key is validated against the user's bcrypt hash (same mechanism as the REST API).
Requests without a valid key receive a 401 JSON response.

Stdio transport bypasses this entirely — middleware is only installed in HTTP mode.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from starlette.types import ASGIApp, Receive, Scope, Send


class ApiKeyMiddleware:
    """Starlette-compatible ASGI middleware that enforces X-API-Key auth."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._data_root = Path(os.environ.get("DATA_ROOT", "./data"))
        self._user_id = os.environ.get("USER_ID", "default")
        # Lazy-load — don't fail at import if hash file isn't present yet
        self._hash: str | None = None

    def _get_hash(self) -> str | None:
        if self._hash is not None:
            return self._hash
        hash_file = self._data_root / "users" / self._user_id / "api_key.hash"
        if hash_file.exists():
            self._hash = hash_file.read_text().strip()
        return self._hash

    def _verify(self, raw_key: str) -> bool:
        stored = self._get_hash()
        if not stored:
            return False
        if not raw_key.startswith("mm_sk_"):
            return False
        try:
            import bcrypt
            return bcrypt.checkpw(raw_key.encode(), stored.encode())
        except Exception:
            return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Extract X-API-Key from headers
        headers = dict(scope.get("headers", []))
        api_key = headers.get(b"x-api-key", b"").decode("utf-8", errors="replace")

        if not api_key or not self._verify(api_key):
            # Return 401
            body = json.dumps({"detail": "Unauthorized. Pass your key via X-API-Key header."}).encode()
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(body)).encode()],
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
