"""Tests for CL-T8: CLI setup wizard + user management."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from mm.cli.main import app

runner = CliRunner()


@pytest.fixture()
def tmp_data_root(monkeypatch, tmp_path):
    """Redirect DATA_ROOT to a temp directory for isolation."""
    monkeypatch.setattr("mm.cli.main.DATA_ROOT", tmp_path)
    yield tmp_path


def _make_user(data_root: Path, username: str) -> Path:
    """Create a user directory with a minimal config.yaml."""
    from mm.core.store import UserStore
    from mm.auth.keys import generate_key, save_key_hash

    store = UserStore(data_root, username)
    store.init()
    cfg = store.get_config()
    cfg.save(store.config_path)
    _, hashed = generate_key()
    save_key_hash(store.user_dir, hashed)
    return store.user_dir


# ─────────────────────────────────────────────────────────────────────────────
# user delete
# ─────────────────────────────────────────────────────────────────────────────

class TestUserDelete:
    def test_delete_requires_confirm_flag(self, tmp_data_root):
        _make_user(tmp_data_root, "alice")
        result = runner.invoke(app, ["user", "delete", "alice"])
        assert result.exit_code != 0

    def test_delete_removes_user_directory(self, tmp_data_root):
        user_dir = _make_user(tmp_data_root, "bob")
        assert user_dir.exists()

        result = runner.invoke(app, ["user", "delete", "bob", "--confirm"])
        assert result.exit_code == 0, result.output
        assert not user_dir.exists()
        assert "deleted" in result.output

    def test_delete_nonexistent_user_exits_1(self, tmp_data_root):
        result = runner.invoke(app, ["user", "delete", "nobody", "--confirm"])
        assert result.exit_code != 0


# ─────────────────────────────────────────────────────────────────────────────
# domain add / rename / remove
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainCommands:
    def test_domain_add(self, tmp_data_root):
        _make_user(tmp_data_root, "carol")
        result = runner.invoke(app, [
            "domain", "add", "finance", "Finance", "--user", "carol"
        ])
        assert result.exit_code == 0, result.output
        assert "finance" in result.output

        # Verify persisted
        from mm.config.user import UserConfig
        from mm.core.store import UserStore
        store = UserStore(tmp_data_root, "carol")
        cfg = UserConfig.load(store.config_path)
        ids = [d.id for d in cfg.domains]
        assert "finance" in ids

    def test_domain_add_duplicate_fails(self, tmp_data_root):
        _make_user(tmp_data_root, "dave")
        runner.invoke(app, ["domain", "add", "sports", "Sports", "--user", "dave"])
        result = runner.invoke(app, ["domain", "add", "sports", "Sports Again", "--user", "dave"])
        assert result.exit_code != 0

    def test_domain_rename(self, tmp_data_root):
        _make_user(tmp_data_root, "eve")
        # health domain exists by default
        result = runner.invoke(app, ["domain", "rename", "health", "Wellness", "--user", "eve"])
        assert result.exit_code == 0, result.output
        assert "Wellness" in result.output

        from mm.config.user import UserConfig
        from mm.core.store import UserStore
        store = UserStore(tmp_data_root, "eve")
        cfg = UserConfig.load(store.config_path)
        health = next(d for d in cfg.domains if d.id == "health")
        assert health.label == "Wellness"

    def test_domain_rename_nonexistent_fails(self, tmp_data_root):
        _make_user(tmp_data_root, "frank")
        result = runner.invoke(app, ["domain", "rename", "nosuch", "Nope", "--user", "frank"])
        assert result.exit_code != 0

    def test_domain_remove(self, tmp_data_root):
        _make_user(tmp_data_root, "grace")
        result = runner.invoke(app, ["domain", "remove", "personal", "--user", "grace"])
        assert result.exit_code == 0, result.output

        from mm.config.user import UserConfig
        from mm.core.store import UserStore
        store = UserStore(tmp_data_root, "grace")
        cfg = UserConfig.load(store.config_path)
        ids = [d.id for d in cfg.domains]
        assert "personal" not in ids

    def test_domain_remove_nonexistent_fails(self, tmp_data_root):
        _make_user(tmp_data_root, "henry")
        result = runner.invoke(app, ["domain", "remove", "nonexistent", "--user", "henry"])
        assert result.exit_code != 0


# ─────────────────────────────────────────────────────────────────────────────
# ingest
# ─────────────────────────────────────────────────────────────────────────────

class TestIngest:
    def test_ingest_files_connector(self, tmp_data_root, tmp_path):
        """ingest --connector files should call FilesConnector.ingest()."""
        from mm.config.user import UserConfig
        from mm.core.store import UserStore

        _make_user(tmp_data_root, "ingrid")
        store = UserStore(tmp_data_root, "ingrid")
        cfg = UserConfig.load(store.config_path)
        cfg.connectors = [{"connector": "files", "path": str(tmp_path)}]
        cfg.save(store.config_path)

        # Create a test file
        (tmp_path / "note.md").write_text("# Hello\nSome content")

        with patch("mm.connectors.files.FilesConnector") as MockConnector:
            mock_instance = MagicMock()
            mock_instance.validate.return_value = (True, "ok")
            mock_instance.ingest.return_value = [MagicMock(), MagicMock()]
            MockConnector.return_value = mock_instance

            result = runner.invoke(app, [
                "ingest", "--connector", "files", "--user", "ingrid"
            ])

        assert result.exit_code == 0, result.output
        assert mock_instance.validate.called
        assert mock_instance.ingest.called
        assert "2 page(s)" in result.output

    def test_ingest_unknown_connector_fails(self, tmp_data_root):
        _make_user(tmp_data_root, "jim")
        # no connectors configured
        result = runner.invoke(app, [
            "ingest", "--connector", "files", "--user", "jim"
        ])
        assert result.exit_code != 0

    def test_ingest_validation_failure_exits(self, tmp_data_root, tmp_path):
        from mm.config.user import UserConfig
        from mm.core.store import UserStore

        _make_user(tmp_data_root, "kate")
        store = UserStore(tmp_data_root, "kate")
        cfg = UserConfig.load(store.config_path)
        cfg.connectors = [{"connector": "files", "path": "/nonexistent/path"}]
        cfg.save(store.config_path)

        with patch("mm.connectors.files.FilesConnector") as MockConnector:
            mock_instance = MagicMock()
            mock_instance.validate.return_value = (False, "Path does not exist")
            MockConnector.return_value = mock_instance

            result = runner.invoke(app, [
                "ingest", "--connector", "files", "--user", "kate"
            ])

        assert result.exit_code != 0


# ─────────────────────────────────────────────────────────────────────────────
# eval command
# ─────────────────────────────────────────────────────────────────────────────

class TestEval:
    def test_eval_when_not_available(self):
        """eval command should exit cleanly when mm.eval.runner doesn't exist."""
        result = runner.invoke(app, ["eval"])
        assert result.exit_code == 0
        assert "CL-T9" in result.output


# ─────────────────────────────────────────────────────────────────────────────
# user create
# ─────────────────────────────────────────────────────────────────────────────

class TestUserCreate:
    def test_create_user(self, tmp_data_root):
        result = runner.invoke(app, ["user", "create", "testuser"])
        assert result.exit_code == 0, result.output
        assert "created" in result.output
        assert "API key" in result.output
        assert (tmp_data_root / "users" / "testuser").exists()
