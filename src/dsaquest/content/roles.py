"""Which problems are reserved, and for what.

The design names three kinds of problem — training, recognition and mastery —
but nothing in the schema records which a problem is. The kind is entirely
positional: a problem is a trial because a stage lists it, and a master problem
because the final test lists it. That works right up until the same problem is
listed twice.

It matters because of what a final test is *for*. A master's final test decides
whether the pattern is held. If it reuses a problem from that master's own
trials, it measures whether the learner remembers that problem — which is the
exact failure the memorisation detector exists to catch, baked into the gate
that is supposed to detect it.

So this module derives the roles from the curricula and reports where they
collide. Two findings are distinguished, because they need different answers:

* **Reuse** — a problem doing two jobs. Fixable by reassigning ids.
* **Shortfall** — a pattern with fewer problems than its roles need. Not
  fixable by reassignment at all; somebody has to write more problems. Saying
  "reuse" here would send an author round a loop that cannot close.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum


class ProblemRole(StrEnum):
    """What a problem is being used for, derived from where it is listed."""

    RECOGNITION = "trial"
    """A stage's trial. The pattern is hidden and the clock runs."""

    MASTERY = "final test"
    """The master's final test. Nothing is named."""

    HELD_OUT = "held out"
    """Reserved for one boss, and unreachable anywhere else."""


@dataclass(frozen=True, slots=True)
class Use:
    """One job a problem has been given."""

    master_id: str
    role: ProblemRole

    def __str__(self) -> str:
        return f"{self.role.value} ({self.master_id})"


@dataclass(frozen=True, slots=True)
class Reuse:
    """A problem doing more than one job."""

    problem_id: str
    uses: tuple[Use, ...]

    @property
    def same_master(self) -> bool:
        """The serious case: the learner has demonstrably already seen it."""
        return len({use.master_id for use in self.uses}) == 1

    def __str__(self) -> str:
        where = ", ".join(str(use) for use in self.uses)
        if any(use.role is ProblemRole.HELD_OUT for use in self.uses):
            why = "it is held out for a boss and must appear nowhere else"
        elif self.same_master:
            why = "the learner has already seen it under this master"
        else:
            why = "shared between masters"
        return f"{self.problem_id}: used as {where} — {why}"


@dataclass(frozen=True, slots=True)
class Shortfall:
    """A pattern that cannot fill its roles without reuse, however assigned."""

    pattern_id: str
    available: int
    needed: int

    @property
    def missing(self) -> int:
        return self.needed - self.available

    def __str__(self) -> str:
        return (
            f"{self.pattern_id}: {self.needed} distinct problems needed by trials and "
            f"final tests, {self.available} authored — write {self.missing} more"
        )


@dataclass(frozen=True, slots=True)
class RoleReport:
    reuses: tuple[Reuse, ...]
    shortfalls: tuple[Shortfall, ...]
    reserved: frozenset[str]
    unreserved: frozenset[str]

    @property
    def serious(self) -> tuple[Reuse, ...]:
        """Reuse within one master — the case that breaks that master's gate."""
        return tuple(r for r in self.reuses if r.same_master)

    @property
    def ok(self) -> bool:
        return not self.reuses and not self.shortfalls

    def lines(self) -> list[str]:
        out = [str(s) for s in self.shortfalls]
        out += [str(r) for r in self.reuses]
        return out


def uses_by_problem(curricula, bosses=()) -> dict[str, list[Use]]:
    """Every job every problem has been given, keyed by problem id."""
    uses: dict[str, list[Use]] = defaultdict(list)
    for boss in bosses or ():
        for problem_id in getattr(boss, "held_out_problem_ids", ()):
            uses[problem_id].append(Use(boss.id, ProblemRole.HELD_OUT))
    for curriculum in curricula:
        for stage in curriculum.stages:
            for problem_id in stage.trial_problem_ids:
                uses[problem_id].append(Use(curriculum.master_id, ProblemRole.RECOGNITION))
        for problem_id in curriculum.final_test_problem_ids:
            uses[problem_id].append(Use(curriculum.master_id, ProblemRole.MASTERY))
    return dict(uses)


def check_roles(curricula, bank, bosses=()) -> RoleReport:
    """Report every problem serving two roles, and every pattern too thin to avoid it.

    A shortfall suppresses the reuse findings for that pattern. Where there are
    not enough problems to go round, the reuse *is* the shortfall showing up
    downstream, and listing both would report one defect twice.
    """
    uses = uses_by_problem(curricula, bosses)

    #: How many distinct problems each pattern's roles ask for.
    demand: dict[str, int] = defaultdict(int)
    for problem_id, jobs in uses.items():
        problem = _problem(bank, problem_id)
        if problem is not None:
            demand[problem.pattern] += len(jobs)

    shortfalls: list[Shortfall] = []
    thin: set[str] = set()
    for pattern_id, needed in sorted(demand.items()):
        available = len(bank.for_pattern(pattern_id))
        if needed > available:
            shortfalls.append(Shortfall(pattern_id, available, needed))
            thin.add(pattern_id)

    reuses: list[Reuse] = []
    for problem_id, jobs in sorted(uses.items()):
        if len(jobs) < 2:
            continue
        held_out = any(use.role is ProblemRole.HELD_OUT for use in jobs)
        problem = _problem(bank, problem_id)
        # A shortfall explains ordinary reuse and suppresses it. It does not
        # explain taking the one thing reserved for the final boss: that is a
        # different defect with a different fix, and "write more problems" is
        # not the answer to it.
        if not held_out and problem is not None and problem.pattern in thin:
            continue
        reuses.append(Reuse(problem_id, tuple(jobs)))

    everything = frozenset(p.id for p in bank)
    reserved = frozenset(uses)
    return RoleReport(
        reuses=tuple(reuses),
        shortfalls=tuple(shortfalls),
        reserved=reserved,
        unreserved=everything - reserved,
    )


def _problem(bank, problem_id: str):
    try:
        return bank[problem_id]
    except (KeyError, LookupError):
        return None
