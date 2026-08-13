// ===========================================================================
// EARLIEST FINISHING TIME
//
// The moment the items conflict with EACH OTHER — two bookings cannot share a
// hall, two shifts cannot share a guard — a shared budget is no longer the
// constraint and "cheapest first" means nothing. What replaces it:
//
//     sort by the END of the range, then take everything that still fits.
//
// The proof, which is the only reason to believe it:
//
//     let O be an optimal schedule and let g be the range that finishes first
//     of all. If O does not contain g, swap g for O's own first range. g ends
//     no later, so nothing else in O is disturbed, and |O| is unchanged. So
//     some optimal schedule contains g. Delete everything overlapping g and
//     repeat on what remains.
//
// The two keys that feel natural and are wrong:
//   * earliest START  — one booking that runs all day is taken first and
//                       destroys the whole schedule;
//   * shortest RANGE  — [1,5] [4,6] [6,10]: the short middle one is taken and
//                       blocks both others, giving 1 where 2 was available.
//
// Convention used throughout: a range that STARTS exactly when another ENDS
// does not conflict with it. Real statements differ; decide before you type.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

struct Range {
    long long start;
    long long finish;
};

// ---------------------------------------------------------------------------
// 1. SELECTION — the most non-overlapping ranges you can accept.
// ---------------------------------------------------------------------------
int max_non_overlapping(vector<Range> v) {
    int taken = 0;
    long long last = LLONG_MIN;             // end of the last acceptance
    // >>> HOLE id=earliest-finish prompt=Accept as many mutually clear ranges as possible: put them in the order that makes each acceptance provably safe, then sweep once carrying `last`
    sort(v.begin(), v.end(), [](const Range& a, const Range& b) {
        return a.finish < b.finish;         // the key IS the algorithm
    });
    for (const Range& r : v) {
        if (r.start >= last) {              // clear of everything already taken
            ++taken;
            last = r.finish;
        }
    }
    // <<< HOLE
    return taken;
}

// ---------------------------------------------------------------------------
// 2. COVERING — the fewest points that touch every range.
//
//    The same sort, read backwards. Walk the ranges by end; whenever one is
//    not yet covered, fire at its END, which is the latest point that still
//    hits it and therefore the point most likely to hit later ranges too.
//
//    "Minimum arrows to burst all balloons" and "fewest sensors covering every
//    interval" are this function with the nouns changed.
// ---------------------------------------------------------------------------
int min_points_touching_all(vector<Range> v) {
    sort(v.begin(), v.end(), [](const Range& a, const Range& b) {
        return a.finish != b.finish ? a.finish < b.finish : a.start < b.start;
    });

    int shots = 0;
    long long aim = LLONG_MIN;
    // >>> HOLE id=fire-at-the-end prompt=Sweep the ranges in the order they finish and place a point only when the current range is not already touched, keeping `aim` on the newest point
    for (const Range& r : v) {
        if (r.start > aim) {                // this range is not yet touched
            ++shots;
            aim = r.finish;                 // the latest point that still hits it
        }
    }
    // <<< HOLE
    return shots;
}

// ---------------------------------------------------------------------------
// 3. THE ROOM COUNT — how many halls are needed so that nothing clashes.
//
//    Not a selection at all: everything is accepted, and the answer is the
//    largest number of ranges alive at any one instant. The starts and ends are
//    sorted SEPARATELY and walked in step, because which range an ending
//    belongs to is irrelevant — only that a room came free.
// ---------------------------------------------------------------------------
int max_concurrent(const vector<Range>& v) {
    vector<long long> starts, ends;
    starts.reserve(v.size());
    ends.reserve(v.size());
    for (const Range& r : v) {
        starts.push_back(r.start);
        ends.push_back(r.finish);
    }
    sort(starts.begin(), starts.end());
    sort(ends.begin(), ends.end());

    int rooms = 0, best = 0;
    size_t i = 0, j = 0;
    // >>> HOLE id=sweep-rooms prompt=Walk the two sorted lists together, opening a room on every start and releasing one on every end that has already passed, recording the largest number open at once in `best`
    while (i < starts.size()) {
        if (rooms > 0 && ends[j] <= starts[i]) {
            --rooms;                        // that hall came free before this start
            ++j;
        } else {
            ++rooms;
            best = max(best, rooms);
            ++i;
        }
    }
    // <<< HOLE
    return best;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n            then n lines: start finish   (finish >= start)
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    if (!(cin >> n)) return 0;

    vector<Range> v(n);
    for (Range& r : v) cin >> r.start >> r.finish;

    cout << max_non_overlapping(v) << "\n";
    cout << min_points_touching_all(v) << "\n";
    cout << max_concurrent(v) << "\n";
    return 0;
}
