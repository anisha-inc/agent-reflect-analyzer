"""Small shared helpers with no heavy dependencies."""

from __future__ import annotations


def parse_owner(repo: str) -> str:
    """Return the owner segment of an ``owner/name`` repository slug.

    >>> parse_owner("octo-org/octo-repo")
    'octo-org'
    """
    owner = repo.split("/", 1)[0].strip()
    if not owner:
        raise ValueError(f"cannot parse owner from repo slug {repo!r}")
    return owner
