# Quickstart Guide

Get from `git clone` to working queries in one sitting.

---

## Prerequisites

- Python 3.11+
- An OpenAI API key (for embeddings — `text-embedding-3-small`)
- An Anthropic or OpenAI API key (for synthesis)
- Optional: Docker + Docker Compose for the containerised path

---

## Path A: Docker Compose (recommended for production)

### 1. Clone and configure

```bash
git clone https://github.com/jungleboyz/monkey-mind-oss.git
cd monkey-mind-oss
cp .env.example .env
```

Edit `.env`:
```bash
OPENAI_API_KEY=sk-...         # Required for embeddings
ANTHROPIC_API_KEY=sk-ant-...  # Required for synthesis (or use OPENAI)
MM_LLM_PROVIDER=anthropic     # anthropic | openai | ollama
MM_EMBED_PROVIDER=openai      # openai | ollama
```

### 2. Start services

```bash
docker compose up -d
```

Wait ~30 seconds for startup. Check health:
```bash
curl http://localhost:8000/health
# → {"status": "ok"}
```

### 3. Create your user

```bash
docker compose exec api monkey-mind user create myname
# → User 'myname' created.
# → Your API key: mm_sk_ABC123... (save this — shown once)
```

### 4. Ingest your first content

**From a folder of notes:**
```bash
docker compose exec api monkey-mind ingest --connector files --user myname
# Prompts for directory path
```

**From GitHub:**
```bash
docker compose exec api monkey-mind ingest --connector github --user myname
# Prompts for GitHub username
```

### 5. Query your context

```bash
curl -X POST http://localhost:8000/query \
  -H "X-API-Key: mm_sk_ABC123..." \
  -H "Content-Type: application/json" \
  -d '{"query": "What should I focus on this week?"}'
```

### 6. Connect to Claude Desktop (MCP)

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "monkey-mind": {
      "command": "docker",
      "args": ["compose", "-f", "/path/to/monkey-mind-oss/docker-compose.yml",
               "exec", "-T", "mcp", "python", "-m", "mm.mcp.server"],
      "env": {
        "USER_ID": "myname"
      }
    }
  }
}
```

Or for local install (Path B), use the simpler config from the README.

---

## Path B: Local Install (development / tinkering)

### 1. Clone and install

```bash
git clone https://github.com/jungleboyz/monkey-mind-oss.git
cd monkey-mind-oss
pip install -e ".[dev]"
```

### 2. Run the setup wizard

```bash
monkey-mind setup
```

The wizard walks you through:
1. Choose a username
2. Configure LLM provider + API key
3. Configure embedding provider + API key
4. Choose connectors (files, GitHub, or both)
5. Run first ingestion
6. Validate with eval suite

Target: **working context library in under 30 minutes.**

### 3. Start the API server

```bash
export DATA_ROOT=~/.monkey-mind
uvicorn mm.api.server:app --host 0.0.0.0 --port 8000
```

### 4. Start the MCP server (separate terminal)

```bash
export DATA_ROOT=~/.monkey-mind
export USER_ID=myname
python -m mm.mcp.server  # stdio mode for Claude Desktop
```

---

## Running the Eval Suite

Check the quality of your context library:

```bash
monkey-mind eval --api-url http://localhost:8000 --api-key mm_sk_ABC123...
```

Output:
```
S1 Within-domain retrieval    PASS
S2 Cross-domain synthesis     PASS
S3 Temporal awareness         PASS
S4 Staleness detection        PASS
S5 Knowledge boundary         PASS
S6 Auth boundary              PASS
S7 Source provenance          PASS
S8 Cross-domain insight       PASS
S9 Connector ingestion        PASS

Score: 9/9 ✅
```

For CI / JSON output:
```bash
monkey-mind eval --api-url http://localhost:8000 --api-key mm_sk_... --output json
```

---

## Managing Domains

```bash
monkey-mind domain add finances "Finances"       # Add new domain
monkey-mind domain rename health "Wellbeing"     # Rename existing
monkey-mind domain remove projects               # Remove domain
```

---

## Troubleshooting

**"Collection not found" on first query**
→ You haven't ingested any content yet. Run `monkey-mind ingest --connector files`.

**401 Unauthorized**
→ Check your API key. Keys are shown once at creation. Rotate with `monkey-mind user rotate-key myname`.

**Slow embeddings**
→ `text-embedding-3-small` is fast. If using Ollama, ensure the model is pulled: `ollama pull nomic-embed-text`.

**MCP server not connecting**
→ Ensure `USER_ID` and `DATA_ROOT` env vars are set correctly in your MCP config.
