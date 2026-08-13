"""Handing a Code Completion exercise to $EDITOR.

The point of leaving the app is that you practise in the environment you
compete in. These tests drive the pieces without launching a real editor —
the suspend/exec path itself is not something a headless test can exercise.
"""

from __future__ import annotations

import json

import pytest

from dsaquest.content.exercises import samples_for
from dsaquest.content.paths import read_template
from dsaquest.game.modes.complete import (
    TODO_MARKER,
    exercise_source,
    find_hole,
    judge_source,
    parse_holes,
)
from dsaquest.judge import compile_flags, workspace

pytestmark = pytest.mark.slow

TEMPLATE = "sliding-window.cpp"


def test_the_workspace_hands_over_the_whole_exercise(tmp_path):
    source = read_template(TEMPLATE)
    hole = parse_holes(source)[0]

    space = workspace.create(
        attempt_id=1,
        starter=exercise_source(source, hole.id),
        statement=f"Fill in the TODO.\n\n    {hole.prompt}\n",
        root=tmp_path,
    )

    written = space.read_source()
    assert TODO_MARKER in written, "the learner must see where the hole is"
    assert "int main(" in written, "they get the whole program, not a fragment"
    assert "HOLE" not in written, "marker syntax must not leak into their editor"
    assert hole.prompt in space.statement.read_text()


def test_clangd_is_given_the_judge_s_own_flags(tmp_path):
    """An editor that disagrees with the judge is worse than no integration."""
    space = workspace.create(attempt_id=2, starter="int main(){}", statement="x", root=tmp_path)
    entry = json.loads((space.directory / "compile_commands.json").read_text())[0]
    for flag in compile_flags("c++20"):
        assert flag in entry["arguments"], flag


def test_a_file_returned_from_the_editor_is_judged_whole(tmp_path):
    """What comes back is a complete program, so splicing would be guesswork."""
    source = read_template(TEMPLATE)
    hole = find_hole(source, parse_holes(source)[0].id)

    space = workspace.create(
        attempt_id=3, starter=exercise_source(source, hole.id), statement="x", root=tmp_path
    )
    # Simulate the learner filling the TODO in place and saving.
    filled = space.read_source().replace(f"{TODO_MARKER}{hole.prompt}", hole.body)
    space.source.write_text(filled)

    report = judge_source(source, space.read_source(), list(samples_for(TEMPLATE)))
    assert not report.reference_failed
    assert report.accepted


def test_an_unfilled_file_is_rejected(tmp_path):
    """Opening the editor and saving without writing anything is not an answer."""
    source = read_template(TEMPLATE)
    hole = parse_holes(source)[0]
    space = workspace.create(
        attempt_id=4, starter=exercise_source(source, hole.id), statement="x", root=tmp_path
    )
    report = judge_source(source, space.read_source(), list(samples_for(TEMPLATE)))
    assert not report.accepted


def test_editing_outside_the_hole_is_the_learners_responsibility(tmp_path):
    """Judging the whole file means breaking anything in it fails, which is honest."""
    source = read_template(TEMPLATE)
    hole = find_hole(source, parse_holes(source)[0].id)
    space = workspace.create(
        attempt_id=5, starter=exercise_source(source, hole.id), statement="x", root=tmp_path
    )
    filled = space.read_source().replace(f"{TODO_MARKER}{hole.prompt}", hole.body)
    broken = filled.replace("int main(", "int notmain(")
    space.source.write_text(broken)

    report = judge_source(source, space.read_source(), list(samples_for(TEMPLATE)))
    assert not report.accepted


def test_the_editor_command_resolves(monkeypatch):
    monkeypatch.setenv("EDITOR", "nvim")
    monkeypatch.delenv("VISUAL", raising=False)
    assert workspace.editor_command() == ["nvim"]

    monkeypatch.setenv("VISUAL", "code --wait")
    assert workspace.editor_command() == ["code", "--wait"]
