// ===========================================================================
// THE QUEUE IS ALREADY SORTED
//
// The handbook puts the hypothesis in one sentence: "In an unweighted graph,
// the length of a path equals the number of its edges, and we can simply use
// breadth-first search to find a shortest path."
//
// EVERY edge costs one. That is what makes the queue work. Vertices leave a
// queue in non-decreasing order of distance, so the first time a vertex is
// reached is already the cheapest time, and dist[v] is written once and never
// touched again.
//
// Two consequences worth holding on to:
//
//   * dist doubles as the visited mark. Initialise it to -1 and the test
//     `dist[v] == -1` is the whole of "have I seen this". There is no second
//     array to keep in step with the first.
//   * writing dist and pushing must happen TOGETHER. Set the distance when v
//     is popped instead and each edge pushes its far endpoint, so the queue
//     holds m + 1 entries rather than n.
//
// And the boundary, which is the entire reason the next pattern exists: give
// one edge a different cost and this code still returns a path. It is simply
// no longer the cheapest one, and nothing in the output says so. On the graph
// 1-2, 2-3, 3-4 each of weight 1 plus a direct 1-4 of weight 5, this file
// reports that 4 is one edge away — and that one edge costs 5, where the route
// through 2 and 3 costs 3.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

using Graph = vector<vector<int>>;

// ---------------------------------------------------------------------------
// 1. SINGLE SOURCE — the form to memorise. -1 means unreached, and stays -1
//    for vertices in other components, which is usually what the statement
//    wants printed.
// ---------------------------------------------------------------------------
vector<int> bfs_dist(const Graph& adj, int s) {
    vector<int> dist(adj.size(), -1);
    queue<int> q;
    dist[s] = 0;
    q.push(s);
    while (!q.empty()) {
        int u = q.front();
        q.pop();
        // >>> HOLE id=first-seen-is-final prompt=Expand u: give every vertex you reach for the first time its distance and queue it, and never revisit one that already has a distance
        for (int v : adj[u]) {
            if (dist[v] == -1) {            // -1 is the visited test
                dist[v] = dist[u] + 1;      // written on PUSH, and never again
                q.push(v);
            }
        }
        // <<< HOLE
    }
    return dist;
}

// ---------------------------------------------------------------------------
// 2. MANY SOURCES AT ONCE — the cheapest trick in the region.
//
//    "Distance from the NEAREST guard / fire / exit" does not need one sweep
//    per source. Seed the queue with all of them at distance zero and the
//    single sweep answers every vertex, still in O(n + m). Running k separate
//    searches costs k times as much and computes the same thing.
//
//    Compare this loop with form 1: only the initialisation differs.
// ---------------------------------------------------------------------------
vector<int> multi_source_dist(const Graph& adj, const vector<int>& sources) {
    vector<int> dist(adj.size(), -1);
    queue<int> q;
    // >>> HOLE id=multi-source prompt=Start the sweep from every source at once, so one pass answers "distance to the nearest source" for every vertex
    for (int s : sources) {
        if (dist[s] != -1) continue;        // a repeated source is harmless
        dist[s] = 0;
        q.push(s);
    }
    // <<< HOLE
    while (!q.empty()) {
        int u = q.front();
        q.pop();
        for (int v : adj[u]) {
            if (dist[v] == -1) {
                dist[v] = dist[u] + 1;
                q.push(v);
            }
        }
    }
    return dist;
}

// ---------------------------------------------------------------------------
// 3. A GRID IS A GRAPH — vertices are cells, edges are the four steps, and
//    every step costs one by construction. That is why so many unweighted
//    shortest-path problems arrive drawn as a maze.
//
//    Neighbours are arithmetic rather than a stored list, so the adjacency
//    never has to be built: r*c cells, at most 4*r*c edges, still linear.
// ---------------------------------------------------------------------------
vector<vector<int>> grid_dist(const vector<string>& grid, int sr, int sc) {
    const int R = (int)grid.size();
    const int C = R ? (int)grid[0].size() : 0;
    const array<int, 4> dr = {1, -1, 0, 0};
    const array<int, 4> dc = {0, 0, 1, -1};

    vector<vector<int>> dist(R, vector<int>(C, -1));
    if (R == 0 || C == 0 || grid[sr][sc] == '#') return dist;

    queue<pair<int, int>> q;
    dist[sr][sc] = 0;
    q.push({sr, sc});
    while (!q.empty()) {
        auto [r, c] = q.front();
        q.pop();
        for (int k = 0; k < 4; ++k) {
            int nr = r + dr[k], nc = c + dc[k];
            if (nr < 0 || nr >= R || nc < 0 || nc >= C) continue;
            if (grid[nr][nc] == '#' || dist[nr][nc] != -1) continue;
            dist[nr][nc] = dist[r][c] + 1;
            q.push({nr, nc});
        }
    }
    return dist;
}

// ---------------------------------------------------------------------------
// 4. THE ROUTE, NOT ONLY ITS LENGTH.
//
//    "How far" and "which way" are different questions and get confused with
//    each other constantly. Record where each vertex was first reached FROM,
//    then walk the parents back from the target and reverse. Empty means the
//    target is unreachable, which is not the same as a distance of zero.
// ---------------------------------------------------------------------------
vector<int> bfs_path(const Graph& adj, int s, int t) {
    vector<int> dist(adj.size(), -1), parent(adj.size(), -1);
    queue<int> q;
    dist[s] = 0;
    q.push(s);
    while (!q.empty()) {
        int u = q.front();
        q.pop();
        for (int v : adj[u]) {
            if (dist[v] == -1) {
                dist[v] = dist[u] + 1;
                parent[v] = u;
                q.push(v);
            }
        }
    }
    vector<int> path;
    if (dist[t] == -1) return path;
    // >>> HOLE id=rebuild-path prompt=Turn the parent array into the route from s to t, in that order
    for (int at = t; at != -1; at = parent[at]) path.push_back(at);
    reverse(path.begin(), path.end());
    // <<< HOLE
    return path;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n m           vertices 1..n, then m undirected edges "u v"
//   s t           source, and a target for the path
//   k             then k source vertices for the multi-source sweep
//   R C           then R rows of a grid, '#' impassable
// Prints: the distances from s, the multi-source distances, the path s -> t,
// and the grid distances from the top-left cell.
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
        adj[v].push_back(u);
    }

    int s = 1, t = n;
    if (!(cin >> s >> t)) return 0;
    if (s < 1 || s > n) s = 1;
    if (t < 1 || t > n) t = n;

    vector<int> dist = bfs_dist(adj, s);
    for (int u = 1; u <= n; ++u) cout << dist[u] << ' ';
    cout << "\n";

    int k = 0;
    if (!(cin >> k)) return 0;
    vector<int> sources;
    for (int i = 0; i < k; ++i) {
        int x;
        if (!(cin >> x)) return 0;
        if (x >= 1 && x <= n) sources.push_back(x);
    }
    vector<int> near = multi_source_dist(adj, sources);
    for (int u = 1; u <= n; ++u) cout << near[u] << ' ';
    cout << "\n";

    vector<int> path = bfs_path(adj, s, t);
    if (path.empty()) {
        cout << "none\n";
    } else {
        for (int u : path) cout << u << ' ';
        cout << "\n";
    }

    int R = 0, C = 0;
    if (!(cin >> R >> C) || R <= 0 || C <= 0) return 0;
    vector<string> grid(R);
    for (string& row : grid) {
        if (!(cin >> row)) return 0;
    }
    vector<vector<int>> gd = grid_dist(grid, 0, 0);
    for (const vector<int>& row : gd) {
        for (int x : row) cout << x << ' ';
        cout << "\n";
    }
    return 0;
}
