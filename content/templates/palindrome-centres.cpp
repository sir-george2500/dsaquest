// ===========================================================================
// PALINDROMES BY THEIR CENTRES
//
// A palindrome is defined by its MIDDLE, not by its ends. There are 2n - 1
// possible middles in a string of length n — n characters and n - 1 gaps
// between them — and every palindromic substring grows outwards from exactly
// one of them. Enumerate the middles, not the O(n^2) pairs of endpoints.
//
//     d1[i] = how many ODD  palindromes are centred at character i
//             (equivalently: the radius, counting the centre itself)
//     d2[i] = how many EVEN palindromes are centred in the gap BEFORE i
//
// For "abacaba":  d1 = [1, 2, 1, 4, 1, 2, 1]   d2 = [0, 0, 0, 0, 0, 0, 0]
// For "aaaa":     d1 = [1, 2, 2, 1]            d2 = [0, 1, 2, 1]
//
// Two facts fall straight out of those arrays and neither needs another pass:
//
//   * the number of palindromic substrings (as occurrences) is sum(d1) + sum(d2)
//         "abacaba" -> 12,   "aaaa" -> 10
//   * s[l..r] is a palindrome iff the radius at its own centre reaches its ends
//
// Expanding by hand from every centre is O(n^2) and is the right answer up to
// about n = 5000. On an all-equal string of length 1e5 it is 5e9 comparisons
// and it will not finish. Manacher does the same work in O(n) by refusing to
// re-compare anything already inside a palindrome it has found — the mirror
// trick below, which is the same idea as the Z-array's window.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. EXPAND AROUND THE CENTRE — O(n^2), and the version to write first.
//
//    Returns the longest palindromic substring. Both parities must be tried:
//    an odd-only expansion misses "abba" entirely and no test with an odd
//    answer will ever tell you.
// ---------------------------------------------------------------------------
string longest_palindrome(const string& s) {
    int n = (int)s.size();
    if (n == 0) return "";
    int best_l = 0, best_len = 1;
    // >>> HOLE id=expand-centres prompt=For every one of the 2n-1 centres, push both ends outwards while the characters agree, and keep the start and length of the longest palindrome seen
    for (int c = 0; c < n; ++c) {
        for (int parity = 0; parity < 2; ++parity) {
            int l = c, r = c + parity;                 // parity 0: odd, 1: even
            while (l >= 0 && r < n && s[l] == s[r]) { --l; ++r; }
            ++l; --r;                                  // step back onto the match
            if (r - l + 1 > best_len) { best_len = r - l + 1; best_l = l; }
        }
    }
    // <<< HOLE
    return s.substr(best_l, best_len);
}

// ---------------------------------------------------------------------------
// 2. MANACHER, ODD CENTRES — O(n).
//
//    [l, r] is the palindrome found so far that reaches furthest right. A
//    position i inside it mirrors to l + r - i, and the radius there is
//    already known — so start from it instead of from 1. Clamp to r - i + 1:
//    beyond the known palindrome nothing has been verified, and trusting the
//    mirror past its edge is the classic wrong answer here.
//
//    r never moves left, and every character comparison that fails ends a
//    position while every one that succeeds pushes r right. That is the whole
//    linear-time argument.
// ---------------------------------------------------------------------------
vector<int> manacher_odd(const string& s) {
    int n = (int)s.size();
    vector<int> d1(n, 0);
    // >>> HOLE id=manacher-odd prompt=Fill d1 with the odd radii: seed each position from its mirror inside the rightmost known palindrome, clamped to that palindrome's remaining reach, extend by direct comparison, then move the window when it reaches further right
    for (int i = 0, l = 0, r = -1; i < n; ++i) {
        int k = (i > r) ? 1 : min(d1[l + r - i], r - i + 1);
        while (i - k >= 0 && i + k < n && s[i - k] == s[i + k]) ++k;
        d1[i] = k--;
        if (i + k > r) { l = i - k; r = i + k; }
    }
    // <<< HOLE
    return d1;
}

// ---------------------------------------------------------------------------
// 3. MANACHER, EVEN CENTRES — O(n).
//
//    The same code with the centre sitting in the gap BEFORE i, which moves
//    two indices by one each. d2[i] counts the even palindromes whose right
//    half starts at i, so d2[0] is always 0.
//
//    Writing this twice, carefully, is honest work. The alternative — inserting
//    '#' between every pair of characters and running the odd version on the
//    doubled string — is shorter to write and slower, uses twice the memory,
//    and turns every index into an arithmetic puzzle at the moment you need to
//    read an answer back out.
// ---------------------------------------------------------------------------
vector<int> manacher_even(const string& s) {
    int n = (int)s.size();
    vector<int> d2(n, 0);
    // >>> HOLE id=manacher-even prompt=Fill d2 with the even radii the same way, remembering that the centre now lies in the gap before i so the left end starts one further out
    for (int i = 0, l = 0, r = -1; i < n; ++i) {
        int k = (i > r) ? 0 : min(d2[l + r - i + 1], r - i + 1);
        while (i - k - 1 >= 0 && i + k < n && s[i - k - 1] == s[i + k]) ++k;
        d2[i] = k--;
        if (i + k > r) { l = i - k - 1; r = i + k; }
    }
    // <<< HOLE
    return d2;
}

// ---------------------------------------------------------------------------
// 4. WHAT THE RADII ANSWER, once you have them.
// ---------------------------------------------------------------------------
long long count_palindromic_substrings(const string& s) {
    long long total = 0;
    for (int v : manacher_odd(s)) total += v;
    for (int v : manacher_even(s)) total += v;
    return total;
}

// O(1) per query: does the radius at this range's own centre reach its ends?
bool is_palindrome(const vector<int>& d1, const vector<int>& d2, int l, int r) {
    if (l > r) return false;
    int len = r - l + 1;
    if (len % 2 == 1) return d1[(l + r) / 2] >= (len + 1) / 2;
    return d2[(l + r + 1) / 2] >= len / 2;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   s l r
//     -> the longest palindromic substring of s
//     -> how many palindromic substrings s has, counting occurrences
//     -> d1
//     -> d2
//     -> whether s[l..r] is a palindrome
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    string s;
    int l, r;
    if (!(cin >> s >> l >> r)) return 0;

    cout << longest_palindrome(s) << "\n";
    cout << count_palindromic_substrings(s) << "\n";

    vector<int> d1 = manacher_odd(s), d2 = manacher_even(s);
    for (int v : d1) cout << v << ' ';
    cout << "\n";
    for (int v : d2) cout << v << ' ';
    cout << "\n";

    bool ok = l >= 0 && r < (int)s.size() && is_palindrome(d1, d2, l, r);
    cout << (ok ? 1 : 0) << "\n";

    return 0;
}
