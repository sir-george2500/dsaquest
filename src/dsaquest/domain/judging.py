"""Types exchanged with the judge.

These live in ``domain`` so that the game, learning and UI layers can talk about
verdicts without importing the sandbox — which drags in subprocess handling and
is Linux-specific. Tests for the scheduler construct these directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .enums import Verdict


class CheckerKind(StrEnum):
    """How a submission's stdout is compared against the expected output."""

    TOKENS = "tokens"
    """Whitespace-insensitive token equality. The sane default for CP."""

    EXACT = "exact"
    """Byte-exact after stripping one trailing newline. For formatting exercises."""

    FLOAT = "float"
    """Token-wise numeric comparison within ``epsilon``."""

    UNORDERED_LINES = "unordered_lines"
    """Lines must match as a multiset. For 'print any valid ordering' problems."""

    SPECIAL = "special"
    """Multiple valid answers: a per-problem C++ validator decides. Phase 3."""


@dataclass(frozen=True, slots=True)
class Limits:
    """Resource envelope for one execution.

    Defaults mirror a typical Codeforces/LeetCode budget. ``wall_ms`` is
    deliberately larger than ``cpu_ms``: a program that blocks on I/O or sleeps
    burns wall time without burning CPU, and we must still kill it.
    """

    cpu_ms: int = 2000
    wall_ms: int = 5000
    memory_mb: int = 256
    output_kb: int = 8192
    """Cap on captured stdout/stderr. Exceeding it is an Output Limit verdict."""
    file_size_kb: int = 16384
    """RLIMIT_FSIZE — the largest *file* the process may write.

    Deliberately separate from ``output_kb``: stdout is a pipe, which RLIMIT_FSIZE
    does not govern, while compilation must write a multi-megabyte binary. Sharing
    one number between the two makes the linker fail with 'File too large'.
    """
    max_pids: int = 64
    stack_mb: int = 64
    """Recursion-heavy patterns (tree DFS) need more than the 8 MB default."""

    def __post_init__(self) -> None:
        if self.wall_ms <= self.cpu_ms:
            raise ValueError("wall_ms must exceed cpu_ms so blocked processes are still killed")
        if self.memory_mb < 16:
            raise ValueError("memory_mb below 16 cannot even start a libstdc++ binary")
        if self.stack_mb > self.memory_mb:
            raise ValueError("stack_mb cannot exceed memory_mb")


@dataclass(frozen=True, slots=True)
class TestCase:
    __test__ = False  # this is judge input, not a pytest class

    name: str
    stdin: str
    expected: str
    hidden: bool = False
    """Hidden tests are judged but their input is not shown on failure.

    They exist to stop pattern-matching against the samples, but we still reveal
    a *characterisation* ('n=200000, all distinct') because a verdict with no
    diagnostic teaches nothing.
    """
    characterisation: str = ""
    limits: Limits | None = None
    """Per-test override; ``None`` means use the problem's limits."""


@dataclass(frozen=True, slots=True)
class CompileResult:
    ok: bool
    binary_path: str | None
    log: str
    duration_ms: int
    command: tuple[str, ...] = ()

    @property
    def verdict(self) -> Verdict | None:
        return None if self.ok else Verdict.COMPILE_ERROR


@dataclass(frozen=True, slots=True)
class TestOutcome:
    name: str
    verdict: Verdict
    cpu_ms: int
    wall_ms: int
    memory_kb: int
    exit_code: int | None = None
    signal: int | None = None
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    diff_hint: str = ""
    """Human-readable first divergence, e.g. 'token 3: expected 7, got 6'."""
    hidden: bool = False
    characterisation: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict.is_pass


@dataclass(frozen=True, slots=True)
class JudgeReport:
    """The full result of judging one submission against one test set."""

    verdict: Verdict
    outcomes: tuple[TestOutcome, ...] = ()
    compile_log: str = ""
    compile_ms: int = 0
    message: str = ""
    """Set for CE/IE, where there are no per-test outcomes to explain the result."""

    @property
    def passed(self) -> int:
        return sum(1 for o in self.outcomes if o.passed)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def accepted(self) -> bool:
        return self.verdict.is_pass

    @property
    def max_cpu_ms(self) -> int:
        return max((o.cpu_ms for o in self.outcomes), default=0)

    @property
    def max_memory_kb(self) -> int:
        return max((o.memory_kb for o in self.outcomes), default=0)

    @property
    def first_failure(self) -> TestOutcome | None:
        return next((o for o in self.outcomes if not o.passed), None)

    @classmethod
    def compile_error(cls, log: str, duration_ms: int = 0) -> JudgeReport:
        return cls(
            verdict=Verdict.COMPILE_ERROR,
            compile_log=log,
            compile_ms=duration_ms,
            message="Compilation failed",
        )

    @classmethod
    def internal_error(cls, message: str) -> JudgeReport:
        """A judge/sandbox failure. Never attributed to the submitter."""
        return cls(verdict=Verdict.INTERNAL_ERROR, message=message)


@dataclass(frozen=True, slots=True)
class Submission:
    """What the user hands to the judge."""

    source: str
    language_standard: str = "c++20"
    extra_flags: tuple[str, ...] = field(default=())
