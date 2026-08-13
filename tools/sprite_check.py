"""Validate sprite files. Exits non-zero on the first real problem."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dsaquest.art.sprite import SpriteError, parse_sprite  # noqa: E402

CANON = 24


def check(path: Path) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")

    rows = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    widths = Counter(len(r) for r in rows)
    if len(widths) > 1:
        problems.append(f"ragged rows: widths {dict(widths)} — every row must be the same length")
    try:
        sprite = parse_sprite(text, name=path.stem)
    except SpriteError as exc:
        problems.append(str(exc))
        return problems

    if (sprite.width, sprite.height) != (CANON, CANON):
        problems.append(f"{sprite.width}x{sprite.height}, want {CANON}x{CANON}")
    if not sprite.name:
        problems.append("no '# name:' line")

    solid = sum(1 for row in sprite.rows for px in row if px is not None)
    coverage = solid / (sprite.width * sprite.height or 1)
    if coverage < 0.15:
        problems.append(f"only {coverage:.0%} of the grid is painted — the subject is too thin")
    if coverage > 0.95:
        problems.append(f"{coverage:.0%} painted — no silhouette, it is a filled rectangle")

    colours = {px for row in sprite.rows for px in row if px}
    if len(colours) < 3:
        problems.append(f"{len(colours)} colours — too flat to read as a figure")
    return problems


def main() -> int:
    failed = 0
    for arg in sys.argv[1:]:
        path = Path(arg)
        problems = check(path)
        if problems:
            failed += 1
            print(f"FAIL {path.name}")
            for p in problems:
                print(f"       {p}")
        else:
            sprite = parse_sprite(path.read_text(), name=path.stem)
            colours = len({px for row in sprite.rows for px in row if px})
            print(f"ok   {path.name:<26} {sprite.width}x{sprite.height}  {colours} colours")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
