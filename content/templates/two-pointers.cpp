// ===========================================================================
// TWO POINTERS  (the converging form)
//
// l = 0, r = n-1 on a SORTED (or otherwise monotone) sequence. At every step
// compare the two ends, then PROVE one of them is useless and throw it away.
//
// The discard argument is the whole pattern:
//
//     a[l] + a[r] < target  =>  a[l] paired with any surviving partner is
//                               <= a[l] + a[r] < target, so a[l] is dead
//                               forever. l must move right.
//     a[l] + a[r] > target  =>  symmetric: a[r] is dead, r must move left.
//
// If you cannot state an argument of that shape for your problem, you are
// guessing and the O(n) sweep is unjustified.
//
// l only increases and r only decreases, so together they take at most n
// steps - that is the linearity, not the loop shape.
//
// NOT this pattern: if BOTH pointers move forward and the region between them
// is what you are maintaining, that is a sliding window.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. CONVERGING on a sorted array — the pair with a given sum.
//    Returns indices into `a`, or {-1, -1}.
// ---------------------------------------------------------------------------
pair<int, int> pair_sum_sorted(const vector<int>& a, long long target) {
    int l = 0, r = (int)a.size() - 1;

    // >>> HOLE id=discard prompt=Close the two ends toward each other, each step proving that one endpoint can belong to no remaining answer and throwing it away
    while (l < r) {                              // strict: no self-pairing
        long long s = (long long)a[l] + a[r];    // cast, or 1e9 + 1e9 overflows
        if (s == target) return {l, r};
        if (s < target) ++l;                     // every partner left to a[l] is <= a[r]
        else            --r;                     // every partner left to a[r] is >= a[l]
    }
    // <<< HOLE
    return {-1, -1};
}

// Same skeleton, different test: the two ends must agree instead of sum to a
// target. Both move because neither side is the one that "failed".
bool is_palindrome(const string& s) {
    int l = 0, r = (int)s.size() - 1;
    while (l < r) {
        if (s[l] != s[r]) return false;
        ++l;
        --r;
    }
    return true;
}

// ---------------------------------------------------------------------------
// 2. FIX ONE, THEN CONVERGE — every distinct triple summing to `target`.
//    O(n^2): the outer loop pins a[i], the inner sweep is form 1 on the tail.
//    Duplicate skipping is the classic bug source; all three skips matter.
// ---------------------------------------------------------------------------
vector<array<int, 3>> three_sum(vector<int> a, long long target) {
    sort(a.begin(), a.end());                    // the precondition, never assume it
    const int n = (int)a.size();
    vector<array<int, 3>> out;

    for (int i = 0; i + 2 < n; ++i) {
        if (i > 0 && a[i] == a[i - 1]) continue; // (a) same pinned value => same triples

        const long long need = target - a[i];
        int l = i + 1, r = n - 1;

        while (l < r) {
            long long s = (long long)a[l] + a[r];
            if (s < need) {
                ++l;
            } else if (s > need) {
                --r;
            } else {
                // >>> HOLE id=triple-dedupe prompt=A triple has just been found: record it, then move both ends inward past every repeat of the two values you just used, without ever letting them cross
                out.push_back({a[i], a[l], a[r]});
                ++l;
                --r;                                        // (b) both, or it repeats forever
                while (l < r && a[l] == a[l - 1]) ++l;      // (c) l < r guard, or you walk off
                while (l < r && a[r] == a[r + 1]) --r;
                // <<< HOLE
            }
        }
    }
    return out;
}

// ---------------------------------------------------------------------------
// 3. CONVERGING on something that is not a sum — container with most water.
//    Start at maximum width; the discard argument is about the SHORTER wall.
// ---------------------------------------------------------------------------
long long max_container_area(const vector<int>& h) {
    int l = 0, r = (int)h.size() - 1;
    long long best = 0;

    while (l < r) {
        // >>> HOLE id=shorter-wall prompt=Score the pair of walls you are standing on, then retire whichever of the two can never take part in a larger area
        long long area = (long long)min(h[l], h[r]) * (r - l);
        best = max(best, area);

        // The shorter wall caps every pair it belongs to, and width only
        // shrinks from here, so no pair using it can ever beat `area`.
        if (h[l] < h[r]) ++l;
        else             --r;
        // <<< HOLE
    }
    return best;
}

// ---------------------------------------------------------------------------
// 4. SAME DIRECTION — slow write pointer, fast read pointer.
//    Invariant: [0, slow) is the finished answer; fast scans the raw input.
//    Nothing is discarded from an end here, but nothing is maintained between
//    the pointers either - so it is still not a window.
// ---------------------------------------------------------------------------
int dedup_sorted(vector<int>& a) {
    if (a.empty()) return 0;

    int slow = 1;                                     // a[0] is always kept
    for (int fast = 1; fast < (int)a.size(); ++fast)
        if (a[fast] != a[slow - 1])                   // compare against what was WRITTEN
            a[slow++] = a[fast];

    a.resize(slow);
    return slow;
}

// One pointer per sequence: the smaller head is always safe to emit, because
// nothing behind it in either list can be smaller. `<=` keeps it stable.
vector<int> merge_sorted(const vector<int>& x, const vector<int>& y) {
    vector<int> out;
    out.reserve(x.size() + y.size());

    size_t i = 0, j = 0;
    while (i < x.size() && j < y.size()) {
        if (x[i] <= y[j]) out.push_back(x[i++]);
        else              out.push_back(y[j++]);
    }
    while (i < x.size()) out.push_back(x[i++]);
    while (j < y.size()) out.push_back(y[j++]);
    return out;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n target
//   n values          (sorted internally for forms 1, 2 and 4)
//   m
//   m heights         (form 3)
//   word              (palindrome check)
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    long long target;
    if (!(cin >> n >> target)) return 0;

    vector<int> raw(n);
    for (int& x : raw) cin >> x;

    vector<int> a = raw;
    sort(a.begin(), a.end());

    auto [pl, pr] = pair_sum_sorted(a, target);
    if (pl < 0) cout << "no pair\n";
    else        cout << a[pl] << " " << a[pr] << "\n";

    vector<array<int, 3>> triples = three_sum(raw, target);
    cout << triples.size() << "\n";
    for (const auto& t : triples) cout << t[0] << " " << t[1] << " " << t[2] << "\n";

    int m;
    if (!(cin >> m)) return 0;
    vector<int> h(m);
    for (int& x : h) cin >> x;
    cout << max_container_area(h) << "\n";

    vector<int> uniq = a;
    cout << dedup_sorted(uniq) << "\n";

    // Both halves of a sorted array are sorted: split, then merge them back.
    vector<int> part1(a.begin(), a.begin() + n / 2);
    vector<int> part2(a.begin() + n / 2, a.end());
    vector<int> merged = merge_sorted(part1, part2);
    for (size_t i = 0; i < merged.size(); ++i) cout << merged[i] << (i + 1 == merged.size() ? "" : " ");
    cout << "\n";

    string word;
    if (cin >> word) cout << (is_palindrome(word) ? "yes" : "no") << "\n";
    return 0;
}
