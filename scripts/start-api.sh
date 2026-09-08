#!/bin/sh
# Railway injects PORT at runtime — use it, fall back to 8000 for local dev
exec uvicorn mm.api.server:app --host 0.0.0.0 --port "${PORT:-8000}"
