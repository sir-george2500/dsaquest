// ===========================================================================
// THE SECOND AXIS
//
// One index is enough while the only thing you must remember is WHERE you are.
// The moment the legality of a choice depends on how much of a shared budget
// has already been spent, that remainder is part of the state, and the state
// grows an axis:
//
//     dp[i][w] = the best value obtainable from the first i items
//                using total weight at most w
//
// Say the sentence with both indices in it or the table means nothing.
//
// The transition is a case split on one item, and there are exactly two cases:
//
//     skip it:  dp[i][w]  =  dp[i-1][w]
//     take it:  dp[i][w]  =  dp[i-1][w - weight[i]] + value[i]      (if it fits)
//
// Notice that BOTH cases read row i - 1. That single fact is what forces the
// loop direction once the row is rolled away, and it is the bug this template
// exists to inoculate against.
//
// This is the problem the Ridge of Greed cannot solve. Capacity 50 with items
// (value 60, weight 10), (100, 20), (120, 30): value-per-weight sorting takes
// the first two for 160 and cannot fit the third into the remaining 20. The
// optimum is 100 + 120 = 220. No ranking of the items produces it, because
// what a choice costs is capacity that a better combination needed.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. THE 0/1 KNAPSACK — each item taken whole, or not at all.
//
//    The item axis is rolled away: one row is kept and updated in place. That
//    is legal only if, while item i is being processed, every cell the
//    transition READS still holds row i - 1's value.
//
//    dp[w] reads dp[w - weight], which is to its LEFT. So the left of the row
//    must still be stale when it is read, which means w must descend.
//
//    Run the loop forwards and dp[w - weight] has already been updated with
//    item i, so item i is taken twice — and three times, and four. On a single
//    item of weight 1 and value 1 with capacity 3:
//
//        descending:  dp = 0 1 1 1     (correct: one item, one unit of value)
//        ascending:   dp = 0 1 2 3     (the unbounded answer, silently)
//
//    Every sample where no item is worth repeating passes under both. That is
//    what makes it a judge bug rather than a sample bug.
//
//    The "skip" case needs no code: leaving the cell alone IS keeping row
//    i - 1's value, which is exactly what skipping means.
// ---------------------------------------------------------------------------
long long knapsack01(const vector<long long>& value, const vector<int>& weight, int capacity) {
    vector<long long> dp(capacity + 1, 0);
    // >>> HOLE id=zero-one-descending prompt=For each item, update the single dp row in the direction that keeps the cell being read at the previous item's value, so no item is ever taken twice
    for (size_t i = 0; i < value.size(); ++i) {
        for (int w = capacity; w >= weight[i]; --w) {
            dp[w] = max(dp[w], dp[w - weight[i]] + value[i]);
        }
    }
    // <<< HOLE
    return dp[capacity];
}

// ---------------------------------------------------------------------------
// 2. THE UNBOUNDED KNAPSACK — an unlimited supply of each kind.
//
//    Identical table, identical transition, and the loop runs the other way.
//    Ascending is correct here *because* dp[w - weight] has already seen this
//    item: that is precisely how a second copy of it gets taken.
//
//    Capacity 5 with items (value 4, weight 2) and (value 5, weight 3):
//
//        0/1:        dp = 0 0 4 5 5 9
//        unbounded:  dp = 0 0 4 5 8 9      (dp[4] = two of the first item)
//
//    One character of difference between the two functions. Learn them as a
//    pair or you will learn neither.
// ---------------------------------------------------------------------------
long long knapsack_unbounded(const vector<long long>& value, const vector<int>& weight,
                             int capacity) {
    vector<long long> dp(capacity + 1, 0);
    // >>> HOLE id=unbounded-ascending prompt=For each item, update the dp row in the direction that deliberately lets a cell reuse the same item any number of times
    for (size_t i = 0; i < value.size(); ++i) {
        for (int w = weight[i]; w <= capacity; ++w) {
            dp[w] = max(dp[w], dp[w - weight[i]] + value[i]);
        }
    }
    // <<< HOLE
    return dp[capacity];
}

// ---------------------------------------------------------------------------
// 3. SUBSET SUM — the cell is a yes/no rather than a number.
//
//    reach[s] = can some subset of the items processed so far total EXACTLY s?
//
//    "Exactly" changes the border and nothing else: only reach[0] starts true,
//    because the empty subset totals zero and nothing else is reachable before
//    any item has been seen. Initialising the whole array to true would be
//    claiming every total is achievable from no items at all.
//
//    Same descending loop, same reason. The return value here is the largest
//    reachable total not exceeding the target, which is the shape the
//    partition question needs: run it to sum/2 and the two halves differ by
//    total - 2 * best.  On [1, 5, 11, 5] the total is 22, the best half is 11,
//    and the difference is 0.
// ---------------------------------------------------------------------------
int best_reachable_total(const vector<int>& item, int target) {
    vector<char> reach(target + 1, 0);
    reach[0] = 1;                            // the empty subset, and only it
    // >>> HOLE id=subset-reachability prompt=Mark every total reachable by some subset of the items, without letting a single item contribute to one total more than once
    for (int x : item) {
        for (int s = target; s >= x; --s) {
            if (reach[s - x]) reach[s] = 1;
        }
    }
    // <<< HOLE
    for (int s = target; s >= 0; --s) {
        if (reach[s]) return s;
    }
    return 0;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n C  then n pairs "value weight"  -> 0/1 best, then unbounded best
//   m T  then m item sizes            -> largest reachable total <= T
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n, capacity;
    if (!(cin >> n >> capacity)) return 0;
    vector<long long> value(n);
    vector<int> weight(n);
    for (int i = 0; i < n; ++i) cin >> value[i] >> weight[i];
    cout << knapsack01(value, weight, capacity) << "\n";
    cout << knapsack_unbounded(value, weight, capacity) << "\n";

    int m, target;
    cin >> m >> target;
    vector<int> item(m);
    for (int& x : item) cin >> x;
    cout << best_reachable_total(item, target) << "\n";

    return 0;
}
