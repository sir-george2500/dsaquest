// ===========================================================================
// THE POINT THAT MINIMISES
//
// Nothing is selected and nothing is ordered. One value is chosen, and every
// element is dragged to it. Which value depends entirely on how the cost of
// dragging is measured, and the two common measures have different answers:
//
//     sum of |a_i - x|      minimised at the MIDDLE of the sorted values
//     sum of (a_i - x)^2    minimised at the MEAN
//
// The proof for the first is a balance argument. Move x one step to the right:
// every element already to the left costs one more, every element to the right
// costs one less. So the total changes by (count on the left - count on the
// right), which is zero exactly when the two sides are balanced. That is the
// middle, and it is why an outlier — which moves the mean and not the middle —
// cannot drag the answer.
//
// On [1, 2, 9]: the middle is 2 and costs 1+0+7 = 8; the mean is 4 and costs
// 3+2+5 = 10. Under squares the ranking reverses: 4 costs 38, 2 costs 50.
// Same input, two objectives, two different points. Read which one is asked.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. ABSOLUTE COST — the whole pattern in three lines.
//
//    When n is even, every value between the two middles is equally optimal
//    (the balance is exact across that whole stretch), so a[n/2] is always a
//    safe choice and no special case is needed.
// ---------------------------------------------------------------------------
long long min_total_distance(vector<long long> a) {
    long long total = 0;
    // >>> HOLE id=take-the-middle prompt=Choose the one value that minimises the sum of absolute differences, then charge every element for the distance it must travel to reach it
    sort(a.begin(), a.end());
    long long target = a[a.size() / 2];
    for (long long x : a) total += llabs(x - target);
    // <<< HOLE
    return total;
}

// ---------------------------------------------------------------------------
// 2. SQUARED COST — the mean, and why one rounding is not enough.
//
//    The real minimiser is sum/n, which is rarely an integer. Rounding once
//    and hoping is the standard way to be off by a little on the tests whose
//    mean lands near .5, so both neighbours are scored. Three candidates cost
//    3n operations and remove the entire class of bug.
//
//    Integer division truncates toward zero, so for negative sums sum/n is
//    already the ceiling — scanning one below as well is what makes this
//    correct for negative input rather than merely correct for the samples.
// ---------------------------------------------------------------------------
long long min_total_squares(const vector<long long>& a) {
    long long sum = 0;
    for (long long x : a) sum += x;
    long long n = (long long)a.size();

    long long best = LLONG_MAX;
    // >>> HOLE id=both-sides-of-the-mean prompt=Score the integers around the value that minimises a squared cost, keeping the smallest total in `best`
    long long mid = sum / n;                // truncated: scan its neighbours too
    for (long long cand = mid - 1; cand <= mid + 1; ++cand) {
        long long total = 0;
        for (long long x : a) total += (x - cand) * (x - cand);
        best = min(best, total);
    }
    // <<< HOLE
    return best;
}

// ---------------------------------------------------------------------------
// 3. THE RAMP TRANSFORM — "make them consecutive" is the same question.
//
//    The values must end up as h, h+1, h+2, ... in the order given, and h is
//    free. The cost is sum |a_i - (h + i)| = sum |(a_i - i) - h|, which is
//    form 1 applied to a_i - i. One subtraction converts a problem that looks
//    new into one already solved — and the whole trick is that subtraction.
//
//    Nothing is sorted here on purpose: position i is fixed by the statement,
//    so the subtraction must happen before any reordering.
// ---------------------------------------------------------------------------
long long min_cost_to_consecutive(vector<long long> a) {
    // >>> HOLE id=subtract-the-index prompt=Turn "the values must end up consecutive, in this order" into the plain question form 1 already answers, without reordering anything first
    for (size_t i = 0; i < a.size(); ++i) a[i] -= (long long)i;
    // <<< HOLE
    return min_total_distance(a);
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n            then n values (may be negative)
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    if (!(cin >> n) || n <= 0) return 0;

    vector<long long> a(n);
    for (long long& x : a) cin >> x;

    cout << min_total_distance(a) << "\n";
    cout << min_total_squares(a) << "\n";
    cout << min_cost_to_consecutive(a) << "\n";
    return 0;
}
