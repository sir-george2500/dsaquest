// ===========================================================================
// CLIMB IN POWERS OF TWO
//
// Walking k steps up a tree costs k, and k can be n. Precompute where each
// vertex lands after 1, 2, 4, 8, ... steps and every climb becomes at most
// log n jumps, because every k is a sum of distinct powers of two — the same
// fact the bits master taught, used on a tree instead of on a number.
//
//     up[0][v] = parent of v
//     up[k][v] = up[k-1][ up[k-1][v] ]        half the jump, twice
//
// Two conventions decided once, here, and never revisited:
//
//   * the ROOT IS ITS OWN PARENT. Then an overlong jump saturates at the root
//     instead of reading index 0, and not one query in this file needs a guard.
//   * depth of the root is 0. Any offset works — the distance formula cancels
//     it — but mixing two of them inside one program does not.
//
// The table costs n log n. At n = 2*10^5 that is 18 levels, because 2^18 =
// 262144 is past the deepest possible climb of 199999: about 14 MB of int.
// Sizing it at 20 "to be safe" costs a third more memory for nothing.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

vector<vector<int>> g;
vector<vector<int>> up;                      // up[k][v]
vector<int> depth_;
int LOG = 1;

// ---------------------------------------------------------------------------
// 1. THE BUILD.
//
//    Breadth-first, so a chain of 2*10^5 vertices is a queue rather than a
//    stack overflow. The sweep fills up[0] and depth_ together, because the
//    parent and the depth are learned at the same instant.
//
//    Then the table. The LEVEL loop must be the OUTER one: up[k][v] reads
//    up[k-1] at a vertex that may be anywhere in the tree, so every entry of
//    level k-1 must already exist. Nest them the other way round and the
//    answers are right for shallow queries and quietly wrong for deep ones.
// ---------------------------------------------------------------------------
void build(int root, int n) {
    LOG = 1;
    while ((1 << LOG) < n) ++LOG;            // enough to jump past any depth

    up.assign(LOG + 1, vector<int>(n + 1, root));
    depth_.assign(n + 1, 0);

    vector<int> queue_;
    queue_.reserve(n);
    queue_.push_back(root);
    up[0][root] = root;                      // the root is its own parent
    vector<char> seen(n + 1, 0);
    seen[root] = 1;
    for (size_t head = 0; head < queue_.size(); ++head) {
        int v = queue_[head];
        for (int to : g[v]) {
            if (seen[to]) continue;
            seen[to] = 1;
            up[0][to] = v;
            depth_[to] = depth_[v] + 1;
            queue_.push_back(to);
        }
    }

    // >>> HOLE id=lift-table prompt=Fill every remaining level of up from the level below it, in the only order that has each entry it reads already computed
    for (int k = 1; k <= LOG; ++k) {
        for (int v = 1; v <= n; ++v) {
            up[k][v] = up[k - 1][up[k - 1][v]];
        }
    }
    // <<< HOLE
}

// ---------------------------------------------------------------------------
// 2. THE K-TH ANCESTOR.
//
//    Nothing but a loop over the set bits of k. k = 5 is 101 in binary, so it
//    is one jump of 4 and one jump of 1 — two table reads, not five steps.
//    On a chain 1-2-...-9 the 5th ancestor of 9 is 4, reached as 9 -> 8 by the
//    jump of 1 and 8 -> 4 by the jump of 4.
//
//    Because the root is its own parent, asking for an ancestor further up
//    than the root returns the root rather than reading out of bounds. If a
//    statement needs "there is no such ancestor" reported instead, compare k
//    against depth_[v] BEFORE the loop; do not try to detect it inside.
// ---------------------------------------------------------------------------
int kth_ancestor(int v, int k) {
    // >>> HOLE id=kth-ancestor prompt=Climb exactly k levels above v using the table, in a number of steps proportional to the bits of k rather than to k itself
    for (int b = 0; b <= LOG; ++b) {
        if (k >> b & 1) v = up[b][v];
    }
    return v;
    // <<< HOLE
}

// ---------------------------------------------------------------------------
// 3. THE MEETING POINT, AND THE DISTANCE.
//
//    Two phases, and they must happen in this order:
//
//      (a) LEVEL them. Lift the deeper vertex by the difference in depths.
//          Everything after this assumes the two sit at the same depth, so
//          skipping it makes the second phase mean nothing.
//
//      (b) If they are now the SAME vertex, one was an ancestor of the other
//          and that vertex is the answer. Return before the descending loop —
//          this is the case people forget, and it costs an even number of
//          steps on exactly those pairs.
//
//      (c) Otherwise descend the powers from the largest, jumping only while
//          the two land on DIFFERENT vertices. Jumping when they agree
//          overshoots to a common ancestor that is too high, usually the root.
//          After the loop both sit exactly one step below the answer.
//
//    Then the distance is pure arithmetic: the route from u to w goes up to
//    the meeting point and down again, and the shared part above it is counted
//    twice, so subtract it twice.
// ---------------------------------------------------------------------------
int meet(int u, int w) {
    if (depth_[u] < depth_[w]) swap(u, w);
    u = kth_ancestor(u, depth_[u] - depth_[w]);
    if (u == w) return u;
    // >>> HOLE id=descend prompt=With u and w now at the same depth and known to differ, lift both to the two vertices sitting immediately below their deepest shared ancestor, then return that ancestor
    for (int b = LOG; b >= 0; --b) {
        if (up[b][u] != up[b][w]) {
            u = up[b][u];
            w = up[b][w];
        }
    }
    return up[0][u];
    // <<< HOLE
}

int distance_between(int u, int w) {
    return depth_[u] + depth_[w] - 2 * depth_[meet(u, w)];
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n              then n-1 lines "u v"
//   q              then q lines "u w k"
//   -> one line per query: the deepest shared ancestor of u and w, the
//      distance between them, and the k-th ancestor of u.
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

    build(1, n);

    int q;
    if (!(cin >> q)) return 0;
    for (int i = 0; i < q; ++i) {
        int u, w, k;
        if (!(cin >> u >> w >> k)) return 0;
        cout << meet(u, w) << " " << distance_between(u, w) << " "
             << kth_ancestor(u, k) << "\n";
    }

    return 0;
}
