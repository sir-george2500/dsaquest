"""Sample inputs for Mode C.

Deliberately inputs only — no expected outputs. The intact template is the
oracle, so the answer key is derived rather than authored and cannot drift out
of agreement with the code it is checking.
"""

from __future__ import annotations

from functools import cache

import yaml

from .loader import ContentError
from .paths import exercises_file


@cache
def sample_inputs() -> dict[str, tuple[str, ...]]:
    path = exercises_file()
    if not path.is_file():
        raise ContentError([f"missing {path}"])
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ContentError([f"{path.name}: expected a mapping of template name to inputs"])
    return {name: tuple(values) for name, values in raw.items()}


def samples_for(template_file: str) -> tuple[str, ...]:
    """Sample stdin strings for one template.

    Raises rather than returning an empty tuple: differential judging with no
    inputs would silently accept any answer at all.
    """
    found = sample_inputs().get(template_file)
    if not found:
        known = ", ".join(sorted(sample_inputs())) or "none"
        raise ContentError(
            [f"no sample inputs for template {template_file!r}; known templates: {known}"]
        )
    return found
