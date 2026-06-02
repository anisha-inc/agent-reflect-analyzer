"""Stable per-developer + per-repo hashes matching the bash shipper.

Mirrors ship.sh:38-51 — sha256 of git user.email and origin URL, truncated to
16 hex chars (~64 bits). Identical inputs → identical outputs; fallback to
realpath of cwd if origin remote is absent.
"""

from __future__ import annotations

import hashlib
import os
import pathlib

from .subprocess_util import run_external


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def dev_id() -> str:
    email = run_external(["git", "config", "user.email"], timeout=5, env={**os.environ}).strip()
    if not email:
        raise RuntimeError("git config user.email is empty")
    return _sha16(email)


def proj_id() -> str:
    try:
        url = run_external(
            ["git", "remote", "get-url", "origin"], timeout=5, env={**os.environ}
        ).strip()
        if url:
            return _sha16(url)
    except RuntimeError:
        pass
    return _sha16(str(pathlib.Path(os.getcwd()).resolve()))
