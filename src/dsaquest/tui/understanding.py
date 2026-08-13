"""The BEFORE SUBMISSION panel.

One widget, mounted by every screen that judges code, so the three questions
are asked identically everywhere. A learner should not be able to tell from the
phrasing whether they are in a trial or a boss fight.

The fields carry ``name`` rather than ``id``. Ids must be unique across the
whole app, and this panel is mounted, removed and mounted again within a single
fight — Textual defers ``remove_children()``, so an id-based panel collides
with the one it is replacing. ``name`` has no such constraint and is what
``answer()`` reads.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Button, Input, Static

from ..game.understanding import QUESTIONS, Answer

UNDERSTANDING_CSS = """
UnderstandingPanel { height: auto; padding: 1 2; margin: 1 2; border: round $warning; }
UnderstandingPanel > Static.uc-head { text-style: bold; padding: 0 0 1 0; }
UnderstandingPanel > Static.uc-prompt { padding: 1 0 0 0; }
UnderstandingPanel > Input { margin: 0; }
UnderstandingPanel > Button { width: 100%; margin: 1 0 0 0; }
"""


class UnderstandingPanel(Vertical):
    """Three questions, asked before the code is judged."""

    class Submitted(Message):
        def __init__(self, answer: Answer) -> None:
            super().__init__()
            self.answer = answer

    def __init__(self, *, note: str = "") -> None:
        super().__init__()
        self.note = note

    def compose(self) -> ComposeResult:
        yield Static("BEFORE SUBMISSION", classes="uc-head")
        if self.note:
            yield Static(self.note, classes="uc-prompt")
        for question in QUESTIONS:
            yield Static(question.prompt, classes="uc-prompt")
            yield Input(name=question.key, classes="uc-field")
        yield Button("Commit and be judged", classes="uc-commit")

    def on_mount(self) -> None:
        first = self.query(Input).first()
        if first is not None:
            first.focus()

    def answer(self) -> Answer:
        values = {field.name: field.value for field in self.query(Input) if field.name}
        return Answer(**{question.key: values.get(question.key, "") for question in QUESTIONS})

    def commit(self) -> None:
        self.post_message(self.Submitted(self.answer()))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.has_class("uc-commit"):
            event.stop()
            self.commit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter moves to the next field, and commits from the last one."""
        event.stop()
        fields = list(self.query(Input))
        index = fields.index(event.input)
        if index + 1 < len(fields):
            fields[index + 1].focus()
        else:
            self.commit()
