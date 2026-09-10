"""Auth layer for the Monkey Mind MCP HTTP server.

Supports two auth modes (both validate against the same bcrypt hash):

1. X-API-Key header  — used by curl / direct clients
2. OAuth 2.0 Client Credentials — used by Claude Mobile / claude.ai connectors
   POST /token  {client_id, client_secret, grant_type=client_credentials}
   → {access_token, token_type, expires_in}
   Subsequent requests: Authorization: Bearer <access_token>

The access_token IS the mm_sk_ key — stateless, no token DB needed.
Stdio transport bypasses all of this entirely.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import parse_qs

from starlette.types import ASGIApp, Receive, Scope, Send


class OAuthMCPMiddleware:
    """ASGI middleware that handles:
    - POST /token  → OAuth client credentials token endpoint
    - All other paths → Bearer or X-API-Key validation
    """

    TOKEN_PATH = b"/token"

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._data_root = Path(os.environ.get("DATA_ROOT", "./data"))
        self._user_id = os.environ.get("USER_ID", "default")
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
        if not stored or not raw_key.startswith("mm_sk_"):
            return False
        try:
            import bcrypt
            return bcrypt.checkpw(raw_key.encode(), stored.encode())
        except Exception:
            return False

    async def _read_body(self, receive: Receive) -> bytes:
        body = b""
        while True:
            msg = await receive()
            body += msg.get("body", b"")
            if not msg.get("more_body"):
                break
        return body

    async def _send_json(self, send: Send, status: int, data: dict) -> None:
        body = json.dumps(data).encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body)).encode()],
                [b"cache-control", b"no-store"],
            ],
        })
        await send({"type": "http.response.body", "body": body})

    async def _handle_token(self, scope: Scope, receive: Receive, send: Send) -> None:
        """OAuth 2.0 client credentials token endpoint."""
        body = await self._read_body(receive)
        # Support both form-encoded and JSON bodies
        try:
            params = {k: v[0] for k, v in parse_qs(body.decode()).items()}
        except Exception:
            params = {}
        if not params:
            try:
                params = json.loads(body)
            except Exception:
                params = {}

        grant_type = params.get("grant_type", "")
        client_secret = params.get("client_secret", "")

        if grant_type != "client_credentials":
            await self._send_json(send, 400, {"error": "unsupported_grant_type"})
            return

        if not client_secret or not self._verify(client_secret):
            await self._send_json(send, 401, {"error": "invalid_client"})
            return

        # The access token IS the mm_sk_ key — stateless, no DB needed
        await self._send_json(send, 200, {
            "access_token": client_secret,
            "token_type": "bearer",
            "expires_in": 86400,
        })

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "").encode() or scope.get("raw_path", b"")
        if isinstance(path, str):
            path = path.encode()

        # Route /token to OAuth handler
        if scope["type"] == "http" and path == self.TOKEN_PATH:
            await self._handle_token(scope, receive, send)
            return

        # All other paths — validate Bearer or X-API-Key
        headers = {k.lower(): v for k, v in scope.get("headers", [])}

        # Try Bearer token first
        auth_header = headers.get(b"authorization", b"").decode("utf-8", errors="replace")
        token = ""
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()

        # Fall back to X-API-Key
        if not token:
            token = headers.get(b"x-api-key", b"").decode("utf-8", errors="replace")

        if not token or not self._verify(token):
            base_url = os.environ.get("MCP_BASE_URL", "")
            www_auth = f'Bearer realm="Monkey Mind", resource_metadata="{base_url}/.well-known/oauth-authorization-server"'
            body = json.dumps({
                "detail": "Unauthorized. Use OAuth client credentials (/token) or X-API-Key header."
            }).encode()
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(body)).encode()],
                    [b"www-authenticate", www_auth.encode()],
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)


# Backwards-compatible alias
ApiKeyMiddleware = OAuthMCPMiddleware
