"""Controlled vocabularies for the whole system.

Everything here is a stable, persisted identifier. Values are written into the
SQLite database and into content YAML, so **renaming a value is a migration**.
Add new members freely; never repurpose an old one.
"""

from __future__ import annotations

from enum import StrEnum


class Difficulty(StrEnum):
    """Difficulty is assigned by the content author, not derived from the pattern.

    The scale deliberately measures *insight required*, not lines of code:

    EASY    one pattern, signals are explicit in the statement
    MEDIUM  one pattern, signals are implied; or a standard two-step composition
    HARD    pattern is disguised, or requires a non-obvious state/invariant choice
    EXPERT  two patterns composed, or a tight constraint that rules out the naive fit
    BOSS    unlabelled, multi-pattern, must be explained before it is accepted
    """

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"
    BOSS = "boss"

    @property
    def rank(self) -> int:
        return _DIFFICULTY_RANK[self]

    @property
    def base_xp(self) -> int:
        return _DIFFICULTY_XP[self]


_DIFFICULTY_RANK: dict[Difficulty, int] = {
    Difficulty.EASY: 0,
    Difficulty.MEDIUM: 1,
    Difficulty.HARD: 2,
    Difficulty.EXPERT: 3,
    Difficulty.BOSS: 4,
}

_DIFFICULTY_XP: dict[Difficulty, int] = {
    Difficulty.EASY: 25,
    Difficulty.MEDIUM: 50,
    Difficulty.HARD: 100,
    Difficulty.EXPERT: 150,
    Difficulty.BOSS: 250,
}


class Dimension(StrEnum):
    """The three *independently scheduled* memory dimensions.

    Each (pattern, dimension) pair owns its own FSRS card, because they decay
    at genuinely different rates: you can keep recognising Monotonic Stack long
    after you have lost the ability to write one from scratch.

    Speed / accuracy / retention are deliberately NOT here — they are derived
    from the event log rather than scheduled. See ``domain.mastery``.
    """

    RECOGNITION = "recognition"
    """Can I name the pattern from an unlabelled statement? (Modes A, D)"""

    RECALL = "recall"
    """Given the name, can I produce signals, invariant, complexity, template? (Mode B)"""

    IMPLEMENTATION = "implementation"
    """Can I write correct C++ under time pressure? (Modes C, E)"""


class GameMode(StrEnum):
    HUNTER = "hunter"
    """Mode A — identify the pattern behind an unlabelled statement."""

    RECALL = "recall"
    """Mode B — cued recall of a pattern's structure."""

    COMPLETE = "complete"
    """Mode C — fill the holes in a partially written template."""

    DUEL = "duel"
    """Mode D — separate two deliberately confusable statements."""

    BOSS = "boss"
    """Mode E — unlabelled, explain-then-implement mastery test."""

    SOLVE = "solve"
    """Free practice: full implementation with the pattern known."""

    @property
    def trains(self) -> Dimension:
        return _MODE_DIMENSION[self]


_MODE_DIMENSION: dict[GameMode, Dimension] = {
    GameMode.HUNTER: Dimension.RECOGNITION,
    GameMode.DUEL: Dimension.RECOGNITION,
    GameMode.RECALL: Dimension.RECALL,
    GameMode.COMPLETE: Dimension.IMPLEMENTATION,
    GameMode.SOLVE: Dimension.IMPLEMENTATION,
    GameMode.BOSS: Dimension.IMPLEMENTATION,
}


class Verdict(StrEnum):
    """Judge outcome for a single test case or a whole submission."""

    ACCEPTED = "AC"
    WRONG_ANSWER = "WA"
    TIME_LIMIT = "TLE"
    MEMORY_LIMIT = "MLE"
    RUNTIME_ERROR = "RE"
    COMPILE_ERROR = "CE"
    OUTPUT_LIMIT = "OLE"
    INTERNAL_ERROR = "IE"
    """Sandbox or harness failure — never the submitter's fault, never counted against them."""

    @property
    def is_pass(self) -> bool:
        return self is Verdict.ACCEPTED

    @property
    def label(self) -> str:
        return _VERDICT_LABEL[self]


_VERDICT_LABEL: dict[Verdict, str] = {
    Verdict.ACCEPTED: "Accepted",
    Verdict.WRONG_ANSWER: "Wrong Answer",
    Verdict.TIME_LIMIT: "Time Limit Exceeded",
    Verdict.MEMORY_LIMIT: "Memory Limit Exceeded",
    Verdict.RUNTIME_ERROR: "Runtime Error",
    Verdict.COMPILE_ERROR: "Compilation Error",
    Verdict.OUTPUT_LIMIT: "Output Limit Exceeded",
    Verdict.INTERNAL_ERROR: "Judge Error",
}


class Rating(StrEnum):
    """FSRS review grade. Mirrors ``fsrs.Rating`` but keeps the domain library-free."""

    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"

    @property
    def fsrs_value(self) -> int:
        """1..4, the encoding the FSRS library and the literature use."""
        return _RATING_VALUE[self]


_RATING_VALUE: dict[Rating, int] = {
    Rating.AGAIN: 1,
    Rating.HARD: 2,
    Rating.GOOD: 3,
    Rating.EASY: 4,
}


class MistakeCode(StrEnum):
    """Controlled vocabulary of *why* an attempt failed.

    This exists so "your most common mistake" is a real query instead of an
    unimplementable promise. Free-text notes cannot be aggregated; these can.

    Codes are grouped by prefix:
      PATTERN_  chose the wrong pattern (the mistake this app is built to fix)
      INVARIANT_ right pattern, broken loop invariant
      BOUNDS_   right pattern, off-by-one / boundary handling
      CPP_      language- or STL-level error rather than an algorithmic one
      COMPLEX_  correct but too slow / too much memory
    """

    # --- pattern selection ---------------------------------------------------
    PATTERN_DP_OVER_GREEDY = "PATTERN_DP_OVER_GREEDY"
    PATTERN_GREEDY_OVER_DP = "PATTERN_GREEDY_OVER_DP"
    PATTERN_BRUTE_OVER_WINDOW = "PATTERN_BRUTE_OVER_WINDOW"
    PATTERN_PREFIX_OVER_WINDOW = "PATTERN_PREFIX_OVER_WINDOW"
    PATTERN_WINDOW_OVER_PREFIX = "PATTERN_WINDOW_OVER_PREFIX"
    PATTERN_SORT_OVER_HASH = "PATTERN_SORT_OVER_HASH"
    PATTERN_LINEAR_OVER_BINARY_SEARCH = "PATTERN_LINEAR_OVER_BINARY_SEARCH"
    PATTERN_DIRECT_OVER_SEARCH_ON_ANSWER = "PATTERN_DIRECT_OVER_SEARCH_ON_ANSWER"
    PATTERN_SEARCH_ON_ANSWER_OVER_DIRECT = "PATTERN_SEARCH_ON_ANSWER_OVER_DIRECT"
    """Reached for a feasibility predicate when the value was sitting in a sorted container."""
    PATTERN_PREFIX_OVER_HASH = "PATTERN_PREFIX_OVER_HASH"
    """Built prefix sums when the elements' adjacency was irrelevant and counting sufficed."""
    PATTERN_WINDOW_OVER_HASH = "PATTERN_WINDOW_OVER_HASH"
    """Maintained a window on a problem where order and adjacency did not matter."""
    PATTERN_BFS_OVER_DIJKSTRA = "PATTERN_BFS_OVER_DIJKSTRA"
    """An unweighted shortest path used where the edges have weights. The
    central mistake of the graph region, and the one that fails silently: a
    breadth-first sweep returns a path, and the path is real, and it is not
    the shortest one."""

    PATTERN_UNRECOGNISED = "PATTERN_UNRECOGNISED"

    # --- invariants ----------------------------------------------------------
    INVARIANT_WINDOW_NOT_SHRUNK = "INVARIANT_WINDOW_NOT_SHRUNK"
    INVARIANT_WINDOW_SHRUNK_TOO_FAR = "INVARIANT_WINDOW_SHRUNK_TOO_FAR"
    INVARIANT_STALE_DEQUE_INDEX = "INVARIANT_STALE_DEQUE_INDEX"
    INVARIANT_MISSING_VISITED_SET = "INVARIANT_MISSING_VISITED_SET"
    INVARIANT_WRONG_MONOTONIC_DIRECTION = "INVARIANT_WRONG_MONOTONIC_DIRECTION"
    INVARIANT_COUNTER_NOT_DECREMENTED = "INVARIANT_COUNTER_NOT_DECREMENTED"

    # --- boundaries ----------------------------------------------------------
    BOUNDS_BINARY_SEARCH_OFF_BY_ONE = "BOUNDS_BINARY_SEARCH_OFF_BY_ONE"
    BOUNDS_BINARY_SEARCH_INFINITE_LOOP = "BOUNDS_BINARY_SEARCH_INFINITE_LOOP"
    BOUNDS_PREFIX_INDEX_SHIFT = "BOUNDS_PREFIX_INDEX_SHIFT"
    BOUNDS_OFF_BY_ONE = "BOUNDS_OFF_BY_ONE"
    """A length used as an index or vice versa, a loop bound one out."""

    BOUNDS_MISSED_CASE = "BOUNDS_MISSED_CASE"
    """One of two symmetric cases handled and the other forgotten — even-length
    palindromes, the empty subarray, the single-node tree."""

    BOUNDS_EMPTY_INPUT = "BOUNDS_EMPTY_INPUT"
    BOUNDS_SINGLE_ELEMENT = "BOUNDS_SINGLE_ELEMENT"

    # --- C++ / STL -----------------------------------------------------------
    CPP_INT_OVERFLOW = "CPP_INT_OVERFLOW"
    CPP_ITERATOR_INVALIDATION = "CPP_ITERATOR_INVALIDATION"
    CPP_UNINITIALISED_VALUE = "CPP_UNINITIALISED_VALUE"
    CPP_OUT_OF_BOUNDS = "CPP_OUT_OF_BOUNDS"
    CPP_SLOW_IO = "CPP_SLOW_IO"
    CPP_UNORDERED_MAP_WORST_CASE = "CPP_UNORDERED_MAP_WORST_CASE"

    # --- complexity ----------------------------------------------------------
    COMPLEX_TOO_SLOW = "COMPLEX_TOO_SLOW"
    COMPLEX_TOO_MUCH_MEMORY = "COMPLEX_TOO_MUCH_MEMORY"
    COMPLEX_RECURSION_DEPTH = "COMPLEX_RECURSION_DEPTH"

    @property
    def is_pattern_choice(self) -> bool:
        """True when the mistake was picking the wrong tool, not misusing the right one."""
        return self.value.startswith("PATTERN_")
