// ===========================================================================
// THE WALK THAT BENDS ONCE
//
// The longest route in a tree. Two methods, and they are here together on
// purpose, because they fail differently and a warrior who knows only one
// cannot tell which failure he is looking at.
//
//   Method 1  Root it anywhere. Every path has a HIGHEST vertex — the one
//             closest to the root — and above that vertex the path is just
//             two downward chains glued together. So keep, per vertex, the
//             two deepest branches hanging off it and add them.
//
//   Method 2  Walk to the farthest vertex from anywhere. Walk to the farthest
//             vertex from THAT. The second distance is the answer. Four lines,
//             and it hands you the two endpoints for free.
//
// Method 2 is shorter and method 2 is the one that is wrong more often: its
// proof needs a unique route between every pair, so a cycle kills it, and it
// needs distances that cannot shrink, so a negative edge weight kills it too.
// Method 1 survives both. Learn which you are holding.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

vector<vector<int>> g;

// ---------------------------------------------------------------------------
// 1. THE TWO-BEST FOLD.
//
//    down[v] = the number of edges from v to the deepest vertex below it.
//    The candidate answer AT v is the best branch plus the second best: that
//    is the longest path whose highest vertex is v.
//
//    Two things people get wrong here, both of them silent:
//
//      * taking only the deepest branch. Then the answer is the HEIGHT of the
//        tree, which is right on a chain and about half the truth otherwise.
//      * looking only at the root. On 1-2, 2-3, 2-4, 3-5, 4-6 rooted at 1 the
//        root has one child, so the root sees 3 where the answer is 4 — the
//        path 5-3-2-4-6 bends at vertex 2 and never touches the root.
//
//    So: best and SECOND best, and maximise over EVERY vertex.
// ---------------------------------------------------------------------------
int best_fold;

int dfs_down(int v, int parent) {
    int first = 0, second = 0;               // the two deepest branches at v
    for (int to : g[v]) {
        if (to == parent) continue;
        int branch = dfs_down(to, v) + 1;
        if (branch > first) {
            second = first;
            first = branch;
        } else if (branch > second) {
            second = branch;
        }
    }
    // >>> HOLE id=two-best prompt=Record the longest path whose highest vertex is v into best_fold, then return the length of the deepest single chain hanging below v
    best_fold = max(best_fold, first + second);
    return first;
    // <<< HOLE
}

// ---------------------------------------------------------------------------
// 2. THE TWO SWEEPS.
//
//    Breadth-first rather than recursive, so a chain of 2*10^5 vertices is a
//    queue and not a stack overflow. On an unweighted tree every edge costs
//    one, so breadth-first order IS distance order.
//
//    Why the second sweep lands on a real endpoint: draw the longest path
//    horizontally with everything else hanging off it. Wherever you start,
//    your route joins that path at some vertex x, and the farthest vertex from
//    x is one of the path's two ends — nothing hanging off can be farther, or
//    it would have been part of a longer path.
// ---------------------------------------------------------------------------
vector<int> sweep(int source, int n) {
    vector<int> dist(n + 1, -1);
    vector<int> queue_;
    queue_.reserve(n);
    dist[source] = 0;
    queue_.push_back(source);
    // >>> HOLE id=bfs-sweep prompt=Fill dist with the number of edges from source to every vertex, using queue_ as a plain first-in-first-out list
    for (size_t head = 0; head < queue_.size(); ++head) {
        int v = queue_[head];
        for (int to : g[v]) {
            if (dist[to] != -1) continue;
            dist[to] = dist[v] + 1;
            queue_.push_back(to);
        }
    }
    // <<< HOLE
    return dist;
}

int farthest(const vector<int>& dist, int n) {
    int best = 1;
    for (int v = 1; v <= n; ++v) {
        if (dist[v] > dist[best]) best = v;
    }
    return best;
}

// ---------------------------------------------------------------------------
// 3. ECCENTRICITY, RADIUS AND CENTRE.
//
//    ecc[v] is the distance from v to whatever is farthest from it. On a tree
//    the farthest vertex from ANY v is always one of the two endpoints of a
//    longest path, so two distance arrays give all n eccentricities at once —
//    no third sweep, no per-vertex search.
//
//    The radius is then the smallest eccentricity, and it always comes out as
//    the length of the longest path divided by two, rounded up. That is the
//    answer to "place one depot so the worst journey is as short as possible",
//    which is what these statements are usually really asking.
// ---------------------------------------------------------------------------
vector<int> eccentricities(const vector<int>& from_a, const vector<int>& from_b, int n) {
    vector<int> ecc(n + 1, 0);
    // >>> HOLE id=eccentricity prompt=For every vertex, record how far away the farthest vertex from it is, using only the two distance arrays already computed
    for (int v = 1; v <= n; ++v) {
        ecc[v] = max(from_a[v], from_b[v]);
    }
    // <<< HOLE
    return ecc;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n              then n-1 lines "u v"
//   -> line 1: the longest path, in edges, by the fold
//   -> line 2: the same number by the two sweeps — they must agree
//   -> line 3: the radius
//   -> line 4: the eccentricity of every vertex
//
// If the statement counts VERTICES on the path rather than edges, add one.
// Decide which before you write the initialiser, not after test 3 fails.
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

    best_fold = 0;
    dfs_down(1, 0);
    cout << best_fold << "\n";

    vector<int> from_one = sweep(1, n);
    int a = farthest(from_one, n);
    vector<int> from_a = sweep(a, n);
    int b = farthest(from_a, n);
    vector<int> from_b = sweep(b, n);
    cout << from_a[b] << "\n";

    vector<int> ecc = eccentricities(from_a, from_b, n);
    int radius = ecc[1];
    for (int v = 1; v <= n; ++v) radius = min(radius, ecc[v]);
    cout << radius << "\n";

    for (int v = 1; v <= n; ++v) cout << ecc[v] << " \n"[v == n];

    return 0;
}
