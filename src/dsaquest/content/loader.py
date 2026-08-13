"""Loading and validating the pattern library.

Pydantic validates each file in isolation. The checks that matter for a
*learning* system are cross-file, and they live here: a confusion that points at
a pattern which does not exist silently degrades Pattern Hunter's distractors,
and a prerequisite cycle makes a world permanently unreachable. Both are
invisible at runtime and obvious at load time, so we fail at load time.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import yaml
from pydantic import ValidationError

from ..domain.pattern import Pattern
from .paths import content_root, patterns_dir, templates_dir


class ContentError(RuntimeError):
    """Raised when the content tree is internally inconsistent."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        joined = "\n  - ".join(problems)
        super().__init__(f"content validation failed ({len(problems)} problem(s)):\n  - {joined}")


# NB: no slots=True — cached_property needs a __dict__ to memoise into.
@dataclass(frozen=True)
class PatternLibrary:
    """An immutable, validated view of ``content/patterns``."""

    patterns: dict[str, Pattern]

    def __getitem__(self, pattern_id: str) -> Pattern:
        try:
            return self.patterns[pattern_id]
        except KeyError:
            raise KeyError(f"unknown pattern {pattern_id!r}") from None

    def __contains__(self, pattern_id: object) -> bool:
        return pattern_id in self.patterns

    def __len__(self) -> int:
        return len(self.patterns)

    def __iter__(self):
        return iter(self.ordered)

    @cached_property
    def ordered(self) -> tuple[Pattern, ...]:
        """Every pattern in campaign order: by world, then by position within it."""
        return tuple(sorted(self.patterns.values(), key=lambda p: (p.world, p.order, p.id)))

    @cached_property
    def worlds(self) -> dict[int, tuple[Pattern, ...]]:
        grouped: dict[int, list[Pattern]] = {}
        for pattern in self.ordered:
            grouped.setdefault(pattern.world, []).append(pattern)
        return {world: tuple(items) for world, items in sorted(grouped.items())}

    def confusable_ids(self, pattern_id: str) -> tuple[str, ...]:
        """Patterns this one is mistaken for — the distractor pool for Mode A."""
        return tuple(c.pattern_id for c in self[pattern_id].confusable_with)

    def dependents(self, pattern_id: str) -> tuple[str, ...]:
        """Patterns that list ``pattern_id`` as a prerequisite."""
        return tuple(p.id for p in self.ordered if pattern_id in p.prerequisites)


def load_pattern_file(path) -> Pattern:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ContentError([f"{path.name}: expected a YAML mapping at the top level"])
    try:
        return Pattern.model_validate(raw)
    except ValidationError as exc:
        details = [
            f"{path.name}: {'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        ]
        raise ContentError(details) from None


def load_library(*, strict: bool = True) -> PatternLibrary:
    """Load every pattern YAML and cross-validate the graph.

    ``strict=False`` skips the cross-file checks, which is only useful while
    authoring a pattern whose neighbours do not exist yet.
    """
    directory = patterns_dir()
    files = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
    if not files:
        raise ContentError([f"no pattern files found in {directory}"])

    problems: list[str] = []
    patterns: dict[str, Pattern] = {}

    for path in files:
        try:
            pattern = load_pattern_file(path)
        except ContentError as exc:
            problems.extend(exc.problems)
            continue
        if pattern.id in patterns:
            problems.append(f"{path.name}: duplicate pattern id {pattern.id!r}")
            continue
        if path.stem != pattern.id:
            problems.append(
                f"{path.name}: file name must match pattern id {pattern.id!r} "
                f"(expected {pattern.id}.yaml)"
            )
        patterns[pattern.id] = pattern

    if strict:
        problems.extend(_cross_validate(patterns))

    if problems:
        raise ContentError(problems)

    return PatternLibrary(patterns=patterns)


def _cross_validate(patterns: dict[str, Pattern]) -> list[str]:
    problems: list[str] = []
    known = set(patterns)
    templates = templates_dir()

    def check_refs(pattern: Pattern, field: str, ids: tuple[str, ...]) -> None:
        for ref in ids:
            if ref == pattern.id:
                problems.append(f"{pattern.id}: {field} refers to itself")
            elif ref not in known:
                problems.append(f"{pattern.id}: {field} refers to unknown pattern {ref!r}")

    seen_slots: dict[tuple[int, int], str] = {}

    for pattern in patterns.values():
        check_refs(pattern, "prerequisites", pattern.prerequisites)
        check_refs(pattern, "related", pattern.related)
        check_refs(pattern, "confusable_with", tuple(c.pattern_id for c in pattern.confusable_with))
        check_refs(pattern, "anti_signals.instead", tuple(a.instead for a in pattern.anti_signals))

        if not (templates / pattern.template_file).is_file():
            problems.append(
                f"{pattern.id}: template_file {pattern.template_file!r} not found in {templates}"
            )

        slot = (pattern.world, pattern.order)
        if slot in seen_slots:
            problems.append(
                f"{pattern.id}: world {pattern.world} order {pattern.order} "
                f"already taken by {seen_slots[slot]!r}"
            )
        else:
            seen_slots[slot] = pattern.id

        # A confusion must be mutual to be useful. If A is mistaken for B, then a
        # learner seeing B needs the discriminator too - and Duel pairs both ways.
        for confusion in pattern.confusable_with:
            other = patterns.get(confusion.pattern_id)
            if other is not None and other.confusion_with(pattern.id) is None:
                problems.append(
                    f"{pattern.id}: confusable_with {confusion.pattern_id!r} is not reciprocated "
                    f"(add a confusable_with entry for {pattern.id!r} to {other.id})"
                )

    problems.extend(_find_prerequisite_cycles(patterns))
    return problems


def _find_prerequisite_cycles(patterns: dict[str, Pattern]) -> list[str]:
    """Depth-first cycle detection over the prerequisite DAG."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(patterns, WHITE)
    problems: list[str] = []

    def visit(node: str, trail: list[str]) -> None:
        colour[node] = GREY
        for prereq in patterns[node].prerequisites:
            if prereq not in patterns:
                continue  # already reported as an unknown reference
            if colour[prereq] == GREY:
                cycle = " -> ".join([*trail, node, prereq])
                problems.append(f"prerequisite cycle: {cycle}")
            elif colour[prereq] == WHITE:
                visit(prereq, [*trail, node])
        colour[node] = BLACK

    for node in patterns:
        if colour[node] == WHITE:
            visit(node, [])
    return problems


def describe_content_root() -> str:
    return str(content_root())
