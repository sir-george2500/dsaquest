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

**Playable end to end.** 1238 tests.

- [x] Domain model
- [x] Sandboxed C++ judge — cgroups + bubblewrap + rlimits, ~9 ms overhead
- [x] Content: 39 patterns, 189 problems, 41 templates, 9 concept animations
- [x] SQLite storage + migrations
- [x] FSRS-6 scheduling and the mastery model
- [x] Game engine: XP, levels, streaks, unlocks, achievements
- [x] All five modes — Hunter, Recall, Completion, Duel, Boss Fight
- [x] 11 masters with full curricula, 12 guardians including the Elite Coder
- [x] Story mode: a prologue, 11 chapters, and a journey that always knows
      what comes next
- [x] The Codex — each master's biography, school, legend and failure,
      opening as you earn your way in
- [x] Masters who diagnose *which* of the three dimensions is holding you
      back, in their own voice
- [x] Textual TUI + CLI, nvim workspace handoff

- [x] Masters who go back a step when you are stuck, rather than pressing the
      same drill you keep failing

Known gap: 14 more problems would let every trial and final test draw something
you have not already seen. Until then a trial may reuse a problem you have met.

### The eleven regions

Ordered for teaching, not by difficulty. The clusters are chosen to be
*confusable* — mixing them up is the exact failure this app exists to fix.

```
I    The Warrior Awakens     Elder Vhast          constraints and estimation
II   The Straight Line       Warden Ilsa Korrin   arrays, prefix sums, windows
III  The Halving             Adjudicator Kol      binary search, on data and answer
IV   The Unlit               Grandmaster Ragine   bitmasks and subset DP
V    The Standing Record     Keeper Maelin Vore   heaps, ordered sets, Fenwick, segment trees
VI   The One Swap            Strategist Dovan Rhe greedy and exchange arguments
VII  The Unrooted            Sage Orenna Thal     trees, diameters, binary lifting
VIII The Second Reading      Scribe Halvern Ash   strings, hashing, tries, Manacher
IX   The Long Way Round      Warlord Grune        graphs, BFS/DFS, Dijkstra, toposort
X    The Last Safe Number    Oracle Cassiun       modular arithmetic, sieves, gcd
XI   The Kept Answer         Archivist Solvane    dynamic programming
XII  The True Secret         THE ELITE CODER      everything, unlabelled
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

## Play

```bash
dsa
```

That is the whole of it. The first run opens the prologue, asks your name, and
puts you on the road; every run after that resumes exactly where you stopped.

The home screen always leads with **one** action — *Continue Journey* — and it
is always the right one. Take it and the game decides whether you are meeting a
master, training under them, sitting a trial, facing their guardian, or walking
into the next region. You never have to work out what to do next.

| Key | |
|---|---|
| `enter` or `1` | Continue Journey — the only thing you need |
| `2` | The road: every chapter, its master and its guardian |
| `3` | Training grounds — free practice |
| `4` | Review what is due |
| `5` | Pattern Duel — two statements that want to be confused |
| `6` | Roster — the character cards |
| `7` | Codex — who the masters are, as you earn it |
| `q` | Quit. Progress is saved continuously; there is no save command |

Inside a lesson, `w` plays the concept animation for the idea being taught —
the same idea, moving, before anyone asks you to reproduce it.

Other entry points, if you want to skip the story and drill:

```bash
dsa practice     # a session the scheduler picked
dsa review       # only what is due today
dsa stats        # progress and weakest patterns
dsa pattern sliding-window
dsa doctor       # check the sandbox and toolchain
```

### Make it look right

The art is half-block pixel work, so it wants a font with square-ish cells and
no ligature surprises. Monaspace Xenon is what it was drawn against:

```bash
yay -S ttf-monaspace          # Arch (AUR)
```

Then set your terminal font to **Monaspace Xenon**. Anything monospaced works;
this one is what the portraits were tuned for.

A terminal of at least **100×34** gets the full layout — portraits, the arena
floor, the side dossiers. Below that the game drops the art rather than
cropping it, and stays fully playable down to 80×24.

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
pytest                    # everything — about an hour, 514 of these compile C++
pytest -m "not slow"      # the other 722, about fifteen minutes
pytest tests/e2e          # the game driven through its real screens
pytest tests/security     # sandbox escape attempts
```

The suite leans on **end-to-end** tests: they drive the real Textual screens
against a real database and a real C++ judge, because that is where the bugs
actually were. A unit test would not have caught a boss whose explain phase was
unanswerable, or a portrait whose bottom border was cropped on every master.

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
