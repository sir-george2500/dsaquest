# DSA Quest

A terminal game that trains **pattern recognition** for competitive-programming
C++ — not a problem archive.

It exists to answer one question, over and over, until the answer is automatic:

> *Can I recognise this pattern when the problem doesn't tell me which one to use?*

## The idea

Most practice tools test whether you can solve a problem you already know the
category of. That trains the wrong half of the skill. DSA Quest never shows you
a pattern label before you've committed to a guess, and it schedules patterns
back at you as your memory of them decays.

Three things you can be good or bad at, tracked and scheduled **independently**,
because they decay at different rates:

| Dimension | Question | Trained by |
|---|---|---|
| **Recognition** | Can I name the pattern from an unlabelled statement? | Pattern Hunter, Duel |
| **Recall** | Given the name, can I produce the signals, invariant, complexity, template? | Pattern Recall |
| **Implementation** | Can I write correct C++ under time? | Code Completion, Boss Fight |

You can keep recognising Monotonic Stack long after you've lost the ability to
write one. One "mastery" number hides that. Three cards don't.

## Status

Early. Phase 1 (MVP) in progress — see `docs/architecture.md` for the plan.

- [x] Domain model
- [x] Sandboxed C++ judge
- [ ] Content: 6 patterns
- [ ] Storage
- [ ] FSRS scheduling
- [ ] Game modes
- [ ] TUI

## Requirements

- Linux with cgroup v2 and unprivileged user namespaces
- `g++` (C++20), `bubblewrap`, `util-linux`
- Python 3.11+
- Optional: `nvim` — full solves hand off to `$EDITOR` with a generated
  `compile_commands.json`, so clangd sees exactly the flags the judge uses

```bash
sudo pacman -S bubblewrap util-linux gcc   # Arch
```

## Install

```bash
git clone <repo> && cd dsa-quest
uv venv && uv pip install -e ".[dev]"
```

## Run

```bash
dsa              # interactive
dsa practice     # a session picked by the scheduler
dsa review       # only what's due
dsa stats        # progress and weakest patterns
dsa pattern sliding-window
```

## Test

```bash
pytest                    # everything
pytest -m "not slow"      # skip the ones that compile C++
pytest tests/security     # sandbox escape attempts
```

## Architecture

```
tui/ cli/          Textual screens; Typer commands (lazy — `dsa stats` never imports Textual)
   ↓
game/              modes, XP, levels, streaks, unlocks
learning/          FSRS scheduling, mastery model, recommendations
   ↓
content/           YAML patterns and problem templates, seeded instantiation
judge/             sandboxed compile + run
storage/           SQLite repositories
   ↓
domain/            pure types — imports nothing internal
```

Content lives in versioned YAML under `content/`; SQLite holds **only user
state**. Editing a problem never requires a migration, and your progress
survives content updates.

See `docs/architecture.md`.

## Licence

MIT
