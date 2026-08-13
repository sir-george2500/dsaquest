// ===========================================================================
// REDUCE AS YOU GO
//
// The whole of modular arithmetic in one sentence: addition, subtraction and
// multiplication all survive the remainder, so you may take the remainder at
// EVERY step instead of once at the end. Division does not survive, and that
// is a separate weapon (see fast-exponentiation.cpp).
//
//     (a + b) % m == ((a % m) + (b % m)) % m
//     (a - b) % m == ((a % m) - (b % m) + m) % m
//     (a * b) % m == ((a % m) * (b % m)) % m
//     (a / b) % m == NOTHING. There is no such rule.
//
// Two things kill more submissions in this region than every algorithmic
// mistake combined, and neither of them looks like a bug when you read it:
//
//   1. OVERFLOW. `a * b % m` is evaluated as `(a * b) % m`. The product is
//      formed FIRST, at full width, and only then reduced. With a and b below
//      m <= 1e9 the product reaches 1e18: fine in a long long (LLONG_MAX is
//      about 9.2e18), catastrophic in an int (INT_MAX is 2147483647). Signed
//      overflow is undefined behaviour, so the failure is not even a reliable
//      wrong answer. And if m itself can reach 1e18, a long long is no longer
//      enough either — see mulmod below.
//
//   2. THE SIGN. C++ integer division truncates towards zero, so the remainder
//      carries the sign of the DIVIDEND: -3 % 7 is -3, not 4. Any subtraction
//      can produce a negative residue, and a negative residue used as an array
//      index reads memory that is not yours.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. A PRODUCT OVER A ROW — reduced at every step.
//
//    The unreduced product of 200000 values near 1e9 has roughly 1.8 million
//    decimal digits. No integer type in the language holds it, so "compute it,
//    then take the remainder" is not slow, it is impossible. Reducing at each
//    step keeps the accumulator below m for ever, and the only value that ever
//    exceeds m is the single product `acc * x`, which is why acc and x must
//    both already be below m before they meet.
//
//    `1 % m` rather than `1`: when m is 1 every residue is 0, including the
//    empty product, and a bare 1 is the one wrong answer that case admits.
// ---------------------------------------------------------------------------
long long product_mod(const vector<long long>& a, long long m) {
    long long acc = 1 % m;
    // >>> HOLE id=reduce-product prompt=Multiply every element of `a` into `acc` so that no intermediate value ever exceeds m*m, leaving the product modulo m in `acc`
    for (long long x : a) {
        acc = acc * (x % m) % m;        // both factors < m, so the product < m*m
    }
    // <<< HOLE
    return acc;
}

// ---------------------------------------------------------------------------
// 2. THE SIGN OF THE REMAINDER.
//
//    -3 % 7 is -3. Add m and it becomes 4; take the remainder again and a
//    value that was ALREADY in range stays in range. Both steps are needed:
//
//        x = -7, m = 7   ->  x % m = 0,  + m = 7,  % m = 0     correct
//        without the second %, the answer would be 7, which is not a residue.
//
//    This is the only place a residue is allowed to be built from a subtraction
//    without a comment above it, and it is three characters longer than the
//    version that is wrong.
// ---------------------------------------------------------------------------
long long positive_mod(long long x, long long m) {
    long long r = 0;
    // >>> HOLE id=positive-residue prompt=Put into `r` the unique value in [0, m) congruent to x, given that x may be negative and that C++ % keeps the sign of the dividend
    r = (x % m + m) % m;
    // <<< HOLE
    return r;
}

// ---------------------------------------------------------------------------
// 3. A NUMBER TOO LONG TO STORE — Horner's rule under the modulus.
//
//    The input is a decimal string of up to a million digits. It has no
//    numeric type at all. But a decimal number is built by the recurrence
//
//        value(d[0..i]) = value(d[0..i-1]) * 10 + d[i]
//
//    and both operations survive the modulus, so the residue can be built one
//    digit at a time and never exceeds 10 * m + 9.
//
//    1234 mod 7, digit by digit:  1, 5, 4, 2 — and 1234 = 176 * 7 + 2.
// ---------------------------------------------------------------------------
long long decimal_mod(const string& digits, long long m) {
    long long r = 0;
    // >>> HOLE id=horner-digits prompt=Fold the decimal digits of the string into `r` one at a time so that `r` is always the residue of the prefix read so far
    for (char c : digits) {
        r = (r * 10 + (c - '0')) % m;
    }
    // <<< HOLE
    return r;
}

// ---------------------------------------------------------------------------
// When the modulus itself is large: a * b overflows a long long the moment
// m passes about 3037000499 (the square root of LLONG_MAX). __int128 is not
// standard C++ but every judge's g++ and clang++ have it, it costs two
// instructions, and it is the difference between a correct answer and
// undefined behaviour. There is no hole here because there is nothing to
// think about: if m can exceed 3e9, you use this.
// ---------------------------------------------------------------------------
long long mulmod(long long a, long long b, long long m) {
    return (long long)((__int128)a * b % m);
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n m           then n values           -> their product modulo m
//   x m2                                  -> the residue of x in [0, m2)
//   digits m3                             -> the decimal string modulo m3
//   a b m4                                -> a * b modulo m4, in 128 bits
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    long long m;
    if (!(cin >> n >> m)) return 0;
    vector<long long> a(n);
    for (long long& x : a) cin >> x;
    cout << product_mod(a, m) << "\n";

    long long x, m2;
    cin >> x >> m2;
    cout << positive_mod(x, m2) << "\n";

    string digits;
    long long m3;
    cin >> digits >> m3;
    cout << decimal_mod(digits, m3) << "\n";

    long long p, q, m4;
    cin >> p >> q >> m4;
    cout << mulmod(p, q, m4) << "\n";

    return 0;
}
