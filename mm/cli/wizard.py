"""Interactive setup wizard for Monkey Mind."""
from __future__ import annotations

import os
from pathlib import Path

import typer

DATA_ROOT = Path.home() / ".monkey-mind"


def run_wizard() -> None:
    """Walk user through initial configuration interactively."""
    typer.echo("\n🐒 Welcome to Monkey Mind Setup Wizard\n")

    # ── Detect existing config ───────────────────────────────────────────────
    # Try to find any existing user config
    existing_users: list[str] = []
    if DATA_ROOT.exists():
        existing_users = [
            p.name for p in DATA_ROOT.iterdir()
            if p.is_dir() and (p / "config.yaml").exists()
        ]

    if existing_users:
        typer.echo(f"Existing users found: {', '.join(existing_users)}")
        reconfigure = typer.confirm("Reconfigure?", default=False)
        if not reconfigure:
            typer.echo("Setup cancelled. Run 'monkey-mind setup' again to reconfigure.")
            raise typer.Exit(0)

    # ── Step 1: Username ─────────────────────────────────────────────────────
    username = typer.prompt("Step 1/8 · Enter username (alphanumeric + hyphens)").strip()
    if not username:
        typer.echo("Username cannot be empty.", err=True)
        raise typer.Exit(1)

    from mm.core.store import UserStore
    from mm.auth.keys import generate_key, save_key_hash
    from mm.config.user import UserConfig, LLMConfig, EmbedConfig

    store = UserStore(DATA_ROOT, username)
    store.init()

    if (store.config_path).exists():
        cfg = UserConfig.load(store.config_path)
    else:
        cfg = UserConfig.default(username)
        raw_key, hashed = generate_key()
        save_key_hash(store.user_dir, hashed)
        typer.echo(f"\n✓ User '{username}' created.")
        typer.echo(f"  API key (shown once — store safely):\n\n  {raw_key}\n")

    # ── Step 2: LLM provider ─────────────────────────────────────────────────
    llm_providers = ["anthropic", "openai", "ollama"]
    typer.echo("Step 2/8 · LLM provider")
    for i, p in enumerate(llm_providers, 1):
        typer.echo(f"  {i}. {p}")
    llm_choice = typer.prompt("Choose [1-3]", default="1")
    try:
        llm_provider = llm_providers[int(llm_choice) - 1]
    except (ValueError, IndexError):
        llm_provider = "anthropic"

    if llm_provider != "ollama":
        llm_key = typer.prompt(f"Enter {llm_provider} API key", hide_input=True, default="")
        if llm_key:
            _set_env_var(f"{llm_provider.upper()}_API_KEY", llm_key)

    cfg.llm = LLMConfig(provider=llm_provider, model=_default_model(llm_provider))

    # ── Step 3: Embedding provider ───────────────────────────────────────────
    embed_providers = ["openai", "local"]
    typer.echo("Step 3/8 · Embedding provider")
    for i, p in enumerate(embed_providers, 1):
        typer.echo(f"  {i}. {p}")
    embed_choice = typer.prompt("Choose [1-2]", default="1")
    try:
        embed_provider_name = embed_providers[int(embed_choice) - 1]
    except (ValueError, IndexError):
        embed_provider_name = "openai"

    if embed_provider_name == "openai":
        embed_key = typer.prompt("Enter OpenAI API key (or leave blank if already set)", hide_input=True, default="")
        if embed_key:
            _set_env_var("OPENAI_API_KEY", embed_key)

    cfg.embedding = EmbedConfig(
        provider=embed_provider_name,
        model="text-embedding-3-small" if embed_provider_name == "openai" else "local",
    )

    # ── Step 4: Connectors ───────────────────────────────────────────────────
    typer.echo("Step 4/8 · Choose connectors")
    typer.echo("  1. files")
    typer.echo("  2. github")
    typer.echo("  3. both")
    connector_choice = typer.prompt("Choose [1-3]", default="1")

    connector_ids: list[str] = []
    if connector_choice == "2":
        connector_ids = ["github"]
    elif connector_choice == "3":
        connector_ids = ["files", "github"]
    else:
        connector_ids = ["files"]

    connector_configs: list[dict] = []

    # ── Step 5/6: Connector-specific config ──────────────────────────────────
    for cid in connector_ids:
        if cid == "files":
            connector_configs.append(_configure_files_connector())
        elif cid == "github":
            connector_configs.append(_configure_github_connector())

    cfg.connectors = connector_configs
    cfg.save(store.config_path)
    typer.echo("\n✓ Configuration saved.")

    # ── Step 7: First ingestion ──────────────────────────────────────────────
    run_ingest = typer.confirm("Step 7/8 · Run first ingestion now?", default=True)
    if run_ingest:
        for conn_cfg in connector_configs:
            _run_ingestion(conn_cfg, store)
    else:
        typer.echo("Skipping ingestion. Run 'monkey-mind ingest --connector <name>' later.")

    # ── Step 8: Eval ─────────────────────────────────────────────────────────
    typer.echo("Step 8/8 · Eval")
    _run_eval_if_available()

    # ── Summary ──────────────────────────────────────────────────────────────
    typer.echo("\n🎉 Your context library is ready!")
    typer.echo(f"   User:      {username}")
    typer.echo(f"   LLM:       {cfg.llm.provider} / {cfg.llm.model}")
    typer.echo(f"   Embedding: {cfg.embedding.provider}")
    typer.echo(f"   Connectors: {', '.join(c['connector'] for c in connector_configs)}")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _default_model(provider: str) -> str:
    return {
        "anthropic": "claude-haiku-4-5",
        "openai": "gpt-4o-mini",
        "ollama": "llama3",
    }.get(provider, "claude-haiku-4-5")


def _set_env_var(key: str, value: str) -> None:
    """Write key=value to ~/.monkey-mind/.env and set in current process."""
    os.environ[key] = value
    env_path = DATA_ROOT / ".env"
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()
    # Remove existing key
    lines = [l for l in lines if not l.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines) + "\n")
    typer.echo(f"  ✓ {key} saved to {env_path}")


def _configure_files_connector() -> dict:
    """Prompt for files connector config, validate path."""
    typer.echo("Step 5/8 · Files connector configuration")
    while True:
        dir_path = typer.prompt("Enter directory path to ingest").strip()
        p = Path(dir_path).expanduser()
        if p.exists():
            typer.echo(f"  ✓ Path exists: {p}")
            return {"connector": "files", "path": str(p)}
        typer.echo(f"  ✗ Path does not exist: {p}. Please try again.", err=True)


def _configure_github_connector() -> dict:
    """Prompt for GitHub connector config, call validate()."""
    from mm.connectors.github import GitHubConnector

    typer.echo("Step 6/8 · GitHub connector configuration")
    while True:
        gh_user = typer.prompt("Enter GitHub username").strip()
        token = typer.prompt("Enter GitHub token (optional, for higher rate limits)", default="")
        config: dict = {"username": gh_user}
        if token:
            config["github_token"] = token

        connector = GitHubConnector(config, None)
        typer.echo(f"  Validating GitHub user '{gh_user}'...")
        ok, msg = connector.validate()
        if ok:
            typer.echo(f"  ✓ GitHub user '{gh_user}' validated.")
            return {"connector": "github", **config}
        typer.echo(f"  ✗ Validation failed: {msg}. Please try again.", err=True)


def _run_ingestion(conn_cfg: dict, store) -> None:
    """Instantiate connector, validate, then ingest."""
    from mm.connectors.files import FilesConnector
    from mm.connectors.github import GitHubConnector

    cid = conn_cfg.get("connector", "")
    cfg_copy = {k: v for k, v in conn_cfg.items() if k != "connector"}

    if cid == "files":
        connector = FilesConnector(cfg_copy, None)
    elif cid == "github":
        connector = GitHubConnector(cfg_copy, None)
    else:
        typer.echo(f"Unknown connector '{cid}', skipping.", err=True)
        return

    typer.echo(f"\nIngesting via '{cid}'...")
    ok, msg = connector.validate()
    if not ok:
        typer.echo(f"  ✗ Connector validation failed: {msg}", err=True)
        return

    try:
        pages = connector.ingest()
        typer.echo(f"  ✓ Ingested {len(pages)} page(s) via '{cid}'.")
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"  ✗ Ingestion error: {exc}", err=True)


def _run_eval_if_available() -> None:
    """Call eval runner if it exists."""
    try:
        from mm.eval import runner  # type: ignore[import]
        typer.echo("Running eval...")
        runner.run()
    except (ImportError, AttributeError):
        typer.echo("Eval not available — run after CL-T9 is built.")
