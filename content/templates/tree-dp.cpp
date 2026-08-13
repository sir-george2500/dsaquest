// ===========================================================================
// A STATE FOR EVERY VERTEX
//
// A plain fold sends ONE number up from each child: a size, a sum, a count.
// That works right up until taking a vertex changes what its parent is allowed
// to do. Then one number is not enough, because the parent's best move depends
// on which way the child went — and the child cannot know that yet.
//
// The fix is to send up one number PER DECISION:
//
//     dp[v][0] = the best value inside v's subtree, given v is NOT taken
//     dp[v][1] = the best value inside v's subtree, given v IS taken
//
// and let the parent choose. Nothing outside v's subtree is ever consulted;
// that is what makes the recursion sound and what makes the definition worth
// writing out in words before you write it in code.
//
// The three forms below are the same traversal three times. Watch what changes
// between form 1 and form 2: max becomes plus, plus becomes times, and a
// modulus appears. Nothing else. The states are identical, because the
// CONSTRAINT is identical; only the question changed.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

const long long MOD = 1000000007LL;

vector<vector<int>> g;

// ---------------------------------------------------------------------------
// 1. TAKE OR LEAVE — maximum weight with no two chosen vertices adjacent.
//
//    The two transitions are NOT symmetric, and the asymmetry is the whole
//    secret:
//
//        take[v]  = w[v] + sum over children of skip[c]
//        skip[v]  =        sum over children of max(skip[c], take[c])
//
//    Taking v FORBIDS every child, so only skip[c] is available. Leaving v
//    forbids nothing, so each child independently does whatever is best for
//    it. Writing skip[v] as a sum of skip[c] is the commonest bug in this
//    whole region and it is quiet: the answer is merely too small.
//
//    Why not greedy? A centre worth 3 with three leaves worth 2 each. Greedy
//    takes the 3 and is blocked; the answer is 2 + 2 + 2 = 6. No ordering of
//    the vertices repairs that, which is exactly why a state exists.
// ---------------------------------------------------------------------------
vector<long long> take_, skip_;

void dfs_independent(int v, int parent, const vector<long long>& w) {
    take_[v] = w[v];
    skip_[v] = 0;
    for (int to : g[v]) {
        if (to == parent) continue;
        dfs_independent(to, v, w);
        // >>> HOLE id=take-or-leave prompt=Fold the finished child `to` into v's two states, remembering that taking v forbids taking `to` while leaving v forbids nothing
        take_[v] += skip_[to];
        skip_[v] += max(skip_[to], take_[to]);
        // <<< HOLE
    }
}

// ---------------------------------------------------------------------------
// 2. THE SAME RECURSION, COUNTING.
//
//    ways0[v] = number of legal arrangements inside v's subtree with v unused
//    ways1[v] = number of them with v used
//
//    The children are independent of one another once v's own state is fixed,
//    so the counts MULTIPLY where the optimising version added, and the
//    "either way" of max becomes the "either way" of ways0 + ways1.
//
//    Reduce after every multiplication. The product doubles roughly once per
//    independent choice, so a modulus applied only at the end is wrong from
//    about the fortieth vertex — long before any sample reaches it.
// ---------------------------------------------------------------------------
vector<long long> ways0, ways1;

void dfs_count(int v, int parent) {
    ways0[v] = 1;
    ways1[v] = 1;
    for (int to : g[v]) {
        if (to == parent) continue;
        dfs_count(to, v);
        // >>> HOLE id=count-fold prompt=Fold the finished child into v's two counts, keeping every intermediate value reduced modulo MOD
        ways0[v] = ways0[v] * (ways0[to] + ways1[to]) % MOD;
        ways1[v] = ways1[v] * ways0[to] % MOD;
        // <<< HOLE
    }
}

// ---------------------------------------------------------------------------
// 3. THE OTHER SIDE OF THE SAME COIN — the fewest vertices covering every edge.
//
//    Now the constraint sits on an EDGE rather than on a vertex: for every
//    edge, at least one end must be chosen. Read it downwards from v:
//
//        cover1[v] = 1 + sum over children of min(cover0[c], cover1[c])
//        cover0[v] =     sum over children of cover1[c]
//
//    If v is not chosen then every edge down to a child must be covered by the
//    child, so cover1[c] is forced. If v is chosen those edges are already
//    covered and each child is free again.
//
//    On a tree this always comes out as n minus the answer to form 1 with all
//    weights 1 — the complement of a largest independent set is a smallest
//    vertex cover. Use that as a self-check when you are unsure of a sign.
// ---------------------------------------------------------------------------
vector<int> cover0, cover1;

void dfs_cover(int v, int parent) {
    cover0[v] = 0;
    cover1[v] = 1;
    for (int to : g[v]) {
        if (to == parent) continue;
        dfs_cover(to, v);
        cover0[v] += cover1[to];
        cover1[v] += min(cover0[to], cover1[to]);
    }
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n              then n-1 lines "u v"      then n weights
//   -> line 1: the largest total weight with no two chosen vertices adjacent
//   -> line 2: how many legal choices there are at all, modulo 1e9+7
//   -> line 3: the fewest vertices touching every edge
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    if (!(cin >> n) || n < 1) return 0;

    g.assign(n + 1, {});
    for (int i = 0; i + 1 < n; ++i) {
        int u, v;
        if (!(cin >> u >> v)) return 0;
        g[u].push_back(v);
        g[v].push_back(u);
    }

    vector<long long> w(n + 1, 0);
    for (int v = 1; v <= n; ++v) {
        if (!(cin >> w[v])) return 0;
    }

    take_.assign(n + 1, 0);
    skip_.assign(n + 1, 0);
    dfs_independent(1, 0, w);
    cout << max(take_[1], skip_[1]) << "\n";

    ways0.assign(n + 1, 0);
    ways1.assign(n + 1, 0);
    dfs_count(1, 0);
    cout << (ways0[1] + ways1[1]) % MOD << "\n";

    cover0.assign(n + 1, 0);
    cover1.assign(n + 1, 0);
    dfs_cover(1, 0);
    cout << min(cover0[1], cover1[1]) << "\n";

    return 0;
}
