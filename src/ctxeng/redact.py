"""Stable pseudonyms so analysis output can leave the machine it was produced on.

Aliases are a salted hash of the real identifier. The salt is generated once and kept outside
the repository (``CTXENG_HOME``, default ``~/.ctxeng``), so aliases are consistent across runs
on one machine but cannot be reversed by anyone reading a published report.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path

from .patterns import scrub

__all__ = ["alias", "project_alias", "session_alias", "scrub", "home_dir"]


def home_dir() -> Path:
    return Path(os.environ.get("CTXENG_HOME", "~/.ctxeng")).expanduser()


_SALT: str | None = None


def _salt() -> str:
    global _SALT
    if _SALT is None:
        path = home_dir() / "salt"
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(secrets.token_hex(16), encoding="utf-8")
        _SALT = path.read_text(encoding="utf-8").strip()
    return _SALT


def alias(kind: str, value: str, length: int = 6) -> str:
    digest = hashlib.sha256(f"{_salt()}|{kind}|{value}".encode("utf-8")).hexdigest()
    return f"{kind}-{digest[:length]}"


def project_alias(slug: str) -> str:
    return alias("project", slug)


def session_alias(session_id: str) -> str:
    return alias("session", session_id)
