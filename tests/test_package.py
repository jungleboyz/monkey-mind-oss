"""Smoke tests — verify package structure and imports."""


def test_mm_importable():
    import mm
    assert mm is not None


def test_subpackages_importable():
    from mm import connectors, cli, mcp, auth, config, core, embedding, api, ingestion
    for pkg in (connectors, cli, mcp, auth, config, core, embedding, api, ingestion):
        assert pkg is not None


def test_cli_app_exists():
    from mm.cli.main import app
    assert app is not None


def test_cli_commands():
    from typer.testing import CliRunner
    from mm.cli.main import app
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("setup", "ingest", "query", "eval"):
        assert cmd in result.output
