"""Sample inputs for Mode C.

Deliberately inputs only — no expected outputs. The intact template is the
oracle, so the answer key is derived rather than authored and cannot drift out
of agreement with the code it is checking.

Read from ``exercises.yaml`` and from every ``exercises/*.yaml``. The directory
exists because one shared file cannot be written by several authors at once —
two agents appending to it at the same moment lose one of the two edits, which
is a silent failure that surfaces much later as "no sample inputs for template".
A template defined in both places is an error rather than a merge: whichever
won would be arbitrary.
"""

from __future__ import annotations

from functools import cache

import yaml

from .loader import ContentError
from .paths import exercises_dir, exercises_file


@cache
def sample_inputs() -> dict[str, tuple[str, ...]]:
    root = exercises_file()
    directory = exercises_dir()
    paths = [root] if root.is_file() else []
    paths += sorted(directory.glob("*.yaml")) if directory.is_dir() else []
    if not paths:
        raise ContentError([f"missing {root} and {directory}/*.yaml"])

    merged: dict[str, tuple[str, ...]] = {}
    owner: dict[str, str] = {}
    problems: list[str] = []
    for path in paths:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            problems.append(f"{path.name}: expected a mapping of template name to inputs")
            continue
        for name, values in raw.items():
            if name in merged:
                problems.append(
                    f"{path.name}: template {name!r} already has samples in {owner[name]}"
                )
                continue
            merged[name] = tuple(values)
            owner[name] = path.name
    if problems:
        raise ContentError(problems)
    return merged


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
