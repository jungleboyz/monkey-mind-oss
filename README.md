# Monkey Mind

> Your AI tools forget you every conversation. Monkey Mind remembers everything, across every tool, forever.

**Monkey Mind** is an open-source, self-hosted personal context library for developers. It gives your AI tools — Claude, Cursor, ChatGPT — a persistent, structured memory of who you are, what you've worked on, and what matters to you.

No more re-explaining yourself. No more pasting stale context into system prompts.

---

## Why Monkey Mind?

| The problem | The solution |
|------------|-------------|
| AI tools forget you every conversation | Monkey Mind persists your context across all tools |
| Context is scattered across notes, GitHub, files | One structured library, multiple sources |
| You don't know if your context is stale | Staleness detection + eval suite |
| You can't trust AI answers about yourself | Every fact traced to a source |
| Locked into one AI provider | Works with any LLM + embedding model |

**Positioning:** Google Personal Intelligence, but open source, self-hosted, and works with any AI.

---

## Quickstart (5 minutes)

### Option A: Docker Compose

```bash
git clone https://github.com/jungleboyz/monkey-mind-oss.git
cd monkey-mind-oss
cp .env.example .env
# Edit .env — add your OPENAI_API_KEY and ANTHROPIC_API_KEY
docker compose up -d
```

The API is now running at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

Create your first user and get an API key:
```bash
docker compose exec api monkey-mind user create myname
# → Your API key: mm_sk_... (save this — shown once)
```

### Option B: Local install

```bash
git clone https://github.com/jungleboyz/monkey-mind-oss.git
cd monkey-mind-oss
pip install -e .
monkey-mind setup
```

The setup wizard walks you through everything in under 30 minutes.

---

## Full Setup Guide

See **[docs/quickstart.md](docs/quickstart.md)** for the complete walkthrough:
- Connecting your first sources (files, GitHub)
- Running your first query
- Connecting to Claude Desktop via MCP
- Running the eval suite

---

## Features

- **Domain-structured context** — 6 default life domains (health, professional, personal, strategic, temporal, projects). Add your own.
- **Two-tier retrieval** — summary + detail embeddings for fast, deep answers
- **Cross-domain synthesis** — "what should I focus on this week?" draws from health, work, and calendar simultaneously
- **Provenance tracking** — every fact traces back to its source
- **Staleness detection** — configurable thresholds per domain; stale sources flagged in responses
- **Knowledge boundary** — says "I don't know" instead of hallucinating
- **MCP server** — connects to Claude Desktop, Cursor, and any MCP-compatible tool
- **REST API** — documented, authenticated, OpenAPI spec included
- **Pluggable connectors** — file upload and GitHub out of the box; community builds the rest
- **Self-hosted** — your data never leaves your machine
- **Model-agnostic** — bring your own OpenAI, Anthropic, or Ollama keys

---

## Connectors

| Connector | Status | What it ingests |
|-----------|--------|----------------|
| **Files** | ✅ Built-in | Markdown, text, PDF from any local directory |
| **GitHub** | ✅ Built-in | Profile, repos, READMEs, contribution patterns |
| Obsidian | 🔜 Phase 2 | Vault notes and links |
| Gmail | 🔜 Phase 2 | Email threads (OAuth) |
| Community | 🤝 Build one | See [connector dev guide](docs/connector-dev-guide.md) |

---

## MCP Integration (Claude Desktop / Cursor)

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "monkey-mind": {
      "command": "python",
      "args": ["-m", "mm.mcp.server"],
      "env": {
        "USER_ID": "myname",
        "DATA_ROOT": "/path/to/.monkey-mind"
      }
    }
  }
}
```

Then ask Claude: *"What should I focus on this week?"* — and it will draw from your health, work, and strategic domains.

---

## CLI Reference

```bash
monkey-mind setup                          # Interactive setup wizard
monkey-mind ingest --connector files       # Ingest from file connector
monkey-mind ingest --connector github      # Ingest from GitHub connector
monkey-mind eval                           # Run quality eval suite
monkey-mind domain add <id> <label>        # Add a domain
monkey-mind domain rename <id> <label>     # Rename a domain
monkey-mind domain remove <id>             # Remove a domain
monkey-mind user create <name>             # Create user + generate API key
monkey-mind user delete <name> --confirm   # Delete all user data
```

---

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full technical design.

**High-level flow:**
```
Source (files/GitHub) → Connector → ConnectorPage
  → Two-tier embedding (summary + detail)
  → ChromaDB (per-user collection)
  → REST API / MCP server → Your AI tool
```

---

## Contributing

Monkey Mind is Apache 2.0. Contributions welcome.

**Best first contribution:** Build a connector. The connector interface is clean and documented — see [docs/connector-dev-guide.md](docs/connector-dev-guide.md).

```bash
git clone https://github.com/jungleboyz/monkey-mind-oss.git
cd monkey-mind-oss
pip install -e ".[dev]"
python -m pytest tests/ -v
```

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

---

*Context is the moat. Monkey Mind proved the architecture. Now we prove the market.*
