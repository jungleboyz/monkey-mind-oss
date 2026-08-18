# Monkey Mind

> Your AI tools forget you every conversation. Monkey Mind remembers everything, across every tool, forever.

**Monkey Mind** is an open-source, self-hosted personal context library for developers. It gives your AI tools (Claude Desktop, Cursor, and any MCP-compatible client) persistent, structured knowledge about you — so you stop re-explaining yourself every conversation.

## What it does

- **Structured context** across 6 life domains: health, professional, personal, strategic, temporal, projects
- **Cross-domain retrieval** — ask a question, get answers that draw from your whole life, not one silo
- **Two connectors out of the box**: file/directory upload and GitHub profile
- **MCP server** — plug into Claude Desktop, Cursor, or any MCP-compatible tool
- **Eval suite** — measure the quality of your context library, not just vibes
- **Self-hosted, no telemetry, BYOK** — your data stays yours

## Quickstart

```bash
# 1. Clone and set up
git clone https://github.com/jungleboyz/monkey-mind-oss
cd monkey-mind-oss
cp .env.example .env
# Edit .env with your API keys

# 2. Start
docker compose up -d

# 3. Set up your context library
monkey-mind setup

# 4. Ask a question
curl -X POST http://localhost:8000/query \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "What should I focus on this week?"}'
```

See [docs/quickstart.md](docs/quickstart.md) for the full setup guide.

## Documentation

- [Quickstart](docs/quickstart.md)
- [Architecture](docs/architecture.md)
- [Connector Dev Guide](docs/connector-dev-guide.md)

## License

Apache 2.0 — see [LICENSE](LICENSE).
