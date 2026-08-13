"""Judge orchestration: compile once, run every test, produce a report."""

from __future__ import annotations

import signal
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path

from ..domain.enums import Verdict
from ..domain.judging import (
    CheckerKind,
    JudgeReport,
    Limits,
    Submission,
    TestCase,
    TestOutcome,
)
from .checker import check
from .compiler import BINARY_NAME, SANDBOX_WORK, compile_submission
from .sandbox import SandboxResult, run_sandboxed

#: How much of a stream to keep for display. Enough to show a stack trace or the
#: start of a wrong answer, small enough never to flood the terminal.
_EXCERPT_CHARS = 2000

ProgressHook = Callable[[TestOutcome], None]


def judge(
    submission: Submission,
    tests: Iterable[TestCase],
    *,
    limits: Limits | None = None,
    checker: CheckerKind = CheckerKind.TOKENS,
    epsilon: float = 1e-6,
    stop_on_first_failure: bool = False,
    on_result: ProgressHook | None = None,
    workdir: Path | None = None,
) -> JudgeReport:
    """Compile and run ``submission`` against ``tests``.

    ``stop_on_first_failure`` is off by default: seeing that you failed 1 of 20
    tests is very different feedback from failing 18 of 20, and that difference
    is exactly what tells you whether the bug is an edge case or the approach.
    """
    limits = limits or Limits()
    tests = list(tests)

    if workdir is not None:
        workdir.mkdir(parents=True, exist_ok=True)
        return _judge_in(
            workdir, submission, tests, limits, checker, epsilon, stop_on_first_failure, on_result
        )

    with tempfile.TemporaryDirectory(prefix="dsaq-judge-") as tmp:
        return _judge_in(
            Path(tmp),
            submission,
            tests,
            limits,
            checker,
            epsilon,
            stop_on_first_failure,
            on_result,
        )


def _judge_in(
    workdir: Path,
    submission: Submission,
    tests: list[TestCase],
    limits: Limits,
    checker: CheckerKind,
    epsilon: float,
    stop_on_first_failure: bool,
    on_result: ProgressHook | None,
) -> JudgeReport:
    build = compile_submission(submission, workdir)
    if not build.ok:
        return JudgeReport.compile_error(build.log, build.duration_ms)

    outcomes: list[TestOutcome] = []
    for case in tests:
        outcome = _run_one(workdir, case, case.limits or limits, checker, epsilon)
        outcomes.append(outcome)
        if on_result is not None:
            on_result(outcome)
        if stop_on_first_failure and not outcome.passed:
            break

    verdict = _aggregate(outcomes)
    return JudgeReport(
        verdict=verdict,
        outcomes=tuple(outcomes),
        compile_log=build.log,
        compile_ms=build.duration_ms,
    )


def _run_one(
    workdir: Path,
    case: TestCase,
    limits: Limits,
    checker: CheckerKind,
    epsilon: float,
) -> TestOutcome:
    result = run_sandboxed(
        [f"{SANDBOX_WORK}/{BINARY_NAME}"],
        limits=limits,
        # Read-only: a solution has no business writing to its own directory,
        # and mounting it read-only turns "accidentally opened a file" into a
        # clean runtime error instead of a corrupted workspace.
        binds=[(str(workdir), SANDBOX_WORK, False)],
        chdir=SANDBOX_WORK,
        stdin_data=case.stdin.encode(),
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )

    verdict, hint = _classify(result, case, limits, checker, epsilon)

    return TestOutcome(
        name=case.name,
        verdict=verdict,
        cpu_ms=result.cpu_ms,
        wall_ms=result.wall_ms,
        memory_kb=result.max_rss_kb,
        exit_code=result.exit_code,
        signal=result.signal,
        stdout_excerpt=_excerpt(result.stdout),
        stderr_excerpt=_excerpt(result.stderr),
        diff_hint=hint,
        hidden=case.hidden,
        characterisation=case.characterisation,
    )


def _classify(
    result: SandboxResult,
    case: TestCase,
    limits: Limits,
    checker: CheckerKind,
    epsilon: float,
) -> tuple[Verdict, str]:
    """Map a raw sandbox result to a verdict.

    Order matters, and the ordering is driven by which evidence is strongest.
    A program that exhausts memory often *also* exhausts time while thrashing,
    so the unambiguous signals are consulted first: the wall-clock deadline we
    measured ourselves, then SIGXCPU (which only the CPU rlimit produces), then
    the cgroup's oom_kill counter. Only after those do we fall back to weaker
    inference.
    """
    if result.timed_out:
        return Verdict.TIME_LIMIT, f"exceeded {limits.wall_ms} ms wall clock"

    if result.cpu_exhausted:
        return Verdict.TIME_LIMIT, f"exceeded the {limits.cpu_ms} ms CPU budget"

    if result.oom_killed:
        return Verdict.MEMORY_LIMIT, f"exceeded {limits.memory_mb} MB"

    if result.output_truncated:
        return Verdict.OUTPUT_LIMIT, f"produced more than {limits.output_kb} KB of output"

    if result.looks_like_oom:
        return Verdict.MEMORY_LIMIT, f"exceeded {limits.memory_mb} MB"

    if result.cpu_ms > limits.cpu_ms:
        return Verdict.TIME_LIMIT, f"used {result.cpu_ms} ms CPU, limit {limits.cpu_ms} ms"

    if result.signal is not None:
        return Verdict.RUNTIME_ERROR, _signal_hint(result.signal)

    if result.exit_code not in (0, None):
        return Verdict.RUNTIME_ERROR, f"exited with status {result.exit_code}"

    verdict_check = check(
        result.stdout.decode("utf-8", "replace"),
        case.expected,
        checker,
        epsilon=epsilon,
    )
    if verdict_check.matched:
        return Verdict.ACCEPTED, ""
    return Verdict.WRONG_ANSWER, verdict_check.hint


def _signal_hint(sig: int) -> str:
    """Translate a fatal signal into the bug that usually causes it."""
    hints = {
        signal.SIGSEGV: (
            "segmentation fault — out-of-bounds index, null/dangling pointer, "
            "or runaway recursion overflowing the stack"
        ),
        signal.SIGABRT: ("aborted — an uncaught exception, a failed assert, or std::bad_alloc"),
        signal.SIGFPE: "arithmetic error — integer division or modulo by zero",
        signal.SIGILL: (
            "illegal instruction — almost always undefined behaviour that -O2 "
            "compiled into a trap (signed overflow, division by a provable zero, "
            "or a missing return from a non-void function)"
        ),
        signal.SIGBUS: "bus error — misaligned or invalid memory access",
        signal.SIGKILL: "killed by the sandbox — most likely memory exhaustion",
    }
    try:
        name = signal.Signals(sig).name
    except ValueError:  # pragma: no cover
        name = f"signal {sig}"
    return hints.get(sig, f"terminated by {name}")


def _aggregate(outcomes: list[TestOutcome]) -> Verdict:
    """Report the *first* failure's verdict, not the most severe.

    Tests are ordered from smallest to largest, so the first failure is the
    simplest reproducing case — the one worth debugging first.
    """
    if not outcomes:
        return Verdict.INTERNAL_ERROR
    for outcome in outcomes:
        if not outcome.passed:
            return outcome.verdict
    return Verdict.ACCEPTED


def _excerpt(raw: bytes) -> str:
    text = raw.decode("utf-8", "replace")
    if len(text) <= _EXCERPT_CHARS:
        return text
    return text[:_EXCERPT_CHARS] + f"\n… [{len(text) - _EXCERPT_CHARS} more characters]"
