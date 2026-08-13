"""The shipped C++ templates must build clean under the judge's own flags.

A starter template that emits warnings the moment you open it teaches the wrong
lesson, and a template that fails to compile makes the app look broken before
the user has written a line.
"""

from __future__ import annotations

import subprocess

import pytest

from dsaquest.content.paths import read_template, templates_dir
from dsaquest.domain import Submission, TestCase, Verdict
from dsaquest.judge import compile_flags, judge

pytestmark = pytest.mark.slow

TEMPLATES = ["starter.cpp", "starter_full.cpp"]


@pytest.mark.parametrize("name", TEMPLATES)
def test_template_compiles_through_the_judge(name: str):
    report = judge(
        Submission(source=read_template(name)),
        [TestCase(name="empty", stdin="", expected="")],
    )
    assert report.verdict is not Verdict.COMPILE_ERROR, report.compile_log
    assert report.accepted, report.first_failure


@pytest.mark.parametrize("name", TEMPLATES)
def test_template_is_warning_free(name: str):
    report = judge(
        Submission(source=read_template(name)),
        [TestCase(name="empty", stdin="", expected="")],
    )
    assert report.compile_log.strip() == "", f"{name} is not warning-clean:\n{report.compile_log}"


def test_debug_macro_costs_nothing_without_local():
    """`debug(...)` must vanish entirely when LOCAL is undefined."""
    source = read_template("starter_full.cpp").replace(
        "void solve() {\n",
        'void solve() {\n    int n = 41;\n    debug(n);\n    cout << n + 1 << "\\n";\n',
        1,
    )
    report = judge(
        Submission(source=source),
        [TestCase(name="quiet", stdin="", expected="42\n")],
    )
    assert report.accepted, report.first_failure
    assert report.outcomes[0].stderr_excerpt == "", "debug() leaked output into a judged run"


def test_debug_macro_prints_names_and_nested_values_under_local(tmp_path):
    """Compiled with -DLOCAL it must name each argument and recurse into containers."""
    source = read_template("starter_full.cpp").replace(
        "void solve() {\n",
        "void solve() {\n"
        "    int n = 5;\n"
        "    vector<vector<int>> g{{1, 2}, {3}};\n"
        '    pair<int, string> p{7, "hi"};\n'
        "    debug(n, g);\n"
        "    debug(p, max(n, 3));\n",
        1,
    )
    src = tmp_path / "dbg.cpp"
    src.write_text(source)
    binary = tmp_path / "dbg"

    build = subprocess.run(
        ["g++", *compile_flags("c++20"), "-DLOCAL", "-o", str(binary), str(src)],
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stderr
    assert build.stderr.strip() == "", f"debug build warns:\n{build.stderr}"

    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
    err = run.stderr
    assert "n = 5" in err
    assert "g = {{1, 2}, {3}}" in err, err
    assert 'p = (7, "hi")' in err, err
    # The name splitter must respect bracket depth rather than the first comma.
    assert "max(n, 3) = 5" in err, err


def test_starter_stays_small():
    """The default stub is minimal on purpose; guard against creep."""
    lines = [ln for ln in read_template("starter.cpp").splitlines() if ln.strip()]
    assert len(lines) <= 20, f"starter.cpp has grown to {len(lines)} lines"


def test_templates_directory_is_discoverable():
    assert templates_dir().is_dir()
    assert (templates_dir() / "starter.cpp").is_file()
