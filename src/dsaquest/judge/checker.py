"""Output comparison.

A verdict with no diagnostic teaches nothing, so every mismatch produces a
``diff_hint`` naming the first divergence. "Wrong Answer" sends you back to
re-read your code; "token 3: expected 7, got 6" sends you to the bug.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..domain.judging import CheckerKind

#: Long tokens are elided in hints so a hint never becomes a wall of text.
_MAX_TOKEN_ECHO = 40


@dataclass(frozen=True, slots=True)
class CheckResult:
    matched: bool
    hint: str = ""


def check(
    actual: str,
    expected: str,
    kind: CheckerKind = CheckerKind.TOKENS,
    *,
    epsilon: float = 1e-6,
) -> CheckResult:
    match kind:
        case CheckerKind.TOKENS:
            return _check_tokens(actual, expected)
        case CheckerKind.EXACT:
            return _check_exact(actual, expected)
        case CheckerKind.FLOAT:
            return _check_float(actual, expected, epsilon)
        case CheckerKind.UNORDERED_LINES:
            return _check_unordered(actual, expected)
        case CheckerKind.SPECIAL:  # pragma: no cover - Phase 3
            raise NotImplementedError("special judges arrive with Boss Fights")
    raise ValueError(f"unknown checker kind: {kind}")


def _elide(token: str) -> str:
    return token if len(token) <= _MAX_TOKEN_ECHO else token[:_MAX_TOKEN_ECHO] + "…"


def _check_tokens(actual: str, expected: str) -> CheckResult:
    a, e = actual.split(), expected.split()
    # strict=False is deliberate throughout this module: a length mismatch is a
    # *result* we report specifically ("output ended early"), not an exception.
    for i, (got, want) in enumerate(zip(a, e, strict=False), start=1):
        if got != want:
            return CheckResult(False, f"token {i}: expected {_elide(want)}, got {_elide(got)}")
    if len(a) == len(e):
        return CheckResult(True)
    if len(a) < len(e):
        return CheckResult(
            False,
            f"output ended early: expected {len(e)} tokens, got {len(a)} "
            f"(next expected: {_elide(e[len(a)])})",
        )
    return CheckResult(
        False,
        f"too much output: expected {len(e)} tokens, got {len(a)} "
        f"(first extra: {_elide(a[len(e)])})",
    )


def _check_exact(actual: str, expected: str) -> CheckResult:
    a, e = actual.rstrip("\n"), expected.rstrip("\n")
    if a == e:
        return CheckResult(True)
    a_lines, e_lines = a.splitlines(), e.splitlines()
    for i, (got, want) in enumerate(zip(a_lines, e_lines, strict=False), start=1):
        if got != want:
            col = next(
                (c for c, (x, y) in enumerate(zip(got, want, strict=False), start=1) if x != y),
                min(len(got), len(want)) + 1,
            )
            return CheckResult(False, f"line {i}, column {col}: expected {want!r}, got {got!r}")
    return CheckResult(False, f"expected {len(e_lines)} lines, got {len(a_lines)}")


def _check_float(actual: str, expected: str, epsilon: float) -> CheckResult:
    a, e = actual.split(), expected.split()
    if len(a) != len(e):
        return CheckResult(False, f"expected {len(e)} numbers, got {len(a)}")
    for i, (got, want) in enumerate(zip(a, e, strict=False), start=1):
        try:
            gv, wv = float(got), float(want)
        except ValueError:
            if got != want:
                return CheckResult(False, f"token {i}: expected {_elide(want)}, got {_elide(got)}")
            continue
        if abs(gv - wv) > epsilon * max(1.0, abs(wv)):
            return CheckResult(
                False, f"token {i}: expected {want}, got {got} (delta {abs(gv - wv):.3g})"
            )
    return CheckResult(True)


def _check_unordered(actual: str, expected: str) -> CheckResult:
    a = Counter(line.strip() for line in actual.splitlines() if line.strip())
    e = Counter(line.strip() for line in expected.splitlines() if line.strip())
    if a == e:
        return CheckResult(True)
    missing = e - a
    extra = a - e
    parts = []
    if missing:
        parts.append(
            f"missing {sum(missing.values())} line(s), e.g. {_elide(next(iter(missing)))!r}"
        )
    if extra:
        parts.append(
            f"unexpected {sum(extra.values())} line(s), e.g. {_elide(next(iter(extra)))!r}"
        )
    return CheckResult(False, "; ".join(parts))
