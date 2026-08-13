# DSA Warrior — Game Design

Design document for the warrior-journey layer. Written after the codebase audit
and the Competitive Programmer's Handbook curriculum audit.

---

## 0. What this product is

> A daily training ritual that makes you measurably better at understanding,
> recognising and implementing competitive-programming patterns in C++, wrapped
> in a warrior's journey demanding enough that you want to come back tomorrow.

Two engines, never confused:

| | Purpose | Owns |
|---|---|---|
| **Learning engine** | Creates competence | Scheduling, mastery, retention, adaptation |
| **Game engine** | Creates motivation | Masters, respect, bosses, arcs, dialogue, timers |

**The rule everything obeys:** the game layer *wraps* the learning loop and never
replaces it. Every dramatic element must be a faithful rendering of a real
measurement. A master who says "pathetic" when you actually did well destroys
the only thing that makes his harshness bearable — that it is *true*.

**The test for every future feature:** does this make the player better at
understanding, recognising, remembering or applying algorithms? If it only adds
grinding, time-in-app or XP, it does not ship.

---

## 1. The Master is a teacher before he is an opponent

This is the core of the design and the thing a lesser version gets backwards.

A master does not throw an unlabelled problem at a student and wait for failure.
He teaches the technique, drills it until the hand moves without the mind, and
only then removes the label to find out whether the student *understood*.

```
MASTER
   ↓
TEACH THE CONCEPT          what this is, and why it exists
   ↓
REVEAL THE PATTERN         named openly — nothing hidden yet
   ↓
TEACH THE SECRET           the trick that collapses the work
   ↓
DEMONSTRATE               worked example, concrete numbers
   ↓
GUIDED PRACTICE            drills — pattern known
   ↓
RECALL TRAINING            can you produce the trick from memory?
   ↓
APPLICATION                a real problem, pattern still named
   ↓
FINAL TEST                 pattern HIDDEN
   ↓
MASTER'S JUDGMENT          verdict, diagnosis, what happens next
```

### Why this does not contradict recognition training

The founding premise stands: *"I can solve problems but I struggle to recognise
patterns."* Recognition can only be **tested** with the pattern hidden.

But recognition cannot be **taught** by hiding things. It is taught by building
a library of techniques so thoroughly that the signals become visible. You
cannot recognise a sliding window you have never been shown.

| Phase | Pattern | Trains | Combat analogy |
|---|---|---|---|
| Teach | named | knowledge | the sensei demonstrates |
| Drill | named | fluency | a thousand repetitions |
| Test | **hidden** | recognition, understanding | sparring |
| Boss | **hidden**, composed | transfer | a real fight |

Hiding the pattern before the technique is taught does not train recognition. It
trains frustration.

---

## 2. Secrets — the unit of teaching

A master teaches a **secret**, not a topic. A secret is one small observation
that collapses a class of problems.

Each secret carries its own required-exercise budget, and the master **decides
when you are done** — the numbers below are starting points, not quotas.

```
MASTER OF BITS

  Secret 1  Reading the lowest bit        n & 1          ~3 exercises
  Secret 2  Clearing the lowest set bit   n & (n - 1)    ~4 exercises
  Secret 3  Counting set bits             loop on the above  ~5 exercises
  Secret 4  Masks and subsets             1 << k         ~6 exercises
  Secret 5  Cancellation                  n ^ n, n ^ 0   ~4 exercises

  Final test                              3 unfamiliar problems, nothing named
```

### What a lesson looks like

```
╔══════════════════════════════════════════════════════════╗
║              MASTER OF BIT MANIPULATION                  ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  "Today you learn to read the bits."                     ║
║                                                          ║
║  "Before you fight, you must understand your weapon."    ║
║                                                          ║
║  SECRET 1 — THE LOWEST BIT                               ║
║                                                          ║
║      n & 1   tells you whether the lowest bit is 0 or 1  ║
║                                                          ║
║  DEMONSTRATION                                           ║
║                                                          ║
║      13 = 1101      13 & 1 = 1      odd                  ║
║      12 = 1100      12 & 1 = 0      even                 ║
║                                                          ║
║  WHAT TO WATCH FOR                                       ║
║                                                          ║
║      n % 2 on a negative n returns -1, not 1.            ║
║      & 1 does not lie. Prefer it.                        ║
║      n >> 1 is not division by two when n is negative.   ║
║                                                          ║
║  "Memorise it. You will use it often."                   ║
╚══════════════════════════════════════════════════════════╝
```

### Teaching scales with level

The same master returns with harder secrets as the student rises:

| Level | Secret taught | Question asked |
|---|---|---|
| Beginner | `n & 1` | Is n odd or even? |
| Intermediate | `n & (n - 1)` | How do you remove the lowest set bit? |
| Advanced | composition | How many set bits are present? |
| Expert | **nothing named** | An unfamiliar problem. Recognise it yourself. |

```
Learn → Practice → Recall → Apply → Recognise independently
```

---

## 3. Three kinds of problem, kept strictly separate

| Kind | Player is told | Purpose |
|---|---|---|
| **Training problem** | the concept, explicitly | fluency in the technique |
| **Recognition problem** | nothing; asked *which* technique | recognition |
| **Master problem** | nothing at all — a normal CP problem | transfer |

Mixing these is how a training tool becomes a quiz. A training problem that
hides its pattern is not harder, it is just unfair; a master problem that names
its pattern is not a test at all.

---

## 4. Timers are generous. Time is a secondary metric.

The goal is not *"can you type fast?"* It is *"can you understand and solve this
correctly under reasonable competitive pressure?"*

A player must never lose because the clock was artificially short.

| Task | Time |
|---|---|
| Concept recall | 1–3 min |
| Easy problem | 8–15 min |
| Medium problem | 15–30 min |
| Hard problem | 30–60 min |
| Master Trial | 30–90 min |
| Boss challenge | 45–120 min |

All configurable, all tuned against real data as it accumulates.

### Time is ranked below understanding

Primary: **understanding, correctness, recognition, reasoning, implementation,
retention.** Speed is an *additional* metric on top.

A slow, correct, well-understood solution is progress and is reported as
progress. The game makes you faster as a *consequence* of understanding, not by
threatening you with a clock.

### Timeout is not a memory failure

Load-bearing rule. A timeout means slow, not forgotten. Rating it as forgotten
would tell the scheduler you lost a pattern you actually hold.

```
correct, fast     → Easy
correct, slow     → Good        speed is reported, not punished
TIMEOUT           → Hard        never "Again"
wrong             → Again
judge failure     → no rating at all
```

### Time analysis is a diagnosis, not a scoreboard

```
TIME ANALYSIS
  Pattern recognition   0:31   ✓
  Planning              0:58   ✓
  Implementation        4:12   ✗
  Debugging             1:08   ✗
  Total                 6:49        target 6:00

  Your bottleneck is implementation, not recognition.
  You knew the pattern in 31 seconds and then took four minutes to type it.
  → Code Completion drills on this template
```

Debug time only exists after a failed submission, which makes it the sharpest
signal we have: high debug time means you code before you think.

---

## 5. Understanding check before submission

On Master problems, trials and bosses, the player states their reasoning before
the code is judged:

```
BEFORE SUBMISSION

  What is the key idea?          > ______________________
  What is the expected complexity? > ____________________
  What invariant are you maintaining? > _________________
```

This exists to prevent *"I memorised the code but have no idea why it works."*
It is graded against the pattern's rubric, and it feeds the **Conceptual
Understanding** dimension directly. Getting the code right with the reasoning
wrong is recorded as exactly that — and the master says so.

---

## 6. Warrior Strength — seven dimensions

Strength is never "problems solved". It is derived so that grinding easy content
cannot inflate it.

```
WARRIOR STRENGTH                                    82

  Pattern Recognition      ████████████████░░░░     82
  Conceptual Understanding ██████████████████░░     91
  Implementation           ███████████████░░░░░     76
  Problem Solving          ████████████████░░░░     84
  Retention                ██████████████░░░░░░     73
  Speed                    ████████████░░░░░░░░     61
  Consistency              ███████████████████░     94
```

| Dimension | Source | Scheduled? |
|---|---|---|
| Pattern Recognition | recognition card | **yes** — FSRS |
| Conceptual Understanding | understanding checks + recall card | **yes** — FSRS |
| Implementation | implementation card | **yes** — FSRS |
| Problem Solving | accuracy on **Master problems only** (unaided, hidden pattern) | derived |
| Retention | minimum retrievability across cards | derived |
| Speed | median time vs. target, by mode and difficulty | derived |
| Consistency | days practised, sessions finished, returns after failure, review adherence | derived |

Three scheduled cards, four derived metrics. Problem Solving is measured *only*
on unaided problems, so drilling with the pattern named cannot raise it.

**Overall strength weights understanding highest and speed lowest**, matching
§4. Speed contributes but can never carry a weak understanding score.

---

## 7. Commitment is a first-class signal

The masters notice dedication, not only talent. Tracked:

```
days practised           sessions completed        patterns revisited
boss attempts            review adherence          improvement over time
returns after a failure
```

This is what makes a master say:

> *"You failed this trial three days ago. Today you solved it. That is
> improvement. Continue."*

Consistency feeds Warrior Strength directly, and it is the one dimension a
merely talented player cannot shortcut.

---

## 8. Praise is genuine, proportional, and therefore rare

Masters are strict, not cruel. They are not withholding praise as a technique —
they give it exactly when it is earned, which is what makes it land.

| Achievement | Master says |
|---|---|
| Small success | "Correct." / "Continue." |
| Strong performance | "Good. You recognised the pattern quickly." |
| Exceptional | "That was well done. You saw the trap before it appeared." |
| Major | "I have trained many students. Few remain when the problems become difficult. You did. **You have earned my respect.**" |

Rarity is mechanical, not a matter of authoring discipline: each master carries
a `praise_threshold`, and the top tier only fires for performances in the top
decile *of your own history with that master*. Praise therefore tracks genuine
improvement rather than an absolute bar, and it cannot be farmed.

Failure dialogue always arrives with a diagnosis and a route back. Hostility
attaches to the *performance*, never the person, and never leaves the fiction.

> *"I am not here to make you feel special. I am here to make you stronger.
>  If you fail, we train. If you improve, I acknowledge it.
>  If you master the technique, I respect you."*

---

## 9. The Master remembers you

Each master keeps state about the student:

```
what you previously failed        which patterns are weak
which secrets you have forgotten  how fast you improve
how many attempts you needed      whether you practise consistently
```

> *MASTER OF GRAPHS: "You struggled with Dijkstra last week. Today you solved
> three weighted shortest-path problems unaided. Your weakness is becoming a
> strength."*

All of this is already in the event log — `attempt`, `review_log`, `mistake`.
The master layer reads it; nothing new needs recording except which lines have
already been spoken, so he does not repeat himself.

---

## 10. Masters detect memorisation

If a player scores well on problems they have seen and poorly on fresh variants
of the same pattern, that is memorisation, not mastery — and it is measurable:

```
memorisation_gap = accuracy(seen instances) − accuracy(fresh variants)
```

Above threshold, with enough samples, the master calls it:

> *"You remember the solution. You do not understand the technique. That is not
> mastery. I will give you a different problem."*

He then generates a **structurally different problem on the same pattern** —
different skin, constraints, input representation, objective. The parameterised
problem machinery and the brute-force oracle already built are exactly what this
requires.

This is the mechanism that stops the whole product degrading into recall of a
problem set.

---

## 11. Adaptive question counts

The master decides when you are ready. Never a fixed quota.

| Evidence | Master's response |
|---|---|
| Concept grasped quickly | fewer drills, harder variations, earlier final test |
| Repeated failure | more worked examples, simpler variations, targeted recall, later test |
| Correct but slow | same difficulty, more repetition for fluency |
| Correct but reasoning wrong | recall and explanation drills, not more coding |

Mastery is never "you completed 20 questions". It is: can you **recognise,
explain, recall, implement, use in a variation, and recognise unaided?** Only
then does mastery move significantly.

---

## 12. Memory training on a real schedule

Some techniques are meant to be memorised. The master says so plainly — *"You
will use this often. Memorise it."* — and then the scheduler validates it
through application, not recitation.

```
Day 1   Learn        the secret is taught
Day 2   Recall       produce it from memory
Day 4   Apply        use it, pattern named
Day 7   Variation    same secret, different shape
Day 14  Mixed        among other patterns, unnamed
Day 30  Boss         under pressure, composed
```

This is FSRS doing what it already does, with the *kind* of exercise changing as
the interval grows. Memorisation becomes durable knowledge because every
repetition demands more than the last.

---

## 13. Curriculum — 30 families, ~90 secrets

The handbook has 30 chapters. One core family per chapter, each expanding into
secrets, algorithms and archetypes.

```
FAMILY (30) → SECRET (~90) → ARCHETYPE → VARIANT → BOSS
```

| Region | CPH ch. | Status |
|---|---|---|
| The Village | 1–2 | complexity estimation, C++ fundamentals — MISSING |
| Plains of Arrays | 3, 4, 8, 9.1 | hashing ✓ prefix ✓ two-pointers ✓ window ✓, monotonic ✗ |
| Halls of Search | 3.3, 5 | binary search ✓ search-on-answer ✓, complete search ✗ |
| Vault of Structures | 4, 9.2–9.4 | MISSING |
| Ridge of Greed | 6 | MISSING |
| Forest of Trees | 14, 15, 18 | MISSING |
| Sea of Graphs | 11–13, 16, 17, 19, 20 | MISSING |
| The Forbidden Art | 7, 10.5 | MISSING |
| Temple of Numbers | 21–24 | MISSING |
| Library of Strings | 26 | MISSING |
| Summit of the Seven | 25, 27–30 | MISSING |

**Current coverage: 6 secrets of ~90; 4 of 30 chapters, all partial.**

---

## 14. The world

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

Regions after the Plains open **in parallel**. The prerequisite DAG already
implemented drives this — you are never made to grind an unrelated region.

### The masters

Naming convention: **`<Rank> <Name>, <Epithet>` — Master of `<Domain>`**. Ranks
are never repeated, so the rank alone tells you who is speaking. All names are
original; none references an existing franchise.

| Region | Master | Character |
|---|---|---|
| The Village | **Elder Vhast, the Unhurried** | Master of Foundations — complexity, C++, estimation. Patient in a way none of the others are. |
| Plains of Arrays | **Warden Ilsa Korrin, the Straight Line** | Master of Arrays. Blunt. Believes most problems are simpler than the student wants them to be. |
| Halls of Search | **Adjudicator Sevrin Kol, the Halving** | Master of Search. Cold, precise, obsessed with efficiency. *"Your solution works. But it is slow."* |
| Vault of Structures | **Grandmaster Ragine, Keeper of the Thirty-Two** | Master of Bits. Finds decimal thinking sentimental. |
| Vault of Structures | **Keeper Maelin Vore, the Ledger** | Master of Structures — heaps, ordered sets, Fenwick, segment trees. Records everything, forgives nothing. |
| Ridge of Greed | **Strategist Dovan Rhe, the Exchange** | Master of Greed. Will not accept an answer without a proof that the local choice is safe. |
| Forest of Trees | **Sage Orenna Thal, the Rooted** | Master of Trees. Speaks in questions. |
| Sea of Graphs | **Warlord Thessaly Grune, the Unbridged** | Master of Graphs. Aggressive and unforgiving. *"You know BFS. But do you know when BFS is wrong?"* |
| The Forbidden Art | **Archivist Nym Solvane, the State** | Master of Dynamic Programming. Impossible to impress. *"Define what dp[i] actually means."* |
| Temple of Numbers | **Oracle Cassiun, the Remainder** | Master of Mathematics. Talks past the student as often as to them. |
| Library of Strings | **Scribe Halvern Ash, the Prefix** | Master of Strings. Quiet, meticulous, faintly amused. |
| Summit of the Seven | **The Seven Nameless** | Legendary bosses. They have no names because they are not teachers. |
| — | **THE ELITE CODER** | The final boss. Gives you a problem. Nothing more. |

### Arcs

| Arc | Regions | New mechanic |
|---|---|---|
| I — The Awakening | Village, Plains | lessons and drills; no timer |
| II — The First Master | Halls of Search | timer appears; Master Trials |
| III — The Hidden Patterns | Structures, Greed | hidden patterns; duels |
| IV — Forest and Sea | Trees, Graphs | multi-pattern bosses; phases |
| V — The Forbidden Art | DP | explain-before-implement enforced |
| VI — The Seven Masters | Numbers, Strings, Summit | legendary bosses; no hints |
| Final | — | held-out problems; nothing familiar |

---

## 15. The three currencies, kept distinct

| | Answers | Behaviour | Gates? |
|---|---|---|---|
| **Warrior Strength** | *Can I actually do this?* | 7 dimensions, decays | **Yes — the only gate** |
| **Respect** | *What have I proven to this master?* | per master, **never decays**, difficulty-weighted, diminishing returns | No — governs dialogue and prestige |
| **XP / Level** | *How far along am I?* | global, paces the campaign | No |

Respect never decays: a master forgetting your victories is not strict, it is
broken. Failure costs a little respect and never costs strength or XP — trying
must not be able to make you worse.

---

## 16. Boss system

### Tiers

| Tier | Tests | Gates |
|---|---|---|
| 1 Training Bosses | one foundational secret | next secret group |
| 2 Pattern Bosses | a family, pattern hidden | next region |
| 3 Algorithm Masters | multiple concepts composed | next arc |
| 4 Elite Warriors | multi-pattern, traps, tight constraints | legendary path |
| 5 Legendary Bosses | a whole discipline at depth | **The Final Gate** |
| ∞ The Elite Coder | everything, nothing familiar | — |

### The gate is checked before the fight, not during it

If HP alone decided victory, a weak player could grind attempts until lucky.
So the mastery requirements are satisfied **before the fight unlocks**; HP is
tension and scoring inside it.

### Phases

```
PHASE 1  Identify the pattern           −10 boss HP
PHASE 2  Explain the approach           −10
PHASE 3  Structure and complexity       −10
PHASE 4  Implement                      −30
PHASE 5  Survive hidden tests           −30
         Optimise, where applicable     −20
```

A mistake costs HP, time or a hint — never the whole fight. Bosses are always
retryable and nothing is permanently lost.

### Enrage removes safety, never accelerates the clock

Speeding up a timer punishes careful thought, which is the opposite of §4.
Enrage instead disables remaining hints, reveals the hidden test count, and
doubles both the respect at stake and the respect gained.

### Victory tiers and rematches

Normal → Strong (≤1 hint) → Perfect (no hints, no wrong answers, within target)
→ Legendary (Perfect, under target, hard variant).

Defeated bosses stay available for Rematch, Speed Trial and No-Hint Trial. Every
rematch draws a **generated variant** — same skill, different everything else.

---

## 17. The Elite Coder needs a held-out problem set

The design consequence of his speech, and it changes what content we author.

> *"You have been training against problems that prepared you for me. I will not
> give you a familiar pattern. I will give you a problem. Nothing more."*

If he draws from the training pool he tests recall of that pool, not transfer.
So: **a reserved set, never shown in training at any stage**, composed from
families in unusual combinations, with no signals listed, no hints and no
pattern name — ever. Content validation enforces the reservation so a future
author cannot leak one into rotation.

The masters teach techniques. The bosses test those techniques. The Elite Coder
tests whether you can think when nobody tells you which technique to use.

---

## 18. Characters — data, not code

```
content/characters/master_bits.json    …    elite_coder.json
```

Each declares personality, governed secrets, gate thresholds, boss rules, and
dialogue pools keyed by **measured outcome** — never by a random roll alone.
Randomness only picks *between* lines that already fit the situation.

```
assets/characters/<id>/{portrait.png, portrait.txt, portrait.ansi}
```

Resolution at runtime: kitty graphics → sixel → half-block ANSI → Unicode →
ASCII. Your terminal is kitty, so real images work. `portrait.txt` is mandatory
for every character; images are always optional.

---

## 19. Engine work vs. presentation

| Component | Verdict |
|---|---|
| `judge/` sandbox | **Untouched.** Production-grade already. |
| `learning/` | **Extended:** timeout rating path, understanding dimension |
| `storage/` | **New tables:** `respect`, `boss_record`, `phase_timing`, `lesson_progress`, `character_memory` |
| `game/` | Kept; respect added alongside XP |
| Masters, arcs, dialogue, combat metaphor | **Pure presentation** |
| **`lessons/`** | **New.** Secrets, demonstrations, adaptive drill counts |
| **`timing/`** | **New.** Generous limits, phase instrumentation, timeout semantics |
| **`boss/`** | **New.** Phases, HP, gates, enrage, variants |
| **`world/`** | **New.** Regions, arcs, masters, dialogue, respect, master memory |
| `tui/` | New screens: lesson, journey map, boss arena, timer HUD, verdict |

---

## 20. Build order

1. **`lessons/`** — the teach → drill → test spine, with the Master of Bits as
   the first full vertical slice. Without this the masters are not teachers.
2. **`timing/`** — generous limits, phase instrumentation, timeout semantics.
3. **`world/`** — characters, dialogue, respect, master memory, regions, arcs.
4. **`boss/`** — phases, HP, gates, enrage, rematch, variants.
5. **Curriculum** — the 26 missing chapters, region by region in campaign order.
6. **The Elite Coder** — held-out set, final gate.

Each stage ships playable. No stage requires rewriting the previous one.

---

## 21. What this design refuses

- **No timer acceleration**, and no tight timers. They punish thinking.
- **No strength or XP loss on failure.** Trying must never make you worse.
- **No respect decay.** A master does not forget.
- **No boss winnable without the mastery gate.** HP cannot substitute for skill.
- **No praise on a schedule.** Earned against your own history, or not given.
- **No hidden pattern before the technique has been taught.** That is not
  difficulty, it is withholding.
- **No mastery credit for question count.** Six abilities, demonstrated.
- **No dialogue that insults the person.** Hostility attaches to performance,
  stays inside the fiction, and always arrives with a route back.
- **No engagement metric as a goal.** If the game is fun and you are not
  measurably stronger in three months, it failed.
