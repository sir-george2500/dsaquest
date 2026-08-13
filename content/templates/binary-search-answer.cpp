// ===========================================================================
// BINARY SEARCH ON THE ANSWER
//
// The shape: ANSWER SPACE + MONOTONE PREDICATE.
//
// There is no sorted array to search. You invent the array: it is the range of
// candidate answers, and the "comparison" is a feasibility check
//
//     can(x)  ==  "is an answer as good as x achievable?"
//
// It is only a binary search if can() is MONOTONE — F F F F T T T T, one flip
// and never back. Prove that BEFORE writing code; it is the step everyone
// skips. Typical proof: "if a cap of x lets me finish, a cap of x + 1 lets me
// do everything I did before", i.e. a feasible plan for x is still a plan for
// x + 1.
//
// Loop invariant, held from entry to exit:
//
//     the answer lies in [lo, hi]  —  can(hi) is true, can(lo - 1) is false
//
// Each iteration halves the interval while preserving that, so when lo == hi
// the interval is the answer.
//
// Cost: O(log(range) * cost of can). log(1e18) = 60, so the range is free and
// only the predicate matters.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. MINIMISE THE MAXIMUM — the canonical form. `hi = mid`, answer is lo.
//
//    Split a into exactly k contiguous parts, minimising the largest part sum.
//    (Same problem as: ship all packages within D days; Koko eats bananas in
//    h hours. Only the predicate's story changes.)
//
//    Predicate: with a cap of x, greedily start a new part whenever adding the
//    next value would exceed x. That greedy uses the FEWEST possible parts, so
//    "fits in k parts" <=> parts_needed(x) <= k.
//
//    Monotone: a larger cap never needs more parts.
//    Bounds: lo = max(a)  (a single element must fit in some part)
//            hi = sum(a)  (one part holds everything — always feasible)
// ---------------------------------------------------------------------------
long long parts_needed(const vector<long long>& a, long long cap) {
    // >>> HOLE id=parts-predicate prompt=Count the FEWEST contiguous parts the values can be cut into when no part's sum may exceed cap
    long long parts = 1, cur = 0;
    for (long long v : a) {
        if (cur + v > cap) { ++parts; cur = v; }   // close this part, open next
        else               { cur += v; }
    }
    // <<< HOLE
    return parts;
}

long long min_largest_part(const vector<long long>& a, long long k) {
    // >>> HOLE id=bisect-min-max prompt=Pick one cap that obviously cannot work and one that obviously does, then halve the gap between them until a single cap is left; parts_needed is your only tool
    long long lo = *max_element(a.begin(), a.end());          // smallest legal cap
    long long hi = accumulate(a.begin(), a.end(), 0LL);       // known feasible cap

    while (lo < hi) {
        long long mid = lo + (hi - lo) / 2;                   // never (lo + hi) / 2
        if (parts_needed(a, mid) <= k) hi = mid;              // mid works, keep it
        else                           lo = mid + 1;          // mid fails, discard it
    }
    // <<< HOLE
    return lo;                                                // lo == hi
}

// ---------------------------------------------------------------------------
// 2. MAXIMISE THE MINIMUM — the mirror. `lo = mid`, answer is lo.
//
//    Aggressive cows: place c cows in the given stall positions so the closest
//    pair is as far apart as possible.
//
//    Predicate: with a required spacing of d, greedily take the first stall and
//    then every stall at least d beyond the last taken. That greedy fits the
//    MOST cows, so feasible <=> placed(d) >= c.
//
//    Monotone the other way: if spacing d fits c cows, so does any smaller d.
//
//    THE TRAP: the branch that keeps mid is now `lo = mid`. With the
//    round-down midpoint, hi == lo + 1 gives mid == lo and lo never moves —
//    infinite loop. Round the midpoint UP.
// ---------------------------------------------------------------------------
long long cows_placed(const vector<long long>& xs, long long d) {
    long long placed = 1, last = xs[0];
    for (size_t i = 1; i < xs.size(); ++i) {
        if (xs[i] - last >= d) { ++placed; last = xs[i]; }
    }
    return placed;
}

long long max_min_spacing(vector<long long> xs, long long c) {
    if (c < 2) return 0;                        // no pair, no distance
    sort(xs.begin(), xs.end());

    long long lo = 0;                           // spacing 0 always fits
    long long hi = xs.back() - xs.front();      // more than this fits nobody

    // >>> HOLE id=round-up-mid prompt=Halve the spacing range in the maximise-the-minimum direction, where the branch that ACCEPTS mid keeps it; make sure the loop can still make progress on a two-value range
    while (lo < hi) {
        long long mid = lo + (hi - lo + 1) / 2; // ROUND UP — see above
        if (cows_placed(xs, mid) >= c) lo = mid;
        else                           hi = mid - 1;
    }
    // <<< HOLE
    return lo;
}

// ---------------------------------------------------------------------------
// 3. REAL-VALUED ANSWER — fixed iteration count, never an epsilon.
//
//    Maximum average of a contiguous subarray of length >= k.
//
//    Predicate: subtract the guess x from every element. A subarray has
//    average >= x exactly when its shifted sum is >= 0, so ask whether any
//    window of length >= k has a non-negative shifted sum — prefix sums, plus
//    the running minimum prefix at least k behind.
//
//    Monotone: raising x lowers every shifted sum, so once it is infeasible it
//    stays infeasible.
//
//    WHY A FIXED COUNT: `while (hi - lo > 1e-9)` is a hang waiting to happen —
//    near 1e12 consecutive doubles are already further apart than 1e-9, so the
//    condition never becomes false. 100 halvings shrink any sane range far
//    below double precision, in constant time. Loop, do not converge.
// ---------------------------------------------------------------------------
bool has_window_with_average(const vector<long long>& a, int k, double x) {
    int n = (int)a.size();
    vector<double> pre(n + 1, 0.0);
    for (int i = 0; i < n; ++i) pre[i + 1] = pre[i] + ((double)a[i] - x);

    double min_prefix = pre[0];
    for (int i = k; i <= n; ++i) {
        min_prefix = min(min_prefix, pre[i - k]);   // best start, >= k behind i
        if (pre[i] - min_prefix >= 0.0) return true;
    }
    return false;
}

double max_average_subarray(const vector<long long>& a, int k) {
    double lo = (double)*min_element(a.begin(), a.end());   // always achievable
    double hi = (double)*max_element(a.begin(), a.end());   // never beaten

    for (int it = 0; it < 100; ++it) {
        double mid = lo + (hi - lo) / 2;
        if (has_window_with_average(a, k, mid)) lo = mid;
        else                                    hi = mid;
    }
    return lo;
}

// ---------------------------------------------------------------------------
// Demo harness: reads n, k, then n values (non-negative — the part-splitting
// greedy assumes it).
//   line 1: smallest possible largest sum when split into k parts
//   line 2: largest possible minimum spacing placing k cows at these positions
//   line 3: maximum average over subarrays of length >= k
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n, k;
    if (!(cin >> n >> k)) return 0;
    if (n <= 0 || k <= 0 || k > n) return 0;

    vector<long long> a(n);
    for (long long& x : a) cin >> x;

    cout << min_largest_part(a, k) << "\n";
    cout << max_min_spacing(a, k) << "\n";
    cout << fixed << setprecision(6) << max_average_subarray(a, k) << "\n";
    return 0;
}
