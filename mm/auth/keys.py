"""API key generation and verification."""
from __future__ import annotations

import os
from pathlib import Path

import base58 as _base58
import bcrypt


def generate_key() -> tuple[str, str]:
    """Returns (raw_key, bcrypt_hash). Key format: mm_sk_{base58(32 random bytes)}"""
    raw_bytes = os.urandom(32)
    encoded = _base58.b58encode(raw_bytes).decode('ascii')
    raw_key = f'mm_sk_{encoded}'
    hashed = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode('utf-8')
    return raw_key, hashed


def verify_key(raw_key: str, stored_hash: str) -> bool:
    """Verify raw key against bcrypt hash."""
    return bcrypt.checkpw(raw_key.encode(), stored_hash.encode())


def save_key_hash(user_dir: Path, hash: str) -> None:
    """Save bcrypt hash to user_dir/api_key.hash"""
    (user_dir / 'api_key.hash').write_text(hash)


def load_key_hash(user_dir: Path) -> str | None:
    """Load hash from user_dir/api_key.hash. Returns None if not found."""
    p = user_dir / 'api_key.hash'
    return p.read_text().strip() if p.exists() else None
