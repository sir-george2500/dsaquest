// ===========================================================================
// PREFIX SUMS THAT SURVIVE UPDATES
//
// A prefix-sum table answers any range in O(1) and dies the instant one value
// changes: repairing it costs O(n), so q updates cost O(n*q) and 10^5 of each
// is 10^10 operations.
//
// A Fenwick tree — a binary indexed tree — keeps the same information in a
// form that can be repaired. Cell i holds the sum of a block of the array
// ending at i, and the length of that block is i's LOWEST SET BIT:
//
//     lowbit(i) = i & -i        cell i covers  i - lowbit(i) + 1 .. i
//
//     i =  6   lowbit 2   covers  5..6
//     i =  8   lowbit 8   covers  1..8
//     i = 12   lowbit 4   covers  9..12
//
// Every prefix is then a sum of at most log n of those blocks, and every
// position lies in at most log n of them. Both walks are one line:
//
//     prefix   i -= i & -i     strip the lowest bit, jumping left
//     add      i += i & -i     add the lowest bit, jumping to the enclosing cell
//
// Two rules that outlive every problem:
//   * a Fenwick is ALWAYS 1-indexed. lowbit(0) is 0, so the add loop at
//     position 0 never advances and hangs forever;
//   * a Fenwick answers a range only by SUBTRACTING two prefixes, so the
//     operation must have an inverse. Sums and counts and xors, yes. Minimum,
//     never — that is a segment tree.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. THE TREE ITSELF — two loops, four lines, and the whole structure.
//
//    On a = [3, 2, -1, 6, 5, 4, -3, 3] (1-indexed):
//        prefix(7) = 16, and it visits exactly cells 7, 6 and 4
//        prefix(4) = 10
//        range(5, 7) = 16 - 10 = 6
//        add(3, v)   touches exactly cells 3, 4 and 8
//
//    `add` adds a DELTA. Setting position i to a new value is
//    add(i, wanted - current), which means you keep the plain array too, or
//    you read the old value back with range(i, i).
// ---------------------------------------------------------------------------
struct Fenwick {
    int n = 0;
    vector<long long> bit;

    explicit Fenwick(int size) : n(size), bit(size + 1, 0) {}

    void add(int i, long long delta) {
        // >>> HOLE id=fenwick-add prompt=Add `delta` to position i, repairing every cell whose block contains i — walk upwards by the lowest set bit
        for (; i <= n; i += i & -i) bit[i] += delta;
        // <<< HOLE
    }

    long long prefix(int i) const {
        long long total = 0;
        // >>> HOLE id=fenwick-prefix prompt=Total positions 1..i by adding the cells whose blocks tile that prefix — walk downwards by stripping the lowest set bit
        for (; i > 0; i -= i & -i) total += bit[i];
        // <<< HOLE
        return total;
    }

    // Inclusive, 1-indexed. This subtraction is why the operation must be
    // invertible, and it is the exact line a min-tree cannot write.
    long long range(int l, int r) const { return prefix(r) - prefix(l - 1); }

    // O(n) construction. n separate add() calls would be O(n log n), which is
    // fine at 2*10^5 and is not fine when the tree is rebuilt per test case.
    void build(const vector<long long>& a) {
        for (int i = 1; i <= n; ++i) {
            bit[i] += a[i - 1];
            int parent = i + (i & -i);
            if (parent <= n) bit[parent] += bit[i];
        }
    }
};

// ---------------------------------------------------------------------------
// 2. INDEX BY VALUE, NOT BY POSITION — compress, then count.
//
//    The move that makes a Fenwick more than a mutable prefix table: put the
//    VALUES on the axis. Cell v then holds "how many of the values I have
//    seen so far equal v", and prefix(v - 1) answers "how many are strictly
//    smaller" in O(log n).
//
//    Values reach 10^9, so the axis has to be shrunk first. Sort, unique,
//    erase — and the erase is not optional, since unique only moves the
//    survivors to the front and leaves the tail as it was.
//
//    Rank is 1-based on purpose: rank 0 would hang the add loop.
// ---------------------------------------------------------------------------
vector<int> compress(const vector<long long>& a) {
    vector<long long> values = a;
    sort(values.begin(), values.end());
    values.erase(unique(values.begin(), values.end()), values.end());

    vector<int> rank(a.size());
    for (size_t i = 0; i < a.size(); ++i) {
        // +1 because a Fenwick is 1-indexed and index 0 is a trap, not a slot.
        rank[i] = (int)(lower_bound(values.begin(), values.end(), a[i]) - values.begin()) + 1;
    }
    return rank;
}

// ---------------------------------------------------------------------------
// 3. THE CLASSIC INSTANCE — counting inversions.
//
//    An inversion is a pair i < j with a[i] > a[j]. Sweeping from the RIGHT
//    and asking "how many values already inserted are strictly smaller than
//    this one" counts, for each element, exactly the inversions it heads —
//    and every inversion is headed by exactly one element, so the totals add
//    with no double counting.
//
//    On [5, 1, 4, 2, 8] the inversions are (5,1) (5,4) (5,2) (4,2): four.
//    The sweep produces 0, 0, 1, 0, 3.
//
//    prefix(rank - 1) counts STRICTLY smaller. prefix(rank) would include the
//    equal values, which is a different question and a different answer the
//    moment the input has duplicates.
//
//    The count itself reaches n(n-1)/2, which at n = 2*10^5 is about
//    2*10^10 — long long, and int is a wrong answer on the largest test only.
// ---------------------------------------------------------------------------
long long count_inversions(const vector<long long>& a) {
    if (a.size() < 2) return 0;
    vector<int> rank = compress(a);
    int distinct = *max_element(rank.begin(), rank.end());
    Fenwick tree(distinct);
    long long inversions = 0;
    // >>> HOLE id=count-smaller prompt=Sweep the ranks from the right, adding to `inversions` the number of already-seen values strictly smaller than the current one, then record the current one
    for (int i = (int)rank.size() - 1; i >= 0; --i) {
        inversions += tree.prefix(rank[i] - 1);   // strictly smaller, hence -1
        tree.add(rank[i], 1);
    }
    // <<< HOLE
    return inversions;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n q                              size of the array and number of commands
//   n values                         the array
//   q commands, each either
//       1 i v      add v at position i (1-indexed)
//       2 l r      print the total of positions l..r
//   m         then m values          -> the number of inversions
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n = 0, q = 0;
    if (!(cin >> n >> q)) return 0;
    vector<long long> a(max(n, 0));
    for (long long& x : a) cin >> x;

    Fenwick tree(max(n, 0));
    tree.build(a);

    for (int i = 0; i < q; ++i) {
        int kind = 0;
        if (!(cin >> kind)) return 0;
        if (kind == 1) {
            int pos = 0;
            long long delta = 0;
            cin >> pos >> delta;
            tree.add(pos, delta);
        } else {
            int l = 0, r = 0;
            cin >> l >> r;
            cout << tree.range(l, r) << "\n";
        }
    }

    int m = 0;
    if (!(cin >> m)) return 0;
    vector<long long> b(max(m, 0));
    for (long long& x : b) cin >> x;
    cout << count_inversions(b) << "\n";

    return 0;
}
