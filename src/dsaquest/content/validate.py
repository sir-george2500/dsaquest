"""``python -m dsaquest.content.validate`` — check the content tree.

Used by content authors (human and agent) as a fast feedback loop, and by CI.
Exits non-zero with a list of problems, or zero with a summary.

Problem roles are reported here rather than enforced in the loader, and the two
findings are graded differently on purpose:

* **Reuse** fails the run. It is a mistake in a curriculum file and one edit
  fixes it.
* **Shortfall** reports but does not fail, unless ``--strict``. It means a
  pattern has fewer problems than its roles need, which no edit can fix — it
  needs problems written. A check that goes red and stays red until somebody
  writes fourteen problems is a check people learn to ignore, and then it is
  not protecting anything. ``--strict`` is there to turn it on the day the
  content catches up.
"""

from __future__ import annotations

import sys

from .lessons import load_curricula
from .loader import ContentError, describe_content_root, load_library
from .problems import load_problems
from .roles import check_roles


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    verbose = "-v" in argv or "--verbose" in argv

    try:
        library = load_library()
    except ContentError as exc:
        print(f"FAIL  {describe_content_root()}", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"OK  {len(library)} pattern(s) in {describe_content_root()}")
    for world, patterns in library.worlds.items():
        print(f"  world {world}: " + ", ".join(p.id for p in patterns))

    failed = _report_roles(library, strict="--strict" in argv)

    if verbose:
        for pattern in library:
            confusions = ", ".join(library.confusable_ids(pattern.id)) or "none"
            print(
                f"\n  {pattern.id}  ({pattern.name})"
                f"\n    signals={len(pattern.signals)} traps={len(pattern.traps)} "
                f"rubric={len(pattern.recall_rubric)}"
                f"\n    confusable_with: {confusions}"
            )
    return 1 if failed else 0


def _report_roles(library, *, strict: bool) -> bool:
    """Print the problem-role findings. Returns True if the run should fail."""
    try:
        bank = load_problems(library)
        curricula = load_curricula(library, bank)
    except ContentError as exc:
        print("\nRoles  could not be checked:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return True

    report = check_roles(curricula, bank)
    print(
        f"\nRoles  {len(report.reserved)} problem(s) reserved by trials and final "
        f"tests, {len(report.unreserved)} free for ordinary practice"
    )

    for reuse in report.reuses:
        print(f"  FAIL  {reuse}", file=sys.stderr)
    for shortfall in report.shortfalls:
        label = "FAIL " if strict else "note "
        stream = sys.stderr if strict else sys.stdout
        print(f"  {label} {shortfall}", file=stream)

    if report.shortfalls and not strict:
        missing = sum(s.missing for s in report.shortfalls)
        print(
            f"  note  {missing} more problem(s) would let every trial and final test "
            "draw something the learner has not already seen (--strict to enforce)"
        )
    return bool(report.reuses) or (strict and bool(report.shortfalls))


if __name__ == "__main__":
    raise SystemExit(main())
