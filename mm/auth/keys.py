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


def seed_key_from_env(data_root: Path, user_id: str, service: str) -> None:
    """If MM_OSS_API_KEY is set, make it user_id's API key.

    Lets a Railway variable change rotate the key on redeploy, without editing
    the volume. Also logs which users exist, since the API accepts any user's
    key and an old test user would keep its key working.
    """
    users_dir = Path(data_root) / "users"
    if users_dir.is_dir():
        names = sorted(p.name for p in users_dir.iterdir() if (p / "api_key.hash").exists())
        print(f"[{service}] users with API keys: {', '.join(names) or '(none)'}")

    raw_key = os.environ.get("MM_OSS_API_KEY", "")
    if not raw_key.startswith("mm_sk_"):
        return
    user_dir = users_dir / user_id
    stored = load_key_hash(user_dir)
    if stored and verify_key(raw_key, stored):
        return  # already in sync — bcrypt is slow, don't rewrite every boot
    user_dir.mkdir(parents=True, exist_ok=True)
    save_key_hash(user_dir, bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode("utf-8"))
    print(f"[{service}] API key hash seeded from MM_OSS_API_KEY for user '{user_id}'")
