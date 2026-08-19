# Changelog

All notable changes to Monkey Mind will be documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/)

---

## [0.1.0] — 2026-08-19

### Added
- Core package structure (`mm/`) with Apache 2.0 license
- Two-tier embedding pipeline (summary + detail chunks), model-agnostic via `EmbeddingProvider`
- Multi-tenant user store (per-user SQLite + ChromaDB isolation)
- Connector framework (`BaseConnector`) with file and GitHub connectors
- REST API (FastAPI) with X-API-Key auth, `/query`, `/domains`, `/pages`, `/health`, OpenAPI spec
- MCP server (stdio + HTTP transport) exposing 5 tools for Claude Desktop / Cursor
- CLI: `monkey-mind setup` wizard, `ingest`, `domain`, `user`, `eval` subcommands
- Parameterized 9-scenario eval suite (S1–S9)
- Docker Compose deployment (api + mcp services)
- GitHub Actions CI (tests on PR, eval on main, release on tag)
