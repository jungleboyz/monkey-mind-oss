"""Tests for the generalized embedding pipeline."""
import pytest
from unittest.mock import patch, MagicMock

from mm.connectors.base import ConnectorPage
from mm.embedding.pipeline import build_chunks
from mm.embedding.providers import EmbeddingProvider


def make_page(**kwargs) -> ConnectorPage:
    defaults = dict(
        id="test-page-1",
        domain="work",
        type="note",
        title="Test Page",
        summary="This is the summary.",
        detail_sections={},
        source="manual",
        source_ref="http://example.com",
        connector="test",
    )
    defaults.update(kwargs)
    return ConnectorPage(**defaults)


def test_build_chunks_summary():
    page = make_page()
    chunks = build_chunks([page])
    summary_chunks = [c for c in chunks if c.chunk_type == "summary"]
    assert len(summary_chunks) == 1
    assert summary_chunks[0].text.startswith("[SUMMARY]")


def test_build_chunks_detail():
    page = make_page(detail_sections={"Background": "Some background text.", "Next Steps": "Do things."})
    chunks = build_chunks([page])
    detail_chunks = [c for c in chunks if c.chunk_type == "detail"]
    assert len(detail_chunks) == 2
    headings = {c.metadata["section_heading"] for c in detail_chunks}
    assert "Background" in headings
    assert "Next Steps" in headings


def test_chunk_metadata():
    page = make_page(domain="health", source="jira", connector="jira-connector")
    chunks = build_chunks([page])
    assert len(chunks) > 0
    for chunk in chunks:
        assert chunk.metadata["domain"] == "health"
        assert chunk.metadata["source"] == "jira"
        assert chunk.metadata["connector"] == "jira-connector"


def test_openai_provider_init():
    with patch("openai.OpenAI") as mock_openai:
        provider = EmbeddingProvider.from_config({"provider": "openai", "model": "text-embedding-3-small"})
    assert provider._provider == "openai"
    assert provider._model == "text-embedding-3-small"


def test_ollama_provider_init():
    provider = EmbeddingProvider.from_config({"provider": "ollama", "model": "nomic-embed-text"})
    assert provider._provider == "ollama"
    assert provider._model == "nomic-embed-text"
