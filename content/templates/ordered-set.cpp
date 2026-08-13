// ===========================================================================
// THE ROW THAT KEEPS MOVING
//
// A sorted vector answers "what is nearest to x" in O(log n) and answers
// "insert y" in O(n), because everything after y has to shuffle along. An
// ordered set answers both in O(log n), and that is the entire reason it
// exists: the row is queried and edited in the same loop.
//
// `std::set` and `std::multiset` are balanced binary search trees. What they
// give you, and nothing else does at this price:
//
//     insert / erase          O(log n), and no other iterator is invalidated
//     lower_bound(x)          the first element >= x
//     upper_bound(x)          the first element  > x
//     *begin() / *rbegin()    the smallest / the largest
//
// What they do NOT give you, however much you want it:
//
//     "how many elements are below x"     — no rank. That is a Fenwick tree.
//     s.begin() + k                       — no random access. distance() is O(n).
//     duplicates, in a plain `set`        — insert of a value already present
//                                           does nothing at all, silently.
//
// Two rules that outlive every problem:
//   * on a multiset, erase(value) removes EVERY copy and erase(iterator)
//     removes exactly one — and the one you almost always want is the second;
//   * lower_bound has two failure edges, end() and begin(), and dereferencing
//     either is undefined behaviour rather than an error you will notice.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. ERASE ONE OCCURRENCE, NOT ALL OF THEM.
//
//    On the multiset {2, 5, 5, 5, 9}:
//        ms.erase(5)            leaves {2, 9}         and returns 3
//        ms.erase(ms.find(5))   leaves {2, 5, 5, 9}   and returns an iterator
//
//    Every sliding structure over a multiset removes one arrival at a time,
//    so the first form is a silent, catastrophic wrong answer the moment the
//    data contains a duplicate — and the samples usually do not.
//
//    find() returning end() must be checked. erase(end()) is undefined
//    behaviour, not a no-op.
// ---------------------------------------------------------------------------
bool remove_one(multiset<long long>& ms, long long value) {
    // >>> HOLE id=erase-one prompt=Remove exactly one copy of `value` if the multiset holds one, leaving any other copies alone, and report whether something was removed
    auto found = ms.find(value);
    if (found == ms.end()) return false;
    ms.erase(found);                 // the ITERATOR — erase(value) would take all of them
    return true;
    // <<< HOLE
}

// ---------------------------------------------------------------------------
// 2. BRACKET THE QUERY — lower_bound, and the element before it.
//
//    lower_bound(x) is the first element >= x. The nearest element to x is
//    therefore one of exactly two candidates: that one, and the one before
//    it. Both guards are mandatory and neither is optional politeness:
//
//        it == s.end()     nothing in the set is >= x
//        it == s.begin()   nothing in the set is <  x
//
//    On {2, 7, 7, 13, 20} with x = 8: lower_bound gives 13 and the previous
//    element is 7. |8 - 7| = 1 beats |13 - 8| = 5, so the answer is 7 — and
//    a solution that only looked forward would have said 13.
//
//    For "the largest element <= x" the idiom is upper_bound and step back,
//    NOT lower_bound and step back: on {2, 7, 13} with x = 7, upper_bound
//    gives 13 and stepping back gives 7 (correct); lower_bound gives 7 and
//    stepping back gives 2 (wrong, and only wrong on an exact match).
//
//    Use the MEMBER lower_bound. std::lower_bound over set iterators still
//    compiles, but a set's iterators are not random access, so the algorithm
//    degrades to a linear walk — O(n) per query, and only slow, never wrong,
//    which is the hardest kind of bug to find.
// ---------------------------------------------------------------------------
struct Bracket {
    bool has_below = false;      // the largest element <= x
    bool has_above = false;      // the smallest element >= x
    long long below = 0;
    long long above = 0;
};

Bracket bracket(const multiset<long long>& ms, long long x) {
    Bracket out;
    // >>> HOLE id=bracket prompt=Fill `out` with the smallest element that is at least x and the largest that is at most x, taking care that either side may not exist
    auto it = ms.lower_bound(x);
    if (it != ms.end()) {
        out.has_above = true;
        out.above = *it;
    }
    auto back = ms.upper_bound(x);          // upper, so an exact match counts as below
    if (back != ms.begin()) {
        --back;
        out.has_below = true;
        out.below = *back;
    }
    // <<< HOLE
    return out;
}

// ---------------------------------------------------------------------------
// 3. A WINDOW THAT CAN BE EDITED FROM BOTH ENDS.
//
//    A monotonic deque gives the maximum of a fixed window in O(1) amortised
//    and is the right tool when the window only ever slides forward. The
//    multiset is what you reach for when the window is edited arbitrarily —
//    values removed out of order, or the window's own width changing — and it
//    costs a log factor for that freedom.
//
//    On 1 3 -1 -3 5 3 6 7 with a width of 3 the maxima are 3 3 5 5 6 7.
//
//    *ms.rbegin() is the largest. s.end() is not an element at all, and
//    dereferencing begin() or rbegin() on an empty container is undefined.
// ---------------------------------------------------------------------------
vector<long long> window_maxima(const vector<long long>& a, int width) {
    vector<long long> out;
    if (width <= 0 || (int)a.size() < width) return out;
    multiset<long long> live;
    // >>> HOLE id=slide prompt=Slide a window of `width` across `a`, appending each window's largest value to `out`, keeping `live` holding exactly the values inside the current window
    for (int r = 0; r < (int)a.size(); ++r) {
        live.insert(a[r]);
        if ((int)live.size() > width) remove_one(live, a[r - width]);
        if ((int)live.size() == width) out.push_back(*live.rbegin());
    }
    // <<< HOLE
    return out;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n            then n values        -> inserted into a multiset
//   q            then q probes x      -> "below above", or "-" where none exists
//   d            then d values        -> one copy of each erased; final size
//   p w          then p values        -> the maximum of every window of width w
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n = 0;
    if (!(cin >> n)) return 0;
    multiset<long long> ms;
    for (int i = 0; i < n; ++i) {
        long long x = 0;
        cin >> x;
        ms.insert(x);
    }

    int q = 0;
    if (!(cin >> q)) return 0;
    for (int i = 0; i < q; ++i) {
        long long x = 0;
        cin >> x;
        Bracket found = bracket(ms, x);
        if (found.has_below) cout << found.below; else cout << '-';
        cout << ' ';
        if (found.has_above) cout << found.above; else cout << '-';
        cout << "\n";
    }

    int d = 0;
    if (!(cin >> d)) return 0;
    int removed = 0;
    for (int i = 0; i < d; ++i) {
        long long x = 0;
        cin >> x;
        removed += remove_one(ms, x) ? 1 : 0;
    }
    cout << removed << ' ' << ms.size() << "\n";

    int p = 0, width = 0;
    if (!(cin >> p >> width)) return 0;
    vector<long long> a(max(p, 0));
    for (long long& x : a) cin >> x;
    vector<long long> maxima = window_maxima(a, width);
    for (size_t i = 0; i < maxima.size(); ++i) {
        cout << maxima[i] << (i + 1 == maxima.size() ? '\n' : ' ');
    }
    if (maxima.empty()) cout << "\n";

    return 0;
}
