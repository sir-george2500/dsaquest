"""Levels and the XP curve.

The curve is superlinear — each level costs more than the last — but only
mildly. A steeply exponential curve makes the first week feel great and the
third month feel pointless, which is the opposite of what a retention tool
needs: the whole value of this app accrues to the person still using it in
month six.

Calibration targets, at a realistic ~200 XP for a 20-minute session:

    Pattern Hunter (10)      ~3 weeks
    Algorithm Knight (20)    ~3 months
    Competitive Programmer (30)  ~7 months
    Algorithm Master (50)    ~2 years

``python -m dsaquest.game.levels`` prints the table so the calibration can be
re-checked rather than trusted.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from functools import cache

#: xp_to_next(n) = XP_SCALE * n ** XP_EXPONENT
XP_SCALE = 52.0
XP_EXPONENT = 1.235

MAX_LEVEL = 50

#: Level -> title. Levels between entries keep the last title earned.
TITLES: dict[int, str] = {
    1: "Novice",
    5: "Apprentice",
    10: "Pattern Hunter",
    15: "Pattern Adept",
    20: "Algorithm Knight",
    25: "Algorithm Champion",
    30: "Competitive Programmer",
    40: "Grandmaster of Patterns",
    50: "Algorithm Master",
}


def xp_to_next(level: int) -> int:
    """XP required to go from ``level`` to ``level + 1``."""
    if level < 1:
        raise ValueError("levels start at 1")
    if level >= MAX_LEVEL:
        return 0
    return int(round(XP_SCALE * level**XP_EXPONENT))


@cache
def _thresholds() -> tuple[int, ...]:
    """Cumulative XP at which each level begins. Index 0 is unused."""
    totals = [0, 0]  # level 0 (unused), level 1 starts at 0 XP
    running = 0
    for level in range(1, MAX_LEVEL):
        running += xp_to_next(level)
        totals.append(running)
    return tuple(totals)


def level_for_xp(xp: int) -> int:
    """The level a given lifetime XP total corresponds to."""
    if xp < 0:
        raise ValueError("XP is never negative")
    return min(bisect_right(_thresholds(), xp) - 1, MAX_LEVEL)


def xp_floor(level: int) -> int:
    """Cumulative XP at which ``level`` begins."""
    return _thresholds()[min(max(level, 1), MAX_LEVEL)]


def title_for_level(level: int) -> str:
    earned = [threshold for threshold in TITLES if threshold <= level]
    return TITLES[max(earned)] if earned else TITLES[1]


@dataclass(frozen=True, slots=True)
class LevelProgress:
    level: int
    title: str
    xp_total: int
    xp_into_level: int
    xp_for_level: int
    is_max: bool

    @property
    def fraction(self) -> float:
        if self.is_max or self.xp_for_level == 0:
            return 1.0
        return self.xp_into_level / self.xp_for_level

    @property
    def xp_remaining(self) -> int:
        return max(0, self.xp_for_level - self.xp_into_level)

    def bar(self, width: int = 24, filled: str = "█", empty: str = "░") -> str:
        full = int(self.fraction * width)
        return filled * full + empty * (width - full)


def progress(xp_total: int) -> LevelProgress:
    level = level_for_xp(xp_total)
    is_max = level >= MAX_LEVEL
    floor = xp_floor(level)
    needed = xp_to_next(level)
    return LevelProgress(
        level=level,
        title=title_for_level(level),
        xp_total=xp_total,
        xp_into_level=xp_total - floor,
        xp_for_level=needed,
        is_max=is_max,
    )


def levelled_up(before_xp: int, after_xp: int) -> tuple[int, ...]:
    """Every level crossed by an XP gain, so the UI can celebrate each one."""
    return tuple(range(level_for_xp(before_xp) + 1, level_for_xp(after_xp) + 1))


def _calibration_table(xp_per_day: int = 200) -> str:  # pragma: no cover - a dev tool
    lines = [
        f"XP curve: {XP_SCALE} * n^{XP_EXPONENT}   (assuming {xp_per_day} XP/day)",
        f"{'lvl':>4} {'title':<24} {'to next':>9} {'cumulative':>11} {'days':>7}",
        "-" * 60,
    ]
    for level in (1, 2, 3, 5, 10, 15, 20, 25, 30, 40, 49, 50):
        cumulative = xp_floor(level)
        lines.append(
            f"{level:>4} {title_for_level(level):<24} {xp_to_next(level):>9} "
            f"{cumulative:>11} {cumulative / xp_per_day:>7.0f}"
        )
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    print(_calibration_table())
