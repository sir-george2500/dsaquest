"""Locating the content tree.

Content is data, not code, and it ships two different ways: from a git checkout
during development (``<repo>/content``) and from an installed wheel
(``dsaquest/_content``). Everything that reads content goes through here so the
difference is resolved in exactly one place.
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path


class ContentNotFound(RuntimeError):
    pass


@cache
def content_root() -> Path:
    """Return the directory holding ``patterns/``, ``problems/`` and ``templates/``.

    Resolution order:

    1. ``DSAQUEST_CONTENT`` — an explicit override, used by tests and by anyone
       authoring their own pattern set.
    2. ``dsaquest/_content`` — the installed-wheel location.
    3. ``<repo>/content`` — a development checkout.
    """
    override = os.environ.get("DSAQUEST_CONTENT")
    if override:
        path = Path(override).expanduser().resolve()
        if not path.is_dir():
            raise ContentNotFound(f"DSAQUEST_CONTENT points at {path}, which is not a directory")
        return path

    here = Path(__file__).resolve()
    packaged = here.parent.parent / "_content"
    if (packaged / "templates").is_dir():
        return packaged

    # src/dsaquest/content/paths.py -> repo root is four levels up.
    checkout = here.parents[3] / "content"
    if (checkout / "templates").is_dir():
        return checkout

    raise ContentNotFound(
        "Could not locate the content tree. Set DSAQUEST_CONTENT to the directory "
        "containing patterns/, problems/ and templates/."
    )


def templates_dir() -> Path:
    return content_root() / "templates"


def patterns_dir() -> Path:
    return content_root() / "patterns"


def problems_dir() -> Path:
    return content_root() / "problems"


def read_template(name: str) -> str:
    """Read a C++ template by file name, e.g. ``starter.cpp``."""
    path = templates_dir() / name
    if not path.is_file():
        available = sorted(p.name for p in templates_dir().glob("*.cpp"))
        raise ContentNotFound(f"no template {name!r}; available: {', '.join(available)}")
    return path.read_text(encoding="utf-8")


def exercises_file():
    """Sample inputs for Mode C differential judging."""
    return content_root() / "exercises.yaml"
