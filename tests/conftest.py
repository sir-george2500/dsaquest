"""Shared test setup.

One thing lives here: the prologue does not open by itself. A never-played
profile is shown the story unasked, which is right for a player and wrong for
a test — every test builds a fresh database, so every test would land on the
prologue instead of the screen it came to exercise. The tests that are about
the prologue switch it back on for themselves.
"""

from __future__ import annotations

import pytest

from dsaquest.tui.app import DsaQuestApp


@pytest.fixture(autouse=True)
def _no_prologue_by_default(monkeypatch):
    monkeypatch.setattr(DsaQuestApp, "auto_story", False)
