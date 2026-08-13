// ===========================================================================
// NOTHING BEFORE WHAT IT NEEDS
//
// A one-way edge a -> b is a promise: a comes first. An ordering that keeps
// every such promise is a topological order, and the handbook is blunt about
// when one exists: an acyclic graph always has one, and a graph with a cycle
// never does, because no vertex of the cycle can precede the others.
//
// So the algorithm and the impossibility proof are the same computation. Kahn's
// sweep emits vertices whose in-degree has fallen to zero; if it emits fewer
// than n of them, everything it could not emit is holding a cycle. One
// comparison, and you have both answers.
//
// The order is not unique, and that is normal — the handbook's example graph
// admits several. A judge that accepts "any valid order" is telling you so.
//
// The payoff is form 3. On a directed acyclic graph every state depends only on
// states earlier in the order, so a single pass computes longest paths, path
// counts, reachability counts — anything of the shape
//
//     f(x) = combine over all a with an edge a -> x of f(a)
//
// which is dynamic programming with the recursion order handed to you.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

using Digraph = vector<vector<int>>;

// ---------------------------------------------------------------------------
// 1. KAHN'S SWEEP — the form to memorise, because the cycle test is free.
//
//    Returns an order containing every vertex, or a SHORT list when the graph
//    has a cycle. The caller compares its length with n; there is nothing else
//    to check and no extra state to carry.
//
//    Note the queue never recurses, which is the other reason to prefer it:
//    10^5 dependencies in a chain would overflow the stack in form 2.
// ---------------------------------------------------------------------------
vector<int> kahn(int n, const Digraph& adj) {
    vector<int> indeg(n + 1, 0);
    for (int u = 1; u <= n; ++u)
        for (int v : adj[u]) ++indeg[v];

    queue<int> q;
    for (int u = 1; u <= n; ++u)
        if (indeg[u] == 0) q.push(u);

    vector<int> order;
    order.reserve((size_t)n);
    while (!q.empty()) {
        int u = q.front();
        q.pop();
        order.push_back(u);
        // >>> HOLE id=indegree-zero prompt=Emitting u satisfies one requirement of each vertex it points at; update them and queue any that now have nothing left waiting on
        for (int v : adj[u]) {
            if (--indeg[v] == 0) q.push(v);
        }
        // <<< HOLE
    }
    return order;                          // shorter than n means a cycle
}

// ---------------------------------------------------------------------------
// 2. THE THREE-STATE WALK — the handbook's version, shown so you recognise it.
//
//    0 = untouched, 1 = on the current path, 2 = finished. Reaching a vertex in
//    state 1 means you have walked back onto your own path, which is a cycle.
//    Reaching one in state 2 is fine: it is finished, and finished vertices are
//    already placed.
//
//    Appending each vertex as it FINISHES gives the reverse of a topological
//    order, so the list is reversed at the end. Getting that reversal wrong is
//    the classic bug here, and it is invisible on symmetric tests.
//
//    It recurses, so it is the wrong choice at 10^5 vertices. Form 1 is not.
// ---------------------------------------------------------------------------
static bool visit(int u, const Digraph& adj, vector<int>& state, vector<int>& out) {
    state[u] = 1;
    // >>> HOLE id=grey-means-cycle prompt=Walk into every successor of u, reporting failure if one of them is already on the current path
    for (int v : adj[u]) {
        if (state[v] == 1) return false;   // back onto the current path: a cycle
        if (state[v] == 0 && !visit(v, adj, state, out)) return false;
    }
    // <<< HOLE
    state[u] = 2;
    out.push_back(u);                      // finished, so it belongs last
    return true;
}

bool dfs_topological(int n, const Digraph& adj, vector<int>& order) {
    vector<int> state(n + 1, 0);
    order.clear();
    for (int u = 1; u <= n; ++u)
        if (state[u] == 0 && !visit(u, adj, state, order)) return false;
    reverse(order.begin(), order.end());   // finishing order, reversed
    return true;
}

// ---------------------------------------------------------------------------
// 3. THE PAYOFF — dynamic programming laid over the order.
//
//    Counting the routes from `src` to every vertex. The handbook's example
//    graph, 1->2, 1->4, 4->5, 5->2, 5->3, 2->3, 3->6, has a topological order
//    1, 4, 5, 2, 3, 6 and gives three routes from 1 to 6:
//
//        1->2->3->6      1->4->5->2->3->6      1->4->5->3->6
//
//    Every vertex is finished before anything it points at is touched, so the
//    push `ways[v] += ways[u]` can never read a value that is still growing.
//    Run the same loop in input order instead and the results are simply too
//    small, and change when the edges are shuffled.
//
//    long long, not int: the count doubles at each branch, so forty layers is
//    already past INT_MAX.
// ---------------------------------------------------------------------------
vector<long long> count_paths(int n, const Digraph& adj, const vector<int>& order, int src) {
    vector<long long> ways(n + 1, 0);
    ways[src] = 1;
    // >>> HOLE id=dag-dp prompt=Push each vertex's route count along its outgoing edges, walking the vertices in the one order that guarantees a count is final before it is read
    for (int u : order) {
        if (ways[u] == 0) continue;
        for (int v : adj[u]) ways[v] += ways[u];
    }
    // <<< HOLE
    return ways;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n m           vertices 1..n, then m DIRECTED edges "u v" meaning u before v
// Prints: Kahn's order or "IMPOSSIBLE"; then 1 or 0 for whether the recursive
// walk agrees that the graph is acyclic; then the number of routes from 1 to
// each vertex, or nothing when the graph is cyclic.
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n, m;
    if (!(cin >> n >> m)) return 0;
    if (n <= 0) return 0;

    Digraph adj(n + 1);
    for (int i = 0; i < m; ++i) {
        int u, v;
        if (!(cin >> u >> v)) return 0;
        adj[u].push_back(v);               // ONE direction: a promise, not a link
    }

    vector<int> order = kahn(n, adj);
    const bool acyclic = (int)order.size() == n;
    if (acyclic) {
        for (int u : order) cout << u << ' ';
        cout << "\n";
    } else {
        cout << "IMPOSSIBLE\n";
    }

    vector<int> other;
    cout << (dfs_topological(n, adj, other) ? 1 : 0) << "\n";

    if (acyclic) {
        vector<long long> ways = count_paths(n, adj, order, 1);
        for (int u = 1; u <= n; ++u) cout << ways[u] << ' ';
        cout << "\n";
    }
    return 0;
}
