// ===========================================================================
// SLIDING WINDOW
//
// The invariant is the whole pattern:
//
//     [l, r] is ALWAYS the longest window ending at r that satisfies P.
//
// Each step: admit a[r], then shrink from l until P holds again, then record.
// Every index enters once and leaves once, so it is O(n) despite the inner
// while loop. If you cannot state P as "shrinking from the left can only help",
// this is the wrong pattern.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. VARIABLE window — longest subarray with at most k distinct values.
// ---------------------------------------------------------------------------
int longest_at_most_k_distinct(const vector<int>& a, int k) {
    unordered_map<int, int> freq;
    int best = 0, l = 0;

    for (int r = 0; r < (int)a.size(); ++r) {
        ++freq[a[r]];                       // admit

        // >>> HOLE id=shrink prompt=a[r] has just been admitted; give up positions on the left until the window is legal again, keeping the distinct-value count honest
        while ((int)freq.size() > k) {      // restore the invariant
            if (--freq[a[l]] == 0)
                freq.erase(a[l]);           // erase, or size() lies
            ++l;
        }
        // <<< HOLE

        best = max(best, r - l + 1);        // record
    }
    return best;
}

// ---------------------------------------------------------------------------
// 2. FIXED window — best sum over every window of exactly size k.
//    No while loop: the window slides rather than breathing.
// ---------------------------------------------------------------------------
long long best_fixed_window(const vector<int>& a, int k) {
    if ((int)a.size() < k) return LLONG_MIN;

    long long sum = 0;
    for (int i = 0; i < k; ++i) sum += a[i];

    long long best = sum;
    // >>> HOLE id=slide prompt=Walk the fixed-size window to the end of the array, keeping its sum current in O(1) per step and tracking the best seen
    for (int r = k; r < (int)a.size(); ++r) {
        sum += a[r] - a[r - k];             // one in, one out
        best = max(best, sum);
    }
    // <<< HOLE
    return best;
}

// ---------------------------------------------------------------------------
// 3. The AT-MOST-K trick — how to answer "exactly k".
//
//    exactly(k) = atMost(k) - atMost(k - 1)
//
//    "Exactly k" is not monotonic, so a window cannot maintain it directly.
//    "At most k" is monotonic, so it can. Two windows, subtract. This turns a
//    whole class of otherwise-hard problems into two calls.
// ---------------------------------------------------------------------------
long long count_at_most_k_distinct(const vector<int>& a, int k) {
    if (k < 0) return 0;

    unordered_map<int, int> freq;
    long long total = 0;
    int l = 0;

    for (int r = 0; r < (int)a.size(); ++r) {
        ++freq[a[r]];
        // >>> HOLE id=count-endings prompt=Re-establish the at-most-k invariant, then add the number of valid subarrays whose right end is exactly r
        while ((int)freq.size() > k) {
            if (--freq[a[l]] == 0) freq.erase(a[l]);
            ++l;
        }
        total += r - l + 1;                 // every subarray ending at r
        // <<< HOLE
    }
    return total;
}

long long count_exactly_k_distinct(const vector<int>& a, int k) {
    return count_at_most_k_distinct(a, k) - count_at_most_k_distinct(a, k - 1);
}

// ---------------------------------------------------------------------------
// Demo harness: reads n, k, then n values.
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n, k;
    if (!(cin >> n >> k)) return 0;

    vector<int> a(n);
    for (int& x : a) cin >> x;

    cout << longest_at_most_k_distinct(a, k) << "\n";
    cout << best_fixed_window(a, k) << "\n";
    cout << count_exactly_k_distinct(a, k) << "\n";
    return 0;
}
