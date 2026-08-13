"""Mode C — Code Completion.

Cut the load-bearing lines out of a canonical template and ask the learner to
write them back. The holes are marked inline in the template itself::

    // >>> HOLE id=shrink prompt=Restore the invariant after admitting a[r]
            while ((int)freq.size() > k) {
                if (--freq[a[l]] == 0) freq.erase(a[l]);
                ++l;
            }
    // <<< HOLE

Markers are comments, so the template remains a single source of truth: it
still compiles, still runs, and is still the thing shown in the pattern codex.
There is no parallel "exercise" copy to drift out of sync.

Differential judging
--------------------
The intact template *is* the oracle. We compile it, run it on each sample
input, and use its output as the expected output for the learner's version.
That means a hole can be added, moved or resized without anyone authoring or
maintaining expected outputs — and the answer key can never disagree with the
template, because it is derived from it.

If the reference itself fails, that is a content bug and is reported as a judge
error. It is never charged to the learner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ...domain.enums import Verdict
from ...domain.judging import CheckerKind, JudgeReport, Limits, Submission, TestCase
from ...judge.compiler import BINARY_NAME, SANDBOX_WORK, compile_submission
from ...judge.sandbox import run_sandboxed
from ...judge.service import judge

_OPEN = re.compile(r"^(?P<indent>\s*)//\s*>>>\s*HOLE\s+id=(?P<id>\S+)\s+prompt=(?P<prompt>.*)$")
_CLOSE = re.compile(r"^\s*//\s*<<<\s*HOLE\s*$")

#: Placeholder left in the learner's buffer where the hole was.
TODO_MARKER = "// TODO: "


class TemplateError(RuntimeError):
    """The template's hole markers are malformed. A content bug, not a user error."""


@dataclass(frozen=True, slots=True)
class Hole:
    id: str
    prompt: str
    indent: str
    open_line: int
    close_line: int
    body: str
    """The removed lines, verbatim — the reference answer."""

    @property
    def line_count(self) -> int:
        return self.close_line - self.open_line - 1


def parse_holes(source: str) -> tuple[Hole, ...]:
    lines = source.splitlines()
    holes: list[Hole] = []
    pending: tuple[int, re.Match[str]] | None = None

    for index, line in enumerate(lines):
        opened = _OPEN.match(line)
        if opened:
            if pending is not None:
                raise TemplateError(
                    f"line {index + 1}: hole {opened['id']!r} opens while "
                    f"{pending[1]['id']!r} is still open"
                )
            pending = (index, opened)
            continue

        if _CLOSE.match(line):
            if pending is None:
                raise TemplateError(f"line {index + 1}: hole closed without being opened")
            open_index, match = pending
            holes.append(
                Hole(
                    id=match["id"],
                    prompt=match["prompt"].strip(),
                    indent=match["indent"],
                    open_line=open_index,
                    close_line=index,
                    body="\n".join(lines[open_index + 1 : index]),
                )
            )
            pending = None

    if pending is not None:
        raise TemplateError(f"hole {pending[1]['id']!r} is never closed")

    seen = [h.id for h in holes]
    duplicates = {h for h in seen if seen.count(h) > 1}
    if duplicates:
        raise TemplateError(f"duplicate hole ids: {', '.join(sorted(duplicates))}")

    return tuple(holes)


def find_hole(source: str, hole_id: str) -> Hole:
    for hole in parse_holes(source):
        if hole.id == hole_id:
            return hole
    available = ", ".join(h.id for h in parse_holes(source)) or "none"
    raise TemplateError(f"no hole {hole_id!r}; available: {available}")


def reference_source(source: str) -> str:
    """The template with markers removed and all code intact — the oracle."""
    return "\n".join(
        line for line in source.splitlines() if not (_OPEN.match(line) or _CLOSE.match(line))
    )


def exercise_source(source: str, hole_id: str) -> str:
    """The template with one hole emptied, ready to hand to the learner."""
    hole = find_hole(source, hole_id)
    lines = source.splitlines()
    out: list[str] = []

    for index, line in enumerate(lines):
        if hole.open_line < index < hole.close_line:
            continue
        if index == hole.open_line:
            out.append(f"{hole.indent}{TODO_MARKER}{hole.prompt}")
            continue
        if index == hole.close_line:
            continue
        if _OPEN.match(line) or _CLOSE.match(line):
            continue  # other holes stay filled in
        out.append(line)

    return "\n".join(out)


def splice(source: str, hole_id: str, answer: str) -> str:
    """Put the learner's code back where the hole was."""
    hole = find_hole(source, hole_id)
    lines = source.splitlines()
    out: list[str] = []

    for index, line in enumerate(lines):
        if hole.open_line < index < hole.close_line:
            continue
        if index == hole.open_line:
            out.extend(answer.splitlines() or [""])
            continue
        if index == hole.close_line:
            continue
        if _OPEN.match(line) or _CLOSE.match(line):
            continue
        out.append(line)

    return "\n".join(out)


@dataclass(frozen=True, slots=True)
class CompletionReport:
    report: JudgeReport
    reference_failed: bool = False
    message: str = ""

    @property
    def accepted(self) -> bool:
        return not self.reference_failed and self.report.accepted


def _capture(source: str, stdins: list[str], limits: Limits, workdir: Path) -> list[str] | None:
    """Compile and run ``source`` on each input, returning stdout. ``None`` on failure."""
    build = compile_submission(Submission(source=source), workdir)
    if not build.ok:
        return None

    outputs: list[str] = []
    for stdin_text in stdins:
        result = run_sandboxed(
            [f"{SANDBOX_WORK}/{BINARY_NAME}"],
            limits=limits,
            binds=[(str(workdir), SANDBOX_WORK, False)],
            chdir=SANDBOX_WORK,
            stdin_data=stdin_text.encode(),
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        )
        if not result.ok:
            return None
        outputs.append(result.stdout.decode("utf-8", "replace"))
    return outputs


def judge_completion(
    template_source: str,
    hole_id: str,
    answer: str,
    stdin_samples: list[str],
    *,
    limits: Limits | None = None,
    workdir: Path | None = None,
) -> CompletionReport:
    """Judge a filled hole against the intact template's own behaviour."""
    return judge_source(
        template_source,
        splice(template_source, hole_id, answer),
        stdin_samples,
        limits=limits,
        workdir=workdir,
    )


def judge_source(
    template_source: str,
    candidate: str,
    stdin_samples: list[str],
    *,
    limits: Limits | None = None,
    workdir: Path | None = None,
) -> CompletionReport:
    """Judge a whole program against the intact template's behaviour.

    The editor hand-off gives the learner the complete exercise file and lets
    them fill the hole in place, so what comes back is a full program rather
    than a fragment. Splicing it would mean guessing which lines were theirs;
    judging it whole is both simpler and more honest — they are responsible for
    everything in the file they edited.
    """
    import tempfile

    limits = limits or Limits()
    if not stdin_samples:
        raise ValueError("differential judging needs at least one sample input")

    reference = reference_source(template_source)

    with tempfile.TemporaryDirectory(prefix="dsaq-ref-") as tmp:
        expected = _capture(reference, stdin_samples, limits, Path(tmp))

    if expected is None:
        return CompletionReport(
            report=JudgeReport.internal_error(
                "the reference template does not build or run — this is a content bug"
            ),
            reference_failed=True,
            message="reference failure",
        )

    tests = [
        TestCase(name=f"sample-{index + 1}", stdin=stdin_text, expected=expected_text)
        for index, (stdin_text, expected_text) in enumerate(
            zip(stdin_samples, expected, strict=True)
        )
    ]

    report = judge(
        Submission(source=candidate),
        tests,
        limits=limits,
        checker=CheckerKind.TOKENS,
        workdir=workdir,
    )
    return CompletionReport(report=report)


def hole_hint(hole: Hole) -> str:
    """A shape hint that does not give the code away."""
    plural = "line" if hole.line_count == 1 else "lines"
    return f"about {hole.line_count} {plural}"


def verdict_is_users_fault(report: JudgeReport) -> bool:
    """Whether a verdict should count against the learner's rating."""
    return report.verdict is not Verdict.INTERNAL_ERROR
