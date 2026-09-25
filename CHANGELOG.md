# Changelog

All notable changes to Monkey Mind will be documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/)

---

## [0.2.0] — 2026-09-25

### Added
- Remote MCP connectors for **claude.ai** and **ChatGPT**: OAuth 2.1 Authorization Code + PKCE (S256) with Dynamic Client Registration (#32)
- MCP HTTP transport auth (`X-API-Key`), `/sse` endpoint and OAuth discovery for hosted deployments
- Railway deployment (`railway.toml`, startup scripts) plus `/bootstrap` and `/ingest/files` API endpoints
- macOS Claude Desktop installer (`setup-mcp.sh`) and stack check (`test-mcp.sh`)
- Integration test gate in CI (full Docker stack) and smoke test workflow
- Logo and README rewrite
- `monkey-mind query --user <name> "<question>"` — query from the CLI (was a stub)
- Docker Compose mounts your notes folder (`MM_NOTES_DIR`, default `./notes`) at `/notes`
- CLI and API server load keys the wizard saved to `<DATA_ROOT>/.env`

### Fixed
- `monkey-mind ingest` now embeds and stores pages; previously it read files, reported success, and wrote nothing
- `monkey-mind eval` runs the suite (`--api-url`, `--api-key` / `MM_API_KEY`, `--output`); previously always "not available"
- Query sources cite the actual file and ingest time instead of just `files`, so provenance (S7) and staleness warnings work
- Setup wizard: actually configures connectors, shows the API key, respects `DATA_ROOT`
- Chunker: max chunk size enforced, at least one chunk per page
- Files connector skips unreadable directories instead of crashing
- Docker build (source copied before install)
- Integration CI gate headers (#33)
- Quickstart: use the `setup` wizard (`user create` doesn't configure a connector), `X-API-Key` header (not `Bearer`), `/notes` path in Docker, `MM_USER_ID` for the MCP container

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
