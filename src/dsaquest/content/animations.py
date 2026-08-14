"""Loading concept animations from ``content/animations/``.

One file per animation, named by its id. Loaded strictly: a broken animation
raises rather than being skipped, because a secret that promises a picture and
silently has none is worse than one that never promised.
"""

from __future__ import annotations

from functools import cache

import yaml

from ..anim.scene import Animation
from ..anim.script import ScriptError, build_animation
from .loader import ContentError
from .paths import content_root


def animations_dir():
    return content_root() / "animations"


@cache
def load_animations() -> dict[str, Animation]:
    directory = animations_dir()
    if not directory.is_dir():
        return {}

    animations: dict[str, Animation] = {}
    problems: list[str] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            problems.append(f"{path.name}: {exc}")
            continue
        if not isinstance(raw, dict):
            problems.append(f"{path.name}: expected a mapping")
            continue
        try:
            animation = build_animation(raw, identifier=path.stem)
        except ScriptError as exc:
            problems += [f"{path.name}: {problem}" for problem in exc.problems]
            continue
        if animation.id in animations:
            problems.append(f"{path.name}: duplicate animation id {animation.id!r}")
            continue
        animations[animation.id] = animation

    if problems:
        raise ContentError(problems)
    return animations


def animation_for(secret_id: str, pattern_id: str = "") -> Animation | None:
    """The animation for a secret, or failing that for its pattern.

    Matching on the pattern as well as the secret decouples the two. An
    animation of BFS is true of BFS however a curriculum happens to carve it
    into secrets, and secret ids are being authored in parallel with the
    animations — requiring an exact secret match would mean an animation is
    either written after its curriculum or silently attached to nothing.
    """
    animations = load_animations().values()
    for animation in animations:
        if secret_id and animation.secret == secret_id:
            return animation
    for animation in animations:
        if pattern_id and animation.pattern == pattern_id:
            return animation
    return None
