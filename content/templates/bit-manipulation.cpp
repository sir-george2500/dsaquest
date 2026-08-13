// ===========================================================================
// BIT MANIPULATION
//
// One idea, worn four ways:
//
//     an integer IS a set, and the bit at position i answers "is i a member?"
//
// From that everything follows. Union is `|`, intersection is `&`, symmetric
// difference is `^` — and because `^` is its own inverse, anything that occurs
// an even number of times cancels itself out of a running XOR without being
// counted, stored or sorted.
//
// The constraints, not the words, tell you when to reach for this:
//   n <= 20 with "choose any subset"        -> enumerate all 1<<n masks
//   "appears twice except one"              -> XOR the lot, the pairs vanish
//   "O(1) extra memory, values up to 1e9"   -> a tally is forbidden; bits are free
//
// Width discipline is not optional. `1 << k` is an int and an int has 31 usable
// bits: shift `1u` or `1ULL` instead, or the program is undefined rather than
// merely wrong.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. THE LOW-BIT TOOLKIT — parity, membership, and the lowest set bit.
//
//    x & 1         parity. The whole of "is it odd", in one instruction.
//    x >> i & 1    is i a member? Note the parentheses discipline: `&` binds
//                  looser than `==`, so `x & 1 == 0` silently means `x & 0`.
//    x & -x        isolate the lowest set bit (written unsigned below).
//    x & (x - 1)   clear the lowest set bit.
// ---------------------------------------------------------------------------
bool is_odd(long long x) { return (x & 1) != 0; }

bool has_member(unsigned m, int i) {
    if (i < 0 || i >= 32) return false;         // shifting by the width is UB
    return (m >> i & 1u) != 0u;
}

unsigned lowest_set_bit(unsigned x) { return x & (~x + 1u); }   // x & -x, no signed detour

int popcount_kernighan(unsigned x) {
    int bits = 0;
    // >>> HOLE id=clear-lowest-bit prompt=Tally the set bits by repeatedly deleting the lowest surviving one, so the loop turns once per set bit instead of once per bit of width
    while (x != 0u) {
        x &= x - 1u;                            // the lowest set bit, gone
        ++bits;
    }
    // <<< HOLE
    return bits;
}

// ---------------------------------------------------------------------------
// 2. XOR CANCELLATION — a ^ a == 0, so pairs erase themselves.
//
//    XOR is associative and commutative, so the order of the input is
//    irrelevant: every value that appears an even number of times contributes
//    nothing. That is a hash map's job done in one register.
// ---------------------------------------------------------------------------
unsigned xor_all(const vector<unsigned>& a) {
    unsigned acc = 0u;
    for (unsigned v : a) acc ^= v;
    return acc;
}

// Every value appears twice except exactly two of them. The XOR of everything
// is therefore the XOR of the two survivors, which is non-zero — so they must
// disagree somewhere. Split the whole array on any one position where they
// disagree and each half holds one survivor plus pairs.
pair<unsigned, unsigned> two_unpaired(const vector<unsigned>& a) {
    unsigned total = xor_all(a);
    unsigned first = 0u, second = 0u;

    // >>> HOLE id=split-on-a-differing-bit prompt=total is the XOR of the two survivors; pick one position where they must disagree and deal every element into one of two piles by it, so each pile cancels down to a single survivor
    unsigned probe = lowest_set_bit(total);     // they differ here, if anywhere
    for (unsigned v : a) {
        if ((v & probe) != 0u)
            first ^= v;
        else
            second ^= v;
    }
    // <<< HOLE

    if (first > second) swap(first, second);
    return {first, second};
}

// ---------------------------------------------------------------------------
// 3. A MASK IS THE SET — enumerate subsets when the universe is tiny.
//
//    for (unsigned m = 0; m < (1u << n); ++m)      every one of the 2^n subsets
//    for (unsigned s = m; s; s = (s - 1) & m)      every non-empty submask of m
//
//    2^n * n is 20 million at n = 20 and 20 billion at n = 30. A statement that
//    caps n at 20 (sometimes 25) is not being coy; it is handing you the method.
// ---------------------------------------------------------------------------
long long best_sum_over_subsets(const vector<long long>& a, int k) {
    const int n = (int)a.size();
    if (n > 20 || k < 0 || k > n) return -1;    // keep 1u << n defined and the answer real

    long long best = LLONG_MIN;
    // >>> HOLE id=enumerate-subsets prompt=Sweep every subset of the n elements as an integer, add up the members that subset names, and keep the largest total among subsets holding exactly k of them
    for (unsigned m = 0; m < (1u << n); ++m) {
        if (std::popcount(m) != k) continue;    // wrong size, skip it
        long long sum = 0;
        for (int i = 0; i < n; ++i)
            if (m >> i & 1u) sum += a[i];
        best = max(best, sum);
    }
    // <<< HOLE
    return best == LLONG_MIN ? -1 : best;
}

// Submask enumeration, the other half of the idea. Summed over every m, the
// number of non-empty submasks is 3^n - 2^n: each position is out, in the
// submask, or in m only. Cheap sanity check that the `(s - 1) & m` loop is right.
long long count_submasks_everywhere(int n) {
    if (n < 0 || n > 12) return -1;             // 3^n grows faster than you expect
    const unsigned limit = 1u << n;
    long long total = 0;
    for (unsigned m = 0; m != limit; ++m)
        for (unsigned s = m; s != 0u; s = (s - 1u) & m)
            ++total;
    return total;
}

// ---------------------------------------------------------------------------
// 4. SHIFTS, AND WHAT SIGNED TYPES DO TO THEM
//
//    1 << 31    undefined — the literal is an int and the sign bit is not yours
//    1u << 32   undefined — shifting by the full width, whatever the type
//    -8 >> 1    is -4, not -3: an arithmetic shift rounds towards negative
//               infinity, so `>>` is not division once values can be negative
// ---------------------------------------------------------------------------
unsigned long long bit_value(int k) {
    return (k < 0 || k >= 64) ? 0ULL : (1ULL << k);
}

int highest_bit_index(unsigned long long x) {
    return x == 0ULL ? -1 : (int)std::bit_width(x) - 1;
}

long long halve(long long v) { return v >> 1; }     // floor(v / 2), not trunc

// ---------------------------------------------------------------------------
// Demo harness: reads n and k, then n non-negative values.
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n, k;
    if (!(cin >> n >> k) || n < 0) return 0;

    vector<long long> a(n);
    for (long long& x : a) cin >> x;
    const vector<unsigned> u(a.begin(), a.end());

    long long odds = 0, members = 0, set_bits = 0;
    for (unsigned v : u) {
        odds += is_odd((long long)v);
        members += has_member(v, k);
        set_bits += popcount_kernighan(v);
    }
    cout << odds << " " << members << " " << set_bits << "\n";
    cout << (u.empty() ? 0u : lowest_set_bit(u[0])) << "\n";

    const auto [lo, hi] = two_unpaired(u);
    cout << xor_all(u) << " " << lo << " " << hi << "\n";

    cout << best_sum_over_subsets(a, k) << " " << count_submasks_everywhere(n) << "\n";

    cout << bit_value(k) << " " << highest_bit_index(u.empty() ? 0ULL : u[0]) << " "
         << halve(a.empty() ? -7 : -a[0]) << "\n";
    return 0;
}
