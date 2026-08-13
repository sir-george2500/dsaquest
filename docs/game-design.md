# DSA Warrior — Game Design

The design document for the warrior-journey layer. Written after the codebase
audit and the Competitive Programmer's Handbook curriculum audit.

---

## 0. What this product is

> A daily training ritual that makes you measurably faster at recognising and
> implementing competitive-programming patterns in C++, wrapped in a warrior's
> journey brutal enough that you want to come back tomorrow.

Two engines, and they must never be confused:

| | Purpose | Owns |
|---|---|---|
| **Learning engine** | Creates competence | FSRS scheduling, mastery, retention, difficulty adaptation |
| **Game engine** | Creates motivation | Masters, respect, bosses, HP, arcs, dialogue, timers |

**The one rule everything obeys:** the game layer *wraps* the learning loop and
never replaces it. Every dramatic element must be a faithful rendering of a real
measurement. A master who says "pathetic" when you actually performed well
destroys the only thing that makes the harshness bearable — that it is *true*.

Corollary: no dialogue line, HP number, or boss gate may be driven by anything
other than measured performance.

---

## 1. Curriculum: 30 families, ~90 techniques

The handbook has 30 chapters. That is a happy accident worth exploiting: **one
core family per chapter**, each expanding into techniques, algorithms and
archetypes.

```
FAMILY (30)  →  TECHNIQUE (~90)  →  ARCHETYPE  →  VARIANT  →  BOSS
```

### Mapping, with current status

| Region | CPH ch. | Families | Status |
|---|---|---|---|
| **The Village** | 1–2 | Complexity estimation, C++ fundamentals | MISSING |
| **Plains of Arrays** | 3, 4, 8, 9.1 | Sorting-as-preprocessor, Hashing ✓, Prefix sums ✓, Two pointers ✓, Sliding window ✓, Monotonic stack/deque | 4 of 6 ✓ |
| **Halls of Search** | 3.3, 5 | Binary search ✓, Search on answer ✓, Complete search, Backtracking, Meet in the middle | 2 of 5 ✓ |
| **Vault of Structures** | 4, 9.2–9.4 | Ordered sets, Heaps, Fenwick tree, Segment tree, Sparse table | MISSING |
| **Ridge of Greed** | 6 | Exchange argument, Scheduling, Deadlines, Huffman | MISSING |
| **Forest of Trees** | 14, 15, 18 | Tree DFS/BFS, Diameter, Rerooting, DSU, MST, LCA, Euler tour | MISSING |
| **Sea of Graphs** | 11–13, 16, 17, 19, 20 | Representation, Traversal, Toposort, DAG DP, Cycle detection, Dijkstra, Bellman-Ford, Floyd-Warshall, SCC, Euler paths, Flows, Matching | MISSING |
| **The Forbidden Art** | 7, 10.5 | 1-D DP, Knapsack, LIS, Grid DP, Edit distance, Interval DP, Tree DP, Bitmask DP | MISSING |
| **Temple of Numbers** | 21–24 | Primes, Modular arithmetic, Combinatorics, Inclusion-exclusion, Matrices, Probability, Markov | MISSING |
| **Library of Strings** | 26 | Trie, String hashing, Z-algorithm, KMP | MISSING |
| **Summit of the Seven** | 25, 27–30 | Game theory, Sqrt decomposition, Mo's, Lazy segment trees, Geometry, Sweep line | MISSING |

**Current coverage: 6 techniques of ~90. 4 of 30 chapters, all partial.**

Bit manipulation (ch. 10) is a *cross-cutting* family, taught inside Vault of
Structures and The Forbidden Art rather than as a region.

---

## 2. The world

```
                        THE ELITE CODER
                              ▲
                     [ THE FINAL GATE ]
                              │
              ┌───────────────┴───────────────┐
        LEGENDARY: THE SEVEN            LEGENDARY: THE VOID
              │                               │
        Summit of the Seven          Library of Strings
        Temple of Numbers                     │
              └───────────────┬───────────────┘
                              │
                   THE FORBIDDEN ART  (DP)
                              │
                      SEA OF GRAPHS
                              │
                     FOREST OF TREES
                              │
        ┌─────────────────────┼─────────────────────┐
   RIDGE OF GREED      VAULT OF STRUCTURES     HALLS OF SEARCH
        └─────────────────────┼─────────────────────┘
                              │
                      PLAINS OF ARRAYS
                              │
                        THE VILLAGE
```

Regions after the Plains open **in parallel**, not in a line. The prerequisite
DAG already implemented drives this — you are never made to grind an unrelated
region to reach the one you want.

### Arcs

| Arc | Regions | New mechanic introduced |
|---|---|---|
| I — The Awakening | Village, Plains | Recognition. No timer. |
| II — The First Master | Halls of Search | **Timer appears.** Master Trials. |
| III — The Hidden Patterns | Structures, Greed | **Hidden pattern.** Duels. |
| IV — The Forest and the Sea | Trees, Graphs | **Multi-pattern bosses.** Phases. |
| V — The Forbidden Art | DP | **Enrage.** Explain-before-implement. |
| VI — The Seven Masters | Numbers, Strings, Summit | **Legendary bosses.** No hints. |
| Final — The Elite Coder | — | **Held-out problems.** Nothing familiar. |

---

## 3. The three currencies — kept distinct on purpose

Three numbers is one too many unless each answers a different question.

| | Question it answers | Behaviour | Gates progression? |
|---|---|---|---|
| **Mastery** | *Can I actually do this?* | FSRS-derived, **decays**, per pattern per dimension | **Yes — the only thing that does** |
| **Respect** | *What have I proven to this master?* | Per master, **monotonic**, difficulty-weighted, diminishing returns | No — governs dialogue, rematches, prestige |
| **XP / Level** | *How far along am I?* | Global, monotonic, paces the campaign | No |

**Respect does not open doors. Mastery does.** Respect is how the master *talks*
to you — it is the narrative memory of what you have done, and it must never
decay, because a master forgetting your victories is not ruthless, it is broken.

Respect is difficulty-weighted with diminishing returns so grinding Tier-1
content cannot buy Tier-4 standing:

```
respect_gain = base(outcome) × difficulty_weight × 0.6^(times_at_this_tier_today)
```

Failure costs respect (−1) but **never mastery and never XP**. You cannot be
made worse by trying.

---

## 4. Timer and pressure

### Adaptive limits

```
limit = base(mode, difficulty) × personal_factor × pressure_stage_factor
```

- `base` — the table from the spec (recognition 30–180 s, implementation 5–40 min)
- `personal_factor` — clamped to [0.7, 1.5], derived from your median time on
  that mode/difficulty. The system learns your normal speed and then squeezes.
- `pressure_stage_factor` — 1.0 calm → 0.75 ruthless → 0.6 boss

The clamp matters. Without a floor, a fast player spirals into impossible limits;
without a ceiling, a slow player never feels pressure.

### The five pressure stages

| Stage | Timer | Hints | Pattern shown |
|---|---|---|---|
| 1 Calm Training | none | free | yes |
| 2 Timed Training | generous | free | yes |
| 3 Ruthless Training | tight | costed | yes |
| 4 Master Trial | tight | one only | **hidden** |
| 5 Boss Fight | tight | none | **hidden**, multi-pattern |

A pattern advances stages as its own mastery rises. Stages are per-pattern, not
global — you can be at Stage 4 on Two Pointers and Stage 1 on DP.

### Time is a learning metric, not a punishment

Instrumented phases, with explicit transitions in the UI:

```
recognise  → the moment you commit to a pattern
plan       → until you start typing
implement  → until first submission
debug      → from first failed submission to acceptance
```

Debug time only exists after a failed submission, which makes it the sharpest
diagnostic we have: high debug time means you code before you think.

```
TIME ANALYSIS
  Pattern recognition   0:31   (target 0:45)  ✓
  Planning              0:58   (target 1:00)  ✓
  Implementation        4:12   (target 2:30)  ✗
  Debugging             1:08   (target 0:45)  ✗
  Total                 6:49   (target 6:00)

  Your bottleneck is implementation speed, not recognition.
  You knew the pattern in 31 seconds and then took four minutes to type it.
  → Code Completion drills on this pattern's template
```

### Timeout is not a memory failure

**This is load-bearing.** A timeout means you were slow, not that you forgot.
Rating a timeout as `Again` would tell FSRS you have lost a pattern you actually
know, corrupting the schedule.

```
outcome            recognition card    implementation card
correct, fast      Easy                Easy
correct, slow      Good                Hard
TIMEOUT            Hard                Hard          ← never Again
wrong answer       Again               Again
judge failure      no rating           no rating
```

Timeouts hurt **respect and score**, not the memory model.

---

## 5. Boss engine

### Tiers

| Tier | Name | Tests | Gate to |
|---|---|---|---|
| 1 | Training Bosses | one foundational pattern | next pattern group |
| 2 | Pattern Bosses | a family, pattern hidden | next region |
| 3 | Algorithm Masters | multiple concepts composed | next arc |
| 4 | Elite Warriors | multi-pattern + traps + tight constraints | legendary path |
| 5 | Legendary Bosses | a whole discipline at depth | **The Final Gate** |
| ∞ | The Elite Coder | everything, nothing familiar | — |

### Gates come before the fight, not during it

**Boss HP is drama; the mastery gate is the actual test.** If HP alone decided
victory, a weak player could grind attempts until they got lucky. So:

- The gate (§4 of your spec — recognition ≥ X%, retention ≥ Y%, trial passed)
  must be satisfied *before the fight is unlocked at all*.
- Inside the fight, HP is a scoring and tension device.

This is why the requirements panel exists: it tells you exactly what remains.

### Phases and HP

```
PHASE 1  Identify the pattern          boss −10 HP
PHASE 2  Explain the approach          boss −10 HP
PHASE 3  Choose structure + complexity boss −10 HP
PHASE 4  Implement                     boss −30 HP
PHASE 5  Survive hidden tests          boss −30 HP
         (optimise, when applicable)   boss −20 HP
```

A mistake costs player HP, time, or a hint — it does **not** end the fight.
Reaching 0 player HP ends the attempt, and the attempt is logged with a full
failure diagnosis. Bosses are always retryable; nothing is ever lost permanently.

### Enrage removes safety, never accelerates the clock

Accelerating a timer punishes careful thought, which is the opposite of what
§8 asks the game to teach. Enrage instead:

- disables remaining hints
- reveals the hidden test count so you feel the exposure
- doubles respect loss on failure and doubles it on victory

Fair, dramatic, and it does not make a slow thinker permanently unable to finish.

### Rematch and victory tiers

| Victory | Condition |
|---|---|
| Normal | boss defeated |
| Strong | ≤ 1 hint |
| Perfect | no hints, no wrong answers, no failed submissions, within target time |
| Legendary | Perfect + under target time + hard variant |

Defeated bosses stay available for Rematch / Speed Trial / No-Hint Trial. Every
rematch draws a **generated variant** — same underlying skill, different
narrative skin, constraints and input. The parameterised-problem machinery and
the differential-judging oracle already built are exactly what this needs.

---

## 6. The Elite Coder needs a held-out problem set

This is the design consequence of your final-boss philosophy, and it changes
what content we must author.

> "You have been training against problems that prepared you for me.
>  I will not give you a familiar pattern. I will give you a problem."

If the Elite Coder draws from the same pool as training, it is not testing
transfer — it is testing recall of the pool. So:

- **A reserved set of problems, never shown in training, at any stage.**
- Composed from families in unusual combinations.
- No `signals_present` shown, no hint ladder, no pattern name, ever.
- Content validation must *enforce* the reservation, so a future author cannot
  accidentally leak an Elite Coder problem into the training rotation.

This is the thesis of the whole product made mechanical: the masters teach
techniques, the bosses test those techniques, and the Elite Coder tests whether
you can think when nobody tells you which technique to use.

---

## 7. Characters — data, not code

```
content/characters/
    master_arrays.json
    master_search.json
    ...
    elite_coder.json
```

Each character declares personality, the patterns it governs, gate thresholds,
boss rules, reward rules, and **dialogue pools keyed by measured outcome**:

```json
{
  "id": "master_search",
  "name": "MASTER OF SEARCH",
  "region": "halls-of-search",
  "personality": {"warmth": 0.1, "verbosity": 0.2, "praise_threshold": 0.9},
  "dialogue": {
    "greeting":        ["You are early. That is not the same as being ready."],
    "fail_wrong":      ["You searched linearly. I asked for logarithmic."],
    "fail_timeout":    ["Time. You had the answer and could not reach it."],
    "success":         ["Acceptable."],
    "success_fast":    ["...", "Faster than last time. Continue."],
    "exceptional":     ["You have earned another lesson."],
    "gate_locked":     ["Return when your recognition holds above eighty."],
    "boss_intro":      ["Find the logarithmic solution. DEFEAT ME."]
  }
}
```

Dialogue selection is driven by the outcome record, never by a random roll
alone — randomness only picks *between* lines that already fit the situation.

### Praise budget

`praise_threshold` makes rarity mechanical rather than a matter of authoring
discipline. A master with 0.9 only reaches `exceptional` for performances in the
top 10% of *your own* history with them. Praise stays rare automatically, and it
tracks genuine improvement rather than an absolute bar.

### Portraits

```
assets/characters/<id>/{portrait.png, portrait.txt, portrait.ansi}
```

Resolution order, decided at runtime by capability probe:

```
kitty graphics protocol  →  sixel  →  half-block ANSI  →  Unicode art  →  ASCII
```

Your terminal is kitty, so real images work. **The core game must never depend
on it** — `portrait.txt` is mandatory for every character, images optional.

---

## 8. What is engine work vs. presentation

From the audit. Nothing existing gets rewritten.

| Component | Verdict |
|---|---|
| `judge/` sandbox | **Untouched.** Production-grade already. |
| `learning/` FSRS, mastery | **Extended, not changed.** Add timeout rating path. |
| `storage/` | **New tables only:** `respect`, `boss_record`, `phase_timing`, `character_state`. |
| `game/` XP, unlocks, achievements | Kept. Respect added alongside, not replacing. |
| Masters, arcs, dialogue, combat metaphor | **Pure presentation** over existing worlds/patterns. |
| **`timing/`** | **New subsystem.** Adaptive limits, phase instrumentation, timeout semantics. |
| **`boss/`** | **New subsystem.** Phase state machine, HP, gates, enrage, variants. |
| **`world/`** | **New package.** Regions, arcs, masters, dialogue selection, respect. |
| `tui/` | Substantial new screens: journey map, boss arena, timer HUD, verdict. |

---

## 9. Build order

1. **`timing/`** — adaptive limits, phase instrumentation, timeout semantics, the
   time-analysis report. Everything else depends on it.
2. **`world/`** — characters, dialogue, respect, regions/arcs. Makes it *feel*
   like the game.
3. **`boss/`** — phases, HP, gates, enrage, rematch, variants.
4. **Curriculum** — the 26 missing chapters, authored in parallel, region by
   region in campaign order.
5. **The Elite Coder** — held-out set, final gate, the last screen.

Each stage ships playable. No stage requires rewriting the previous one.

---

## 10. Things this design deliberately refuses

- **No timer acceleration.** Punishes thinking.
- **No XP or mastery loss on failure.** Trying must never make you worse.
- **No respect decay.** A master does not forget.
- **No boss winnable without the mastery gate.** HP cannot substitute for skill.
- **No praise on schedule.** Praise is earned against your own history.
- **No dialogue that insults the person.** Hostility attaches to the performance,
  stays inside the fiction, and always arrives with a diagnosis and a route back.
- **No engagement metric as a goal.** Optimise retention and transfer. If the
  game is fun but you are not measurably faster in three months, it failed.
