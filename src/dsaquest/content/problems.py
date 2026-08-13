"""Loading the problem bank.

One YAML file per pattern, each a list of problems. Cross-checks that matter
for a recognition trainer live here rather than in pydantic, because they are
about the relationship between a problem and the pattern library:

* a statement that names its own pattern is worthless for recognition;
* a problem pointing at a pattern that does not exist is unplayable;
* a hint ladder that reveals the pattern on rung one is not a ladder.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import yaml

from ..domain.enums import Difficulty
from ..domain.problem import Problem
from .loader import ContentError, PatternLibrary
from .paths import problems_dir


# NB: no slots=True — cached_property needs a __dict__.
@dataclass(frozen=True)
class ProblemBank:
    problems: dict[str, Problem]

    def __getitem__(self, problem_id: str) -> Problem:
        try:
            return self.problems[problem_id]
        except KeyError:
            raise KeyError(f"unknown problem {problem_id!r}") from None

    def __len__(self) -> int:
        return len(self.problems)

    def __iter__(self):
        return iter(self.ordered)

    @cached_property
    def ordered(self) -> tuple[Problem, ...]:
        return tuple(
            sorted(self.problems.values(), key=lambda p: (p.pattern, p.difficulty.rank, p.id))
        )

    @cached_property
    def by_pattern(self) -> dict[str, tuple[Problem, ...]]:
        grouped: dict[str, list[Problem]] = {}
        for problem in self.ordered:
            grouped.setdefault(problem.pattern, []).append(problem)
        return {pattern: tuple(items) for pattern, items in grouped.items()}

    def for_pattern(
        self, pattern_id: str, *, difficulty: Difficulty | None = None
    ) -> tuple[Problem, ...]:
        found = self.by_pattern.get(pattern_id, ())
        if difficulty is None:
            return found
        return tuple(p for p in found if p.difficulty is difficulty)

    def patterns_with_problems(self) -> frozenset[str]:
        return frozenset(self.by_pattern)


def load_problems(library: PatternLibrary, *, strict: bool = True) -> ProblemBank:
    directory = problems_dir()
    files = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))

    problems: dict[str, Problem] = {}
    complaints: list[str] = []

    for path in files:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if raw is None:
            continue
        if not isinstance(raw, list):
            complaints.append(f"{path.name}: expected a YAML list of problems")
            continue

        for index, entry in enumerate(raw):
            try:
                problem = Problem.model_validate(entry)
            except Exception as exc:  # pydantic ValidationError
                complaints.append(f"{path.name}[{index}]: {exc}")
                continue

            if problem.id in problems:
                complaints.append(f"{path.name}: duplicate problem id {problem.id!r}")
                continue
            if path.stem != problem.pattern:
                complaints.append(
                    f"{path.name}: problem {problem.id!r} declares pattern "
                    f"{problem.pattern!r}; file name must match the pattern"
                )
            problems[problem.id] = problem

    if strict:
        complaints.extend(_cross_validate(problems, library))

    if complaints:
        raise ContentError(complaints)

    return ProblemBank(problems=problems)


def _cross_validate(problems: dict[str, Problem], library: PatternLibrary) -> list[str]:
    complaints: list[str] = []

    for problem in problems.values():
        if problem.pattern not in library:
            complaints.append(f"{problem.id}: unknown pattern {problem.pattern!r}")
            continue

        if problem.names_pattern:
            complaints.append(
                f"{problem.id}: the statement contains its own pattern name — "
                f"nothing is being recognised"
            )

        if problem.hints:
            early = [i for i, hint in enumerate(problem.hints[:-1]) if hint.reveals_pattern]
            if early:
                complaints.append(
                    f"{problem.id}: hint {early[0] + 1} reveals the pattern before the last rung"
                )

        # Distractors are drawn from the confusion graph, so a pattern with no
        # confusions cannot produce a Hunter round worth playing.
        pattern = library[problem.pattern]
        if not pattern.confusable_with:
            complaints.append(
                f"{problem.id}: pattern {pattern.id!r} has no confusions to draw distractors from"
            )

    return complaints
