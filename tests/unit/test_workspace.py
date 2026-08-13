"""The nvim workspace handoff."""

from __future__ import annotations

import json

from dsaquest.domain.judging import TestCase
from dsaquest.judge import compile_flags
from dsaquest.judge.workspace import create, prune


def test_a_workspace_is_a_real_cpp_project(tmp_path):
    workspace = create(
        attempt_id=7,
        starter="int main(){}\n",
        statement="# Problem\n\nDo the thing.\n",
        root=tmp_path,
    )
    assert workspace.source.name == "solution.cpp"
    assert workspace.read_source() == "int main(){}\n"
    assert "Do the thing" in workspace.statement.read_text()
    assert (workspace.directory / "compile_commands.json").is_file()


def test_clangd_sees_exactly_the_flags_the_judge_uses(tmp_path):
    """An editor that disagrees with the judge is worse than no integration.

    If clangd is configured with different flags, it reports warnings the judge
    will not, and misses the ones it will. Both erode trust in the editor.
    """
    workspace = create(attempt_id=1, starter="int main(){}", statement="x", root=tmp_path)
    entry = json.loads((workspace.directory / "compile_commands.json").read_text())[0]

    for flag in compile_flags("c++20"):
        assert flag in entry["arguments"], f"clangd would not see {flag}"
    assert entry["file"] == str(workspace.source)
    assert entry["directory"] == str(workspace.directory)


def test_visible_tests_are_written_and_hidden_ones_are_not(tmp_path):
    """Hidden tests exist to stop pattern-matching on the samples."""
    workspace = create(
        attempt_id=2,
        starter="int main(){}",
        statement="x",
        tests=[
            TestCase(name="sample", stdin="1\n", expected="1\n"),
            TestCase(name="secret", stdin="9\n", expected="9\n", hidden=True),
        ],
        root=tmp_path,
    )
    written = sorted(p.name for p in (workspace.directory / "tests").iterdir())
    assert written == ["01.in", "01.out"]


def test_creating_a_workspace_twice_is_safe(tmp_path):
    create(attempt_id=3, starter="a", statement="s", root=tmp_path)
    second = create(attempt_id=3, starter="b", statement="s", root=tmp_path)
    assert second.read_source() == "b"


def test_prune_keeps_the_most_recent(tmp_path):
    for attempt in range(6):
        create(attempt_id=attempt, starter="x", statement="y", root=tmp_path)
    removed = prune(keep=2, root=tmp_path)
    assert removed == 4
    assert len(list(tmp_path.iterdir())) == 2


def test_prune_on_a_missing_directory_is_not_an_error(tmp_path):
    assert prune(keep=5, root=tmp_path / "nope") == 0
