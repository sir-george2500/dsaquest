"""Run every authored sample input against its template.

Nothing did this. Sample inputs were validated for existence and shape but
never executed, so an input that violates a template's implicit preconditions —
a query past a sieve bound, an index off the end, an n larger than a fixed
array — surfaced as a crash *during play*, in the middle of a differential
judgement, as a verdict the learner has no way to interpret.

That is exactly how one was found: an author noticed only because running it
segfaulted. This makes that check deliberate rather than lucky.

Correct output is not checked and cannot be: the intact template IS the oracle,
so whatever it prints is by definition right. What is checked is that it
survives — no crash, no timeout, no compile error.

    .venv/bin/python tools/sample_check.py             # every template
    .venv/bin/python tools/sample_check.py sieve       # only matching ones
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dsaquest.content.exercises import sample_inputs  # noqa: E402
from dsaquest.content.paths import read_template  # noqa: E402
from dsaquest.domain.judging import Submission, TestCase, Verdict  # noqa: E402
from dsaquest.judge.service import judge  # noqa: E402

#: Verdicts that mean the program failed to survive its input. WRONG_ANSWER is
#: absent on purpose — we pass an empty expectation, so every surviving run
#: reports WA and that tells us nothing.
FATAL = {
    Verdict.RUNTIME_ERROR,
    Verdict.TIME_LIMIT,
    Verdict.MEMORY_LIMIT,
    Verdict.COMPILE_ERROR,
    Verdict.INTERNAL_ERROR,
}


def check(template: str, inputs: tuple[str, ...]) -> list[str]:
    try:
        source = read_template(template)
    except Exception as exc:
        return [f"{template}: cannot be read — {exc}"]

    report = judge(
        Submission(source=source),
        [
            TestCase(name=f"sample {i + 1}", stdin=text, expected="")
            for i, text in enumerate(inputs)
        ],
    )
    if report.verdict is Verdict.COMPILE_ERROR:
        return [f"{template}: does not compile — {report.compile_log.strip()[:200]}"]

    problems = []
    for outcome in report.outcomes:
        if outcome.verdict in FATAL:
            head = inputs[0][:60].replace("\n", " ⏎ ") if inputs else ""
            problems.append(
                f"{template}: {outcome.name} killed it with {outcome.verdict.value} "
                f"— the input violates a precondition the template does not state ({head}…)"
            )
    return problems


def main(argv: list[str]) -> int:
    wanted = argv[0] if argv else ""
    samples = {k: v for k, v in sample_inputs().items() if wanted in k}
    if not samples:
        print(f"no templates match {wanted!r}", file=sys.stderr)
        return 1

    failures = 0
    for template, inputs in sorted(samples.items()):
        problems = check(template, inputs)
        if problems:
            failures += 1
            for problem in problems:
                print(f"FAIL  {problem}", file=sys.stderr)
        else:
            print(f"ok    {template:<32} {len(inputs)} sample(s) survived")
    print(f"\n{len(samples) - failures} of {len(samples)} templates ran every sample cleanly")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
