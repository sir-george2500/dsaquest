// ===========================================================================
// THE CHEAPEST FRONTIER FIRST
//
// The moment the edges stop costing the same, the queue stops being sorted and
// breadth-first search stops answering the question. It still returns a path.
// It is simply not the cheapest one, and the output does not say so.
//
// The replacement is one sentence: repeatedly take the unfinished vertex with
// the SMALLEST tentative distance, and that distance is already final. The
// handbook calls this the remarkable property of the algorithm. It is a claim,
// and it has a hypothesis:
//
//     NO EDGE MAY HAVE A NEGATIVE WEIGHT.
//
// Because if none does, any other route to the vertex you are about to settle
// must still leave the settled region through some frontier vertex, and every
// frontier vertex already costs at least as much — so it cannot come out
// cheaper. Allow a negative edge and that step collapses. On the handbook's
// four-vertex example (1-2 costing 2, 2-4 costing 3, 1-3 costing 6, 3-4 costing
// -5) this file settles vertex 2 first and reports 5 for vertex 4, while the
// route through 3 costs 6 - 5 = 1.
//
// So the region has three tools and you must be able to say which:
//
//     all weights equal        breadth-first search        O(n + m)
//     weights >= 0             this file, form 1           O(n + m log m)
//     weights may be negative  Bellman-Ford, form 2        O(n m)
//     all pairs, small n       Floyd-Warshall, form 3      O(n^3)
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

//: Large enough to mean "unreached", small enough that INF + w cannot overflow.
//  LLONG_MAX would overflow the moment it meets a relaxation, which is a real
//  and common bug: the sum turns negative and unreachable looks cheapest.
static const long long INF = (long long)4e18;

struct Edge {
    int to;
    long long w;
};
using WGraph = vector<vector<Edge>>;

// ---------------------------------------------------------------------------
// 1. THE HEAP SWEEP — lazy deletion, which is the version to memorise.
//
//    std::priority_queue is a MAX-heap, so greater<> turns it round. (The
//    handbook instead pushes negated distances; same thing, fewer characters,
//    more chances to forget a minus sign.)
//
//    A vertex may sit in the heap several times, once per improvement. Only
//    the smallest copy matters, and the one line `if (d > dist[u]) continue;`
//    throws the rest away. Delete that line and every stale copy is expanded in
//    full: still correct, and quadratic on a dense graph.
// ---------------------------------------------------------------------------
vector<long long> dijkstra(const WGraph& adj, int s) {
    vector<long long> dist(adj.size(), INF);
    priority_queue<pair<long long, int>, vector<pair<long long, int>>,
                   greater<pair<long long, int>>> pq;
    dist[s] = 0;
    pq.push({0, s});
    while (!pq.empty()) {
        auto [d, u] = pq.top();
        pq.pop();
        // >>> HOLE id=settle-and-relax prompt=Throw away a stale copy of u, then relax every edge out of u, pushing each neighbour whose best known total improves
        if (d > dist[u]) continue;          // a stale copy; the good one won
        for (const Edge& e : adj[u]) {
            if (d + e.w < dist[e.to]) {
                dist[e.to] = d + e.w;
                pq.push({dist[e.to], e.to});
            }
        }
        // <<< HOLE
    }
    return dist;
}

// ---------------------------------------------------------------------------
// 2. BELLMAN-FORD — no order at all, which is exactly why negatives survive it.
//
//    n - 1 rounds, each relaxing every edge. A shortest path has at most n - 1
//    edges, and round i fixes every path of i edges, so after n - 1 rounds
//    nothing is left to fix. Stopping early when a round changes nothing is
//    free and is usually most of the running time.
//
//    Then the trick that costs one more round: if an n-th round can STILL
//    reduce something, no shortest path exists at all, because a cycle of
//    negative total length can be walked again for less. Returns false in that
//    case.
// ---------------------------------------------------------------------------
struct Arc {
    int from;
    int to;
    long long w;
};

bool bellman_ford(int n, const vector<Arc>& arcs, int s, vector<long long>& dist) {
    dist.assign(n + 1, INF);
    dist[s] = 0;
    // >>> HOLE id=rounds prompt=Run the n-1 relaxation rounds over every arc, stopping as soon as a whole round changes nothing
    for (int round = 1; round <= n - 1; ++round) {
        bool changed = false;
        for (const Arc& a : arcs) {
            if (dist[a.from] == INF) continue;      // never relax from unreached
            if (dist[a.from] + a.w < dist[a.to]) {
                dist[a.to] = dist[a.from] + a.w;
                changed = true;
            }
        }
        if (!changed) break;
    }
    // <<< HOLE
    for (const Arc& a : arcs) {                     // the extra round: a proof
        if (dist[a.from] == INF) continue;
        if (dist[a.from] + a.w < dist[a.to]) return false;
    }
    return true;
}

// ---------------------------------------------------------------------------
// 3. FLOYD-WARSHALL — every pair, in three lines, in O(n^3).
//
//    Round k allows vertex k as an intermediate stop. The loop order k, i, j is
//    not a style choice: k must be the OUTER loop, because the meaning of
//    d[i][j] during round k is "shortest using only 1..k in the middle". Put k
//    innermost and the code still compiles, still runs, and is wrong.
//
//    Usable only while n is in the hundreds. It tolerates negative edges; a
//    negative d[i][i] afterwards means a negative cycle through i.
// ---------------------------------------------------------------------------
vector<vector<long long>> floyd_warshall(int n, const vector<Arc>& arcs) {
    vector<vector<long long>> d(n + 1, vector<long long>(n + 1, INF));
    for (int i = 1; i <= n; ++i) d[i][i] = 0;
    for (const Arc& a : arcs) d[a.from][a.to] = min(d[a.from][a.to], a.w);

    // >>> HOLE id=all-pairs prompt=Fill the table so d[i][j] ends as the cheapest route from i to j, with the three loops in the only order that is correct
    for (int k = 1; k <= n; ++k) {
        for (int i = 1; i <= n; ++i) {
            if (d[i][k] == INF) continue;
            for (int j = 1; j <= n; ++j) {
                if (d[k][j] == INF) continue;
                d[i][j] = min(d[i][j], d[i][k] + d[k][j]);
            }
        }
    }
    // <<< HOLE
    return d;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n m           vertices 1..n, then m DIRECTED arcs "u v w"
//   s             the source
// Prints: the heap sweep's distances from s, then Bellman-Ford's (or
// "NEGATIVE CYCLE"), then row s of the all-pairs table. Unreached prints as -1.
// ---------------------------------------------------------------------------
static void print_row(const vector<long long>& d, int n) {
    for (int i = 1; i <= n; ++i) cout << (d[i] >= INF ? -1 : d[i]) << ' ';
    cout << "\n";
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n, m;
    if (!(cin >> n >> m)) return 0;
    if (n <= 0) return 0;

    WGraph adj(n + 1);
    vector<Arc> arcs;
    arcs.reserve((size_t)max(m, 0));
    for (int i = 0; i < m; ++i) {
        int u, v;
        long long w;
        if (!(cin >> u >> v >> w)) return 0;
        adj[u].push_back({v, w});
        arcs.push_back({u, v, w});
    }

    int s = 1;
    cin >> s;
    if (s < 1 || s > n) s = 1;

    print_row(dijkstra(adj, s), n);

    vector<long long> bf;
    if (bellman_ford(n, arcs, s, bf)) {
        print_row(bf, n);
    } else {
        cout << "NEGATIVE CYCLE\n";
    }

    vector<vector<long long>> all = floyd_warshall(n, arcs);
    print_row(all[s], n);
    return 0;
}
