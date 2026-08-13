// ===========================================================================
// CROSS OUT EACH MULTIPLE ONCE
//
// Testing one number for primality costs O(sqrt(n)). Testing every number up
// to n that way costs n*sqrt(n), which at n = 1e7 is 3e10 operations and does
// not finish. The sieve turns the question inside out: instead of asking of
// each number "who divides you?", it walks each prime and strikes out its
// multiples. Every composite is struck by its own prime factors and by nobody
// else, so the total work is
//
//     n/2 + n/3 + n/5 + n/7 + ...  =  n * log log n
//
// which at n = 1e7 is a few tens of millions of writes — comfortably under a
// second. There are 664579 primes below 1e7 and 78498 below 1e6; the density
// is what makes counting them by trial division hopeless and by sieve trivial.
//
// Two details that are not decoration:
//
//   * The inner loop starts at i*i, not at 2*i. Every multiple of i below i*i
//     has a factor smaller than i and was therefore struck already. Starting
//     at 2*i is not wrong, only slower — but i*i is where the overflow lives:
//     with `int i`, i*i passes INT_MAX at i = 46341.
//
//   * Store the SMALLEST PRIME FACTOR rather than a bool. It costs the same
//     sieve and buys factorisation of any number in the range in O(log x)
//     with no division loop at all.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. THE SIEVE, STORING THE SMALLEST PRIME FACTOR.
//
//    spf[x] == 0 means "nothing has struck x yet", which for x >= 2 means x is
//    prime. So the outer loop discovers primes as it goes and never needs a
//    separate primality test.
//
//    `(long long)i * i` and not `i * i`: for n up to 1e9 the outer loop reaches
//    31622 and the product is safe, but the same code copied to a problem with
//    a larger bound overflows silently at i = 46341. The cast costs nothing.
// ---------------------------------------------------------------------------
vector<int> smallest_prime_factors(int n) {
    vector<int> spf(n + 1, 0);
    // >>> HOLE id=cross-out-once prompt=Fill spf so that spf[x] is the smallest prime dividing x for every x from 2 to n, striking each composite from its own prime factors only
    for (int i = 2; i <= n; ++i) {
        if (spf[i] != 0) continue;                  // already struck: composite
        spf[i] = i;                                 // untouched: i is prime
        for (long long j = (long long)i * i; j <= n; j += i) {
            if (spf[j] == 0) spf[j] = i;            // first prime to reach j wins
        }
    }
    // <<< HOLE
    return spf;
}

// ---------------------------------------------------------------------------
// 2. FACTORISING INSIDE THE SIEVED RANGE — no division search at all.
//
//    spf[x] hands you a prime factor directly, so the loop is "peel the
//    smallest factor, repeat". Each peel divides x by at least 2, so it runs
//    at most log2(x) times: about twenty steps for x up to 1e6, whatever x is.
//
//    720 = 2^4 * 3^2 * 5, and the number of divisors follows from the
//    exponents alone: (4+1)(2+1)(1+1) = 30.
// ---------------------------------------------------------------------------
vector<pair<int, int>> factorise_sieved(int x, const vector<int>& spf) {
    vector<pair<int, int>> out;
    // >>> HOLE id=peel-the-smallest prompt=Reduce x to 1 by repeatedly removing its smallest prime factor, appending each distinct prime with its exponent to `out`
    while (x > 1) {
        int prime = spf[x];
        int exponent = 0;
        while (x % prime == 0) {
            x /= prime;
            ++exponent;
        }
        out.push_back({prime, exponent});
    }
    // <<< HOLE
    return out;
}

// ---------------------------------------------------------------------------
// 3. FACTORISING ONE LARGE NUMBER — trial division, and the leftover rule.
//
//    A sieve to 1e12 is not memory you have. But one number that size can be
//    factorised by trying every divisor up to its square root, which is 1e6
//    steps, because of a fact worth stating out loud:
//
//        AFTER dividing out every prime factor <= sqrt(n), whatever remains is
//        either 1 or a single PRIME.
//
//    It cannot be composite: two factors each above the square root of the
//    ORIGINAL n would multiply past n. That last `if (n > 1)` is not a tidying
//    step, it is where the largest prime factor comes from, and forgetting it
//    is the classic wrong answer on inputs like 1999999874 = 2 * 999999937.
//
//    `d * d <= n` and not `d <= sqrt(n)`: sqrt returns a double, and a double
//    has 53 bits of mantissa against n's 63, so the comparison is a coin flip
//    on the boundary. Note that n shrinks inside the loop, which is what keeps
//    the bound honest and the loop short.
// ---------------------------------------------------------------------------
vector<pair<long long, int>> factorise_large(long long n) {
    vector<pair<long long, int>> out;
    // >>> HOLE id=stop-at-the-root prompt=Factorise n completely by trial division no further than its square root, remembering that whatever survives the loop is itself prime
    for (long long d = 2; d * d <= n; ++d) {
        if (n % d != 0) continue;
        int exponent = 0;
        while (n % d == 0) {
            n /= d;
            ++exponent;
        }
        out.push_back({d, exponent});
    }
    if (n > 1) out.push_back({n, 1});               // the one prime above the root
    // <<< HOLE
    return out;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n            -> how many primes are at most n
//   q            then q values <= n -> the divisor count of each
//   big          -> the prime factorisation of one large value, "p^e" per factor
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    if (!(cin >> n)) return 0;
    vector<int> spf = smallest_prime_factors(n);

    int primes = 0;
    for (int i = 2; i <= n; ++i) {
        if (spf[i] == i) ++primes;
    }
    cout << primes << "\n";

    int q;
    cin >> q;
    for (int i = 0; i < q; ++i) {
        int x;
        cin >> x;
        long long divisors = 1;
        for (const auto& [prime, exponent] : factorise_sieved(x, spf)) {
            (void)prime;
            divisors *= exponent + 1;
        }
        cout << divisors << "\n";
    }

    long long big;
    cin >> big;
    vector<pair<long long, int>> factors = factorise_large(big);
    for (size_t i = 0; i < factors.size(); ++i) {
        if (i) cout << " ";
        cout << factors[i].first << "^" << factors[i].second;
    }
    cout << "\n";

    return 0;
}
