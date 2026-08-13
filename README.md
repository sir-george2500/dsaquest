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

**Phase 1 (MVP) complete and playable.** 283 tests.

- [x] Domain model
- [x] Sandboxed C++ judge — cgroups + bubblewrap + rlimits, ~9 ms overhead
- [x] Content: 6 patterns, 23 problems, 18 cloze holes
- [x] SQLite storage + migrations
- [x] FSRS-6 scheduling and the mastery model
- [x] Game engine: XP, levels, streaks, unlocks, achievements
- [x] Mode A (Pattern Hunter) and Mode C (Code Completion)
- [x] Textual TUI + CLI
- [x] nvim workspace handoff

Next: Modes B (Pattern Recall), D (Duel) and E (Boss Fight); the remaining
27 patterns; live-reload watch mode.

### The six MVP patterns

Chosen as the most *confusable* cluster rather than the easiest — mixing these
up is the exact failure this app exists to fix.

```
World 1   Hashing & Frequency · Prefix Sums & Difference Arrays
          Two Pointers · Sliding Window
World 2   Binary Search on Sorted Data · Binary Search on the Answer
```

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
git clone git@github.com:sir-george2500/dsaquest.git && cd dsaquest
uv tool install --editable .
```

That puts `dsa` in `~/.local/bin`, so it works from any directory. `--editable`
means edits to the source and to `content/` take effect immediately, with no
reinstall.

If `dsa: command not found` afterwards, `~/.local/bin` is not on your `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"    # add to your shell profile
```

Verify with `dsa doctor`.

### For working on the project itself

A separate dev environment, needed to run the tests:

```bash
uv venv && uv pip install -e ".[dev]"
```

Note this one does **not** put `dsa` on your `PATH` — it lives at
`.venv/bin/dsa` and only works inside the project directory.

## Run

```bash
dsa              # interactive
dsa practice     # a session picked by the scheduler
dsa review       # only what's due
dsa stats        # progress and weakest patterns
dsa pattern sliding-window
```

## Documentation

```bash
make install-man
export MANPATH="$HOME/.local/share/man:$MANPATH"   # add to your shell profile

man dsa            # commands, options, key bindings, verdicts, XP table
man 7 dsa-quest    # mastery model, scheduler, incentives, threat model
```

Both pages are written to be **grepped**. Hyphenation and justification are
disabled so no word breaks across a line, and every searchable fact is repeated
unformatted in a `QUICK REFERENCE` block — bold and italic render as overstrike
sequences that a plain `grep` cannot match.

```bash
man dsa | grep -i "verdict MLE"
man dsa | grep -i "level 30"
man 7 dsa-quest | grep -i fork-bomb
man dsa | col -b | grep -i memory       # to search the formatted sections too
```

Note: OpenSSL also ships a `dsa(1ssl)` page. `make install-man` indexes ours so
`man dsa` resolves here; `man 7 dsa-quest` is unambiguous either way.

## Test

```bash
pytest                    # everything
pytest -m "not slow"      # skip the ones that compile C++
pytest tests/security     # sandbox escape attempts
make test-fast            # same, skipping the C++ compilation tests
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
