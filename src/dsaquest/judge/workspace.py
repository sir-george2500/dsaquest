"""Materialising a real C++ project per attempt, for editing in nvim.

The point of handing off to ``$EDITOR`` rather than embedding an editor is that
you practise in the environment you compete in — same keybinds, same snippets,
same LSP. Muscle memory transfers.

The detail that makes that true is ``compile_commands.json``. Without it clangd
greets you with "no compilation database" and gives half-broken completion on
``<bits/stdc++.h>``. We generate it from the judge's *own* flag list, so what
clangd tells you and what the judge does cannot disagree — an editor that lies
about warnings is worse than no editor integration.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir

from ..domain.judging import TestCase
from .compiler import SOURCE_NAME, compile_flags

APP_NAME = "dsa-quest"


def workspace_root() -> Path:
    return Path(user_data_dir(APP_NAME, appauthor=False)) / "workspace"


@dataclass(frozen=True, slots=True)
class Workspace:
    directory: Path
    source: Path
    statement: Path

    def read_source(self) -> str:
        return self.source.read_text(encoding="utf-8")


def create(
    *,
    attempt_id: int,
    starter: str,
    statement: str,
    tests: list[TestCase] | None = None,
    standard: str = "c++20",
    root: Path | None = None,
) -> Workspace:
    """Write a self-contained C++ project for one attempt."""
    directory = (root or workspace_root()) / f"attempt-{attempt_id}"
    directory.mkdir(parents=True, exist_ok=True)

    source = directory / SOURCE_NAME
    source.write_text(starter, encoding="utf-8")

    statement_path = directory / "statement.md"
    statement_path.write_text(statement, encoding="utf-8")

    _write_compile_commands(directory, source, standard)

    if tests:
        tests_dir = directory / "tests"
        tests_dir.mkdir(exist_ok=True)
        for index, case in enumerate(tests, start=1):
            if case.hidden:
                continue  # hidden tests stay hidden; that is the point of them
            (tests_dir / f"{index:02d}.in").write_text(case.stdin, encoding="utf-8")
            (tests_dir / f"{index:02d}.out").write_text(case.expected, encoding="utf-8")

    return Workspace(directory=directory, source=source, statement=statement_path)


def _write_compile_commands(directory: Path, source: Path, standard: str) -> None:
    """Emit the database clangd needs, using the judge's exact flags."""
    arguments = ["g++", *compile_flags(standard), "-c", str(source)]
    entry = {
        "directory": str(directory),
        "file": str(source),
        "arguments": arguments,
    }
    (directory / "compile_commands.json").write_text(
        json.dumps([entry], indent=2), encoding="utf-8"
    )


def editor_command() -> list[str]:
    """``$VISUAL``/``$EDITOR``, falling back to something that exists."""
    raw = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if raw:
        return shlex.split(raw)
    for candidate in ("nvim", "vim", "nano", "vi"):
        from shutil import which

        if which(candidate):
            return [candidate]
    raise RuntimeError("no editor found; set $EDITOR")


def open_in_editor(workspace: Workspace, *, extra_args: list[str] | None = None) -> int:
    """Run the editor on the workspace and wait. Returns its exit status.

    Called from inside Textual's ``suspend()`` block, which restores the
    terminal first so the editor gets a clean screen and gets it back after.
    """
    command = [*editor_command(), *(extra_args or []), str(workspace.source)]
    return subprocess.call(command, cwd=str(workspace.directory))


def cleanup(workspace: Workspace) -> None:
    """Remove a workspace once its attempt is recorded."""
    import shutil

    shutil.rmtree(workspace.directory, ignore_errors=True)


def prune(keep: int = 20, root: Path | None = None) -> int:
    """Delete all but the most recent ``keep`` workspaces. Returns how many went.

    Workspaces are kept after an attempt on purpose — going back to look at what
    you wrote is useful — but unbounded growth is not.
    """
    import shutil

    base = root or workspace_root()
    if not base.is_dir():
        return 0

    directories = sorted(
        (p for p in base.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed = 0
    for stale in directories[keep:]:
        shutil.rmtree(stale, ignore_errors=True)
        removed += 1
    return removed
