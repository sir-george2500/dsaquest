"""The boundary between our persistence and the FSRS library.

Why FSRS-6 rather than SM-2
---------------------------
SM-2 compresses a card's whole memory into one "ease factor" multiplier. Every
lapse ratchets that factor down and nothing lifts it back up, so difficult
material spirals into ever-shorter intervals — the well-documented *ease hell*.
It also cannot answer "how likely am I to recall this right now?", because it
has no model of forgetting, only a multiplier.

FSRS models three quantities explicitly — Difficulty, Stability, Retrievability
— under a power-law forgetting curve fitted to very large review-log corpora.
Two consequences matter here:

* You state a **target retention** and it schedules to hit it, instead of you
  guessing interval multipliers.
* ``R(t)`` is a real probability of recall right now, which is exactly the
  "Retention: 76%" figure the mastery screen wants. It falls out of the model
  rather than being invented.

Three cards per pattern
-----------------------
Recognition, recall and implementation get *independent* memory states. They
decay at genuinely different rates — you can still spot a monotonic-stack
problem long after you have lost the ability to write one — and a single card
per pattern averages that distinction away, scheduling you on a number that
describes none of your three abilities.

Determinism
-----------
FSRS fuzzes intervals by default to stop reviews clumping. Fuzzing is disabled
in tests so the scheduler is reproducible, and left on in normal use.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fsrs import Card as FsrsCard
from fsrs import Rating as FsrsRating
from fsrs import Scheduler, State

from ..domain.enums import Rating
from ..storage.repositories import CardRecord

#: Our persisted state strings, which are exactly FSRS's minus a "new" that
#: FSRS does not have. See storage.schema for why.
_STATE_TO_FSRS = {
    "learning": State.Learning,
    "review": State.Review,
    "relearning": State.Relearning,
}
_FSRS_TO_STATE = {v: k for k, v in _STATE_TO_FSRS.items()}

_RATING_TO_FSRS = {
    Rating.AGAIN: FsrsRating.Again,
    Rating.HARD: FsrsRating.Hard,
    Rating.GOOD: FsrsRating.Good,
    Rating.EASY: FsrsRating.Easy,
}


def make_scheduler(target_retention: float = 0.90, *, fuzz: bool = True) -> Scheduler:
    """Build a scheduler for a given target retention.

    Lower retention means longer intervals and more forgetting; higher means
    more reviews for the same material. 0.90 is the well-trodden default and a
    sane place to stay unless the learner has a reason to move.
    """
    if not 0.7 <= target_retention <= 0.98:
        raise ValueError(
            f"target retention {target_retention} is outside the useful range 0.70-0.98"
        )
    return Scheduler(desired_retention=target_retention, enable_fuzzing=fuzz)


def _parse(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    # FSRS requires timezone-aware datetimes; a naive one silently misdates.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def to_fsrs(record: CardRecord) -> FsrsCard:
    """Rebuild the library's card from our row.

    ``step`` is carried across deliberately — without it every load restarts the
    learning phase, and nothing ever graduates to review.
    """
    return FsrsCard(
        card_id=record.id,
        state=_STATE_TO_FSRS[record.state],
        step=record.step,
        stability=record.stability,
        difficulty=record.difficulty,
        due=_parse(record.due_at),
        last_review=_parse(record.last_review_at),
    )


def apply_review(
    conn,
    record: CardRecord,
    rating: Rating,
    *,
    scheduler: Scheduler,
    mode,
    now: datetime | None = None,
    attempt_id: int | None = None,
    duration_ms: int | None = None,
) -> CardRecord:
    """Advance a card by one review, persisting both the new state and the log.

    ``reps`` and ``lapses`` are ours to maintain — ``fsrs.Card`` tracks neither.
    A lapse is specifically *forgetting something you had learned*: an ``Again``
    on a card that had reached Review. An ``Again`` during initial learning is
    not a lapse, and counting it as one would make every new pattern look
    fragile.

    The card update and the review-log insert go in one transaction: a crash
    between them would leave a schedule that the log cannot explain, which is
    precisely the corruption the FSRS optimiser cannot recover from.
    """
    from ..storage.db import transaction
    from ..storage.repositories import log_review, update_card

    at = now or datetime.now(UTC)
    before = to_fsrs(record)
    was_in_review = record.state == "review"

    elapsed_days: float | None = None
    if record.last_review_at is not None:
        last = _parse(record.last_review_at)
        assert last is not None
        elapsed_days = (at - last).total_seconds() / 86400

    scheduled_days: float | None = None
    if record.last_review_at is not None:
        due = _parse(record.due_at)
        last = _parse(record.last_review_at)
        assert due is not None and last is not None
        scheduled_days = (due - last).total_seconds() / 86400

    after, _ = scheduler.review_card(before, _RATING_TO_FSRS[rating], review_datetime=at)

    is_lapse = rating is Rating.AGAIN and was_in_review
    reps = record.reps + 1
    lapses = record.lapses + (1 if is_lapse else 0)

    with transaction(conn):
        update_card(
            conn,
            record.id,
            state=_FSRS_TO_STATE[after.state],
            step=after.step,
            stability=after.stability,
            difficulty=after.difficulty,
            due_at=after.due.isoformat(timespec="seconds"),
            last_review_at=at.isoformat(timespec="seconds"),
            reps=reps,
            lapses=lapses,
        )
        log_review(
            conn,
            card_id=record.id,
            rating=rating,
            mode=mode,
            attempt_id=attempt_id,
            elapsed_days=elapsed_days,
            scheduled_days=scheduled_days,
            duration_ms=duration_ms,
            reviewed_at=at.isoformat(timespec="seconds"),
        )

    return CardRecord(
        id=record.id,
        pattern_id=record.pattern_id,
        dimension=record.dimension,
        state=_FSRS_TO_STATE[after.state],
        step=after.step,
        stability=after.stability,
        difficulty=after.difficulty,
        due_at=after.due.isoformat(timespec="seconds"),
        last_review_at=at.isoformat(timespec="seconds"),
        reps=reps,
        lapses=lapses,
    )


def retrievability(
    record: CardRecord,
    *,
    scheduler: Scheduler,
    now: datetime | None = None,
) -> float:
    """Probability of successful recall right now, in [0, 1].

    A never-reviewed card returns 0.0: there is no memory to retrieve, which is
    different from a forgotten one only in how it got there.
    """
    if record.is_new or record.stability is None:
        return 0.0
    return float(scheduler.get_card_retrievability(to_fsrs(record), now or datetime.now(UTC)))


def stability_days(record: CardRecord) -> float:
    """Days until recall probability decays to the target. 0 for unseen cards."""
    return float(record.stability or 0.0)


def next_interval(record: CardRecord, *, now: datetime | None = None) -> timedelta:
    """How long until this card is due. Negative when overdue."""
    due = _parse(record.due_at)
    assert due is not None
    return due - (now or datetime.now(UTC))


def preview(
    record: CardRecord,
    *,
    scheduler: Scheduler,
    now: datetime | None = None,
) -> dict[Rating, timedelta]:
    """What each possible rating would do to this card's interval.

    Shown after an exercise so the learner can see the consequence of the grade
    they were given — the scheduling stops being a black box.
    """
    at = now or datetime.now(UTC)
    out: dict[Rating, timedelta] = {}
    for rating, fsrs_rating in _RATING_TO_FSRS.items():
        updated, _ = scheduler.review_card(to_fsrs(record), fsrs_rating, review_datetime=at)
        out[rating] = updated.due - at
    return out
