// ===========================================================================
// TWO PREFIXES, ONE TABLE
//
// One input needs one index. Two inputs being aligned against each other need
// two, and the state is a table:
//
//     dp[i][j] = the answer for the first i characters of a
//                against the first j characters of b
//
// THE INDEX CONVENTION, stated once and obeyed everywhere below:
//
//     cell (i, j) covers a[0 .. i-1] and b[0 .. j-1].
//     So the characters cell (i, j) has just consumed are a[i-1] and b[j-1].
//     The table is (n+1) by (m+1) because row 0 and column 0 are the EMPTY
//     prefixes, and the empty prefix is a real case with a real answer.
//
// Nearly every bug in this family is that convention being broken halfway down
// a loop — comparing a[i] with b[j], or sizing the table n by m and having
// nowhere to put the border. Write the convention above the loop and check the
// two indices against it before you compile.
//
// The recurrence reads exactly three cells, and each one is a move:
//
//     dp[i-1][j]     delete a[i-1]          (advance in a alone)
//     dp[i][j-1]     insert b[j-1]          (advance in b alone)
//     dp[i-1][j-1]   match or substitute    (advance in both)
//
// Every problem in the family is those three moves with different costs.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. EDIT DISTANCE — the fewest insertions, deletions and substitutions that
//    turn a into b.
//
//    The border is forced by the definition, not chosen. dp[i][0] is the cost
//    of turning the first i characters of a into the EMPTY string, which is i
//    deletions. dp[0][j] is j insertions. Leave the border out and every
//    answer comes back too small by the length of the shorter prefix.
//
//    LOVE -> MOVIE is 2: substitute L for M, then insert I.
//
//        . M O V I E
//      . 0 1 2 3 4 5
//      L 1 1 2 3 4 5
//      O 2 2 1 2 3 4
//      V 3 3 2 1 2 3
//      E 4 4 3 2 2 2
//
//    kitten -> sitting is 3, sunday -> saturday is 3, and a string against
//    itself is 0 without the loop ever looking at a cost.
// ---------------------------------------------------------------------------
vector<vector<int>> edit_table(const string& a, const string& b) {
    int n = (int)a.size(), m = (int)b.size();
    vector<vector<int>> dp(n + 1, vector<int>(m + 1, 0));
    // >>> HOLE id=edit-border-and-moves prompt=Fill the empty-prefix border and then every interior cell, where dp[i][j] is the edit distance between the first i of a and the first j of b, choosing the cheapest of delete, insert and match-or-substitute
    for (int i = 0; i <= n; ++i) dp[i][0] = i;      // i deletions
    for (int j = 0; j <= m; ++j) dp[0][j] = j;      // j insertions
    for (int i = 1; i <= n; ++i) {
        for (int j = 1; j <= m; ++j) {
            int cost = (a[i - 1] == b[j - 1]) ? 0 : 1;
            dp[i][j] = min({dp[i - 1][j] + 1,           // delete a[i-1]
                            dp[i][j - 1] + 1,           // insert b[j-1]
                            dp[i - 1][j - 1] + cost});  // match or substitute
        }
    }
    // <<< HOLE
    return dp;
}

// ---------------------------------------------------------------------------
// 2. LONGEST COMMON SUBSEQUENCE — the same table with a different rule at a
//    match, and a maximisation instead of a minimisation.
//
//    dp[i][j] = the length of the longest subsequence common to a[0..i) and
//    b[0..j). The border is all zeros: nothing is common to a prefix and the
//    empty string.
//
//    A match is not a choice. If a[i-1] == b[j-1] it is always safe to pair
//    them, so the cell is dp[i-1][j-1] + 1 and the other two moves need not be
//    considered at all. That is why this recurrence is shorter than edit
//    distance despite living in the same table.
//
//    LCS("AGGTAB", "GXTXAYB") = 4, namely GTAB.
//
//    Worth memorising, because it is the disguise most often used: the fewest
//    deletions from BOTH strings that make them equal is n + m - 2 * LCS.
//    On "sea" and "eat" the LCS is 2 ("ea"), so 3 + 3 - 4 = 2 deletions.
// ---------------------------------------------------------------------------
int lcs_length(const string& a, const string& b) {
    int n = (int)a.size(), m = (int)b.size();
    vector<vector<int>> dp(n + 1, vector<int>(m + 1, 0));
    // >>> HOLE id=lcs-match-rule prompt=Fill the table so dp[i][j] is the longest common subsequence of the two prefixes, taking the free pairing when the two just-consumed characters agree
    for (int i = 1; i <= n; ++i) {
        for (int j = 1; j <= m; ++j) {
            if (a[i - 1] == b[j - 1]) {
                dp[i][j] = dp[i - 1][j - 1] + 1;
            } else {
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1]);
            }
        }
    }
    // <<< HOLE
    return dp[n][m];
}

// ---------------------------------------------------------------------------
// 3. THE ROLLING FORM — the same edit distance in O(min(n, m)) memory.
//
//    An n by m table of int at n = m = 10^5 is 40 GB. Two rows is 800 KB. The
//    rewrite is mechanical once you notice that a cell only ever reads the
//    previous row and the cell immediately to its left.
//
//    What it costs you: the traceback. The alignment itself cannot be
//    reconstructed from two rows, so use this only when the statement asks for
//    the NUMBER and not for the operations.
//
//    Two full rows is the safe version and it is what is written here. The
//    single-row version is faster and needs the diagonal saved into a scalar
//    before it is overwritten — a step that is forgotten often enough that it
//    is not worth the saving unless the memory limit demands it.
// ---------------------------------------------------------------------------
int edit_distance_rolling(const string& a, const string& b) {
    int n = (int)a.size(), m = (int)b.size();
    vector<int> prev(m + 1, 0), cur(m + 1, 0);
    for (int j = 0; j <= m; ++j) prev[j] = j;       // the i = 0 row
    // >>> HOLE id=rolling-rows prompt=Walk one row at a time, filling `cur` from `prev` with the same three moves and then making `cur` the new `prev`, so only two rows are ever held
    for (int i = 1; i <= n; ++i) {
        cur[0] = i;                                  // turning i characters into nothing
        for (int j = 1; j <= m; ++j) {
            int cost = (a[i - 1] == b[j - 1]) ? 0 : 1;
            cur[j] = min({prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost});
        }
        swap(prev, cur);
    }
    // <<< HOLE
    return prev[m];                                  // after the final swap
}

// ---------------------------------------------------------------------------
// Demo harness.
//   a b   -> edit distance from the full table, then the rolling version
//   c d   -> longest common subsequence length, then the deletions identity
// Strings are read as whitespace-delimited tokens.
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    string a, b;
    if (!(cin >> a >> b)) return 0;
    vector<vector<int>> table = edit_table(a, b);
    cout << table[a.size()][b.size()] << "\n";
    cout << edit_distance_rolling(a, b) << "\n";

    string c, d;
    cin >> c >> d;
    int common = lcs_length(c, d);
    cout << common << "\n";
    cout << (int)c.size() + (int)d.size() - 2 * common << "\n";

    return 0;
}
