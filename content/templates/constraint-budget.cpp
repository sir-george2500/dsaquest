// ===========================================================================
// READ THE BOUND, CHOOSE THE COST
//
// The first thing to read in a problem is not the story. It is the constraint
// block. A modern judge does something in the order of 10^8 simple operations
// per second, so the largest n tells you which complexity classes are still
// available before you have thought of a single algorithm:
//
//     n <= 10        O(n!)                    try every permutation
//     n <= 20        O(2^n) or O(2^n * n)     try every subset
//     n <= 400       O(n^3)
//     n <= 5000      O(n^2)
//     n <= 10^6      O(n log n)
//     n <= 10^7      O(n)
//     n huge         O(log n) or O(1)         a formula, or a halving
//
// The two standard tables disagree on one rung: the Handbook allows O(n^3) up
// to n = 500 and this one stops at 400. That is not a contradiction, it is the
// constant factor — 500^3 is 1.25 * 10^8, which is over the budget below and
// under a generous reading of "hundreds of millions per second". Where the two
// disagree, the estimate is telling you the answer is close, and close is a
// reason to look for the next class down.
//
// Read it in both directions. A large bound REFUSES the double loop and tells
// you to find something cheaper. A small, oddly specific bound — "n <= 20" —
// LICENSES the exhaustive search and tells you to stop looking for cleverness
// that the setter never intended.
//
// Nothing here is an algorithm. It is the arithmetic you do before you have
// one, and it is the only part of a contest that costs nothing to get right.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

//: Roughly what a judge gets through in a second of simple work.
static const long long BUDGET = 100000000LL;

//: Anything past this is reported as astronomical rather than as a number.
static const long long HUGE_COST = 4000000000000000000LL;

// ---------------------------------------------------------------------------
// 1. THE ESTIMATE.
//
//    How many operations does a class of algorithm perform at this n? Saturate
//    rather than overflow: 2^n at n = 200 has no business being computed, and
//    the honest answer is "far more than a second", not a wrapped negative.
//
//    Codes: 1 = O(n), 2 = O(n log n), 3 = O(n^2), 4 = O(n^3),
//           5 = O(2^n), 6 = O(n!).
// ---------------------------------------------------------------------------
static long long saturating_mul(long long a, long long b) {
    if (a == 0 || b == 0) return 0;
    if (a > HUGE_COST / b) return HUGE_COST;
    return a * b;
}

long long operations(long long n, int code) {
    long long ops = 0;
    // >>> HOLE id=estimate prompt=Return the operation count for class `code` at this n, using saturating_mul so nothing overflows: 1 is n, 2 is n log2 n, 3 is n^2, 4 is n^3, 5 is 2^n, 6 is n!
    if (code == 1) {
        ops = n;
    } else if (code == 2) {
        long long bits = 0;
        while ((1LL << bits) < n) ++bits;          // ceil(log2 n), and 0 at n = 1
        ops = saturating_mul(n, max(1LL, bits));
    } else if (code == 3) {
        ops = saturating_mul(n, n);
    } else if (code == 4) {
        ops = saturating_mul(saturating_mul(n, n), n);
    } else if (code == 5) {
        ops = 1;
        for (long long i = 0; i < n && ops < HUGE_COST; ++i) ops = saturating_mul(ops, 2);
    } else if (code == 6) {
        ops = 1;
        for (long long i = 2; i <= n && ops < HUGE_COST; ++i) ops = saturating_mul(ops, i);
    }
    // <<< HOLE
    return ops;
}

// ---------------------------------------------------------------------------
// 2. THE LADDER, READ BACKWARDS.
//
//    Given only n, name the most expensive class that still fits in a second.
//    This is the table above, and it is worth memorising in exactly this form:
//    the answer to "what am I allowed to write?" arrives before the algorithm.
// ---------------------------------------------------------------------------
const char* affordable_class(long long n) {
    const char* answer = "O(1) or O(log n)";
    // >>> HOLE id=ladder prompt=Return the most expensive class that still fits at this n, walking the ladder from the smallest bound upwards: 10 -> factorial, 20 -> subsets, 400 -> cubic, 5000 -> quadratic, 10^6 -> n log n, 10^7 -> linear, and anything larger -> constant or logarithmic
    if (n <= 10) {
        answer = "O(n!)";
    } else if (n <= 20) {
        answer = "O(2^n)";
    } else if (n <= 400) {
        answer = "O(n^3)";
    } else if (n <= 5000) {
        answer = "O(n^2)";
    } else if (n <= 1000000) {
        answer = "O(n log n)";
    } else if (n <= 10000000) {
        answer = "O(n)";
    }
    // <<< HOLE
    return answer;
}

// ---------------------------------------------------------------------------
// 3. WHAT THE SMALL BOUND LICENSED.
//
//    n <= 20 and "choose any subset" together mean the setter has already done
//    the estimate for you: 2^20 is 1048576, and a million subsets is nothing.
//    So the intended solution is to try them all, and looking for something
//    subtler is a way of losing the contest to a problem that was not hard.
//
//    Here: the largest subset total that does not exceed `target`.
// ---------------------------------------------------------------------------
long long best_subset_total(const vector<long long>& weight, long long target) {
    int n = (int)weight.size();
    long long best = 0;                         // the empty subset always fits
    // >>> HOLE id=exhaustive prompt=The bound licensed 2^n, so enumerate every subset of the n weights, total each one, and keep the largest total that does not exceed target
    for (int mask = 0; mask < (1 << n); ++mask) {
        long long total = 0;
        for (int i = 0; i < n; ++i) {
            if (mask & (1 << i)) total += weight[i];
        }
        if (total <= target) best = max(best, total);
    }
    // <<< HOLE
    return best;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   q            then q lines "n code"  -> operations, and FITS / TOO SLOW
//   m            then m values n        -> the class that n can afford
//   k target     then k weights         -> best subset total within target
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int q;
    if (!(cin >> q)) return 0;
    for (int i = 0; i < q; ++i) {
        long long n;
        int code;
        cin >> n >> code;
        long long ops = operations(n, code);
        if (ops >= HUGE_COST) {
            cout << "astronomical TOO SLOW\n";
        } else {
            cout << ops << ' ' << (ops <= BUDGET ? "FITS" : "TOO SLOW") << "\n";
        }
    }

    int m;
    cin >> m;
    for (int i = 0; i < m; ++i) {
        long long n;
        cin >> n;
        cout << affordable_class(n) << "\n";
    }

    int k;
    long long target;
    cin >> k >> target;
    vector<long long> weight(k);
    for (long long& w : weight) cin >> w;
    cout << best_subset_total(weight, target) << "\n";

    return 0;
}
