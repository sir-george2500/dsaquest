"""Lessons: the teach -> drill -> trial -> final test loop."""

from . import final_test
from .plan import DrillVerdict, assess, check_answer, next_drill
from .session import DrillOutcome, Teaching, current_stage, deal, grade, greet, teach
from .trial import Trial, TrialVerdict, all_trials_passed, judge_trial, open_trial, pending_trial

__all__ = [
    "DrillOutcome",
    "DrillVerdict",
    "Teaching",
    "Trial",
    "TrialVerdict",
    "all_trials_passed",
    "assess",
    "check_answer",
    "current_stage",
    "deal",
    "final_test",
    "grade",
    "greet",
    "judge_trial",
    "next_drill",
    "open_trial",
    "pending_trial",
    "teach",
]
