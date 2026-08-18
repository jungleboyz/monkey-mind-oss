"""Monkey Mind CLI entry point."""
import typer

app = typer.Typer(
    name="monkey-mind",
    help="Your AI tools forget you every conversation. Monkey Mind remembers everything.",
    no_args_is_help=True,
)


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
