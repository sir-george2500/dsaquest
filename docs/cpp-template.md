# The C++ template

Two files live in `content/templates/`:

- **`starter.cpp`** — injected into every generated workspace. 16 lines.
- **`starter_full.cpp`** — the same, plus a debug printer and a collision-safe
  hash. Copy from it when you want them.

This document explains every line, and — more usefully — explains what is
*deliberately absent* and why.

---

## Why the default is small

The templates you find on GitHub with 200 lines of `#define` are not what strong
competitive programmers write. tourist's submissions are close to plain STL.
Um_nik's are shorter still. Benq keeps a large library but pastes from it
selectively rather than starting every problem with all of it.

There is a reason beyond taste. **A macro is a translation layer between what
you think and what you type.** Under contest pressure that layer costs you: you
misread your own code, you cannot paste a snippet from an editorial without
rewriting it, and compiler errors point into expansions instead of your logic.

The skill that wins contests is knowing the STL cold. The template is
scaffolding, not the thing.

---

## `starter.cpp`, line by line

```cpp
#include <bits/stdc++.h>
```

A GCC-specific header pulling in the whole standard library. Not portable — it
does not exist on MSVC or libc++ — but every major judge uses GCC, and it costs
~0.5 s of compile time to never think about includes again. This project's judge
uses GCC, so it works here.

```cpp
using namespace std;
```

Genuinely bad practice in production code, genuinely fine here. The reason it's
harmful — name collisions across large codebases and library boundaries — cannot
occur in a single self-contained translation unit that links nothing. Don't
carry the habit into real projects.

```cpp
using ll = long long;
```

The single most valuable line in the file. **Integer overflow is the most common
way a correct algorithm produces a wrong answer** — `n * (n + 1) / 2` overflows
`int` at n ≈ 65,536, and 10⁵ is a small constraint.

Note it's `using`, not `#define int long long`. See below.

```cpp
void solve() { }
```

A separate function so you can `return` early. Without it, bailing out of a
test case means a flag variable or a `goto`, and both cause bugs. With it:

```cpp
void solve() {
    if (impossible) { cout << "-1\n"; return; }
    ...
}
```

```cpp
ios::sync_with_stdio(false);
```

By default C++ streams stay synchronised with C's `stdio` so you can interleave
`printf` and `cout`. That synchronisation makes every `cin >>` unbuffered and
costs roughly **5–10×** on large input. Turning it off is free unless you mix
`scanf`/`printf` with `cin`/`cout` — after this line, don't.

```cpp
cin.tie(nullptr);
```

By default `cin` flushes `cout` before every read, so prompts appear before
input. No judge needs that, and it means a flush per read.

**Exception: interactive problems.** There you must keep the tie, or flush
manually with `cout << flush` after every response. Getting this wrong looks
exactly like a timeout.

```cpp
int tests = 1;
// cin >> tests;
while (tests--) solve();
```

Most Codeforces problems now begin with the number of test cases. Uncommenting
one line is faster and less error-prone than restructuring `main` under
pressure.

### One more thing, not in the file

Use `'\n'`, never `endl`. `endl` writes a newline **and flushes**. In a loop
printing 10⁵ lines that is 10⁵ flushes, and it is a genuinely common cause of
TLE on a correct solution.

---

## What `starter_full.cpp` adds

### `debug(...)`

```
[42] n = 5, v = {1, 2, 3}
[43] g = {{1, 2}, {3}}, m = {("a", 1), ("b", 2)}
```

Prints variable names alongside values, recursively, for any nesting of ranges,
pairs and tuples. Compiles to `((void)0)` unless you pass `-DLOCAL`, so it costs
nothing when judged.

This is the highest-value item in any template. It's the difference between
*reasoning* about a wrong answer and *looking* at it.

```bash
g++ -std=c++20 -O2 -DLOCAL -Wall -Wextra -Wshadow solution.cpp -o sol
```

Two implementation details worth studying, since they're both idioms you'll
reuse:

- `if constexpr (ranges::range<T>)` — chooses the branch **at compile time**, so
  a non-range type never instantiates the loop body. With a plain `if` this
  would not compile at all.
- The name-splitter walks `#__VA_ARGS__` tracking bracket depth, so
  `debug(max(a, b), c)` splits at the right comma rather than the one inside
  `max`.

### `SafeHash` / `safe_map`

libstdc++ hashes integers with the **identity function** and uses a prime-modulo
bucket count. A problem setter who knows your bucket count can supply keys that
all land in one bucket, turning your O(n) `unordered_map` into O(n²). This has
decided real contests — it's why anti-hash tests exist on Codeforces.

`SafeHash` runs keys through splitmix64 with a clock-derived salt, so the
adversary cannot know the collision set in advance.

```cpp
safe_map<int, int> cnt;   // instead of unordered_map<int, int>
```

Alternative worth knowing: `map` is O(log n) but immune, and for n ≤ 10⁵ the
log factor often costs less than you'd guess.

---

## Deliberately absent

### `#define int long long`

Popular, and a bad trade:

1. **It hides the decision.** Knowing *where* a value can exceed 2³¹ is a real
   skill this app tracks (`CPP_INT_OVERFLOW`). Blanket-widening removes the
   question instead of teaching the answer.
2. **It doubles memory.** An array of 10⁷ ints goes from 40 MB to 80 MB. That
   converts an accepted solution into MLE.
3. **It breaks `main`**, whose return type must be `int` — hence the `signed
   main()` you see in these templates, which is a workaround for a
   self-inflicted problem.

Write `ll` where you mean it.

### `#pragma GCC optimize("O3", "unroll-loops")`

Cargo cult. The judge already compiles with `-O2`; `-O3` is occasionally
*slower* (code bloat, worse instruction cache behaviour), and neither fixes a
solution that is asymptotically wrong. If you are close enough to the limit for
this to matter, your complexity is wrong.

### `#define rep(i, a, b) for (int i = a; i < b; i++)` and friends

Saves ~8 characters, costs readability every time you or anyone else reads the
code. `pb`, `mp`, `fi`, `se` are the same trade. `#define all(x) begin(x), end(x)`
is the one with a real case for it — it appears often enough to earn its
keep — and it's still omitted here so that you read `sort(v.begin(), v.end())`
enough times for it to become automatic.

Add it yourself once it genuinely annoys you. That's the right moment for any
abbreviation.

---

## The warnings the judge turns on

```
-Wall -Wextra -Wshadow
```

`-Wshadow` is the one to care about. It catches:

```cpp
for (int i = 0; i < n; i++) {
    for (int i = 0; i < m; i++) {   // warning: declaration shadows previous
        ...
    }
}
```

That bug costs contests and is invisible on inspection. Your `clangd` in nvim
sees the same flags via the generated `compile_commands.json`, so you'll get the
warning as you type rather than at submit time.

---

## What to actually memorise

Not a template. These:

| | |
|---|---|
| `lower_bound` / `upper_bound` | and that they need a **sorted** range, and return iterators |
| `sort` with a lambda comparator | strict weak ordering — `<`, never `<=` |
| `partial_sum`, `iota`, `accumulate` | prefix sums and index fills without a loop |
| `nth_element` | O(n) selection when you don't need a full sort |
| `priority_queue` with `greater<>` | the min-heap you'll reach for constantly |
| `set` / `map` as ordered structures | `lower_bound` **as a member**, not the free function |
| `__builtin_popcount` / `__lg` | and their `ll` variants |

Everything above is trained by the patterns in this app. The template just gets
out of the way.
