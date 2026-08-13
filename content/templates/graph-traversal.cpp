// ===========================================================================
// VISIT EVERY VERTEX ONCE
//
// Every traversal in this region is the same two pieces of state:
//
//     a container of vertices waiting to be expanded   (the frontier)
//     an array saying which vertices have been claimed (the mark)
//
// Swap the container and the algorithm changes name. Take the next vertex from
// the FRONT and it is breadth-first; take it from the BACK and it is
// depth-first. Nothing else differs, which is why they cost the same: O(n + m),
// because each vertex is expanded once and each edge is examined from each of
// its two endpoints.
//
// THE ONE RULE: mark a vertex when you PUSH it, never when you pop it.
//
// Marking on pop still produces the right answer, and it is still a bug. Each
// edge then pushes its far endpoint, so the frontier takes exactly m + 1
// entries instead of n. On the graph 1-2, 1-3, 1-4, 2-5, 3-5, 4-5 that is
// seven pushes for five vertices, and vertex 5 enters the queue three times.
// On the complete graph of ten vertices it is 46 pushes rather than 10. Ship
// that on a dense graph and the verdict is a memory limit, on code whose
// output was correct all along.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

using Graph = vector<vector<int>>;

// ---------------------------------------------------------------------------
// 1. BREADTH-FIRST — the frontier is a queue, so vertices come back in
//    non-decreasing order of distance from the source.
//
//    Read this loop beside form 2 until the only difference you can see is the
//    line that takes the next vertex.
// ---------------------------------------------------------------------------
vector<int> bfs_order(const Graph& adj, int s) {
    vector<char> seen(adj.size(), 0);
    vector<int> order;
    queue<int> q;
    seen[s] = 1;
    q.push(s);
    while (!q.empty()) {
        int u = q.front();
        q.pop();
        order.push_back(u);
        // >>> HOLE id=mark-on-push prompt=Expand u: claim every unseen neighbour and put it on the queue, in the order that keeps each vertex out of the queue more than once
        for (int v : adj[u]) {
            if (!seen[v]) {
                seen[v] = 1;                // claimed on PUSH, not on pop
                q.push(v);
            }
        }
        // <<< HOLE
    }
    return order;
}

// ---------------------------------------------------------------------------
// 2. DEPTH-FIRST — the same loop with a stack. Written iteratively on purpose:
//    a recursive version costs one stack frame per vertex, and a graph that is
//    one long path of 10^6 vertices overflows the usual 8 MB long before the
//    algorithm is at fault.
//
//    Note the mark is still taken on push, so a vertex is never stacked twice.
// ---------------------------------------------------------------------------
vector<int> dfs_order(const Graph& adj, int s) {
    vector<char> seen(adj.size(), 0);
    vector<int> order, stack_;
    seen[s] = 1;
    stack_.push_back(s);
    while (!stack_.empty()) {
        int u = stack_.back();
        stack_.pop_back();
        order.push_back(u);
        for (int v : adj[u]) {
            if (!seen[v]) {
                seen[v] = 1;
                stack_.push_back(v);
            }
        }
    }
    return order;
}

// ---------------------------------------------------------------------------
// 3. CONNECTED COMPONENTS — start a traversal at every vertex not yet claimed.
//    The number of times you had to start IS the answer, and the component id
//    of every vertex falls out of the same sweep for free.
//
//    Vertices are 1..n here; index 0 is left unused so the input needs no
//    arithmetic. Sizing the vectors n + 1 is cheaper than remembering to
//    subtract one in eleven places.
// ---------------------------------------------------------------------------
int count_components(int n, const Graph& adj, vector<int>& component) {
    component.assign(n + 1, 0);
    int found = 0;
    for (int s = 1; s <= n; ++s) {
        if (component[s] != 0) continue;
        ++found;
        // >>> HOLE id=components prompt=Claim the whole component containing s, writing `found` into component[] for every vertex reached
        component[s] = found;
        queue<int> q;
        q.push(s);
        while (!q.empty()) {
            int u = q.front();
            q.pop();
            for (int v : adj[u]) {
                if (component[v] == 0) {
                    component[v] = found;   // the id doubles as the visited mark
                    q.push(v);
                }
            }
        }
        // <<< HOLE
    }
    return found;
}

// ---------------------------------------------------------------------------
// 4. TWO-COLOURING — the same walk answering a different question. Colour the
//    source, colour every neighbour the opposite, and keep going.
//
//    The interesting half is the FAILURE. An edge joining two vertices that
//    already carry the same colour is an odd cycle, and an odd cycle is a proof
//    that no two-colouring exists — not merely that this attempt did not find
//    one. On the handbook's graph 1-2, 1-4, 2-3, 2-5, 3-5, 4-5 the triangle
//    2-3-5 is exactly that proof.
//
//    Colours: 0 = unclaimed, 1 and 2 = the two sides. Unclaimed doubles as the
//    visited mark, so there is no second array to keep in step.
// ---------------------------------------------------------------------------
bool is_bipartite(int n, const Graph& adj, vector<int>& colour) {
    colour.assign(n + 1, 0);
    for (int s = 1; s <= n; ++s) {
        if (colour[s] != 0) continue;      // every component must be checked
        colour[s] = 1;
        queue<int> q;
        q.push(s);
        while (!q.empty()) {
            int u = q.front();
            q.pop();
            // >>> HOLE id=two-colour prompt=Give every unclaimed neighbour of u the opposite colour, and report failure the moment a neighbour already carries u's own colour
            for (int v : adj[u]) {
                if (colour[v] == 0) {
                    colour[v] = 3 - colour[u];
                    q.push(v);
                } else if (colour[v] == colour[u]) {
                    return false;           // an odd cycle: no colouring exists
                }
            }
            // <<< HOLE
        }
    }
    return true;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n m            vertices 1..n, then m undirected edges "u v"
//   s              the source for forms 1 and 2
// Prints: the BFS order, the DFS order, the component count, and 1 or 0 for
// whether the whole graph is bipartite.
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n, m;
    if (!(cin >> n >> m)) return 0;
    if (n <= 0) return 0;

    Graph adj(n + 1);
    for (int i = 0; i < m; ++i) {
        int u, v;
        if (!(cin >> u >> v)) return 0;
        adj[u].push_back(v);
        adj[v].push_back(u);            // undirected: BOTH directions, always
    }

    int s = 1;
    cin >> s;
    if (s < 1 || s > n) s = 1;

    for (int u : bfs_order(adj, s)) cout << u << ' ';
    cout << "\n";
    for (int u : dfs_order(adj, s)) cout << u << ' ';
    cout << "\n";

    vector<int> component;
    cout << count_components(n, adj, component) << "\n";

    vector<int> colour;
    cout << (is_bipartite(n, adj, colour) ? 1 : 0) << "\n";
    return 0;
}
