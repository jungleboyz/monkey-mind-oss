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

### 3. Add your notes

The API container reads notes from `./notes` (mounted read-only at `/notes`). Point `MM_NOTES_DIR` in `.env` at another folder if you prefer.

```bash
mkdir -p notes
cp -r ~/path/to/your/notes/* notes/
```

Domains (health, professional, strategic, projects, temporal, personal) are detected from file and folder names, so `notes/health/sleep.md` lands in *health*. Anything unmatched goes to *personal*.

### 4. Run the setup wizard

```bash
docker compose exec api monkey-mind setup
```

Answer the prompts:

| Prompt | Answer |
|--------|--------|
| Username | anything, e.g. `myname` |
| LLM provider | `1` (anthropic) or `2` (openai) |
| API key prompts | press **Enter** — Docker already has the keys from `.env` |
| Where is your context? | `1` (local files) |
| Directory path | `/notes` |

The wizard creates your user, prints your API key (**save it — shown once**), ingests `/notes`, and runs a test query. You should see `🎉 Your context library is ready!`

> The wizard needs an interactive terminal. `docker compose exec` gives you one; don't add `-T`.
> `monkey-mind user create` only creates a user and key — it does **not** configure a connector, so `ingest` will say "No connector 'files' configured". Use `setup`.

### 5. Query your context

From the CLI:
```bash
docker compose exec api monkey-mind query --user myname "What should I focus on this week?"
```

Or over REST (note the header is `X-API-Key`, not `Authorization: Bearer`):
```bash
curl -X POST http://localhost:8000/query \
  -H "X-API-Key: mm_sk_ABC123..." \
  -H "Content-Type: application/json" \
  -d '{"query": "What should I focus on this week?"}'
```

Added or edited notes? Re-ingest (existing pages are updated, not duplicated):
```bash
docker compose exec api monkey-mind ingest --connector files --user myname
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

Set `MM_USER_ID=myname` in `.env` and run `docker compose up -d mcp` so the MCP container serves your user (it defaults to `default`).

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

Keys you enter in the wizard are saved to `~/.monkey-mind/.env` and loaded automatically by the CLI and API server.

Query from the CLI straight away:
```bash
monkey-mind query --user myname "What should I focus on this week?"
```

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
# Docker: docker compose exec api monkey-mind eval --api-key mm_sk_ABC123...
```

The key can also come from the `MM_API_KEY` environment variable. Cross-domain scenarios (S2, S8) need notes in at least two domains.

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
monkey-mind domain add finances "Finances" --user myname     # Add new domain
monkey-mind domain rename health "Wellbeing" --user myname   # Rename existing
monkey-mind domain remove projects --user myname             # Remove domain
```

---

## Troubleshooting

**"Collection not found" on first query**
→ You haven't ingested any content yet. Run `monkey-mind ingest --connector files --user myname`.

**"No connector 'files' configured for user"**
→ The user was made with `user create`, which doesn't set up connectors. Run `monkey-mind setup` with the same username and choose to reconfigure.

**"Path does not exist" in Docker**
→ Inside the container your notes are at `/notes`, not your host path. Check `MM_NOTES_DIR` in `.env` and restart with `docker compose up -d`.

**Query returns 500**
→ Usually a missing or placeholder LLM key. Check `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` in `.env`, then `docker compose up -d` to reload.

**401 Unauthorized**
→ Check your API key and that you're sending it as `X-API-Key`. Keys are shown once at creation. Rotate with `monkey-mind user rotate-key myname`.

**Slow embeddings**
→ `text-embedding-3-small` is fast. If using Ollama, ensure the model is pulled: `ollama pull nomic-embed-text`.

**MCP server not connecting**
→ Ensure `USER_ID` and `DATA_ROOT` env vars are set correctly in your MCP config.
