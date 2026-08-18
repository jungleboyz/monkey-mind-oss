"""Embedding pipeline: chunking and upsert logic."""
from typing import Callable, Any

from mm.connectors.base import ConnectorPage, Chunk


def build_chunks(pages: list[ConnectorPage]) -> list[Chunk]:
    """Build summary and detail chunks from a list of ConnectorPages."""
    chunks = []
    for page in pages:
        tags_str = ", ".join(page.tags) if isinstance(page.tags, list) else str(page.tags)
        base_meta: dict[str, Any] = {
            "domain": page.domain,
            "type": page.type,
            "source": page.source,
            "source_ref": page.source_ref,
            "connector": page.connector,
            "confidence": page.confidence,
            "tags": tags_str,
            "staleness_threshold_days": str(page.staleness_threshold_days),
            "page_id": page.id,
            "title": page.title,
        }

        # Summary chunk
        if page.summary.strip():
            chunks.append(Chunk(
                id=f"{page.id}::summary",
                text=f"[SUMMARY] {page.summary.strip()}",
                metadata={**base_meta, "chunk_type": "summary", "section_heading": "Summary"},
                chunk_type="summary",
            ))

        # Detail chunks
        for heading, body in page.detail_sections.items():
            if not body.strip():
                continue
            chunks.append(Chunk(
                id=f"{page.id}::detail::{heading}",
                text=f"[DETAIL:{heading}] {body.strip()}",
                metadata={**base_meta, "chunk_type": "detail", "section_heading": heading},
                chunk_type="detail",
            ))

    return chunks


def upsert_chunks(chunks: list[Chunk], collection, embedding_fn: Callable[[list[str]], list[list[float]]]) -> None:
    """Idempotent upsert of chunks into a ChromaDB collection."""
    if not chunks:
        return

    BATCH_SIZE = 50
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i: i + BATCH_SIZE]
        texts = [c.text for c in batch]
        ids = [c.id for c in batch]
        metadatas = [c.metadata for c in batch]
        embeddings = embedding_fn(texts)
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
