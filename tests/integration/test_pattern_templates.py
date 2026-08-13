"""Every pattern's canonical C++ template must build clean under the judge.

These templates are the thing the user copies from and, in Mode C, the thing
holes get cut into. A template that does not compile — or that emits warnings
the judge would show — teaches the wrong lesson at exactly the wrong moment.
"""

from __future__ import annotations

import pytest

from dsaquest.content.loader import load_library
from dsaquest.content.paths import read_template
from dsaquest.domain import Submission, TestCase, Verdict
from dsaquest.judge import judge

pytestmark = pytest.mark.slow

LIBRARY = load_library()
PATTERN_IDS = sorted(LIBRARY.patterns)


@pytest.mark.parametrize("pattern_id", PATTERN_IDS)
def test_pattern_template_compiles_without_warnings(pattern_id: str):
    pattern = LIBRARY[pattern_id]
    report = judge(
        Submission(source=read_template(pattern.template_file)),
        [TestCase(name="empty", stdin="", expected="")],
    )
    assert report.verdict is not Verdict.COMPILE_ERROR, (
        f"{pattern.template_file} failed to compile:\n{report.compile_log}"
    )
    assert report.compile_log.strip() == "", (
        f"{pattern.template_file} is not warning-clean:\n{report.compile_log}"
    )


@pytest.mark.parametrize("pattern_id", PATTERN_IDS)
def test_pattern_template_survives_empty_input(pattern_id: str):
    """A demo harness that segfaults on no input is a bad first impression.

    Templates read from stdin; running one with nothing on stdin must exit
    cleanly rather than crash, since that is what happens the first time
    someone runs it by hand.
    """
    pattern = LIBRARY[pattern_id]
    report = judge(
        Submission(source=read_template(pattern.template_file)),
        [TestCase(name="empty", stdin="", expected="")],
    )
    outcome = report.outcomes[0]
    assert outcome.verdict is not Verdict.RUNTIME_ERROR, (
        f"{pattern.template_file} crashes on empty input: {outcome.diff_hint}"
    )
    assert outcome.verdict is not Verdict.TIME_LIMIT, (
        f"{pattern.template_file} hangs on empty input"
    )


@pytest.mark.parametrize("pattern_id", PATTERN_IDS)
def test_pattern_template_is_substantial(pattern_id: str):
    """Each template should show several forms of the pattern, not one snippet."""
    source = read_template(LIBRARY[pattern_id].template_file)
    code_lines = [
        ln for ln in source.splitlines() if ln.strip() and not ln.strip().startswith("//")
    ]
    assert len(code_lines) >= 30, f"{pattern_id} template looks too thin"
    assert "int main(" in source, f"{pattern_id} template has no runnable demo harness"
