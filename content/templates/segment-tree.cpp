// ===========================================================================
// ANY MERGE, ANY RANGE
//
// A Fenwick tree can only do what it can undo: range(l, r) is
// prefix(r) - prefix(l-1), and that subtraction is the whole method. Ask it
// for the MINIMUM of a range and it has nothing to say, because there is no
// operation that removes a[1..l-1] from a minimum.
//
// A segment tree does not subtract. It stores, at every node, the answer for
// that node's own range, and it answers a query by combining O(log n) whole
// nodes that exactly tile the range asked for. Nothing is ever removed, so
// nothing needs an inverse. It needs only two things of the operation:
//
//     ASSOCIATIVITY   merge(merge(a, b), c) == merge(a, merge(b, c))
//     AN IDENTITY     merge(e, x) == x, for the empty range
//
// gcd(gcd(12,18),24) = gcd(12,gcd(18,24)) = 6, so gcd is fine. Subtraction is
// not: (10-3)-2 = 5 and 10-(3-2) = 9, so a "range difference" tree is
// meaningless however carefully it is coded.
//
// The identity is where the silent bugs live. For a maximum over values that
// may be negative the identity is LLONG_MIN, not 0 — a tree built with 0
// answers "the largest of [-5, -2, -9] is 0", which is not even in the array.
//
// Two forms below:
//   1. the iterative tree, 2n cells, no recursion, point update, range query;
//   2. the recursive tree with LAZY tags, which is what a RANGE update needs.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. THE ITERATIVE TREE — leaves at n..2n-1, parent of i is i/2.
//
//    Node i's children are 2i and 2i+1, so a point update walks from the leaf
//    to the root re-merging as it climbs: log n steps, no recursion, no 4n
//    array, and about twice the speed of the recursive form.
//
//    The query walks the two ends inwards over a HALF-OPEN range [l, r).
//    Whenever the left pointer is a right child it can never be part of a
//    whole parent, so it is taken and stepped past; symmetrically on the
//    right. When the pointers meet, the range has been tiled exactly.
//
//    On [3, 1, 4, 1, 5, 9, 2, 6] the maximum over positions 2..5 is 9 and
//    over 0..3 is 4.
//
//    NB: this bottom-up loop combines nodes out of left-to-right order, which
//    is invisible for max, min, sum and gcd — they are commutative. For a
//    merge that is NOT commutative (matrix products, string concatenation)
//    accumulate the left side and the right side into two separate values and
//    join them at the end.
// ---------------------------------------------------------------------------
struct MaxTree {
    static constexpr long long IDENTITY = LLONG_MIN;   // neutral for max, and 0 is not

    int n = 0;
    vector<long long> t;

    explicit MaxTree(const vector<long long>& a) : n((int)a.size()), t(2 * max((int)a.size(), 1), IDENTITY) {
        for (int i = 0; i < n; ++i) t[n + i] = a[i];
        for (int i = n - 1; i >= 1; --i) t[i] = max(t[2 * i], t[2 * i + 1]);
    }

    void assign(int pos, long long value) {
        // >>> HOLE id=climb prompt=Set the leaf for `pos` to `value` and repair every ancestor, remembering that node i's children are 2i and 2i+1
        pos += n;
        t[pos] = value;
        for (pos >>= 1; pos >= 1; pos >>= 1) t[pos] = max(t[2 * pos], t[2 * pos + 1]);
        // <<< HOLE
    }

    // Half-open [l, r). Returns IDENTITY for an empty range, which is the
    // only honest answer and the reason IDENTITY has to be right.
    long long largest(int l, int r) const {
        long long best = IDENTITY;
        // >>> HOLE id=tile prompt=Combine the O(log n) whole nodes that exactly tile the half-open range [l, r) into `best`, walking the two ends inwards
        for (l += n, r += n; l < r; l >>= 1, r >>= 1) {
            if (l & 1) best = max(best, t[l++]);   // a right child: take it, step past
            if (r & 1) best = max(best, t[--r]);   // ditto, mirrored
        }
        // <<< HOLE
        return best;
    }
};

// ---------------------------------------------------------------------------
// 2. LAZY PROPAGATION — a range update that does not touch the range.
//
//    Adding v to every position of a range of length 2*10^5 as point updates
//    is 2*10^5 climbs. Instead, the same O(log n) nodes that tile the range
//    are each given a TAG saying "everything below me is also owed v", and
//    the node's own answer is corrected immediately. The tag is only pushed
//    to the children when a later call needs to descend past that node.
//
//    Two halves, and both are load-bearing:
//      * apply the tag to the child's ANSWER, so a query stopping there is
//        already correct;
//      * add it to the child's own TAG, so the debt keeps travelling.
//    Do the first and forget the second and the update evaporates one level
//    down; do the second and forget the first and every query above a pending
//    tag reads a stale value.
//
//    4n cells, not 2n: the recursion splits at the midpoint, and for an n
//    that is not a power of two the deepest index overshoots 2n.
// ---------------------------------------------------------------------------
struct AddMinTree {
    static constexpr long long IDENTITY = LLONG_MAX;   // neutral for min

    int n = 0;
    vector<long long> mn, lazy;

    explicit AddMinTree(const vector<long long>& a)
        : n((int)a.size()), mn(4 * max((int)a.size(), 1), 0), lazy(4 * max((int)a.size(), 1), 0) {
        if (n > 0) build(a, 1, 0, n - 1);
    }

    void build(const vector<long long>& a, int node, int lo, int hi) {
        if (lo == hi) {
            mn[node] = a[lo];
            return;
        }
        int mid = (lo + hi) / 2;
        build(a, 2 * node, lo, mid);
        build(a, 2 * node + 1, mid + 1, hi);
        mn[node] = min(mn[2 * node], mn[2 * node + 1]);
    }

    void push(int node) {
        // >>> HOLE id=push-down prompt=Hand this node's pending addition to both children — correcting each child's own answer as well as its tag — and clear it here
        if (lazy[node] == 0) return;
        for (int child : {2 * node, 2 * node + 1}) {
            mn[child] += lazy[node];
            lazy[child] += lazy[node];
        }
        lazy[node] = 0;
        // <<< HOLE
    }

    void add(int node, int lo, int hi, int l, int r, long long v) {
        if (r < lo || hi < l) return;
        if (l <= lo && hi <= r) {
            mn[node] += v;
            lazy[node] += v;
            return;
        }
        push(node);
        int mid = (lo + hi) / 2;
        add(2 * node, lo, mid, l, r, v);
        add(2 * node + 1, mid + 1, hi, l, r, v);
        mn[node] = min(mn[2 * node], mn[2 * node + 1]);
    }

    long long smallest(int node, int lo, int hi, int l, int r) {
        if (r < lo || hi < l) return IDENTITY;
        if (l <= lo && hi <= r) return mn[node];
        push(node);
        int mid = (lo + hi) / 2;
        return min(smallest(2 * node, lo, mid, l, r), smallest(2 * node + 1, mid + 1, hi, l, r));
    }

    // Inclusive [l, r], 0-indexed, for callers who should not have to know
    // that the root is node 1 and spans 0..n-1.
    void add(int l, int r, long long v) {
        if (n > 0) add(1, 0, n - 1, l, r, v);
    }
    long long smallest(int l, int r) { return n > 0 ? smallest(1, 0, n - 1, l, r) : IDENTITY; }
};

// ---------------------------------------------------------------------------
// Demo harness.
//   n q          then n values, then q commands on the MAX tree
//       1 pos v      set position pos (0-indexed) to v
//       2 l r        print the largest over the inclusive range l..r
//   m s          then m values, then s commands on the LAZY MIN tree
//       1 l r v      add v to every position of the inclusive range l..r
//       2 l r        print the smallest over the inclusive range l..r
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n = 0, q = 0;
    if (!(cin >> n >> q)) return 0;
    vector<long long> a(max(n, 0));
    for (long long& x : a) cin >> x;

    MaxTree maxes(a);
    for (int i = 0; i < q; ++i) {
        int kind = 0;
        if (!(cin >> kind)) return 0;
        if (kind == 1) {
            int pos = 0;
            long long value = 0;
            cin >> pos >> value;
            maxes.assign(pos, value);
        } else {
            int l = 0, r = 0;
            cin >> l >> r;
            cout << maxes.largest(l, r + 1) << "\n";     // inclusive -> half-open
        }
    }

    int m = 0, s = 0;
    if (!(cin >> m >> s)) return 0;
    vector<long long> b(max(m, 0));
    for (long long& x : b) cin >> x;

    AddMinTree mins(b);
    for (int i = 0; i < s; ++i) {
        int kind = 0;
        if (!(cin >> kind)) return 0;
        int l = 0, r = 0;
        if (kind == 1) {
            long long v = 0;
            cin >> l >> r >> v;
            mins.add(l, r, v);
        } else {
            cin >> l >> r;
            cout << mins.smallest(l, r) << "\n";
        }
    }

    return 0;
}
