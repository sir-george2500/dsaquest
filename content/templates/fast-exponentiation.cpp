// ===========================================================================
// HALVE THE EXPONENT
//
// a^e needs e multiplications if you loop, and about 2*log2(e) if you notice
// one identity:
//
//     a^e = (a^(e/2))^2            when e is even
//     a^e = a * a^(e-1)            when e is odd
//
// Read from the other end, that is exactly the binary expansion of e: square
// the base at every step, and multiply it into the answer at the steps where
// the bit is set. e = 13 = 1101 costs four squarings and three multiplications
// — seven, against twelve for the loop. At e = 1e18 it is sixty steps against
// a number of steps that does not finish before the heat death of anything.
//
// The same routine, given the exponent m - 2 and a PRIME modulus m, computes
// a modular inverse, which is the only way division enters this region at all.
//
//     a^(m-1) = 1 (mod m)    for prime m and a not a multiple of m  [Fermat]
//     so  a * a^(m-2) = 1,   so  a^(m-2) IS 1/a modulo m.
//
// From an inverse you get binomial coefficients, and from binomial
// coefficients you get most of the counting problems in a contest.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. BINARY EXPONENTIATION.
//
//    `r = 1 % m` because m may be 1. `b %= m` first, because the caller may
//    hand you a base larger than the modulus and `b * b` must stay under m*m.
//    The negative fix-up is there because a caller who subtracted to get b
//    would otherwise square a negative residue and hand back a negative answer.
//
//    Trace of 3^13 mod 1000, one line per iteration:
//
//        e = 13  bit 1   r = 1*3   = 3        b = 3*3     = 9
//        e =  6  bit 0   r         = 3        b = 9*9     = 81
//        e =  3  bit 1   r = 3*81  = 243      b = 81*81   = 561
//        e =  1  bit 1   r = 243*561 = 323    b (unused)
//
//    3^13 = 1594323, and 1594323 mod 1000 is 323.
//
//    Both `r * b` and `b * b` are full products of two values below m. With
//    m <= 1e9 they reach 1e18 and need a long long; with m near 1e18 they need
//    __int128 and there is no warning if you forget.
// ---------------------------------------------------------------------------
long long power(long long b, long long e, long long m) {
    long long r = 1 % m;
    b %= m;
    if (b < 0) b += m;
    // >>> HOLE id=halve-the-exponent prompt=Raise `b` to the power `e` modulo m in about log2(e) steps, leaving the answer in `r` and consuming `e` one bit at a time
    while (e > 0) {
        if (e & 1) r = r * b % m;       // this bit of e is set: fold b in
        b = b * b % m;                  // advance to the next power of two
        e >>= 1;
    }
    // <<< HOLE
    return r;
}

// ---------------------------------------------------------------------------
// 2. DIVISION, VIA FERMAT.
//
//    (a / b) % m is not a thing. What exists is a * inv(b) % m, where inv(b)
//    is the residue satisfying b * inv(b) = 1 (mod m).
//
//        inverse of 3 mod 7 is 5, because 3 * 5 = 15 = 2*7 + 1.
//        3^(7-2) = 3^5 = 243 = 34*7 + 5. The exponent produced it.
//        inverse of 2 mod 1e9+7 is 500000004, and 2 * 500000004 = 1000000008.
//
//    Two preconditions, both silent when broken:
//      * m must be PRIME. Fermat says nothing otherwise, and the answer comes
//        back plausible and wrong. For a composite modulus use extended
//        Euclid (see euclidean-gcd.cpp), which also tells you when no inverse
//        exists at all.
//      * a must not be a multiple of m. 0 has no inverse; neither does 6
//        modulo 12, because they share a factor.
// ---------------------------------------------------------------------------
long long inverse_mod(long long a, long long prime_m) {
    long long r = 0;
    // >>> HOLE id=fermat-inverse prompt=Return in `r` the modular inverse of a for the PRIME modulus prime_m, using nothing but the power routine above
    r = power(a, prime_m - 2, prime_m);
    // <<< HOLE
    return r;
}

// ---------------------------------------------------------------------------
// 3. BINOMIAL COEFFICIENTS MODULO A PRIME.
//
//    C(n, k) = n! / (k! (n-k)!), and the division is three inverses — except
//    that computing three inverses per query is a log factor you do not need.
//    Build the factorials forwards, ONE inverse at the top, and walk the
//    inverse factorials back down:
//
//        invfact[i-1] = invfact[i] * i        because 1/(i-1)! = i / i!
//
//    That is O(n) for the whole table and O(1) per coefficient.
//
//    C(10, 3) = 120. C(200000, 100000) mod 1e9+7 = 879467333.
//
//    The table is only valid while n < p. The moment n reaches p, some factor
//    of n! is p itself, fact[n] is 0, and its "inverse" is 0^(p-2) = 0 — a
//    confident, silent, entirely wrong answer. C(10, 3) = 120 = 1 mod 7, but
//    the table cannot produce it, because 10! mod 7 is 0. That case is Lucas's
//    theorem, and it is a different algorithm.
// ---------------------------------------------------------------------------
struct Binomial {
    long long p;
    vector<long long> fact, invfact;

    Binomial(int n, long long prime) : p(prime), fact(n + 1), invfact(n + 1) {
        fact[0] = 1 % p;
        for (int i = 1; i <= n; ++i) fact[i] = fact[i - 1] * i % p;
        invfact[n] = inverse_mod(fact[n], p);
        for (int i = n; i >= 1; --i) invfact[i - 1] = invfact[i] * i % p;
    }

    long long choose(int upper, int lower) const {
        if (lower < 0 || lower > upper) return 0;
        long long r = 0;
        // >>> HOLE id=binomial-from-tables prompt=Combine fact and invfact into C(upper, lower) modulo p in `r`, reducing between the two multiplications so no product exceeds p*p
        r = fact[upper] * invfact[lower] % p * invfact[upper - lower] % p;
        // <<< HOLE
        return r;
    }
};

// ---------------------------------------------------------------------------
// Demo harness.
//   b e m          -> b^e modulo m
//   a p            -> the inverse of a modulo the prime p
//   n q            then q pairs "upper lower" -> C(upper, lower) modulo 1e9+7
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    long long b, e, m;
    if (!(cin >> b >> e >> m)) return 0;
    cout << power(b, e, m) << "\n";

    long long a, p;
    cin >> a >> p;
    cout << inverse_mod(a, p) << "\n";

    int n, q;
    cin >> n >> q;
    Binomial table(n, 1000000007LL);
    for (int i = 0; i < q; ++i) {
        int upper, lower;
        cin >> upper >> lower;
        cout << table.choose(upper, lower) << "\n";
    }

    return 0;
}
