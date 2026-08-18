"""Tests for UserStore, UserConfig, and auth keys."""
import sqlite3
import pytest
from pathlib import Path

from mm.core.store import UserStore
from mm.config.user import UserConfig
from mm.auth.keys import generate_key, verify_key


def test_user_store_init(tmp_path):
    store = UserStore(tmp_path, 'alice')
    store.init()
    assert store.user_dir.exists()
    assert store.context_dir.exists()
    assert store.chroma_dir.exists()
    assert store.db_path.parent.exists()
    assert store.db_path.exists()


def test_sqlite_schema(tmp_path):
    store = UserStore(tmp_path, 'alice')
    store.init()
    con = sqlite3.connect(store.db_path)
    tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    con.close()
    assert {'pages', 'ingestions', 'auth_log'}.issubset(tables)


def test_collection_name(tmp_path):
    store = UserStore(tmp_path, 'alice')
    assert store.collection_name() == 'mm-alice'


def test_path_traversal_rejected(tmp_path):
    with pytest.raises(ValueError):
        UserStore(tmp_path, '../evil')


def test_two_users_isolated(tmp_path):
    s1 = UserStore(tmp_path, 'alice')
    s2 = UserStore(tmp_path, 'bob')
    assert s1.db_path != s2.db_path
    assert s1.collection_name() != s2.collection_name()


def test_key_generate_verify():
    raw_key, hashed = generate_key()
    assert verify_key(raw_key, hashed) is True


def test_key_format():
    raw_key, _ = generate_key()
    assert raw_key.startswith('mm_sk_')


def test_user_config_default():
    cfg = UserConfig.default('rob')
    assert len(cfg.domains) == 6


def test_user_config_roundtrip(tmp_path):
    cfg = UserConfig.default('rob')
    path = tmp_path / 'config.yaml'
    cfg.save(path)
    cfg2 = UserConfig.load(path)
    assert cfg2.user_id == cfg.user_id
    assert len(cfg2.domains) == len(cfg.domains)
    assert cfg2.llm.provider == cfg.llm.provider
    assert cfg2.embedding.model == cfg.embedding.model
    assert cfg2.domains[0].id == cfg.domains[0].id
