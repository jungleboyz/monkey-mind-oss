"""Ingestion runner: orchestrates connector → chunks → embed → store."""
from __future__ import annotations

import datetime
import sqlite3

import chromadb

from mm.connectors.base import BaseConnector, ConnectorPage
from mm.core.store import UserStore
from mm.embedding.pipeline import build_chunks, upsert_chunks
from mm.embedding.providers import EmbeddingProvider


def run_connector(
    connector: BaseConnector,
    user_store: UserStore,
    embed_provider: EmbeddingProvider,
    dry_run: bool = False,
) -> dict:
    """
    Run a connector and ingest its output.

    Steps:
    1. connector.validate() — raise if invalid
    2. connector.ingest() — get list[ConnectorPage]
    3. build_chunks(pages) — two-tier chunking
    4. embed_provider.embed(texts) — get vectors
    5. upsert_chunks to ChromaDB
    6. upsert pages to SQLite pages table
    7. Record ingestion in SQLite ingestions table

    Returns: {pages_created, pages_updated, chunks_total, status}
    """
    ok, msg = connector.validate()
    if not ok:
        raise ValueError(f"Connector validation failed: {msg}")

    pages: list[ConnectorPage] = connector.ingest()
    chunks = build_chunks(pages)

    pages_created = 0
    pages_updated = 0
    status = "ok"

    if not dry_run:
        # --- ChromaDB ---
        client = chromadb.PersistentClient(path=str(user_store.chroma_dir))
        collection = client.get_or_create_collection(user_store.collection_name())
        upsert_chunks(chunks, collection, embed_provider.embed)

        # --- SQLite ---
        now = datetime.datetime.utcnow().isoformat()
        con = sqlite3.connect(user_store.db_path)
        try:
            for page in pages:
                row = con.execute(
                    "SELECT id FROM pages WHERE id = ?", (page.id,)
                ).fetchone()
                tags_str = ",".join(page.tags) if isinstance(page.tags, list) else str(page.tags)
                if row:
                    con.execute(
                        """UPDATE pages SET domain=?, type=?, title=?, source=?,
                           connector=?, updated_at=?, staleness_threshold_days=?,
                           confidence=?, tags=? WHERE id=?""",
                        (
                            page.domain, page.type, page.title, page.source,
                            page.connector, now, page.staleness_threshold_days,
                            page.confidence, tags_str, page.id,
                        ),
                    )
                    pages_updated += 1
                else:
                    con.execute(
                        """INSERT INTO pages
                           (id, domain, type, title, source, connector,
                            created_at, updated_at, staleness_threshold_days,
                            confidence, tags, raw_path)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            page.id, page.domain, page.type, page.title,
                            page.source, page.connector, now, now,
                            page.staleness_threshold_days, page.confidence,
                            tags_str, page.source_ref,
                        ),
                    )
                    pages_created += 1

            con.execute(
                """INSERT INTO ingestions
                   (connector, source_ref, status, pages_created, pages_updated, ran_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    connector.connector_id,
                    connector.config.get("path", ""),
                    status,
                    pages_created,
                    pages_updated,
                    now,
                ),
            )
            con.commit()
        finally:
            con.close()

    return {
        "pages_created": pages_created,
        "pages_updated": pages_updated,
        "chunks_total": len(chunks),
        "status": status,
    }
