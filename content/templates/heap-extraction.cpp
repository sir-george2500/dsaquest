// ===========================================================================
// TAKE THE EXTREME, THEN LET IT CHANGE
//
// A heap is a sorted row you are not allowed to look at. One element is
// visible — the top — and every insertion keeps that one element correct in
// O(log n) instead of re-sorting in O(n log n).
//
// That single restriction is also the licence. Sorting answers "what is the
// order of these items", and it answers it ONCE, for a collection that never
// moves again. A heap answers "what is the extreme of the collection as it is
// RIGHT NOW", for a collection you are adding to and taking from as you go.
//
// The three forms below are the three shapes that question comes in:
//
//   1. bounded    keep only the k best, throw the rest away as they arrive
//   2. feeding    consume two, produce one, and the product goes back in
//   3. split      two heaps facing each other, so the middle is also visible
//
// One rule that outlives every problem: `priority_queue` puts on top the
// element that no other element beats under its comparator. The default
// comparator is `less`, so the default heap is a MAX-heap. To get a min-heap
// you pass `greater`, and you must write the container type in between:
//
//     priority_queue<long long, vector<long long>, greater<long long>> pq;
//
// And one thing a heap CANNOT do: erase an element that is not the top, or
// change an element's key. If a problem needs that, it is an ordered set —
// or a heap plus lazy deletion, which is form 3's cousin.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

using MinHeap = priority_queue<long long, vector<long long>, greater<long long>>;

// ---------------------------------------------------------------------------
// 1. THE BOUNDED HEAP — keep k, discard the rest.
//
//    To know the k LARGEST you hold a MIN-heap of size k. The inversion is
//    the whole trick, and it is where everyone goes wrong: the top of that
//    heap is the WEAKEST of the k you are keeping, which is exactly the one
//    to throw away when a better candidate arrives. It is also, at every
//    moment, the k-th largest value seen so far.
//
//    Use a MAX-heap here and you evict the best each time, so you finish
//    holding the k smallest. On the stream 5 1 9 3 7 2 with k = 3 a min-heap
//    ends holding {5, 7, 9} and a max-heap ends holding {1, 2, 3}.
//
//    Cost: O(n log k) time and O(k) memory, against O(n log n) and O(n) for
//    sorting. At n = 2*10^5 and k = 10 that is about 660 thousand comparisons
//    instead of 3.5 million, and ten longs of memory instead of two hundred
//    thousand.
// ---------------------------------------------------------------------------
long long sum_of_k_largest(const vector<long long>& a, int k) {
    if (k <= 0) return 0;
    MinHeap keep;
    // >>> HOLE id=bounded-heap prompt=Walk the values and leave `keep` holding exactly the k largest of them, evicting the weakest survivor whenever the heap grows past k
    for (long long x : a) {
        keep.push(x);
        if ((int)keep.size() > k) keep.pop();   // the top is the weakest kept
    }
    // <<< HOLE
    long long total = 0;
    while (!keep.empty()) {
        total += keep.top();
        keep.pop();
    }
    return total;
}

// ---------------------------------------------------------------------------
// 2. THE QUEUE THAT FEEDS ITSELF — pop two, push one.
//
//    Joining two ropes costs their combined length, and the joined rope is
//    still on the floor waiting to be joined again. A sort cannot express
//    this: the new item did not exist when you sorted, and its rank is not
//    known until it is created. The heap re-ranks it for free.
//
//    On weights 10 1 2 5, joining in the order given costs
//    11 + 13 + 18 = 42; always joining the two smallest costs
//    3 + 8 + 18 = 29, and 29 is provably the optimum.
//
//    The total is a sum of sums. With 2*10^5 weights of 10^9 it reaches
//    roughly 3*10^15 — long long, never int.
// ---------------------------------------------------------------------------
long long merge_cost(const vector<long long>& weights) {
    if (weights.size() < 2) return 0;
    MinHeap pq(weights.begin(), weights.end());   // O(n) make_heap, not n pushes
    long long total = 0;
    // >>> HOLE id=feed-back prompt=Join the collection down to a single piece, charging each join the combined weight into `total` and returning the joined piece to `pq`
    while (pq.size() > 1) {
        long long first = pq.top();
        pq.pop();                                 // `first` is a copy on purpose
        long long second = pq.top();
        pq.pop();
        total += first + second;
        pq.push(first + second);
    }
    // <<< HOLE
    return total;
}

// ---------------------------------------------------------------------------
// 3. TWO HEAPS FACING EACH OTHER — the middle becomes visible.
//
//    One heap can show you an end. Two heaps back to back show you the
//    middle: `low` is a max-heap holding the smaller half, `high` is a
//    min-heap holding the larger half, and the median sits at low.top().
//
//    The invariant is the whole structure, and both halves of it matter:
//
//        low.top() <= high.top()                  the halves do not interleave
//        low.size() == high.size()  or  high.size() + 1
//
//    Feed 5, 15, 1, 3 and the lower median after each arrival is 5, 5, 5, 3.
// ---------------------------------------------------------------------------
struct RunningMedian {
    priority_queue<long long> low;   // max-heap: the smaller half
    MinHeap high;                    // min-heap: the larger half

    void insert(long long x) {
        if (low.empty() || x <= low.top()) {
            low.push(x);
        } else {
            high.push(x);
        }
        // >>> HOLE id=rebalance prompt=Restore the size invariant so that `low` holds either as many elements as `high` or exactly one more, moving a single element across
        if (low.size() > high.size() + 1) {
            high.push(low.top());
            low.pop();
        } else if (high.size() > low.size()) {
            low.push(high.top());
            high.pop();
        }
        // <<< HOLE
    }

    // The lower median: for an even count, the smaller of the two middles.
    long long median() const { return low.top(); }
    bool empty() const { return low.empty(); }
};

// ---------------------------------------------------------------------------
// Demo harness.
//   n k        then n values          -> sum of the k largest
//   m          then m weights         -> cost of joining them all
//   p          then p values          -> the running lower median after each
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n = 0, k = 0;
    if (!(cin >> n >> k)) return 0;
    vector<long long> a(max(n, 0));
    for (long long& x : a) cin >> x;
    cout << sum_of_k_largest(a, k) << "\n";

    int m = 0;
    if (!(cin >> m)) return 0;
    vector<long long> weights(max(m, 0));
    for (long long& w : weights) cin >> w;
    cout << merge_cost(weights) << "\n";

    int p = 0;
    if (!(cin >> p)) return 0;
    RunningMedian medians;
    for (int i = 0; i < p; ++i) {
        long long x = 0;
        cin >> x;
        medians.insert(x);
        cout << medians.median() << (i + 1 == p ? '\n' : ' ');
    }
    if (medians.empty()) cout << "\n";

    return 0;
}
