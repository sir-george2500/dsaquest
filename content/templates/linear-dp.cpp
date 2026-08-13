// ===========================================================================
// SAY WHAT dp[i] MEANS
//
// A dynamic program is a DEFINITION first and a loop second. Before a single
// line of code exists there must be one sentence, in words, that says exactly
// what one cell of the array holds. If you cannot say it, you have not started.
//
//     dp[i] = the number of ways to stand on stone i
//     dp[i] = the fewest coins that pay exactly i
//     dp[i] = the largest haul from the first i stores, none of them adjacent
//
// Notice what each sentence pins down: what is FIXED at i, and what is still
// free. Get that wrong and the recurrence cannot be written at all — not
// "written incorrectly", but genuinely unwritable, because you cannot say what
// the thing you are combining actually is.
//
// From a good definition the rest is mechanical:
//
//   1. BASE CASE   what does the definition say about the empty prefix?
//   2. TRANSITION  case-split on the LAST decision, and read the settled cells
//   3. ORDER       fill so that every cell a transition reads is already final
//   4. ANSWER      which cell is the answer? It is not always the last one.
//
// The three forms below share that skeleton. Form 2 is the problem the Ridge
// of Greed could not solve: on the coin system {1, 3, 4} the amount 6 needs
// two coins, and largest-first insists on three. No ordering of the coins
// repairs that; the table does.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

//: Large enough to lose every min(), small enough that INF + 1 does not
//: overflow. INT_MAX is the wrong choice for exactly that second reason.
static const long long INF = (long long)1e18;

// ---------------------------------------------------------------------------
// 1. COUNTING WAYS — dp[i] = the number of distinct routes that stand on stone i.
//
//    The base case is forced by the definition, not chosen: there is exactly
//    one way to stand on stone 0, namely by having done nothing. dp[0] = 1.
//
//    The transition splits on the LAST step taken. The only way to arrive at
//    stone i is from i - 1 or from i - 2, and those routes are disjoint, so
//    the counts add:  dp[i] = dp[i-1] + dp[i-2].
//
//    With n = 5 the table is 1, 1, 2, 3, 5, 8 — Fibonacci, which is why the
//    count must be reduced modulo something: the true value passes 2^63
//    before n reaches 100.
// ---------------------------------------------------------------------------
long long ford_crossings(int n, long long mod) {
    vector<long long> dp(n + 1, 0);
    dp[0] = 1;                              // one way to do nothing
    // >>> HOLE id=count-ways prompt=Fill dp[i] for every stone, where dp[i] counts routes standing on stone i and a step covers one stone or two; reduce modulo `mod` as you go
    for (int i = 1; i <= n; ++i) {
        dp[i] = dp[i - 1];
        if (i >= 2) dp[i] += dp[i - 2];
        dp[i] %= mod;
    }
    // <<< HOLE
    return dp[n];
}

// ---------------------------------------------------------------------------
// 2. MINIMISING — dp[i] = the fewest coins that pay exactly i, or INF if i
//    cannot be paid at all.
//
//    "Or INF" is part of the definition and not an implementation detail. The
//    cell must be able to say "impossible", because on the system {2} the
//    amount 3 genuinely is, and a table that reports 0 there is lying.
//
//    The transition splits on the last coin handed over. If that coin was c,
//    then everything before it paid exactly i - c, and the definition tells us
//    that cost was dp[i - c]:
//
//        dp[i] = 1 + min over every coin c <= i of dp[i - c]
//
//    On {1, 3, 4}: dp = 0 1 2 1 1 2 2 ...  so dp[6] = 2, from 3 + 3.
//    Largest-first answers 4 + 1 + 1 = 3, and it is not close to a fixable
//    kind of wrong — it is the wrong method.
// ---------------------------------------------------------------------------
long long min_coins(const vector<long long>& coin, int amount) {
    vector<long long> dp(amount + 1, INF);
    dp[0] = 0;                              // paying nothing costs no coins
    // >>> HOLE id=min-over-last prompt=Fill dp[i] as one plus the cheapest way to pay i minus some coin, leaving dp[i] at INF when no coin can reach i
    for (int i = 1; i <= amount; ++i) {
        for (long long c : coin) {
            if (c <= i && dp[i - c] != INF) {
                dp[i] = min(dp[i], dp[i - c] + 1);
            }
        }
    }
    // <<< HOLE
    return dp[amount] == INF ? -1 : dp[amount];
}

// ---------------------------------------------------------------------------
// 3. TWO RIVAL DEFINITIONS ON ONE PROBLEM — no two chosen stores may be
//    adjacent, and the haul is to be as large as possible.
//
//    Definition A (free):    dp[i] = the best haul from the first i stores,
//                                    with no statement about whether store i
//                                    was taken.
//    Definition B (forced):  f[i] = the best haul from the first i stores in
//                                    which store i IS taken.
//
//    Both are correct, and they produce DIFFERENT recurrences:
//
//        A:  dp[i] = max(dp[i-1],  dp[i-2] + a[i-1])
//        B:  f[i]  = a[i-1] + max over j <= i-2 of f[j]
//
//    A's answer is the last cell. B's answer is the largest cell anywhere,
//    which is the usual reason students who chose B get the recurrence right
//    and the final line wrong. On a = [5, 1, 1, 5] both give 10, by
//    dp = 0 5 5 6 10 and f = 5 1 6 10.
//
//    This function computes A. It is written next to the comment describing B
//    so that the two can be compared on the same data, which is the only way
//    the phrase "what dp[i] means" becomes concrete rather than a slogan.
// ---------------------------------------------------------------------------
long long best_non_adjacent(const vector<long long>& a) {
    int n = (int)a.size();
    vector<long long> dp(n + 1, 0);
    // dp[0] = 0: the best haul from no stores at all.
    if (n >= 1) dp[1] = max(0LL, a[0]);
    // >>> HOLE id=free-definition prompt=Fill dp[i] for i from 2 to n, where dp[i] is the best haul from the first i stores with no two adjacent, by splitting on whether store i is taken
    for (int i = 2; i <= n; ++i) {
        dp[i] = max(dp[i - 1], dp[i - 2] + a[i - 1]);
    }
    // <<< HOLE
    return dp[n];
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n mod                     -> routes across n stones, modulo mod
//   m amount then m coins     -> fewest coins paying amount exactly, or -1
//   k then k store values     -> best non-adjacent haul
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    long long mod;
    if (!(cin >> n >> mod)) return 0;
    cout << ford_crossings(n, mod) << "\n";

    int m, amount;
    cin >> m >> amount;
    vector<long long> coin(m);
    for (long long& c : coin) cin >> c;
    cout << min_coins(coin, amount) << "\n";

    int k;
    cin >> k;
    vector<long long> store(k);
    for (long long& v : store) cin >> v;
    cout << best_non_adjacent(store) << "\n";

    return 0;
}
