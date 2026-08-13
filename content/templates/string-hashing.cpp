// ===========================================================================
// POLYNOMIAL STRING HASHING — O(1) substring equality, at a price
//
// Read the string as a number in base B, modulo M:
//
//     H[0] = 0
//     H[i+1] = H[i] * B + value(s[i])      (mod M)
//
// Then every substring's hash is one multiply and one subtract:
//
//     hash(l, r) = H[r] - H[l] * B^(r-l)   (mod M)      [ half-open, l..r-1 ]
//
// Worked by hand, B = 31, value('a') = 1, no wrap-around needed:
//     "abc"  ->  H = [0, 1, 33, 1026]     and  B^2 = 961
//     hash(1,3) = 1026 - 1 * 961 = 65     which is 'b'*31 + 'c' = 2*31 + 3 = 65
//
// That is the entire technique, and it turns "are these two substrings equal?"
// from O(len) into O(1). Sorting substrings, binary-searching a longest common
// prefix, counting distinct substrings — all become easy.
//
// THE PRICE. Two different strings can share a hash, and unlike most bugs this
// one is CHOSEN BY YOUR OPPONENT:
//
//   * mod 2^64 (plain unsigned overflow) is not probabilistic at all. For ANY
//     odd base there is a pair of Thue-Morse strings that collide, and with
//     B = 31 they are only 256 characters long. Anybody can generate them
//     without knowing your base.
//   * a single prime near 1e9 dies to the birthday bound: about 37,000 hashes
//     give a 50% chance of a collision, and a string of length 300 already has
//     more substrings than that. These two 20-character strings collide under
//     B = 31, M = 1e9+9:
//         bbaaabbbaaaabbabbbba
//         aabaaababbabaaababab      both hash to 212006090
//
// So: two moduli (or one modulus near 1e18 with __int128), and a base drawn at
// random at run time. The bases below are FIXED only so this file's output is
// reproducible; the commented line is what a real submission uses.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

using ll = long long;

// ---------------------------------------------------------------------------
// 1. THE DOUBLE HASH.
//
//    Two independent (base, modulus) pairs, compared as a pair. The chance of
//    an accidental collision falls from ~1/1e9 to ~1/1e18, and no published
//    anti-hash test can target a base it does not know.
//
//    value(c) MUST NOT be zero for any character that can appear. Map 'a' to 1,
//    not to 0: with 'a' -> 0 the strings "a", "aa" and "aaa" all hash to 0, and
//    so does every prefix of a-runs — a whole family of collisions you built
//    yourself before the setter had to try.
// ---------------------------------------------------------------------------
struct DoubleHash {
    static const ll M1 = 1000000007LL;
    static const ll M2 = 998244353LL;
    ll b1, b2;
    vector<ll> h1, h2, p1, p2;

    DoubleHash(const string& s, ll base1 = 131, ll base2 = 137) : b1(base1), b2(base2) {
        // In a contest: mt19937_64 rng(chrono::steady_clock::now()
        //                              .time_since_epoch().count());
        //               b1 = 200 + rng() % 100000;  b2 = 200 + rng() % 100000;
        int n = (int)s.size();
        h1.assign(n + 1, 0);
        h2.assign(n + 1, 0);
        p1.assign(n + 1, 1);
        p2.assign(n + 1, 1);
        // >>> HOLE id=prefix-hash prompt=Fill h1/h2 with the prefix hashes and p1/p2 with the powers of the two bases, mapping s[i] to (s[i] - 'a' + 1) so that no character contributes zero
        for (int i = 0; i < n; ++i) {
            ll v = (ll)(s[i] - 'a' + 1);          // never 0 — see the note above
            h1[i + 1] = (h1[i] * b1 + v) % M1;
            h2[i + 1] = (h2[i] * b2 + v) % M2;
            p1[i + 1] = p1[i] * b1 % M1;
            p2[i + 1] = p2[i] * b2 % M2;
        }
        // <<< HOLE
    }

    // Hash of s[l .. r-1]. Half-open, like every other range in this codebase.
    pair<ll, ll> sub(int l, int r) const {
        // >>> HOLE id=substring-hash prompt=Return the pair of hashes of the half-open range [l, r), remembering that a subtraction modulo M can go negative in C++ and must be brought back into range
        ll a = (h1[r] - h1[l] % M1 * p1[r - l]) % M1;
        ll b = (h2[r] - h2[l] % M2 * p2[r - l]) % M2;
        if (a < 0) a += M1;                        // C++ % keeps the sign of the dividend
        if (b < 0) b += M2;
        // <<< HOLE
        return {a, b};
    }

    bool equal(int l1, int l2, int len) const { return sub(l1, l1 + len) == sub(l2, l2 + len); }

    int size() const { return (int)h1.size() - 1; }
};

// ---------------------------------------------------------------------------
// 2. LONGEST COMMON PREFIX OF TWO SUFFIXES, by binary search on the length.
//
//    "the first len characters agree" is monotone in len — if len works, so
//    does len - 1 — so the largest len is a binary search, O(log n) per query
//    with no suffix automaton anywhere in sight.
// ---------------------------------------------------------------------------
int lcp_of_suffixes(const DoubleHash& h, int i, int j) {
    int n = h.size();
    int lo = 0, hi = n - max(i, j);
    while (lo < hi) {
        int mid = lo + (hi - lo + 1) / 2;
        if (h.equal(i, j, mid)) lo = mid;
        else hi = mid - 1;
    }
    return lo;
}

// ---------------------------------------------------------------------------
// 3. COUNTING DISTINCT SUBSTRINGS OF A FIXED LENGTH.
//
//    n - k + 1 windows, one hash each, dropped into a set. O(n log n) with no
//    string comparison at all — which is exactly the operation hashing exists
//    to remove.
//
//    Note what is being trusted: two windows with the same hash are ASSUMED
//    equal. That assumption is the whole risk, and it is why the double hash
//    above is not optional.
// ---------------------------------------------------------------------------
int distinct_windows(const string& s, int k) {
    int n = (int)s.size();
    if (k <= 0 || k > n) return 0;
    DoubleHash h(s);
    // >>> HOLE id=distinct-count prompt=Collect the hash of every window of length k into a set of pairs and return how many different ones there were
    set<pair<ll, ll>> seen;
    for (int i = 0; i + k <= n; ++i) seen.insert(h.sub(i, i + k));
    return (int)seen.size();
    // <<< HOLE
}

// ---------------------------------------------------------------------------
// 4. RABIN-KARP SEARCH, with the verification most write-ups leave out.
//
//    A double hash makes a false match vanishingly unlikely; comparing the
//    candidate afterwards makes it impossible, and costs nothing amortised
//    because it only runs on hits. If you cannot afford the check, you have
//    chosen the wrong tool — the prefix function finds every occurrence in
//    O(n + m) and cannot be fooled at all.
// ---------------------------------------------------------------------------
vector<int> search_by_hash(const string& text, const string& pat) {
    vector<int> at;
    int n = (int)text.size(), m = (int)pat.size();
    if (m == 0 || m > n) return at;
    DoubleHash ht(text), hp(pat);
    pair<ll, ll> target = hp.sub(0, m);
    for (int i = 0; i + m <= n; ++i)
        if (ht.sub(i, i + m) == target && text.compare(i, m, pat) == 0) at.push_back(i);
    return at;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   s k pat l1 l2
//     -> the double hash of the whole of s
//     -> number of distinct substrings of s of length k
//     -> occurrences of pat in s (count, then positions)
//     -> whether the suffixes at l1 and l2 share a prefix, and how long
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    string s, pat;
    int k = 0, l1 = 0, l2 = 0;
    if (!(cin >> s >> k >> pat >> l1 >> l2)) return 0;

    DoubleHash h(s);
    pair<ll, ll> whole = h.sub(0, (int)s.size());
    cout << whole.first << ' ' << whole.second << "\n";

    cout << distinct_windows(s, k) << "\n";

    vector<int> at = search_by_hash(s, pat);
    cout << at.size();
    for (int p : at) cout << ' ' << p;
    cout << "\n";

    if (l1 >= 0 && l2 >= 0 && l1 < (int)s.size() && l2 < (int)s.size())
        cout << lcp_of_suffixes(h, l1, l2) << "\n";
    else
        cout << 0 << "\n";

    return 0;
}
