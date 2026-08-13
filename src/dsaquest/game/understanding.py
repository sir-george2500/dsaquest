"""The understanding check — three questions asked *before* the code is judged.

    BEFORE SUBMISSION

      What is the key idea?               > ______________
      What is the expected complexity?    > ______________
      What invariant are you maintaining? > ______________

It exists for one failure mode: *"I memorised the code but have no idea why it
works."* A learner who has drilled a template can produce correct C++ with no
model of why it is correct, and every other signal in this product would call
that mastery.

**The order is the whole mechanism.** The answers are captured before the judge
runs, and cannot be edited afterwards. Asked the other way round, a wrong
verdict tells you your reasoning was wrong and a right one tells you it was
fine, so the answers stop being evidence about the learner and start being
evidence about the judge. Grading code and reasoning *independently* is what
lets "correct code, no idea why" be recorded as exactly that.

**How the grading works, and what it cannot do.** Every answer is matched
lexically against phrases the pattern's author wrote down — the same
``accepts`` machinery Mode B uses, so an author who improves the rubric
improves this too. Nothing here understands English. A learner who is right in
their own words and hits none of the phrases will be marked unsound, and that
is a false negative we accept knowingly, because the alternative — asking them
to grade themselves — is exactly the self-report the check exists to bypass.

What follows from that: **a failed check never blocks a submission, costs no
health and fails no exercise.** It is recorded, and the master says so. A
lexical matcher is not entitled to more authority than that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..domain.pattern import Pattern, RubricPoint
from .modes.recall import match_point

#: Answers shorter than this are treated as unanswered rather than wrong.
#: "idk", "-", "n" are refusals to engage, and scoring them as mistaken
#: reasoning would be a harsher reading than the learner gave us cause for.
MIN_ANSWER_CHARS = 4

#: Fraction of the invariant's distinctive words an answer must contain for the
#: prose fallback to fire. Only reached when no rubric point matched, so it is
#: deliberately conservative: a false positive here credits someone who
#: described a *different* pattern's invariant.
#:
#: Measured over the authored invariants: canonical text scores 1.00, another
#: pattern's invariant peaks at 0.33 (mean 0.05), and vague filler scores 0.00.
#: Set above that peak with margin, because content is still being written and
#: a threshold tuned to one point above the worst observed case is not a
#: threshold, it is a coincidence.
INVARIANT_OVERLAP = 0.45

#: Words carried by almost every invariant, so their presence says nothing.
_NOISE_WORDS = """
    that this with from have been they them then than when what which where
    into over each only ever every some more most much such very will would
    also both because before after while during about above below your
    thing things stuff exactly still cannot always never must does done
    element elements index indices value values array arrays
"""
_NOISE = frozenset(_NOISE_WORDS.split())

_BIG_O = re.compile(r"\b[o0]\s*\(([^)]*)\)", re.IGNORECASE)

#: Prose people write instead of a big-O expression.
_WORDED_COMPLEXITY = {
    "constant": "1",
    "linear": "n",
    "linearithmic": "nlogn",
    "loglinear": "nlogn",
    "logarithmic": "logn",
    "quadratic": "n^2",
    "cubic": "n^3",
    "exponential": "2^n",
    "factorial": "n!",
}


def _norm_term(inner: str) -> str:
    """Normalise the inside of a big-O so the forms people write compare equal.

    ``O(n log n)``, ``O(n*logn)``, ``O(N LOG N)`` and ``O(n lg n)`` are one
    claim written four ways. Base of the logarithm is deliberately erased:
    inside a big-O it is a constant factor, and a learner who writes ``log2``
    is not making a different claim.
    """
    text = inner.lower()
    text = text.replace("**", "^").replace("²", "^2").replace("³", "^3")
    text = re.sub(r"log_?2|log_?e|\blg\b|\bln\b", "log", text)
    text = re.sub(r"[\s*·×]+", "", text)
    text = text.replace("+", " + ").strip()
    return re.sub(r"\bn\^1\b", "n", text)


def big_o_terms(text: str) -> frozenset[str]:
    """Every complexity claim in a piece of text, normalised.

    A set rather than one value because the authored complexities are prose,
    not expressions — one pattern's reads ``"O(n) after sorting, so O(n log n)
    if you must sort; O(n^2) for the fix-one-then-converge form"``. All three
    are true of that pattern depending on the problem, so all three are
    accepted. Insisting on a single canonical answer would mark a correct
    learner wrong.
    """
    terms = {_norm_term(match.group(1)) for match in _BIG_O.finditer(text)}
    lowered = text.lower()
    for word, term in _WORDED_COMPLEXITY.items():
        if re.search(rf"\b{word}\b", lowered):
            terms.add(term)
    return frozenset(term for term in terms if term)


def _words(text: str) -> frozenset[str]:
    return frozenset(
        word
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if len(word) >= 4 and word not in _NOISE
    )


def _overlap(answer: str, canonical: str) -> float:
    """Fraction of the canonical text's distinctive words the answer contains."""
    wanted = _words(canonical)
    if not wanted:
        return 0.0
    return len(wanted & _words(answer)) / len(wanted)


@dataclass(frozen=True, slots=True)
class Question:
    key: str
    prompt: str

    @property
    def label(self) -> str:
        return self.prompt


#: Asked in this order, and always all three. Dropping one for a pattern where
#: it feels awkward would make the check's absence informative.
QUESTIONS: tuple[Question, ...] = (
    Question("key_idea", "What is the key idea?"),
    Question("complexity", "What is the expected complexity?"),
    Question("invariant", "What invariant are you maintaining?"),
)


@dataclass(frozen=True, slots=True)
class Answer:
    """What the learner stated, before seeing any verdict."""

    key_idea: str = ""
    complexity: str = ""
    invariant: str = ""

    def get(self, key: str) -> str:
        return str(getattr(self, key))

    @property
    def blank(self) -> bool:
        return not any(len(self.get(q.key).strip()) >= MIN_ANSWER_CHARS for q in QUESTIONS)


@dataclass(frozen=True, slots=True)
class PartVerdict:
    """How one of the three answers fared."""

    key: str
    prompt: str
    given: str
    answered: bool
    sound: bool
    matched: tuple[str, ...]
    """Rubric point keys this answer hit — the evidence for ``sound``."""

    expected: str
    """What the author says. Shown only after the check is closed."""


@dataclass(frozen=True, slots=True)
class UnderstandingVerdict:
    pattern_id: str
    parts: tuple[PartVerdict, ...]

    def part(self, key: str) -> PartVerdict:
        for part in self.parts:
            if part.key == key:
                return part
        raise KeyError(key)

    @property
    def answered(self) -> int:
        return sum(1 for p in self.parts if p.answered)

    @property
    def sound_count(self) -> int:
        return sum(1 for p in self.parts if p.sound)

    @property
    def score(self) -> float:
        return self.sound_count / len(self.parts) if self.parts else 0.0

    @property
    def sound(self) -> bool:
        """All three stated and all three recognisable."""
        return self.sound_count == len(self.parts)

    @property
    def skipped(self) -> bool:
        return self.answered == 0

    @property
    def weakest(self) -> tuple[PartVerdict, ...]:
        return tuple(p for p in self.parts if not p.sound)


def _complexity_points(pattern: Pattern) -> tuple[RubricPoint, ...]:
    return tuple(p for p in pattern.recall_rubric if "complex" in p.key.lower())


def _invariant_points(pattern: Pattern) -> tuple[RubricPoint, ...]:
    """Points that speak to the invariant.

    Only two patterns key a point ``invariant`` outright; the rest carry the
    same claim under a name of their own (``half-open-invariant``,
    ``query-before-insert``, ``discard-argument``). Those are the *essential*
    points by construction — an essential point is exactly one the author
    considered load-bearing — so the essentials stand in when no point is
    named for the invariant.
    """
    named = tuple(p for p in pattern.recall_rubric if "invariant" in p.key.lower())
    return named or pattern.essential_rubric


def _grade_one(
    question: Question,
    given: str,
    *,
    points: tuple[RubricPoint, ...],
    sound: bool,
    expected: str,
) -> PartVerdict:
    matched = tuple(p.key for p in points if match_point(p, given))
    answered = len(given.strip()) >= MIN_ANSWER_CHARS
    return PartVerdict(
        key=question.key,
        prompt=question.prompt,
        given=given.strip(),
        answered=answered,
        sound=answered and sound,
        matched=matched,
        expected=expected,
    )


def grade_understanding(pattern: Pattern, answer: Answer) -> UnderstandingVerdict:
    """Grade the three statements against what the pattern's author wrote down.

    Never raises on a blank or nonsense answer: an unanswered check is a real
    and different outcome from a wrong one, and both are recorded.
    """
    key_idea = answer.key_idea
    complexity = answer.complexity
    invariant = answer.invariant

    # The key idea is the approach in one line, so any rubric point it lands on
    # is evidence — this is the most forgiving of the three on purpose. It is
    # asked first, and starting with a question that fails most learners would
    # teach them to skip the check.
    idea_points = pattern.recall_rubric

    complexity_points = _complexity_points(pattern)
    complexity_sound = any(match_point(p, complexity) for p in complexity_points) or bool(
        big_o_terms(complexity) & big_o_terms(pattern.complexity.time)
    )

    invariant_points = _invariant_points(pattern)
    invariant_sound = any(match_point(p, invariant) for p in invariant_points) or (
        _overlap(invariant, pattern.invariant) >= INVARIANT_OVERLAP
    )

    return UnderstandingVerdict(
        pattern_id=pattern.id,
        parts=(
            _grade_one(
                QUESTIONS[0],
                key_idea,
                points=idea_points,
                sound=any(match_point(p, key_idea) for p in idea_points),
                expected=pattern.tagline,
            ),
            _grade_one(
                QUESTIONS[1],
                complexity,
                points=complexity_points,
                sound=complexity_sound,
                expected=f"{pattern.complexity.time} time, {pattern.complexity.space} space",
            ),
            _grade_one(
                QUESTIONS[2],
                invariant,
                points=invariant_points,
                sound=invariant_sound,
                expected=pattern.invariant,
            ),
        ),
    )


def hollow(verdict: UnderstandingVerdict, *, code_correct: bool) -> bool:
    """Correct code, unsound reasoning — the thing this check exists to catch."""
    return code_correct and not verdict.sound


def remark(verdict: UnderstandingVerdict, *, code_correct: bool) -> str:
    """What a master says about the reasoning, independent of the code."""
    if verdict.skipped:
        return (
            "You submitted without saying what you were doing. "
            "The code may stand; the understanding is unproven."
            if code_correct
            else "You said nothing about your reasoning, and the code did not hold."
        )
    if verdict.sound:
        return (
            "You said what you were doing before you did it, and you were right."
            if code_correct
            else "Your reasoning was sound. The implementation is what failed — "
            "that is the easier of the two to fix."
        )
    missed = ", ".join(p.key.replace("_", " ") for p in verdict.weakest)
    if code_correct:
        return (
            f"The code is correct and you could not state the {missed}. "
            "That is memorised, not understood, and it will not survive a "
            "problem that is shaped differently."
        )
    return f"The code did not hold, and neither did the {missed}."
