// ===========================================================================
// THE REMAINDER IS THE WHOLE METHOD
//
// Every common divisor of a and b also divides a - b, and therefore divides
// a % b. So the SET of common divisors of (a, b) and of (b, a % b) is the same
// set, and the largest member of it is the same number. Replace the pair and
// repeat; the second component strictly shrinks, so it reaches zero, and at
// that moment the first component is the answer.
//
//     gcd(1071, 462):  1071 = 2*462 + 147
//                       462 = 3*147 +  21
//                       147 = 7* 21 +   0   ->  gcd = 21
//
// Three lines of divergence between a and b, and the worst case over all
// inputs below N is a pair of consecutive Fibonacci numbers — gcd(987, 610)
// takes fourteen steps. That is O(log min(a, b)), which is why gcd is treated
// as free everywhere else in competitive programming.
//
// The two derived facts that carry most problems:
//
//   * lcm(a, b) = a / g * b, and the DIVISION MUST COME FIRST. a * b overflows
//     while the true lcm fits: a = 3e9, b = 4e9, g = 1e9 — a*b is 1.2e19, past
//     LLONG_MAX, while the answer is 1.2e10.
//
//   * Extended Euclid returns x and y with a*x + b*y = g. Everything of the
//     form "can I measure exactly t" is decided by t % g == 0, and the modular
//     inverse for a COMPOSITE modulus is x when g == 1.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. THE DESCENT.
//
//    Note gcd(a, 0) = a, which is not a special case to be guarded but the
//    loop's exit condition. It is also the identity that makes "gcd of a whole
//    row" a fold starting from 0: g = gcd(g, x) for every x, starting at 0,
//    ends at the gcd of the row, and needs no first-element special case.
//
//    std::gcd from <numeric> does this and is what you should use in a
//    contest. Write it once by hand so that when a problem needs the sequence
//    of quotients — a continued fraction, a Stern-Brocot walk — you are not
//    meeting the loop for the first time.
// ---------------------------------------------------------------------------
long long gcd_of(long long a, long long b) {
    if (a < 0) a = -a;
    if (b < 0) b = -b;
    // >>> HOLE id=remainder-descent prompt=Reduce the pair (a, b) until b is zero, so that a holds the greatest common divisor when the loop ends
    while (b != 0) {
        long long r = a % b;
        a = b;
        b = r;
    }
    // <<< HOLE
    return a;
}

// ---------------------------------------------------------------------------
// 2. THE LOWEST COMMON MULTIPLE, WITHOUT OVERFLOW.
//
//    a * b = g * lcm, so lcm = a * b / g. Written that way it is wrong on
//    exactly the inputs that make the problem interesting, because the product
//    is formed before the division. g divides a exactly, so a / g is an
//    integer, and reordering costs nothing:
//
//        a = 3000000000, b = 4000000000, g = 1000000000
//        a * b / g  ->  1.2e19 formed first: past LLONG_MAX, undefined
//        a / g * b  ->  3 * 4e9 = 12000000000. Correct, and never near the edge.
//
//    Folding this over a row still overflows if the true lcm does — lcm grows
//    like a product when the values are coprime — so a statement that asks for
//    an lcm over many values is nearly always asking for it modulo something,
//    and then you cannot divide at all and must factorise instead.
// ---------------------------------------------------------------------------
long long lcm_of(long long a, long long b) {
    if (a == 0 || b == 0) return 0;
    long long g = gcd_of(a, b);
    long long r = 0;
    // >>> HOLE id=divide-before-multiply prompt=Put the lowest common multiple of a and b into `r` using g, in an order that never forms the product a*b
    r = a / g * b;
    // <<< HOLE
    return r;
}

// ---------------------------------------------------------------------------
// 3. EXTENDED EUCLID — the same descent, carrying the coefficients back up.
//
//    At the bottom, a*1 + 0*0 = a, so x = 1, y = 0. Coming back up, the call
//    below returned x1, y1 with
//
//        b*x1 + (a % b)*y1 = g
//
//    and a % b = a - (a/b)*b, so substituting and collecting terms gives
//
//        a*y1 + b*(x1 - (a/b)*y1) = g
//
//    which names the new pair: x = y1, y = x1 - (a/b)*y1. That derivation is
//    the whole of the function; memorising the two assignments without it is
//    how people end up with the coefficients swapped and no idea why.
//
//    egcd(3, 7) returns g = 1, x = -2, y = 1: 3*(-2) + 7*1 = 1. So -2 is an
//    inverse of 3 modulo 7, and -2 + 7 = 5, which is the residue you wanted.
// ---------------------------------------------------------------------------
long long ext_gcd(long long a, long long b, long long& x, long long& y) {
    if (b == 0) {
        x = 1;
        y = 0;
        return a;
    }
    long long x1 = 0, y1 = 0;
    long long g = ext_gcd(b, a % b, x1, y1);
    // >>> HOLE id=bezout-lift prompt=Turn the coefficients (x1, y1) for the pair (b, a % b) into the coefficients (x, y) for the pair (a, b), so that a*x + b*y equals g
    x = y1;
    y = x1 - (a / b) * y1;
    // <<< HOLE
    return g;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n            then n values      -> gcd of the row, then lcm of the row
//   a b                             -> g, x, y with a*x + b*y = g
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    if (!(cin >> n)) return 0;
    vector<long long> v(n);
    for (long long& x : v) cin >> x;

    long long g = 0, l = 1;
    for (long long value : v) {
        g = gcd_of(g, value);
        l = lcm_of(l, value);
    }
    cout << g << " " << l << "\n";

    long long a, b;
    cin >> a >> b;
    long long x = 0, y = 0;
    long long d = ext_gcd(a, b, x, y);
    cout << d << " " << x << " " << y << "\n";

    return 0;
}
