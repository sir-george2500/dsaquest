// ===========================================================================
// THE TYPE IS PART OF THE ALGORITHM
//
// A 32-bit int holds -2147483648 .. 2147483647, which is about +-2 * 10^9.
// A 64-bit long long holds about +-9.2 * 10^18. Contest inputs are chosen to
// sit just inside one of those, and the setter chooses which.
//
// The habit that removes this entire class of wrong answers is one question,
// asked of every line that adds or multiplies:
//
//     how large can this get on the LARGEST input the constraints allow?
//
// 10^5 values of 10^9 sum to 10^14. The number of pairs among 2 * 10^5 items
// is 19999900000. Two coordinates of 10^9 multiply to 10^18. Only the first
// two of those are surprising, and all three are past int.
//
// A note on this file: real signed overflow is undefined behaviour, so it is
// not something a program can portably demonstrate — with -O2 the compiler is
// entitled to assume it never happens. Every "what int would have done" figure
// below is therefore computed through UNSIGNED arithmetic, which wraps by
// definition, and converted back. The numbers are exactly the ones a wrapping
// machine produces; the demonstration is simply honest about how it got them.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

//: What a 32-bit two's-complement accumulator would hold. Well defined:
//: unsigned arithmetic wraps by the standard, and in C++20 the conversion
//: back to a signed type is modular rather than implementation defined.
static int32_t as_int32(int64_t value) {
    return static_cast<int32_t>(static_cast<uint32_t>(value));
}

// ---------------------------------------------------------------------------
// 1. THE ACCUMULATOR.
//
//    The loop is right, the algorithm is right, and the declaration decides
//    the answer. Summing values of 10^9 in an int is wrong after the third
//    element; the failure is invisible on every small test, and on the large
//    one it usually arrives as a negative number.
// ---------------------------------------------------------------------------
struct Totals {
    int32_t narrow;                             // what an int accumulator gives
    long long wide;                             // what the answer actually is
};

Totals accumulate(const vector<long long>& a) {
    Totals t{0, 0};
    // >>> HOLE id=accumulator prompt=Sum the values twice: into t.wide as a long long, and into t.narrow as the 32-bit accumulator a careless declaration would have produced (add each value with as_int32(t.narrow + value))
    for (long long x : a) {
        t.wide += x;
        t.narrow = as_int32(static_cast<int64_t>(t.narrow) + x);
    }
    // <<< HOLE
    return t;
}

// ---------------------------------------------------------------------------
// 2. THE PROMOTION TRAP.
//
//        int a = 123456789;
//        long long b = a * a;      // b is -1757895751, not 15241578750190521
//
//    Both operands are int, so the multiplication happens in int and the
//    widening comes afterwards — too late. The declaration on the left looks
//    correct, which is why this survives being read back.
//
//    The fix is to make one operand wide BEFORE the multiply: 1LL * a * b, or
//    (long long)a * b. Both cost nothing.
// ---------------------------------------------------------------------------
struct Product {
    int32_t narrow;
    long long wide;
};

Product multiply(int a, int b) {
    Product p{0, 0};
    // >>> HOLE id=promotion prompt=Produce both products: p.wide with one operand widened first so the multiplication happens in 64 bits, and p.narrow as the 32-bit result the unwidened expression would have given
    p.wide = 1LL * a * b;
    p.narrow = as_int32(p.wide);
    // <<< HOLE
    return p;
}

// ---------------------------------------------------------------------------
// 3. THE GUARD THAT MUST NOT OVERFLOW WHILE GUARDING.
//
//        if (a * b > limit) ...    // the product already wrapped; the guard
//                                  // passes exactly when it should have fired
//
//    Rearrange it into a division, which cannot overflow:
//
//        if (a != 0 && b > limit / a) ...
//
//    Non-negative operands only — with a negative operand the inequality flips
//    and the truncation direction changes, which is a second bug wearing the
//    first one's clothes.
// ---------------------------------------------------------------------------
bool product_exceeds(long long a, long long b, long long limit) {
    bool exceeds = false;
    // >>> HOLE id=safe-guard prompt=Decide whether a * b would exceed limit for non-negative a and b, without ever forming the product — divide instead
    if (a != 0 && b > limit / a) exceeds = true;
    // <<< HOLE
    return exceeds;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n         then n values     -> int total, true total, and which is right
//   a b                         -> int product, true product
//   x y limit                   -> the honest verdict, and what the naive
//                                  overflowing check would have claimed
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    if (!(cin >> n)) return 0;
    vector<long long> a(n);
    for (long long& x : a) cin >> x;

    Totals t = accumulate(a);
    cout << t.narrow << ' ' << t.wide << ' '
         << (static_cast<long long>(t.narrow) == t.wide ? "AGREE" : "INT LOST IT") << "\n";

    int p, q;
    cin >> p >> q;
    Product prod = multiply(p, q);
    cout << prod.narrow << ' ' << prod.wide << "\n";

    long long x, y, limit;
    cin >> x >> y >> limit;
    bool honest = product_exceeds(x, y, limit);
    bool naive = as_int32(x * y) > limit;       // the wrapped 32-bit check
    cout << (honest ? "EXCEEDS" : "SAFE") << ' '
         << (naive ? "EXCEEDS" : "SAFE") << "\n";

    return 0;
}
