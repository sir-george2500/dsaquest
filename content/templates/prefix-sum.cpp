// ===========================================================================
// PREFIX SUMS & DIFFERENCE ARRAYS
//
// Core idea: pay O(n) once so that every range question is O(1) afterwards.
//
//     pre[0] = 0
//     pre[i] = a[0] + ... + a[i-1]           // pre has n+1 entries, not n
//     sum(a[l..r]) = pre[r+1] - pre[l]       // l, r inclusive, 0-indexed
//
// The size-(n+1), pre[0] = 0 convention is not a style choice. It is what makes
// l = 0 legal without a special case; every off-by-one in this pattern comes
// from writing pre[r] - pre[l-1] over a size-n array. Learn one convention and
// never deviate.
//
// The dual idea: a DIFFERENCE array does O(1) range UPDATE and one O(n) pass to
// read back, because prefix and difference are inverses: prefix(diff(a)) == a.
// Prefix = many queries on a static array. Difference = many updates, read once.
// Neither survives updates INTERLEAVED with queries - that is a Fenwick tree.
//
// Every accumulator here is long long. n = 2e5 values near 1e9 overflows int
// before the third element.
//
// Same skeleton, other monoids: prefix XOR (undone by XOR), prefix product mod p
// (undone by the modular inverse), prefix count of a predicate. Prefix MAX has
// no inverse, so it answers prefixes only - arbitrary ranges need a sparse table.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. THE CONVENTION — build once, query forever.
// ---------------------------------------------------------------------------
vector<long long> build_prefix(const vector<long long>& a) {
    vector<long long> pre(a.size() + 1, 0);           // n + 1, and pre[0] = 0
    for (size_t i = 0; i < a.size(); ++i)
        pre[i + 1] = pre[i] + a[i];
    return pre;
}

// Inclusive range [l, r]. l == 0 needs no special case — that is the point.
long long range_sum(const vector<long long>& pre, int l, int r) {
    if (l > r) return 0;                              // empty range, not an error
    return pre[r + 1] - pre[l];
}

// ---------------------------------------------------------------------------
// 2. PREFIX + HASH MAP — count subarrays with sum == target.
//
//    sum(a[l..r]) == target   <=>   pre[r+1] - pre[l] == target
//                             <=>   pre[l] == pre[r+1] - target
//
//    So sweep once, and at each r ask how many earlier prefixes had the value
//    (running - target). This is the form a sliding window CANNOT replace: with
//    negative values the sum is not monotone in the window, so there is nothing
//    to shrink towards.
//
//    Two details that are the whole difficulty:
//      * seed the map with {0: 1}   — the empty prefix, i.e. subarrays at l = 0
//      * look up BEFORE inserting   — or target == 0 counts empty subarrays
// ---------------------------------------------------------------------------
long long count_subarrays_with_sum(const vector<long long>& a, long long target) {
    unordered_map<long long, long long> seen;
    seen.reserve(a.size() * 2);
    seen[0] = 1;

    long long running = 0, total = 0;
    // >>> HOLE id=complement-lookup prompt=Sweep once, and at every right end credit yourself with the earlier prefixes that would complete a subarray summing to target; the order of asking and recording is the whole bug
    for (long long x : a) {
        running += x;
        auto it = seen.find(running - target);        // query first
        if (it != seen.end()) total += it->second;
        ++seen[running];                              // then record
    }
    // <<< HOLE
    return total;
}

// ---------------------------------------------------------------------------
// 3. DIFFERENCE ARRAY — O(1) range update, one pass to materialise.
//
//    d[l] += v and d[r+1] -= v mean "v starts applying at l and stops after r".
//    The prefix sum of d is the array of accumulated updates. Size is n+1 so
//    that r == n-1 can write d[n] without going out of bounds.
// ---------------------------------------------------------------------------
struct Difference {
    vector<long long> d;

    explicit Difference(size_t n) : d(n + 1, 0) {}

    void add(int l, int r, long long v) {             // inclusive [l, r]
        // >>> HOLE id=diff-update prompt=Record "add v to every index in [l, r]" in O(1), so that one later prefix pass materialises it
        d[l] += v;
        d[r + 1] -= v;
        // <<< HOLE
    }

    vector<long long> materialise() const {           // one O(n) pass at the end
        vector<long long> out(d.size() - 1);
        long long running = 0;
        for (size_t i = 0; i + 1 < d.size(); ++i) {
            running += d[i];
            out[i] = running;
        }
        return out;
    }
};

// ---------------------------------------------------------------------------
// 4. 2-D PREFIX — inclusion-exclusion, then four lookups per rectangle.
//
//    Build:  pre[i+1][j+1] = g[i][j] + pre[i][j+1] + pre[i+1][j] - pre[i][j]
//    Query:  pre[r2+1][c2+1] - pre[r1][c2+1] - pre[r2+1][c1] + pre[r1][c1]
//
//    The final + is the corner that both subtractions removed. Forgetting it is
//    invisible on any rectangle touching row 0 or column 0.
// ---------------------------------------------------------------------------
vector<vector<long long>> build_prefix_2d(const vector<vector<long long>>& g) {
    size_t rows = g.size();
    size_t cols = rows ? g[0].size() : 0;

    vector<vector<long long>> pre(rows + 1, vector<long long>(cols + 1, 0));
    // >>> HOLE id=prefix-2d prompt=Fill the table so that pre[i+1][j+1] is the sum of the whole rectangle from the top-left corner down to cell (i, j)
    for (size_t i = 0; i < rows; ++i)
        for (size_t j = 0; j < cols; ++j)
            pre[i + 1][j + 1] = g[i][j] + pre[i][j + 1] + pre[i + 1][j] - pre[i][j];
    // <<< HOLE
    return pre;
}

long long rect_sum(const vector<vector<long long>>& pre,
                   int r1, int c1, int r2, int c2) {  // inclusive corners
    return pre[r2 + 1][c2 + 1] - pre[r1][c2 + 1] - pre[r2 + 1][c1] + pre[r1][c1];
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n k
//   a[0..n-1]
//   q            then q lines: l r v   (inclusive, 0-indexed range add)
//   rows cols    then rows*cols grid values
//   r1 c1 r2 c2  (inclusive query rectangle)
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    long long k;
    if (!(cin >> n >> k)) return 0;

    vector<long long> a(n);
    for (long long& x : a) cin >> x;

    // 1. whole-array sum through the prefix array
    vector<long long> pre = build_prefix(a);
    cout << range_sum(pre, 0, n - 1) << "\n";

    // 2. subarrays summing to k (negatives welcome)
    cout << count_subarrays_with_sum(a, k) << "\n";

    // 3. seed a difference array with `a`, apply q range adds, materialise once
    int q;
    cin >> q;
    Difference diff(n);
    for (int i = 0; i < n; ++i) diff.add(i, i, a[i]);
    for (int t = 0; t < q; ++t) {
        int l, r;
        long long v;
        cin >> l >> r >> v;
        diff.add(l, r, v);
    }
    vector<long long> updated = diff.materialise();
    for (int i = 0; i < n; ++i) cout << updated[i] << " \n"[i + 1 == n];

    // 4. 2-D: whole grid, then one interior rectangle
    int rows, cols;
    cin >> rows >> cols;
    vector<vector<long long>> g(rows, vector<long long>(cols));
    for (auto& row : g)
        for (long long& x : row) cin >> x;

    vector<vector<long long>> pre2d = build_prefix_2d(g);
    cout << rect_sum(pre2d, 0, 0, rows - 1, cols - 1) << "\n";

    int r1, c1, r2, c2;
    cin >> r1 >> c1 >> r2 >> c2;
    cout << rect_sum(pre2d, r1, c1, r2, c2) << "\n";
    return 0;
}
