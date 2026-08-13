// ===========================================================================
// ONE PASS DOWN, EVERY ANSWER UP
//
// n vertices, n-1 edges, all connected. That sentence is a tree, and it is
// almost never the word the statement uses. What it gives you:
//
//   * no cycles, so there is exactly one route between any two vertices;
//   * removing any edge splits the whole thing into exactly two pieces;
//   * you may declare ANY vertex the root, and nothing in the input changes.
//
// Once a root is fixed, "everything below v" is a set, the recursion on v
// returns having filled in exactly that set, and every per-vertex question is
// one fold of the children into the parent.
//
// Three rules that outlive every problem in this file:
//   * on a tree the parent replaces the visited set — one argument, not an array;
//   * the combining line goes AFTER the recursive call, never before it;
//   * anything that multiplies two subtree sizes together is a long long.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. THE SIZE FOLD — recursive, and the version you should be able to type
//    without thinking.
//
//    sz[v] = 1 + sum of sz[child]. The `if (to == parent) continue;` is doing
//    the whole job of a visited array: a tree has no cycles, so the only way
//    to re-enter a vertex is straight back along the edge you arrived on.
//    Drop that line and the walk is v -> child -> v -> child until the stack
//    dies, on any input with at least one edge.
//
//    Note where `sz[v] += sz[to]` sits. Above the recursive call it reads the
//    initialiser and every answer comes back as 1 + (number of children).
// ---------------------------------------------------------------------------
vector<vector<int>> g;
vector<int> sz;

void dfs_size(int v, int parent) {
    sz[v] = 1;
    // >>> HOLE id=size-fold prompt=Visit every neighbour of v except the one you arrived from, and fold each child's subtree size into sz[v]
    for (int to : g[v]) {
        if (to == parent) continue;
        dfs_size(to, v);
        sz[v] += sz[to];
    }
    // <<< HOLE
}

// ---------------------------------------------------------------------------
// 2. THE SAME FOLD, ITERATIVELY — what you reach for when the input might be
//    a chain of 2*10^5 vertices.
//
//    A stack frame for the function above costs about 80 bytes under g++ -O2,
//    so an 8 MB stack runs out somewhere near 100000 nested calls and reports
//    nothing but a runtime error on the one test that happens to be a path.
//
//    The fix is not cleverness, it is order. A breadth-first sweep produces a
//    list in which every parent appears before its children; walking that list
//    BACKWARDS visits every child before its parent, which is exactly the
//    guarantee post-order recursion was buying you.
// ---------------------------------------------------------------------------
vector<int> par;
vector<int> order_;

void build_order(int root, int n) {
    par.assign(n + 1, 0);
    order_.clear();
    order_.reserve(n);
    vector<int> queue_(1, root);
    par[root] = root;                        // the root is its own parent
    for (size_t head = 0; head < queue_.size(); ++head) {
        int v = queue_[head];
        order_.push_back(v);
        for (int to : g[v]) {
            if (to == par[v]) continue;
            par[to] = v;
            queue_.push_back(to);
        }
    }
}

vector<long long> subtree_sum(const vector<long long>& value, int root, int n) {
    build_order(root, n);
    vector<long long> total(n + 1, 0);
    for (int v = 1; v <= n; ++v) total[v] = value[v];
    // >>> HOLE id=reverse-order prompt=Walk order_ so that every vertex is finished before its parent is read, adding each vertex's total into its parent's
    for (size_t i = order_.size(); i-- > 0;) {
        int v = order_[i];
        if (v != root) total[par[v]] += total[v];
    }
    // <<< HOLE
    return total;
}

// ---------------------------------------------------------------------------
// 3. THE EDGE SPLIT — the single most reused line in this whole region.
//
//    Every edge in a rooted tree is "the edge above" exactly one non-root
//    vertex c. Cut it and the tree falls into two pieces: c's subtree, of size
//    sz[c], and everything else, of size n - sz[c]. Two numbers per edge, and
//    one post-order pass hands you all of them.
//
//    What it counts: a pair of vertices (u, w) is separated by that edge
//    exactly when one of them is inside c's subtree and the other is not, so
//    the edge is used by sz[c] * (n - sz[c]) of the routes. Sum that over
//    every edge and you have the total of ALL pairwise distances, without ever
//    computing a single distance.
//
//    The product peaks at n^2/4 — 10^10 at n = 2*10^5 — so it is a long long
//    or it is a wrong answer on the large tests only.
// ---------------------------------------------------------------------------
long long total_pairwise_distance(int n) {
    long long total = 0;
    // >>> HOLE id=edge-split prompt=Add up, over every edge of the tree, the number of vertex pairs whose route uses that edge
    for (int v = 2; v <= n; ++v) {
        total += (long long)sz[v] * (long long)(n - sz[v]);
    }
    // <<< HOLE
    return total;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n              then n-1 lines "u v"      then n values
//   -> line 1: the subtree size of every vertex
//   -> line 2: the total of the distances between all pairs
//   -> line 3: the subtree value total of every vertex
//
// Vertices are numbered 1..n. Rooted at 1, arbitrarily, because on a tree
// that costs nothing.
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

    vector<long long> value(n + 1, 0);
    for (int v = 1; v <= n; ++v) {
        if (!(cin >> value[v])) return 0;
    }

    sz.assign(n + 1, 0);
    dfs_size(1, 0);

    for (int v = 1; v <= n; ++v) cout << sz[v] << " \n"[v == n];
    cout << total_pairwise_distance(n) << "\n";

    vector<long long> total = subtree_sum(value, 1, n);
    for (int v = 1; v <= n; ++v) cout << total[v] << " \n"[v == n];

    return 0;
}
