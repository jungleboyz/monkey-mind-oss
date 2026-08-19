"""MCP server for Monkey Mind OSS.

Exposes 5 tools:
  - query_context
  - list_domains
  - get_page
  - search_pages
  - get_staleness_report

Supports:
  stdio transport (default, for Claude Desktop)
  HTTP transport (--transport http --port N, for Cursor)

Environment:
  USER_ID   — user to scope all queries to
  DATA_ROOT — root data directory (default: ./data)
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

from mcp.server.mcpserver import MCPServer

# ------------------------------------------------------------------ #
# Server init
# ------------------------------------------------------------------ #

mcp = MCPServer("monkey-mind")

# ------------------------------------------------------------------ #
# Store factory  (reads env on first call, cached per process)
# ------------------------------------------------------------------ #

_store: Any = None


def _get_store():
    global _store
    if _store is None:
        from mm.core.store import UserStore

        user_id = os.environ.get("USER_ID", "default")
        data_root = Path(os.environ.get("DATA_ROOT", "./data"))
        _store = UserStore(data_root, user_id)
        _store.init()
    return _store


def _text(content: str, sources: list = None, staleness_warnings: list = None) -> dict:
    """Build a MCP-compliant tool response."""
    return {
        "content": [{"type": "text", "text": content}],
        "sources": sources or [],
        "staleness_warnings": staleness_warnings or [],
    }


# ------------------------------------------------------------------ #
# Tools
# ------------------------------------------------------------------ #


@mcp.tool()
def query_context(
    query: str,
    domains: Optional[list[str]] = None,
    limit: int = 10,
) -> dict:
    """Semantic search over the user's context library with LLM synthesis.

    Args:
        query: The question or search query.
        domains: Optional list of domain IDs to restrict the search.
        limit: Maximum number of source chunks to retrieve (default 10).

    Returns:
        MCP tool result with synthesised answer, sources, and staleness warnings.
    """
    from mm.api.query import QueryEngine

    store = _get_store()
    engine = QueryEngine()
    chunks = engine.retrieve(store, query, domains=domains, limit=limit)
    user_config = store.get_config()
    result = engine.synthesise(query, chunks, user_config)
    return _text(
        result["answer"],
        sources=result.get("sources", []),
        staleness_warnings=result.get("staleness_warnings", []),
    )


@mcp.tool()
def list_domains() -> dict:
    """List all domains in the user's context library with page counts and staleness info.

    Returns:
        MCP tool result with domains list.
    """
    store = _get_store()
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

    return _text(json.dumps({"domains": domains}, indent=2))


@mcp.tool()
def get_page(path: str) -> dict:
    """Retrieve a specific context page by its path/ID.

    Args:
        path: The page path or ID (as stored in metadata).

    Returns:
        MCP tool result with page metadata and content.
    """
    store = _get_store()
    con = sqlite3.connect(store.db_path)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM pages WHERE id=?", (path,)).fetchone()
    con.close()

    if row is None:
        return _text(f"Page not found: {path}")

    page = dict(row)
    # Try to read raw file content if available
    raw_path = page.get("raw_path")
    content_text = ""
    if raw_path:
        raw = Path(raw_path)
        if not raw.is_absolute():
            raw = store.context_dir / raw_path
        if raw.exists():
            try:
                content_text = raw.read_text(encoding="utf-8", errors="replace")
            except Exception:
                content_text = ""

    result = {
        "metadata": page,
        "content": content_text,
    }
    return _text(json.dumps(result, indent=2, default=str))


@mcp.tool()
def search_pages(term: str, domain: Optional[str] = None) -> dict:
    """Keyword/metadata search over stored context pages.

    Args:
        term: Search term (matched against title, source, tags, and ID).
        domain: Optional domain ID to restrict the search.

    Returns:
        MCP tool result with matching pages list.
    """
    store = _get_store()
    con = sqlite3.connect(store.db_path)
    con.row_factory = sqlite3.Row
    like = f"%{term}%"

    if domain:
        rows = con.execute(
            """SELECT * FROM pages
               WHERE domain=?
                 AND (title LIKE ? OR source LIKE ? OR tags LIKE ? OR id LIKE ?)
               ORDER BY updated_at DESC""",
            (domain, like, like, like, like),
        ).fetchall()
    else:
        rows = con.execute(
            """SELECT * FROM pages
               WHERE title LIKE ? OR source LIKE ? OR tags LIKE ? OR id LIKE ?
               ORDER BY updated_at DESC""",
            (like, like, like, like),
        ).fetchall()
    con.close()

    pages = [dict(r) for r in rows]
    return _text(json.dumps({"pages": pages, "count": len(pages)}, indent=2, default=str))


@mcp.tool()
def get_staleness_report(domain: Optional[str] = None) -> dict:
    """Get a report of pages exceeding their staleness threshold.

    Args:
        domain: Optional domain ID to restrict the report.

    Returns:
        MCP tool result with stale pages and their ages.
    """
    store = _get_store()
    con = sqlite3.connect(store.db_path)
    con.row_factory = sqlite3.Row

    if domain:
        rows = con.execute(
            "SELECT * FROM pages WHERE domain=? ORDER BY updated_at ASC", (domain,)
        ).fetchall()
    else:
        rows = con.execute("SELECT * FROM pages ORDER BY updated_at ASC").fetchall()
    con.close()

    now = datetime.datetime.utcnow()
    stale: list[dict] = []

    for row in rows:
        page = dict(row)
        updated_str = page.get("updated_at", "")
        threshold = int(page.get("staleness_threshold_days") or 30)
        if updated_str:
            try:
                updated = datetime.datetime.fromisoformat(
                    updated_str.replace("Z", "+00:00")
                ).replace(tzinfo=None)
                age_days = (now - updated).days
                if age_days > threshold:
                    stale.append(
                        {
                            "id": page["id"],
                            "domain": page["domain"],
                            "title": page.get("title"),
                            "updated_at": updated_str,
                            "age_days": age_days,
                            "threshold_days": threshold,
                        }
                    )
            except ValueError:
                pass

    report = {"stale_pages": stale, "count": len(stale)}
    warnings = [
        f"{p['id']} is {p['age_days']} days old (threshold: {p['threshold_days']})"
        for p in stale
    ]
    return _text(
        json.dumps(report, indent=2, default=str),
        staleness_warnings=warnings,
    )


# ------------------------------------------------------------------ #
# Entry point
# ------------------------------------------------------------------ #


def main() -> None:
    parser = argparse.ArgumentParser(description="Monkey Mind MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport to use (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port for HTTP transport (default: 8001)",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        asyncio.run(mcp.run_stdio_async())
    else:
        # HTTP / streamable-http (Cursor)
        asyncio.run(mcp.run_streamable_http_async(host="127.0.0.1", port=args.port))


if __name__ == "__main__":
    main()
