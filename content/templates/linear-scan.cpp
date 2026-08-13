// ===========================================================================
// ONE PASS, ONE RUNNING ANSWER
//
// The nested loop that recomputes a summary of the prefix at every position is
// the most common way a correct O(n) idea is written as an O(n^2) program. The
// cure is always the same question:
//
//     what did position i-1 already know, and how do I carry it forward?
//
// Name that quantity, keep it in a variable, update it in O(1) as each element
// arrives, and the inner loop has nothing left to do. The whole pattern is one
// walk, two or three scalars, and no container at all — which is also why it
// survives bounds where storing the input would not.
//
// Three rules that the three forms below exist to teach:
//   * take the answer INSIDE the loop, or a run that ends early is never
//     scored;
//   * initialise a maximum from the data, never from 0, unless the empty
//     answer is genuinely allowed;
//   * anything summed over the array is long long.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. THE SHAPE, WITH NOTHING IN THE WAY.
//
//    Total and maximum in a single pass. Nobody gets this wrong, which is the
//    point: it shows the skeleton — one loop, state updated per element, the
//    answer always correct for the prefix read so far — before the skeleton
//    has anything difficult hung on it.
//
//    Note `total` is long long. 10^5 values of 10^9 reach 10^14, and an int
//    accumulator passes INT_MAX on the third element.
// ---------------------------------------------------------------------------
struct Summary {
    long long total;
    long long largest;
};

Summary summarise(const vector<long long>& a) {
    Summary s{0, LLONG_MIN};
    // >>> HOLE id=running-summary prompt=Walk the values once, accumulating the total and keeping the largest seen; both must be correct for the prefix read so far at every step
    for (long long x : a) {
        s.total += x;
        s.largest = max(s.largest, x);
    }
    // <<< HOLE
    return s;
}

// ---------------------------------------------------------------------------
// 2. THE LARGEST SUM OF A CONTIGUOUS STRETCH.
//
//    The state to carry is the best stretch that ENDS at the current position.
//    There are only two candidates for it: the previous best stretch extended
//    by this element, or this element starting a new one. Whichever is larger
//    is the new state, and the answer is the largest state ever held.
//
//    The empty stretch is NOT allowed here, so `best` starts at the first
//    element rather than at 0. Start it at 0 and an all-negative row reports 0
//    — an answer that is not any stretch of the row at all. Some statements do
//    allow the empty stretch; that is a sentence to read, not a default.
//
//    On [-1, 2, 4, -3, 5, 2, -5, 2] the answer is 10, from 2 4 -3 5 2.
// ---------------------------------------------------------------------------
long long largest_stretch_sum(const vector<long long>& a) {
    if (a.empty()) return 0;
    long long best = a[0];
    long long ending_here = a[0];
    // >>> HOLE id=best-ending-here prompt=For each remaining element decide between extending the stretch that ends at the previous position and starting again at this element, then score the result before moving on
    for (size_t i = 1; i < a.size(); ++i) {
        ending_here = max(a[i], ending_here + a[i]);
        best = max(best, ending_here);
    }
    // <<< HOLE
    return best;
}

// ---------------------------------------------------------------------------
// 3. THE LONGEST RUN.
//
//    Same shape, different state: a counter that grows while a property of
//    ADJACENT elements holds and resets to 1 when it breaks. The maximum is
//    taken inside the loop, because the longest run is very often not the one
//    the row ends on.
// ---------------------------------------------------------------------------
int longest_non_decreasing_run(const vector<long long>& a) {
    if (a.empty()) return 0;
    int best = 1;
    int run = 1;
    // >>> HOLE id=run-length prompt=Extend the current run while each element is at least its predecessor and restart it at 1 when that breaks, scoring the best length as you go
    for (size_t i = 1; i < a.size(); ++i) {
        run = (a[i] >= a[i - 1]) ? run + 1 : 1;
        best = max(best, run);
    }
    // <<< HOLE
    return best;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n   then n values  ->  total, largest, largest stretch sum, longest run
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    if (!(cin >> n)) return 0;
    vector<long long> a(n);
    for (long long& x : a) cin >> x;

    Summary s = summarise(a);
    cout << s.total << ' ' << (a.empty() ? 0 : s.largest) << "\n";
    cout << largest_stretch_sum(a) << "\n";
    cout << longest_non_decreasing_run(a) << "\n";

    return 0;
}
