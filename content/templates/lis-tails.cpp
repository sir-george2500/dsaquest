// ===========================================================================
// THE TAILS ARRAY
//
// Form 1 is the quadratic recurrence and it comes first on purpose: the fast
// version is unreadable until you have seen exactly what its inner loop
// replaced. Do not skip to Form 2.
//
// The state, said properly:
//
//     length[k] = the length of the longest increasing subsequence that ends
//                 EXACTLY at position k
//
// The word "exactly" is the whole definition. Drop it — "the longest
// increasing subsequence among the first k elements" — and no transition can
// be written at all, because you would not know whether a[k] is allowed to
// extend whatever that subsequence was. This is the sharpest example in the
// whole region of a definition being the difference between a solvable and an
// unwritable problem.
//
// On the array [6, 2, 5, 1, 7, 4, 8, 3] the lengths are 1 1 2 1 3 2 4 2 and
// the answer is 4, achieved by 2, 5, 7, 8.
//
// The answer is the MAXIMUM over the array, not its last cell — because the
// best subsequence need not end at the last element.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. THE O(n^2) RECURRENCE — correct, and the right thing to write first.
//
//    For each k, look back at every earlier position i with a[i] < a[k] and
//    take the best chain ending there. If none exists the chain is just a[k]
//    alone, which is why every cell starts at 1.
//
//    Perfectly acceptable up to about n = 5000. At n = 2 * 10^5 it is
//    4 * 10^10 operations and a time-limit verdict, which is the whole reason
//    Form 2 exists.
// ---------------------------------------------------------------------------
int lis_quadratic(const vector<int>& a) {
    int n = (int)a.size();
    if (n == 0) return 0;
    vector<int> length(n, 1);
    // >>> HOLE id=quadratic-recurrence prompt=Fill length[k] as the longest strictly increasing subsequence ending exactly at k, by looking back at every earlier position whose value is smaller
    for (int k = 0; k < n; ++k) {
        for (int i = 0; i < k; ++i) {
            if (a[i] < a[k]) length[k] = max(length[k], length[i] + 1);
        }
    }
    // <<< HOLE
    return *max_element(length.begin(), length.end());
}

// ---------------------------------------------------------------------------
// 2. THE TAILS ARRAY — O(n log n), and one sentence carries all of it.
//
//        tails[k] = the SMALLEST value that can end an increasing subsequence
//                   of length k + 1, among the elements seen so far
//
//    Two consequences follow immediately and neither is obvious without the
//    sentence:
//
//      * tails is strictly increasing, always — so it can be binary searched.
//      * exactly one cell changes per element: either the array grows by one
//        at the end, or one existing entry is lowered.
//
//    Why lowering an entry is safe: a shorter tail can only be extended by
//    more of what comes later, and the LENGTH the cell represents is unchanged.
//    Nothing is ever lost.
//
//    THE TAILS ARRAY IS NOT A SUBSEQUENCE OF THE INPUT. On [6,2,5,1,7,4,8,3]
//    it ends as [1, 3, 7, 8] — but 3 is the final element of the input, so
//    nothing can follow it. The true answer is 2, 5, 7, 8. Only the array's
//    SIZE means anything; printing its contents is a wrong answer that has the
//    right length.
//
//    lower_bound finds the first entry NOT LESS than x, and overwriting it is
//    what enforces STRICT increase: an entry equal to x is replaced rather
//    than extended.
// ---------------------------------------------------------------------------
int lis_strict(const vector<int>& a) {
    vector<int> tails;
    // >>> HOLE id=tails-lower-bound prompt=For each value, either extend `tails` or overwrite the single entry it belongs in, keeping tails[k] equal to the smallest value that can end a strictly increasing subsequence of length k+1
    for (int x : a) {
        vector<int>::iterator it = lower_bound(tails.begin(), tails.end(), x);
        if (it == tails.end()) {
            tails.push_back(x);          // longer than anything so far
        } else {
            *it = x;                     // a smaller tail for the same length
        }
    }
    // <<< HOLE
    return (int)tails.size();
}

// ---------------------------------------------------------------------------
// 3. THE NON-DECREASING VARIANT — one function name of difference.
//
//    upper_bound finds the first entry STRICTLY GREATER than x, so an entry
//    equal to x is walked past rather than overwritten, and equal neighbours
//    are allowed to extend a chain.
//
//    On [2, 2, 2] the two functions give 1 and 3. No sample with distinct
//    values can tell them apart, which is why the statement's wording —
//    "increasing" against "non-decreasing" — is worth reading twice before a
//    single line is typed.
//
//    The same array answers "how many elements must be removed so the rest
//    never decreases": n minus this.
// ---------------------------------------------------------------------------
int lis_non_decreasing(const vector<int>& a) {
    vector<int> tails;
    // >>> HOLE id=tails-upper-bound prompt=Repeat the tails method with the one change that lets a value equal to an existing tail extend the chain instead of replacing it
    for (int x : a) {
        vector<int>::iterator it = upper_bound(tails.begin(), tails.end(), x);
        if (it == tails.end()) {
            tails.push_back(x);
        } else {
            *it = x;
        }
    }
    // <<< HOLE
    return (int)tails.size();
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n then n values -> quadratic LIS, tails LIS, non-decreasing, removals
// The first two must always agree; if they do not, Form 2 is wrong.
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    if (!(cin >> n)) return 0;
    vector<int> a(n);
    for (int& x : a) cin >> x;

    cout << lis_quadratic(a) << "\n";
    cout << lis_strict(a) << "\n";
    cout << lis_non_decreasing(a) << "\n";
    cout << n - lis_non_decreasing(a) << "\n";

    return 0;
}
