"""Isolated process execution.

Threat model
------------
The code being run is written by the user, but "the user" includes a future
user who pasted something from the internet, and a content bug that ships a
malicious reference solution. So we assume the payload is hostile and must not
be able to read the home directory, reach the network, exhaust the machine, or
survive the judge.

Defence layering, outermost first::

    systemd-run --user --scope   cgroup v2: MemoryMax, MemorySwapMax=0, TasksMax
        └── bwrap                namespaces: no net, no host FS, own PID ns
            └── prlimit          per-process rlimits: CPU, address space, file size
                └── payload

Each layer catches what the one above cannot:

* **TasksMax** is the only real fork-bomb defence. ``RLIMIT_NPROC`` is
  deliberately *not* used: it is enforced per-UID, so a fork bomb in the sandbox
  would exhaust the limit for the user's entire login session — the judge would
  take down the desktop it is running on.
* **MemoryMax** is a backstop that prevents host OOM. ``RLIMIT_AS`` at the same
  value is what actually produces a clean, attributable failure: the allocation
  returns null, libstdc++ throws ``std::bad_alloc``, and we get a diagnosable
  abort instead of an opaque SIGKILL.
* **wall_ms > cpu_ms** because a process blocked on a read burns wall time
  without burning CPU. ``RLIMIT_CPU`` alone would never fire on ``cin >> x``
  with no input.
* **--new-session** is not optional. Without a fresh session the payload can
  ``TIOCSTI``-inject keystrokes into the terminal that launched the judge.

Measurement
-----------
Resource usage is read from the **cgroup**, not from ``wait4``. This is not a
stylistic choice: ``bwrap`` does not propagate its child's rusage to its own
parent, so ``wait4`` on the sandbox reports ~0 ms CPU and ~7 MB peak for a
process that actually burned 1.5 s and 68 MB. Measured on this machine::

    bare                  cpu=1.54s  maxrss=67.7MB
    systemd-run only      cpu=1.55s  maxrss=67.7MB
    bwrap                 cpu=0.00s  maxrss= 7.0MB   <-- rusage lost here
    systemd-run + bwrap   cpu=0.00s  maxrss= 6.9MB

The cgroup is strictly better anyway: it accounts for the entire process tree
including forks, and ``memory.events:oom_kill`` turns "was this a memory kill?"
from a heuristic into a fact. We locate the cgroup by reading
``/proc/<pid>/cgroup`` of the systemd-run process rather than by guessing the
unit path, and sample it *during* execution because the transient scope is
garbage-collected as soon as it empties.
"""

from __future__ import annotations

import errno
import os
import selectors
import shutil
import signal
import time
import uuid
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from ..domain.judging import Limits

# Read/write chunk size when pumping the payload's pipes.
_CHUNK = 65536

# How long to wait for a killed process group to actually die before escalating.
_REAP_GRACE_S = 0.5

# Sampling period for the pipe/cgroup poll loop. memory.peak is a high-water
# mark, so this only bounds how much of a final-instant spike we could miss.
_POLL_S = 0.02

_CGROUP_ROOT = Path("/sys/fs/cgroup")


@dataclass(frozen=True, slots=True)
class SandboxResult:
    """Raw outcome of one sandboxed execution. Verdict mapping happens upstream."""

    exit_code: int | None
    signal: int | None
    stdout: bytes
    stderr: bytes
    cpu_ms: int
    wall_ms: int
    max_rss_kb: int
    timed_out: bool
    output_truncated: bool
    oom_killed: bool = False
    """Read from the cgroup's ``memory.events:oom_kill`` counter — a fact, not a guess."""

    @property
    def killed(self) -> bool:
        return self.signal is not None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.signal is None

    @property
    def cpu_exhausted(self) -> bool:
        """True when RLIMIT_CPU fired.

        The soft limit is set below the hard limit so the kernel delivers
        SIGXCPU first. That makes a CPU-limit kill distinguishable from an OOM
        kill, which would otherwise also arrive as an indistinguishable SIGKILL.
        """
        return self.signal == signal.SIGXCPU

    @property
    def looks_like_oom(self) -> bool:
        """Did this die for lack of memory?

        ``oom_killed`` is authoritative. Failing that, ``RLIMIT_AS`` makes the
        allocation fail cleanly and libstdc++ aborts with ``std::bad_alloc``.
        """
        if self.oom_killed:
            return True
        if self.timed_out or self.cpu_exhausted:
            return False
        return self.signal == signal.SIGABRT and b"bad_alloc" in self.stderr


class SandboxUnavailable(RuntimeError):
    """Raised when the host cannot provide the isolation we require.

    We refuse to fall back to unsandboxed execution. Running untrusted C++ with
    host privileges to keep a game working is not a trade we make.
    """


@cache
def _tool(name: str) -> str | None:
    return shutil.which(name)


@cache
def probe() -> dict[str, bool]:
    """Detect which isolation layers this host actually supports."""
    caps = {
        "bwrap": _tool("bwrap") is not None,
        "prlimit": _tool("prlimit") is not None,
        "systemd_run": _tool("systemd-run") is not None,
        "cgroup2": os.path.isdir("/sys/fs/cgroup")
        and os.path.exists("/sys/fs/cgroup/cgroup.controllers"),
        "userns": False,
    }
    try:
        with open("/proc/sys/user/max_user_namespaces") as fh:
            caps["userns"] = int(fh.read().strip()) > 0
    except (OSError, ValueError):
        caps["userns"] = False
    return caps


def require_sandbox() -> None:
    """Fail loudly at startup rather than silently at judge time."""
    caps = probe()
    missing = [k for k in ("bwrap", "prlimit", "userns") if not caps[k]]
    if missing:
        raise SandboxUnavailable(
            "DSA Quest will not execute C++ without isolation. Missing: "
            + ", ".join(missing)
            + ".\nOn Arch: sudo pacman -S bubblewrap util-linux"
        )


class _CgroupProbe:
    """Samples cgroup v2 accounting for a transient systemd scope.

    The scope is created by systemd-run and destroyed the moment it empties, so
    everything is read *while the payload runs*. All reads are best-effort: if
    cgroups are unavailable the sandbox still works, it just reports zeros and
    falls back to signal-based classification.

    We match on an explicit unit name rather than accepting whatever cgroup the
    child happens to be in. Between fork and systemd-run relocating itself, the
    child still sits in *our* cgroup — which is also a ``.scope`` — and reading
    that reports the entire terminal session's cumulative CPU. That mistake
    surfaces as a plausible-looking 400-second CPU reading on a program that
    ran for one second.
    """

    __slots__ = ("_pid", "_unit", "path", "cpu_us", "peak_kb", "oom_kills")

    def __init__(self, pid: int, unit: str | None) -> None:
        self._pid = pid
        self._unit = unit
        self.path: Path | None = None
        self.cpu_us = 0
        self.peak_kb = 0
        self.oom_kills = 0

    def _attach(self) -> bool:
        if self.path is not None:
            return True
        if self._unit is None:
            return False
        try:
            raw = Path(f"/proc/{self._pid}/cgroup").read_text()
        except OSError:
            return False
        # Format is "0::/user.slice/.../<unit>" for cgroup v2.
        rel = raw.strip().rsplit("::", 1)[-1]
        candidate = _CGROUP_ROOT / rel.lstrip("/")
        if candidate.name != self._unit:
            # Still in the inherited cgroup; systemd-run has not relocated yet.
            return False
        if candidate.is_dir():
            self.path = candidate
            return True
        return False

    def sample(self) -> None:
        if not self._attach():
            return
        assert self.path is not None
        try:
            self.peak_kb = max(self.peak_kb, int((self.path / "memory.peak").read_text()) // 1024)
        except (OSError, ValueError):
            pass
        try:
            for line in (self.path / "cpu.stat").read_text().splitlines():
                if line.startswith("usage_usec"):
                    self.cpu_us = max(self.cpu_us, int(line.split()[1]))
                    break
        except (OSError, ValueError):
            pass
        try:
            for line in (self.path / "memory.events").read_text().splitlines():
                if line.startswith("oom_kill "):
                    self.oom_kills = max(self.oom_kills, int(line.split()[1]))
                    break
        except (OSError, ValueError):
            pass


def _bwrap_argv(
    *,
    binds: list[tuple[str, str, bool]],
    chdir: str,
    argv: list[str],
    env: dict[str, str] | None = None,
    allow_net: bool = False,
) -> list[str]:
    """Build the bubblewrap command.

    ``binds`` entries are ``(host_path, sandbox_path, writable)``.
    """
    cmd = [
        "bwrap",
        "--die-with-parent",
        "--new-session",
        "--unshare-user",
        "--unshare-ipc",
        "--unshare-pid",
        "--unshare-uts",
        "--unshare-cgroup-try",
        # The toolchain and libstdc++ live here. Read-only, and it is the only
        # host path visible - no /home, no /etc/shadow, no ~/.ssh, no ~/.aws.
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/sbin",
        "/sbin",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--tmpfs",
        "/run",
        # Deliberately no /proc: nothing we run needs it, and it is a rich
        # source of host information and of /proc/self/mem style tricks.
        "--hostname",
        "sandbox",
        "--clearenv",
    ]
    if not allow_net:
        cmd.append("--unshare-net")

    for host_path, sandbox_path, writable in binds:
        cmd += ["--bind" if writable else "--ro-bind", host_path, sandbox_path]

    for key, value in (env or {}).items():
        cmd += ["--setenv", key, value]

    cmd += ["--chdir", chdir, "--"]
    cmd += argv
    return cmd


def _prlimit_argv(limits: Limits, argv: list[str]) -> list[str]:
    """Wrap ``argv`` in per-process rlimits.

    Applied innermost so the limits bind the payload rather than the sandbox
    scaffolding. ``--cpu`` is in whole seconds (the kernel's granularity),
    rounded up; the wall-clock deadline is the precise timer.

    The CPU limit is set as ``soft:hard`` with a one-second gap on purpose. At
    the soft limit the kernel sends SIGXCPU, whose default action is to
    terminate — so we observe signal 24 and know unambiguously that this was a
    timeout. If soft equalled hard the process would be SIGKILLed instead,
    which is indistinguishable from an OOM kill.
    """
    cpu_s = max(1, -(-limits.cpu_ms // 1000))
    return [
        "prlimit",
        f"--cpu={cpu_s}:{cpu_s + 1}",
        f"--as={limits.memory_mb * 1024 * 1024}",
        f"--fsize={limits.file_size_kb * 1024}",
        f"--stack={limits.stack_mb * 1024 * 1024}",
        "--nofile=64",
        "--core=0",
        "--",
        *argv,
    ]


def _scope_argv(limits: Limits, argv: list[str], unit: str | None) -> list[str]:
    """Wrap ``argv`` in a transient systemd scope carrying cgroup v2 limits."""
    caps = probe()
    if unit is None or not (caps["systemd_run"] and caps["cgroup2"]):
        return argv
    return [
        "systemd-run",
        "--user",
        "--scope",
        "--quiet",
        "--collect",
        f"--unit={unit}",
        "-p",
        f"MemoryMax={limits.memory_mb}M",
        "-p",
        "MemorySwapMax=0",
        "-p",
        f"TasksMax={limits.max_pids}",
        "--",
        *argv,
    ]


def _drain(
    pid: int,
    pgid: int,
    stdin_fd: int,
    stdout_fd: int,
    stderr_fd: int,
    payload: bytes,
    limits: Limits,
    probe_cg: _CgroupProbe,
) -> tuple[bytes, bytes, bool, bool, int]:
    """Pump the child's pipes until it exits or the wall deadline passes.

    Also samples the cgroup on every iteration, because the transient scope
    disappears the instant the payload exits.

    Returns ``(stdout, stderr, timed_out, truncated, status)``.
    """
    cap = limits.output_kb * 1024
    deadline = time.monotonic() + limits.wall_ms / 1000

    out = bytearray()
    err = bytearray()
    truncated = False
    offset = 0

    sel = selectors.DefaultSelector()
    sel.register(stdout_fd, selectors.EVENT_READ, "out")
    sel.register(stderr_fd, selectors.EVENT_READ, "err")
    if payload:
        sel.register(stdin_fd, selectors.EVENT_WRITE, "in")
    else:
        os.close(stdin_fd)
        stdin_fd = -1

    open_reads = 2
    timed_out = False

    try:
        while open_reads:
            probe_cg.sample()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break

            for key, _ in sel.select(timeout=min(remaining, _POLL_S)):
                tag = key.data
                fd = key.fileobj  # int, since we registered raw fds

                if tag == "in":
                    try:
                        written = os.write(fd, payload[offset : offset + _CHUNK])
                        offset += written
                    except BrokenPipeError:
                        # Payload exited without reading all of stdin. Normal.
                        sel.unregister(fd)
                        os.close(fd)
                        stdin_fd = -1
                        continue
                    if offset >= len(payload):
                        sel.unregister(fd)
                        os.close(fd)
                        stdin_fd = -1
                    continue

                chunk = os.read(fd, _CHUNK)
                if not chunk:
                    sel.unregister(fd)
                    open_reads -= 1
                    continue

                buf = out if tag == "out" else err
                if len(buf) < cap:
                    buf.extend(chunk[: cap - len(buf)])
                    if len(buf) >= cap:
                        truncated = True
                else:
                    truncated = True
    finally:
        sel.close()
        if stdin_fd >= 0:
            os.close(stdin_fd)

    probe_cg.sample()

    if truncated or timed_out:
        _kill_group(pgid, pid)

    status = _reap(pid)
    probe_cg.sample()
    return bytes(out), bytes(err), timed_out, truncated, status


def _kill_group(pgid: int, pid: int) -> None:
    """SIGKILL the whole process group, then the leader as a fallback.

    bwrap's PID namespace means killing its child tears down every descendant,
    but the group kill also covers the systemd-run and bwrap scaffolding.
    """
    for target, sender in ((pgid, os.killpg), (pid, os.kill)):
        try:
            sender(target, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def _reap(pid: int) -> int:
    """waitpid the child, escalating to SIGKILL if it lingers."""
    deadline = time.monotonic() + _REAP_GRACE_S
    while True:
        try:
            waited, status = os.waitpid(pid, os.WNOHANG)
        except OSError as exc:  # pragma: no cover - defensive
            if exc.errno != errno.EINTR:
                raise
            continue
        if waited:
            return status
        if time.monotonic() > deadline:
            _kill_group(pid, pid)
            return os.waitpid(pid, 0)[1]
        time.sleep(0.002)


def run_sandboxed(
    argv: list[str],
    *,
    limits: Limits,
    binds: list[tuple[str, str, bool]],
    chdir: str,
    stdin_data: bytes = b"",
    env: dict[str, str] | None = None,
    _calibrating: bool = False,
) -> SandboxResult:
    """Execute ``argv`` under the full isolation stack.

    ``argv`` is interpreted *inside* the sandbox, so paths must be sandbox
    paths (typically ``/box/...``) rather than host paths.
    """
    require_sandbox()

    caps = probe()
    unit = f"dsaq-{uuid.uuid4().hex}.scope" if caps["systemd_run"] and caps["cgroup2"] else None

    inner = _prlimit_argv(limits, argv)
    jailed = _bwrap_argv(binds=binds, chdir=chdir, argv=inner, env=env)
    command = _scope_argv(limits, jailed, unit)

    stdin_r, stdin_w = os.pipe()
    stdout_r, stdout_w = os.pipe()
    stderr_r, stderr_w = os.pipe()
    os.set_blocking(stdin_w, False)
    os.set_blocking(stdout_r, False)
    os.set_blocking(stderr_r, False)

    started = time.monotonic()
    pid = os.fork()

    if pid == 0:  # pragma: no cover - child branch never returns
        # Only async-signal-safe operations between fork and exec.
        try:
            os.setpgid(0, 0)
            os.dup2(stdin_r, 0)
            os.dup2(stdout_w, 1)
            os.dup2(stderr_w, 2)
            for fd in (stdin_r, stdin_w, stdout_r, stdout_w, stderr_r, stderr_w):
                try:
                    os.close(fd)
                except OSError:
                    pass
            os.execvp(command[0], command)
        except BaseException:
            os._exit(127)

    for fd in (stdin_r, stdout_w, stderr_w):
        os.close(fd)

    # The child races us to setpgid; do it here too so the group exists either way.
    try:
        os.setpgid(pid, pid)
    except (ProcessLookupError, PermissionError, OSError):
        pass

    cgroup = _CgroupProbe(pid, unit)
    out, err, timed_out, truncated, status = _drain(
        pid, pid, stdin_w, stdout_r, stderr_r, stdin_data, limits, cgroup
    )
    wall_ms = int((time.monotonic() - started) * 1000)

    for fd in (stdout_r, stderr_r):
        try:
            os.close(fd)
        except OSError:
            pass

    exit_code = os.waitstatus_to_exitcode(status) if not os.WIFSIGNALED(status) else None
    sig = os.WTERMSIG(status) if os.WIFSIGNALED(status) else None

    # The process we wait on is systemd-run, not the payload. When the payload
    # dies from a signal, the scaffolding exits *normally* with status 128+N
    # (the shell convention) rather than being signalled itself. Without this
    # translation every segfault surfaces as "exited with status 139" and the
    # diagnostics in service.py never fire.
    if sig is None and exit_code is not None and 128 < exit_code < 192:
        sig = exit_code - 128
        exit_code = None

    baseline_kb = 0 if _calibrating else _baseline_kb()

    return SandboxResult(
        exit_code=exit_code if exit_code is None or exit_code >= 0 else None,
        signal=sig,
        stdout=out,
        stderr=err,
        cpu_ms=cgroup.cpu_us // 1000,
        wall_ms=wall_ms,
        max_rss_kb=max(0, cgroup.peak_kb - baseline_kb),
        timed_out=timed_out,
        output_truncated=truncated,
        oom_killed=cgroup.oom_kills > 0,
    )


@cache
def _baseline_kb() -> int:
    """Peak memory of the sandbox scaffolding alone.

    The cgroup contains systemd-run and bwrap as well as the payload, so its
    ``memory.peak`` sits a few MB above the payload's true usage. Measuring that
    floor once and subtracting it turns a number that is always wrong in the
    same direction into one the user can trust.
    """
    try:
        result = run_sandboxed(
            ["/bin/true"],
            limits=Limits(cpu_ms=1000, wall_ms=4000, memory_mb=64),
            binds=[],
            chdir="/tmp",
            _calibrating=True,
        )
        return result.max_rss_kb
    except Exception:  # pragma: no cover - never let calibration break judging
        return 0
