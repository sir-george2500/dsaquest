// ===========================================================================
// COUNT WITHOUT WALKING
//
// "How many integers between l and r have this property?" is never a loop.
// The endpoints reach 10^18 and the loop would not finish, so the count is
// built out of two counts taken from the beginning:
//
//     count(l, r) = F(r) - F(l - 1)
//
// where F(x) is the count over everything up to and including x. Every bug in
// this family is one of two things: the l - 1 written as l, or a division that
// rounded towards zero when it should have rounded down.
//
// Three facts worth holding exactly:
//   * the number of integers in [l, r] is r - l + 1, and at l = r that is 1;
//   * the multiples of k up to a non-negative n number exactly n / k;
//   * C++ division truncates TOWARDS ZERO, so -7 / 2 is -3 where the floor
//     is -4. Above zero the two agree, which is why this bug survives every
//     sample built from positive numbers.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. THE DIVISION THE LANGUAGE DOES NOT GIVE YOU.
//
//    Floor division: round towards minus infinity, whatever the sign. Write it
//    once, call it everywhere, and the whole class of below-zero off-by-ones
//    disappears. The divisor is assumed positive, which is true of every count
//    in this file — a "step of k" is never negative.
//
//        floor_div( 7, 2) =  3      7 / 2 =  3    agree
//        floor_div(-7, 2) = -4     -7 / 2 = -3    differ by one
//        floor_div(-1, 3) = -1     -1 / 3 =  0    differ by one
// ---------------------------------------------------------------------------
long long floor_div(long long a, long long b) {
    long long q = 0;
    // >>> HOLE id=floor-div prompt=Divide a by the positive b rounding towards minus infinity, correcting the truncation C++ performs when the division is not exact and a is negative
    q = a / b;
    if ((a % b != 0) && ((a < 0) != (b < 0))) --q;
    // <<< HOLE
    return q;
}

// ---------------------------------------------------------------------------
// 2. THE PATTERN, IN ONE LINE.
//
//    The multiples of k up to x number floor(x / k) — including 0, which is a
//    multiple of everything, so the count is honest below zero as well. The
//    interval [l, r] is then the difference of two such counts, and the l - 1
//    is what includes the left endpoint.
//
//    Write F(r) - F(l) instead and the answer is too small by exactly one on
//    every test where l itself is a multiple, and exactly right on every test
//    where it is not. That is why it reaches the judge alive.
// ---------------------------------------------------------------------------
long long count_multiples(long long l, long long r, long long k) {
    if (l > r || k <= 0) return 0;
    long long total = 0;
    // >>> HOLE id=count-multiples prompt=Count the multiples of k in the inclusive interval [l, r] as the difference of two counts taken from the beginning, using floor_div so that negative endpoints stay correct
    total = floor_div(r, k) - floor_div(l - 1, k);
    // <<< HOLE
    return total;
}

// ---------------------------------------------------------------------------
// 3. TWO CONDITIONS, ONE OVERLAP.
//
//    "Divisible by a OR by b" is not the sum of the two counts: everything
//    divisible by both has been counted twice. What is divisible by both is
//    exactly what is divisible by their least common multiple, so subtract
//    that count once. With c conditions there are 2^c - 1 terms, which stays
//    cheap for the two or three conditions such statements ever use.
//
//    In [1, 100]: 50 multiples of 2, 33 of 3, 16 of 6, so 50 + 33 - 16 = 67.
// ---------------------------------------------------------------------------
static long long saturating_lcm(long long a, long long b) {
    long long g = gcd(a, b);
    long long left = a / g;
    // Guard first: a multiple past 4 * 10^18 cannot land in any interval whose
    // endpoints fit in a long long, so a saturated value counts zero of them.
    if (left > 4000000000000000000LL / b) return 4000000000000000000LL;
    return left * b;
}

long long count_divisible_by_either(long long l, long long r, long long a, long long b) {
    long long answer = 0;
    // >>> HOLE id=inclusion-exclusion prompt=Count the integers in [l, r] divisible by a or by b, adding both counts and removing the overlap once — the overlap is the multiples of their least common multiple, from saturating_lcm
    answer = count_multiples(l, r, a) + count_multiples(l, r, b)
           - count_multiples(l, r, saturating_lcm(a, b));
    // <<< HOLE
    return answer;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   q   then q lines "l r k"      -> size of the interval, multiples of k
//   m   then m lines "l r a b"    -> how many are divisible by a or by b
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int q;
    if (!(cin >> q)) return 0;
    for (int i = 0; i < q; ++i) {
        long long l, r, k;
        cin >> l >> r >> k;
        long long size = (l > r) ? 0 : r - l + 1;
        cout << size << ' ' << count_multiples(l, r, k) << "\n";
    }

    int m;
    cin >> m;
    for (int i = 0; i < m; ++i) {
        long long l, r, a, b;
        cin >> l >> r >> a >> b;
        cout << count_divisible_by_either(l, r, a, b) << "\n";
    }

    return 0;
}
