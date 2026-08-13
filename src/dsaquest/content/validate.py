"""``python -m dsaquest.content.validate`` — check the content tree.

Used by content authors (human and agent) as a fast feedback loop, and by CI.
Exits non-zero with a list of problems, or zero with a summary.
"""

from __future__ import annotations

import sys

from .loader import ContentError, describe_content_root, load_library


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

    if verbose:
        for pattern in library:
            confusions = ", ".join(library.confusable_ids(pattern.id)) or "none"
            print(
                f"\n  {pattern.id}  ({pattern.name})"
                f"\n    signals={len(pattern.signals)} traps={len(pattern.traps)} "
                f"rubric={len(pattern.recall_rubric)}"
                f"\n    confusable_with: {confusions}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
