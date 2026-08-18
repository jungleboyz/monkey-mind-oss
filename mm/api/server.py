"""FastAPI REST server for Monkey Mind."""
from __future__ import annotations

import datetime
import os
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from mm.auth.keys import load_key_hash, verify_key
from mm.core.store import UserStore

app = FastAPI(
    title="Monkey Mind",
    description="Personal context library API",
    version="0.1.0",
)

DATA_ROOT = Path(os.environ.get("DATA_ROOT", "./data"))
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


# ------------------------------------------------------------------ #
# Auth dependency
# ------------------------------------------------------------------ #


async def get_user_store(
    api_key: Optional[str] = Depends(API_KEY_HEADER),
    request: Request = None,  # type: ignore[assignment]
) -> UserStore:
    """Authenticate via X-API-Key header and return the matching UserStore."""
    users_dir = DATA_ROOT / "users"
    matched_store: Optional[UserStore] = None
    endpoint = str(request.url.path) if request else ""
    ip = request.client.host if (request and request.client) else ""
    key_hint = (api_key[:8] + "...") if api_key and len(api_key) >= 8 else (api_key or "")

    if api_key and users_dir.exists():
        for user_dir in users_dir.iterdir():
            if not user_dir.is_dir():
                continue
            stored_hash = load_key_hash(user_dir)
            if stored_hash and verify_key(api_key, stored_hash):
                user_id = user_dir.name
                matched_store = UserStore(DATA_ROOT, user_id)
                break

    result = "ok" if matched_store else "fail"

    # Write auth_log — pick a store to write to
    log_store = matched_store
    if log_store is None and api_key and users_dir.exists():
        # Try to find any valid store to log against (first user)
        for user_dir in users_dir.iterdir():
            if user_dir.is_dir() and (user_dir / "db" / "metadata.sqlite3").exists():
                log_store = UserStore(DATA_ROOT, user_dir.name)
                break

    if log_store is not None:
        try:
            con = sqlite3.connect(log_store.db_path)
            con.execute(
                "INSERT INTO auth_log (key_hint, result, endpoint, ip, ts) VALUES (?,?,?,?,?)",
                (key_hint, result, endpoint, ip, datetime.datetime.utcnow().isoformat()),
            )
            con.commit()
            con.close()
        except Exception:
            pass

    if matched_store is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return matched_store


# ------------------------------------------------------------------ #
# Request / response models
# ------------------------------------------------------------------ #


class QueryRequest(BaseModel):
    query: str
    domains: Optional[list[str]] = None
    limit: int = 10


# ------------------------------------------------------------------ #
# Routes
# ------------------------------------------------------------------ #


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/query")
async def query(body: QueryRequest, store: UserStore = Depends(get_user_store)):
    from mm.api.query import QueryEngine

    engine = QueryEngine()
    chunks = engine.retrieve(store, body.query, domains=body.domains, limit=body.limit)
    user_config = store.get_config()
    result = engine.synthesise(body.query, chunks, user_config)
    return result


@app.get("/domains")
async def list_domains(store: UserStore = Depends(get_user_store)):
    user_config = store.get_config()
    con = sqlite3.connect(store.db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT domain, COUNT(*) as page_count FROM pages GROUP BY domain"
    ).fetchall()
    con.close()

    counts: dict[str, int] = {row["domain"]: row["page_count"] for row in rows}
    domains = []
    for d in user_config.domains:
        domains.append(
            {
                "id": d.id,
                "label": d.label,
                "staleness_threshold_days": d.staleness_threshold_days,
                "page_count": counts.get(d.id, 0),
            }
        )
    return {"domains": domains}


@app.get("/pages")
async def list_pages(
    domain: Optional[str] = None,
    store: UserStore = Depends(get_user_store),
):
    con = sqlite3.connect(store.db_path)
    con.row_factory = sqlite3.Row
    if domain:
        rows = con.execute(
            "SELECT * FROM pages WHERE domain=? ORDER BY updated_at DESC", (domain,)
        ).fetchall()
    else:
        rows = con.execute("SELECT * FROM pages ORDER BY updated_at DESC").fetchall()
    con.close()
    return {"pages": [dict(r) for r in rows]}


@app.get("/pages/{path:path}")
async def get_page(path: str, store: UserStore = Depends(get_user_store)):
    con = sqlite3.connect(store.db_path)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM pages WHERE id=?", (path,)).fetchone()
    con.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Page not found")
    return dict(row)
