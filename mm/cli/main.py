"""Monkey Mind CLI entry point."""
import shutil
import typer
from pathlib import Path

app = typer.Typer(
    name="monkey-mind",
    help="Your AI tools forget you every conversation. Monkey Mind remembers everything.",
    no_args_is_help=True,
)

user_app = typer.Typer(help="Manage Monkey Mind users.")
app.add_typer(user_app, name="user")

DATA_ROOT = Path.home() / '.monkey-mind'


@user_app.command('create')
def user_create(name: str = typer.Argument(..., help='Username (alphanumeric + hyphens)')):
    """Create user directory, generate API key, and print it once."""
    from mm.core.store import UserStore
    from mm.auth.keys import generate_key, save_key_hash

    store = UserStore(DATA_ROOT, name)
    store.init()
    cfg = store.get_config()
    cfg.save(store.config_path)

    raw_key, hashed = generate_key()
    save_key_hash(store.user_dir, hashed)

    typer.echo(f"✓ User '{name}' created.")
    typer.echo(f"  API key (shown once, store it safely):\n\n  {raw_key}\n")


@user_app.command('delete')
def user_delete(
    name: str = typer.Argument(...),
    confirm: bool = typer.Option(False, '--confirm', help='Required to actually delete'),
):
    """Remove all data for a user."""
    from mm.core.store import UserStore

    if not confirm:
        typer.echo("Pass --confirm to actually delete the user.", err=True)
        raise typer.Exit(1)

    store = UserStore(DATA_ROOT, name)
    if store.user_dir.exists():
        shutil.rmtree(store.user_dir)
        typer.echo(f"✓ User '{name}' deleted.")
    else:
        typer.echo(f"User '{name}' not found.", err=True)
        raise typer.Exit(1)


@user_app.command('rotate-key')
def user_rotate_key(name: str = typer.Argument(...)):
    """Generate a new API key, invalidating the old one."""
    from mm.core.store import UserStore
    from mm.auth.keys import generate_key, save_key_hash

    store = UserStore(DATA_ROOT, name)
    if not store.user_dir.exists():
        typer.echo(f"User '{name}' not found.", err=True)
        raise typer.Exit(1)

    raw_key, hashed = generate_key()
    save_key_hash(store.user_dir, hashed)
    typer.echo(f"✓ API key rotated for '{name}'.")
    typer.echo(f"  New API key (shown once):\n\n  {raw_key}\n")


@app.command()
def setup():
    """Interactive setup wizard — zero to working context library in < 30 minutes."""
    typer.echo("Setup wizard coming in CL-T8.")


@app.command()
def ingest(connector: str = typer.Option(..., help="Connector ID to run (e.g. files, github)")):
    """Run a connector to ingest content into your context library."""
    typer.echo(f"Ingestion via '{connector}' coming in CL-T4/CL-T5.")


@app.command()
def query(q: str = typer.Argument(..., help="Your question")):
    """Query your context library."""
    typer.echo("Query coming in CL-T6.")


@app.command()
def eval(output: str = typer.Option("text", help="Output format: text | json")):
    """Run the eval suite against your context library."""
    typer.echo("Eval suite coming in CL-T9.")


@app.callback(invoke_without_command=True)
def version(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit"),
):
    if version:
        typer.echo("monkey-mind 0.1.0")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


if __name__ == "__main__":
    app()
