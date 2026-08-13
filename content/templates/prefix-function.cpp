// ===========================================================================
// THE PREFIX FUNCTION — borders, KMP, periods, and the Z-array
//
// One idea, four uses: compare a string against ITSELF and never re-read a
// character you have already accounted for.
//
//     pi[i] = the length of the longest proper prefix of s[0..i] that is also
//             a suffix of s[0..i].     ("proper" = shorter than i + 1)
//
// The whole family lives on one observation. If the border of s[0..i-1] has
// length k and s[i] == s[k], the border grows to k + 1. If it does not, the
// only shorter candidate is the border OF THAT BORDER — pi[k-1] — because a
// border of s[0..i] shorter than k is also a border of the length-k prefix.
// So the fallback chain is pi[k-1], pi[pi[k-1]-1], ... and it never restarts
// from zero. k rises by at most one per step and every fallback lowers it, so
// the total work is O(n) even though the inner loop looks quadratic.
//
// What it buys you, in the order these become reflexes:
//   * substring search in O(n + m) with no hashing and no chance of collision;
//   * the smallest period of a string, in one subtraction;
//   * how many times each prefix occurs, in one backwards sweep;
//   * the Z-array, which answers "how far does the string match itself here?"
//
// Two rules that outlive every problem:
//   * the separator between pattern and text must be a byte that CANNOT occur
//     in either string, or the match count is wrong;
//   * never index cnt[pi[i] - 1] without checking pi[i] > 0 first.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. THE PREFIX FUNCTION itself.
//
//    "abacaba" -> [0, 0, 1, 0, 1, 2, 3]
//                            ^        ^ the whole prefix "aba" is also a suffix
//
//    pi[0] is always 0: a one-character string has no PROPER border.
// ---------------------------------------------------------------------------
vector<int> prefix_function(const string& s) {
    int n = (int)s.size();
    vector<int> pi(n, 0);
    // >>> HOLE id=pi-fallback prompt=Fill pi[i] for every i from 1: start from the previous border length, fall back through pi[k-1] while the next character disagrees, and extend by one when it agrees
    for (int i = 1; i < n; ++i) {
        int k = pi[i - 1];
        while (k > 0 && s[i] != s[k]) k = pi[k - 1];   // the border of the border
        if (s[i] == s[k]) ++k;
        pi[i] = k;
    }
    // <<< HOLE
    return pi;
}

// ---------------------------------------------------------------------------
// 2. EVERY BORDER, not just the longest.
//
//    Walking pi[k-1] from pi[n-1] lists all border lengths in decreasing order.
//    "abacaba" -> 3, 1  (that is "aba" and "a", and there are no others).
// ---------------------------------------------------------------------------
vector<int> all_border_lengths(const string& s) {
    vector<int> lens;
    if (s.empty()) return lens;
    vector<int> pi = prefix_function(s);
    for (int k = pi.back(); k > 0; k = pi[k - 1]) lens.push_back(k);
    return lens;
}

// ---------------------------------------------------------------------------
// 3. KMP SEARCH — every occurrence, overlaps included, in O(n + m).
//
//    Run the prefix function over  pattern + SEP + text  and report every
//    position whose pi equals the pattern length. The separator must be a byte
//    that occurs in NEITHER string, otherwise a border may run across the join
//    and the count is wrong: searching "aab" inside "aabaabaab" with no
//    separator at all reports 1 occurrence where there are 3.
//
//    '\1' is used here because the inputs are printable text. If the input can
//    be arbitrary bytes, there is no safe separator — compare pi >= m against
//    the text region instead, or use the automaton form.
// ---------------------------------------------------------------------------
vector<int> occurrences(const string& pat, const string& text) {
    vector<int> at;
    if (pat.empty() || pat.size() > text.size()) return at;
    // >>> HOLE id=kmp-search prompt=Join the pattern to the text with the separator, run the prefix function once, and push the start position in `text` of every full match into `at`
    string joined = pat + '\1' + text;
    vector<int> pi = prefix_function(joined);
    int m = (int)pat.size();
    for (int i = m + 1; i < (int)joined.size(); ++i)
        if (pi[i] == m) at.push_back(i - 2 * m);       // i is the LAST index of the match
    // <<< HOLE
    return at;
}

// ---------------------------------------------------------------------------
// 4. THE SMALLEST PERIOD, in one subtraction.
//
//    p = n - pi[n-1] is the smallest p with s[i] == s[i + p] for every valid i.
//    The string is p repeated exactly n / p times IF AND ONLY IF n % p == 0.
//
//      "aabaab"  n=6  pi.back()=3  p=3  6 % 3 == 0  -> "aab" twice
//      "abcabca" n=7  pi.back()=4  p=3  7 % 3 != 0  -> period 3, not a repeat
//
//    The second case is the one people get wrong: 3 IS the smallest period of
//    "abcabca", it simply does not tile the string exactly.
// ---------------------------------------------------------------------------
int smallest_period(const string& s) {
    if (s.empty()) return 0;
    vector<int> pi = prefix_function(s);
    return (int)s.size() - pi.back();
}

bool is_a_repetition(const string& s) {
    int p = smallest_period(s);
    return p > 0 && (int)s.size() % p == 0 && p < (int)s.size();
}

// ---------------------------------------------------------------------------
// 5. HOW OFTEN EACH PREFIX OCCURS, in one backwards sweep.
//
//    Start every prefix at count 1 (itself) and push each position's count
//    down its border chain — one step, because the chain does the rest as the
//    sweep continues.  "abacaba" -> "a" 4 times, "ab" 2, "aba" 2, the rest 1.
//
//    The guard matters: pi[i] == 0 would index cnt[-1], which is undefined
//    behaviour and, in practice, silently corrupts whatever sits before cnt.
// ---------------------------------------------------------------------------
vector<int> prefix_occurrences(const string& s) {
    int n = (int)s.size();
    vector<int> cnt(n, 1);
    if (n == 0) return cnt;
    vector<int> pi = prefix_function(s);
    for (int i = n - 1; i >= 1; --i)
        if (pi[i] > 0) cnt[pi[i] - 1] += cnt[i];       // the guard is load-bearing
    return cnt;
}

// ---------------------------------------------------------------------------
// 6. THE Z-ARRAY — the same idea, measured forwards.
//
//    z[i] = length of the longest common prefix of s and s[i..].  By
//    convention z[0] = n.  "abacaba" -> [7, 0, 1, 0, 3, 0, 1].
//
//    [l, r) is the rightmost segment known to equal a prefix of s. Inside it
//    the answer is already known from position i - l, so the only comparisons
//    ever made are past r — and r never moves backwards, which is the whole
//    O(n) argument.
// ---------------------------------------------------------------------------
vector<int> z_function(const string& s) {
    int n = (int)s.size();
    vector<int> z(n, 0);
    if (n == 0) return z;
    z[0] = n;
    // >>> HOLE id=z-window prompt=Fill z[i] for every i from 1: seed it from the mirror position inside the rightmost known match, extend it by direct comparison, then move that window when it reaches further right
    for (int i = 1, l = 0, r = 0; i < n; ++i) {
        if (i < r) z[i] = min(r - i, z[i - l]);        // never past the known segment
        while (i + z[i] < n && s[z[i]] == s[i + z[i]]) ++z[i];
        if (i + z[i] > r) { l = i; r = i + z[i]; }
    }
    // <<< HOLE
    return z;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   pat text s
//     -> pi of pat
//     -> occurrences of pat in text (count, then the positions)
//     -> smallest period of s, and whether s is an exact repetition
//     -> z of s
//     -> occurrence count of every prefix of s
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    string pat, text, s;
    if (!(cin >> pat >> text >> s)) return 0;

    for (int v : prefix_function(pat)) cout << v << ' ';
    cout << "\n";

    vector<int> at = occurrences(pat, text);
    cout << at.size();
    for (int p : at) cout << ' ' << p;
    cout << "\n";

    cout << smallest_period(s) << ' ' << (is_a_repetition(s) ? 1 : 0) << "\n";

    for (int v : z_function(s)) cout << v << ' ';
    cout << "\n";

    for (int v : prefix_occurrences(s)) cout << v << ' ';
    cout << "\n";

    vector<int> borders = all_border_lengths(s);
    cout << borders.size();
    for (int v : borders) cout << ' ' << v;
    cout << "\n";

    return 0;
}
