"""Sandboxed C++ compilation.

The compiler runs inside the same jail as the payload. That is not paranoia
theatre — a compiler is an interpreter with filesystem access:

* ``#include "/etc/passwd"`` prints file contents in the error message.
* ``__has_include(...)`` is a file-existence oracle.
* GCC 15+ implements ``#embed``, which copies arbitrary host files straight
  into the produced binary.

Inside the jail only ``/usr`` (the toolchain) and the scratch directory exist,
so all three degrade to reading public system files.

Compilation also gets a *separate, larger* limit set than execution: g++ with
``-O2`` on ``<bits/stdc++.h>`` routinely needs ~1 GB and several seconds, and
applying the 256 MB runtime cap here would fail every submission.
"""

from __future__ import annotations

import time
from pathlib import Path

from ..domain.judging import CompileResult, Limits, Submission
from .sandbox import run_sandboxed

#: Compilation is heavier than execution. These bound a runaway template
#: expansion or a compiler bomb without tripping ordinary code.
COMPILE_LIMITS = Limits(
    cpu_ms=20_000,
    wall_ms=45_000,
    memory_mb=2048,
    output_kb=512,
    # A -static-libstdc++ binary is several megabytes; the linker needs room to
    # write it. This is the file-write limit, not the diagnostics limit.
    file_size_kb=262_144,
    max_pids=64,
    stack_mb=256,
)

#: Flags mirrored into compile_commands.json so clangd in nvim agrees with the
#: judge. Divergence here means the editor lies to you, which is worse than no
#: editor integration at all.
BASE_FLAGS: tuple[str, ...] = (
    "-O2",
    "-pipe",
    "-static-libstdc++",
    "-Wall",
    "-Wextra",
    "-Wshadow",
    "-Wno-unused-result",
    "-Wno-sign-compare",
    "-fno-plt",
)

SANDBOX_WORK = "/box"
SOURCE_NAME = "solution.cpp"
BINARY_NAME = "solution"


def compile_flags(standard: str = "c++20", extra: tuple[str, ...] = ()) -> list[str]:
    return [f"-std={standard}", *BASE_FLAGS, *extra]


def compile_submission(
    submission: Submission,
    workdir: Path,
    *,
    limits: Limits = COMPILE_LIMITS,
) -> CompileResult:
    """Compile ``submission`` into ``workdir/solution``.

    ``workdir`` is a host directory that will be bind-mounted writable at
    ``/box``. It must already exist and should be per-attempt.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    source = workdir / SOURCE_NAME
    source.write_text(submission.source, encoding="utf-8")

    binary = workdir / BINARY_NAME
    if binary.exists():
        binary.unlink()

    argv = [
        "g++",
        *compile_flags(submission.language_standard, submission.extra_flags),
        f"{SANDBOX_WORK}/{SOURCE_NAME}",
        "-o",
        f"{SANDBOX_WORK}/{BINARY_NAME}",
    ]

    started = time.monotonic()
    result = run_sandboxed(
        argv,
        limits=limits,
        binds=[(str(workdir), SANDBOX_WORK, True)],
        chdir=SANDBOX_WORK,
        env={"PATH": "/usr/bin:/bin", "TMPDIR": "/tmp", "LC_ALL": "C"},
    )
    duration_ms = int((time.monotonic() - started) * 1000)

    log = _clean_log(result.stderr.decode("utf-8", "replace"))

    if result.timed_out:
        return CompileResult(
            ok=False,
            binary_path=None,
            log=log + "\n[judge] compilation timed out — check for runaway template recursion",
            duration_ms=duration_ms,
            command=tuple(argv),
        )

    ok = result.ok and binary.exists()
    if ok:
        binary.chmod(0o755)

    return CompileResult(
        ok=ok,
        binary_path=str(binary) if ok else None,
        log=log,
        duration_ms=duration_ms,
        command=tuple(argv),
    )


def _clean_log(log: str, *, max_chars: int = 8000) -> str:
    """Strip sandbox paths so errors read as ``solution.cpp:12:5`` not ``/box/...``.

    A wall of template instantiation noise teaches nothing, so we also keep only
    the head of very long logs — the first error is nearly always the real one.
    """
    cleaned = log.replace(f"{SANDBOX_WORK}/", "")
    if len(cleaned) <= max_chars:
        return cleaned.strip()
    head = cleaned[:max_chars]
    return head.rstrip() + f"\n… [{len(cleaned) - max_chars} more characters truncated]"
