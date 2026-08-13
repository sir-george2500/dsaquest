// ===========================================================================
// BINARY SEARCH ON SORTED DATA
//
// Everything below uses the HALF-OPEN convention. The invariant is:
//
//     the answer always lies in [lo, hi)   -- lo inclusive, hi exclusive
//     everything left of lo  is < x        (already rejected)
//     everything at/right of hi is >= x    (already accepted)
//
// hi starts at n, NOT n-1, because "not found" must be representable: the
// answer index n means "past the last element". The loop is `while (lo < hi)`
// and it exits with lo == hi, which is the single answer index. There is no
// separate found/not-found branch and no `hi - 1` anywhere, which is why this
// convention eats most off-by-one bugs before they happen.
//
// Two rules keep it terminating:
//   * mid = lo + (hi - lo) / 2   -- lo + hi can overflow int; this cannot,
//                                   and it floors toward lo so mid < hi always.
//   * when mid is REJECTED you must write lo = mid + 1, never lo = mid.
//     With lo = mid, a two-element range where mid == lo never shrinks and
//     the loop spins forever. Rejecting mid means excluding it.
//
// You will mostly call std::lower_bound. Learn the hand-written loop anyway:
// it is the one that generalises to predicates the STL has no name for.
// ===========================================================================

#include <bits/stdc++.h>
#include <cassert>
using namespace std;

// ---------------------------------------------------------------------------
// 1. THE HAND-WRITTEN LOOP — this is the form to internalise.
//
//    lb: first index i with a[i] >= x   (== n if every element is < x)
//    ub: first index i with a[i] >  x
//    Both return an INDEX in [0, n]. Neither can fail.
// ---------------------------------------------------------------------------
int lb_hand(const vector<int>& a, int x) {
    // >>> HOLE id=lb-loop prompt=Set up a half-open range that can also express "past the last element", then shrink it until only the first index whose value is not below x remains
    int lo = 0, hi = (int)a.size();          // answer in [lo, hi]
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (a[mid] < x) lo = mid + 1;        // mid rejected -> exclude it
        else            hi = mid;            // mid still a candidate -> keep it
    }
    // <<< HOLE
    return lo;
}

int ub_hand(const vector<int>& a, int x) {
    int lo = 0, hi = (int)a.size();
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        // >>> HOLE id=ub-branch prompt=Same loop as lb_hand, but it must land on the first index STRICTLY greater than x; change as little as possible
        if (a[mid] <= x) lo = mid + 1;       // only `<` becomes `<=`
        else             hi = mid;
        // <<< HOLE
    }
    return lo;
}

// Presence test, built from lb. Note the order of the guards: bounds check
// FIRST, then dereference. lb can legally return n.
bool contains_hand(const vector<int>& a, int x) {
    int i = lb_hand(a, x);
    return i < (int)a.size() && a[i] == x;
}

// ---------------------------------------------------------------------------
// 2. THE STL WAY — same three answers, as iterators.
//
//    lower_bound -> first element >= x. If x is ABSENT this is the insertion
//                   point, i.e. the first element GREATER than x -- it does not
//                   return end() to signal "missing". Check *it == x yourself.
//    upper_bound -> first element >  x.
//    equal_range -> {lower_bound, upper_bound} in one call, one traversal.
//    binary_search -> bool only, throws the position away. Rarely what you want.
//
//    Count of occurrences = upper_bound - lower_bound. Because the range is
//    half-open, that subtraction is the count with no +1 and no -1.
// ---------------------------------------------------------------------------
struct Query {
    int lo_idx, hi_idx;      // indices, not iterators, so they print
    int count;
    bool present;
};

Query probe_stl(const vector<int>& a, int x) {
    // >>> HOLE id=equal-range prompt=Obtain both boundary positions of x in one traversal, convert them to indices, and read the number of occurrences straight off them
    auto [first, last] = equal_range(a.begin(), a.end(), x);
    Query q;
    q.lo_idx  = (int)(first - a.begin());
    q.hi_idx  = (int)(last  - a.begin());
    q.count   = (int)(last - first);         // == 0 exactly when x is absent
    q.present = q.count > 0;
    // <<< HOLE
    return q;
}

// ---------------------------------------------------------------------------
// 3. FIRST ELEMENT SATISFYING A PREDICATE — the general form.
//
//    std::partition_point wants a range partitioned as
//        true true true false false false
//    and returns the first `false`. So phrase the predicate as "still too
//    small". This is how you search a vector<pair<K,V>> sorted by key, or any
//    struct, without writing a comparator.
//
//    Bonus idiom for pairs: lower_bound on {x, INT_MIN} finds the first entry
//    with key >= x, because pair compares lexicographically and INT_MIN loses
//    every second-element tie.
// ---------------------------------------------------------------------------
int first_with_key_at_least(const vector<pair<int, int>>& v, int key) {
    auto it = partition_point(v.begin(), v.end(),
                              [key](const pair<int, int>& e) { return e.first < key; });
    return (int)(it - v.begin());
}

int first_with_key_at_least_pairtrick(const vector<pair<int, int>>& v, int key) {
    auto it = lower_bound(v.begin(), v.end(),
                          pair<int, int>{key, numeric_limits<int>::min()});
    return (int)(it - v.begin());
}

// ---------------------------------------------------------------------------
// 4. NODE-BASED CONTAINERS — use the MEMBER function.
//
//    std::set / std::map iterators are bidirectional, not random access, so
//    std::lower_bound(s.begin(), s.end(), x) still "works" but advances one
//    node at a time: O(n) comparisons-worth of pointer chasing. On n = 2e5
//    inside a loop that is a TLE that looks like an algorithmic mistake.
//
//        auto it = lower_bound(s.begin(), s.end(), x);   // <-- NOT THIS: O(n)
//        auto it = s.lower_bound(x);                     // <-- THIS: O(log n)
//
//    Same for map::lower_bound (searches by key) and multiset::equal_range.
// ---------------------------------------------------------------------------
string set_lower_bound_str(const set<int>& s, int x) {
    auto it = s.lower_bound(x);              // member: walks the tree, O(log n)
    if (it == s.end()) return "end";
    return to_string(*it);
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n, then n values in NON-DECREASING order, then q, then q query values.
// For each query prints: lower_bound idx, upper_bound idx, occurrences,
// present?, the same lower_bound index found on a sorted-by-key pair vector
// (two ways), and set::lower_bound.
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    if (!(cin >> n)) return 0;
    vector<int> a(n);
    for (int& v : a) cin >> v;

    // Sorted by key for free: a is sorted, so (a[i], i) is sorted too.
    vector<pair<int, int>> kv(n);
    for (int i = 0; i < n; ++i) kv[i] = {a[i], i};

    set<int> s(a.begin(), a.end());

    int q;
    if (!(cin >> q)) return 0;
    while (q--) {
        int x;
        cin >> x;

        Query st = probe_stl(a, x);
        // The hand-written loop must agree with the STL, always.
        assert(lb_hand(a, x) == st.lo_idx);
        assert(ub_hand(a, x) == st.hi_idx);
        assert(contains_hand(a, x) == st.present);

        cout << x
             << " lb=" << st.lo_idx
             << " ub=" << st.hi_idx
             << " cnt=" << st.count
             << " found=" << (st.present ? 1 : 0)
             << " pair_pp=" << first_with_key_at_least(kv, x)
             << " pair_lb=" << first_with_key_at_least_pairtrick(kv, x)
             << " set_lb=" << set_lower_bound_str(s, x)
             << "\n";
    }
    return 0;
}
