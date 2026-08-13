// ===========================================================================
// SORT BY THE RIGHT KEY
//
// Every greedy algorithm in this region has the same two lines of shape:
//
//     sort(items by SOME key);
//     for (item : items) if (it still fits) take it;
//
// The sweep is never the difficulty. The key is. Choose it wrongly and the
// code is still short, still fast, still readable, and still wrong — which is
// why "it worked on the sample" is more dangerous here than anywhere else.
//
// A key is only correct once you can state the exchange argument for it:
//
//     take some optimal answer, force my first choice into it, and show the
//     result is still legal and no worse.
//
// Three objectives below, three different keys, and one of them (0/1 knapsack,
// mentioned in form 3) has NO safe key at all. Learn which is which.
//
// Two rules that outlive every problem:
//   * a comparator must be a STRICT weak ordering — `<`, never `<=`;
//   * never divide to compare a ratio. Cross multiply.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. THE COUNT OBJECTIVE — cheapest first.
//
//    "How MANY can I afford?" is the case where the local choice is provably
//    safe. Proof: suppose some optimal selection of k items omits the cheapest
//    item c. Remove any one of its members and put c in. The total did not
//    rise (c is the cheapest), so the selection is still affordable, and it
//    still has k items. So an optimal answer containing c exists — always.
//
//    Note what this proof does NOT say: nothing about maximising VALUE. Swap
//    "how many" for "how much" and the argument collapses (see form 3).
// ---------------------------------------------------------------------------
int max_items_within_budget(vector<long long> cost, long long budget) {
    int taken = 0;
    // >>> HOLE id=cheapest-first prompt=Fit as many items as the budget allows, in the order that makes each choice provably safe, counting into `taken` and spending from `budget`
    sort(cost.begin(), cost.end());
    for (long long c : cost) {
        if (c > budget) break;              // nothing later is cheaper: stop
        budget -= c;
        ++taken;
    }
    // <<< HOLE
    return taken;
}

// ---------------------------------------------------------------------------
// 2. THE CANONICAL COIN SYSTEM — largest first.
//
//    Largest-first is optimal for systems like {1, 2, 5, 10, 20, 50, 100} and
//    is NOT optimal in general: on {1, 3, 4} with amount 6 it answers 4+1+1 = 3
//    coins where 3+3 = 2 is optimal. The statement licenses the greedy by
//    naming the system; it is never licensed by the shape of the question.
//
//    Returns -1 when the amount cannot be paid at all, which is why the loop
//    below must not silently spin.
// ---------------------------------------------------------------------------
long long min_notes(vector<long long> denom, long long amount) {
    sort(denom.begin(), denom.end());       // ascending, so the largest is last
    long long used = 0;
    // >>> HOLE id=largest-first prompt=Walk the denominations from the largest downwards, paying as much of `amount` as each one can and adding the notes spent to `used`
    for (int i = (int)denom.size() - 1; i >= 0; --i) {
        used += amount / denom[i];          // take as many as fit, all at once
        amount %= denom[i];
    }
    // <<< HOLE
    return amount == 0 ? used : -1;
}

// ---------------------------------------------------------------------------
// 3. THE RATIO KEY — value per unit, and only because items are DIVISIBLE.
//
//    Fractional knapsack: sort by value/weight and fill. The exchange argument
//    works because any unit of a lower ratio can be swapped for a unit of a
//    higher one, and units are what divisibility gives you.
//
//    Delete the word "divisible" and this is 0/1 knapsack, where the same code
//    is WRONG: capacity 50 with items (v=60,w=10), (v=100,w=20), (v=120,w=30)
//    gives 60 + 100 = 160 by ratio, while 100 + 120 = 220 is optimal. There is
//    no key that fixes it. That problem is dynamic programming.
//
//    The comparison is cross multiplied: a.value/a.weight > b.value/b.weight
//    becomes a.value*b.weight > b.value*a.weight. No division, no double, no
//    two items that "tie" because 7/2 and 10/3 both truncate to 3.
// ---------------------------------------------------------------------------
struct Item {
    long long value;
    long long weight;                       // strictly positive
};

long double best_divisible_value(vector<Item> items, long long capacity) {
    // >>> HOLE id=ratio-key prompt=Put the items in the order that lets the fill loop below stop the moment the capacity runs out, using no division anywhere
    sort(items.begin(), items.end(), [](const Item& a, const Item& b) {
        return a.value * b.weight > b.value * a.weight;   // ratio, cross multiplied
    });
    // <<< HOLE
    long double total = 0;
    for (const Item& item : items) {
        if (capacity <= 0) break;
        long long take = min(capacity, item.weight);
        total += (long double)item.value * (long double)take / (long double)item.weight;
        capacity -= take;
    }
    return total;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n B          then n costs        -> how many fit inside B
//   m A          then m denominations-> fewest notes making A, or -1
//   k C          then k pairs value weight -> best divisible value inside C
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    long long budget;
    if (!(cin >> n >> budget)) return 0;

    vector<long long> cost(n);
    for (long long& c : cost) cin >> c;
    cout << max_items_within_budget(cost, budget) << "\n";

    int m;
    long long amount;
    cin >> m >> amount;
    vector<long long> denom(m);
    for (long long& d : denom) cin >> d;
    cout << min_notes(denom, amount) << "\n";

    int k;
    long long capacity;
    cin >> k >> capacity;
    vector<Item> items(k);
    for (Item& item : items) cin >> item.value >> item.weight;
    cout << fixed << setprecision(6) << (double)best_divisible_value(items, capacity) << "\n";

    return 0;
}
