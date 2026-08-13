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
// cheaper. Allow a negative edge and that step collapses. Form 1b below reports
// precisely what the claim asserts — the value a vertex holds at the moment it
// is selected — and on the handbook's four-vertex example (1->2 costing 2, 2->4
// costing 3, 1->3 costing 6, 3->4 costing -5) it hands back 5 for vertex 4,
// where the route through vertex 3 costs 6 - 5 = 1.
//
// Be precise about where the damage is. It is in the CLAIM, not in any one
// line of code: an implementation that keeps writing into dist[] after a vertex
// has been settled may well end up holding the right number anyway, and the
// handbook's own listing does exactly that on this graph. You are bitten the
// moment you BELIEVE the value at selection time — by breaking out of the loop
// when the target is popped, or by reading an answer off a vertex as it
// settles.
//
// Form 1, the lazy version, is bitten a different way. Its bound was "each
// vertex expanded once"; with a negative edge a vertex is expanded again every
// time it improves, and on a graph with a negative CYCLE it never stops at all.
// That is why main() refuses to run it when a negative weight is present. An
// algorithm outside its hypothesis is not slightly wrong. It is undefined.
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
// 1b. THE CLAIM ITSELF, WRITTEN DOWN.
//
//     "Whenever a vertex is selected, its distance is final." That sentence is
//     the algorithm. This function reports exactly what it asserts: the value
//     carried by each vertex at the moment it is first taken off the heap, and
//     nothing that is discovered afterwards.
//
//     With non-negative weights that is identical to form 1 — the claim is
//     true, so believing it costs nothing. With a negative edge it is not, and
//     the gap is visible in one number. On 1->2 costing 2, 2->4 costing 3,
//     1->3 costing 6 and 3->4 costing -5, vertex 4 is taken off the heap
//     holding 5, so this reports 5; the route through vertex 3 costs 6 - 5 = 1.
//
//     Read that against form 2's answer in the harness output. Be careful what
//     you conclude from an implementation that merely *stores* into an array:
//     the handbook's own listing keeps writing to distance[] after a vertex is
//     processed, so on this graph its array happens to end up holding 1. The
//     unsound step is believing the value at selection time — which is what you
//     do the moment you `break` out of the loop when the target is popped, or
//     read an answer off a vertex as you settle it.
//
//     It always terminates: at most one vertex is settled per pop.
// ---------------------------------------------------------------------------
vector<long long> dijkstra_at_settle_time(const WGraph& adj, int s) {
    vector<long long> dist(adj.size(), INF), settled(adj.size(), INF);
    vector<char> processed(adj.size(), 0);
    priority_queue<pair<long long, int>, vector<pair<long long, int>>,
                   greater<pair<long long, int>>> pq;
    dist[s] = 0;
    pq.push({0, s});
    while (!pq.empty()) {
        auto [d, u] = pq.top();
        pq.pop();
        if (processed[u]) continue;
        processed[u] = 1;
        settled[u] = d;                     // the claim: this value is final
        for (const Edge& e : adj[u]) {
            if (dist[u] + e.w < dist[e.to]) {
                dist[e.to] = dist[u] + e.w;
                pq.push({dist[e.to], e.to});
            }
        }
    }
    return settled;
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
// Prints four lines: the lazy heap sweep's distances from s (or the words
// NEGATIVE WEIGHTS, because outside its hypothesis it may never terminate);
// the value each vertex carried at the moment it was settled, which is what
// the finality claim asserts and is wrong when a weight is negative;
// Bellman-Ford's answer, or NEGATIVE CYCLE; and row s of the all-pairs table.
// Unreached prints as -1.
//
// Run it on the two lines "4 4 / 1 2 2 / 2 4 3 / 1 3 6 / 3 4 -5 / 1" and read
// the second and third rows against each other. That gap is this whole file.
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
    bool non_negative = true;
    for (int i = 0; i < m; ++i) {
        int u, v;
        long long w;
        if (!(cin >> u >> v >> w)) return 0;
        adj[u].push_back({v, w});
        arcs.push_back({u, v, w});
        if (w < 0) non_negative = false;
    }

    int s = 1;
    cin >> s;
    if (s < 1 || s > n) s = 1;

    // The guard is the lesson: the lazy sweep is not merely inaccurate outside
    // its hypothesis, it may never finish. So it is not run outside it.
    if (non_negative) {
        print_row(dijkstra(adj, s), n);
    } else {
        cout << "NEGATIVE WEIGHTS\n";
    }
    print_row(dijkstra_at_settle_time(adj, s), n);

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
