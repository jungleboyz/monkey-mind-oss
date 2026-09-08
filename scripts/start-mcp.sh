#!/bin/sh
# Railway injects PORT at runtime — use it, fall back to 8001 for local dev
exec python -m mm.mcp.server --transport http --port "${PORT:-8001}"
