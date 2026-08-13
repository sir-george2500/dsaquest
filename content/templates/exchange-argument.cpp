// ===========================================================================
// THE ADJACENT SWAP
//
// Sometimes nothing is refused. Every task is done, every piece is used, and
// the only question is the ORDER. There is no key written in the statement,
// so you derive one:
//
//     take any two items that sit next to each other, write the cost of "a
//     then b" and the cost of "b then a", subtract. Everything before them and
//     everything after them cancels, because the pair occupies the same span
//     of time either way. What survives is a comparison between a and b alone
//     — and that comparison is your comparator.
//
// Why adjacent pairs are enough: any permutation can be turned into any other
// by repeated swaps of neighbours. If no neighbouring pair can be improved by
// swapping, no permutation is better at all. That is the whole proof.
//
// Two rules, both learned the expensive way:
//   * cross multiply, never divide — a double cannot separate 1000000007/3
//     from 1000000009/3, and the test data will contain both;
//   * `<`, never `<=`. A comparator that says an item precedes itself is
//     undefined behaviour inside std::sort.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. UNWEIGHTED — minimise the sum of finishing times. Shortest job first.
//
//    Two jobs of length a and b starting at time S:
//        a first:  (S+a) + (S+a+b) = 2S + 2a + b
//        b first:  (S+b) + (S+b+a) = 2S + 2b + a
//    So a belongs first exactly when a < b. Nothing else in the schedule
//    appears in that comparison, which is why sorting is legal.
//
//    Note what is NOT in the derivation: deadlines. "Maximise the sum of
//    (deadline - finishing time)" has a fixed sum of deadlines, so it is the
//    same problem, and the deadlines are a decoy.
// ---------------------------------------------------------------------------
long long min_total_completion(vector<long long> duration) {
    long long clock = 0, total = 0;
    // >>> HOLE id=shortest-first prompt=Run every job in the order the swap argument proves optimal, keeping a running `clock` and adding each finishing time to `total`
    sort(duration.begin(), duration.end());
    for (long long d : duration) {
        clock += d;                         // this job finishes here
        total += clock;
    }
    // <<< HOLE
    return total;
}

// ---------------------------------------------------------------------------
// 2. WEIGHTED — minimise the sum of weight * finishing time.
//
//    The same swap, carrying the weights:
//        a first:  w_a(S+t_a) + w_b(S+t_a+t_b)
//        b first:  w_b(S+t_b) + w_a(S+t_b+t_a)
//        difference = w_b*t_a - w_a*t_b
//    So a belongs first exactly when t_a/w_a < t_b/w_b, i.e.
//    t_a * w_b < t_b * w_a.
//
//    Shortest-first is the special case w = 1, and it is WRONG the moment the
//    weights differ: jobs (t=1,w=1) and (t=10,w=100) cost 1101 shortest-first
//    and 1011 in the derived order.
// ---------------------------------------------------------------------------
struct Job {
    long long time;                         // strictly positive
    long long weight;                       // strictly positive
};

long long min_weighted_completion(vector<Job> jobs) {
    long long clock = 0, total = 0;
    // >>> HOLE id=ratio-swap prompt=Order the jobs by the rule the weighted swap produces, using no division, then accumulate weight times finishing time into `total`
    sort(jobs.begin(), jobs.end(), [](const Job& a, const Job& b) {
        return a.time * b.weight < b.time * a.weight;     // t_a/w_a < t_b/w_b
    });
    for (const Job& job : jobs) {
        clock += job.time;
        total += job.weight * clock;
    }
    // <<< HOLE
    return total;
}

// ---------------------------------------------------------------------------
// 3. THE DERIVED KEY NEED NOT BE A NUMBER.
//
//    Arrange the pieces so the concatenation is the largest possible. The same
//    swap: "a then b" is the string a+b and "b then a" is b+a, so a belongs
//    first exactly when a+b > b+a. Comparing lengths, or first characters, or
//    numeric value, all fail — "3" beats "30" because 330 > 303.
//
//    The final guard is not decoration: {"0","0"} concatenates to "00", and
//    the answer is "0".
// ---------------------------------------------------------------------------
string largest_concatenation(vector<string> pieces) {
    // >>> HOLE id=concat-order prompt=Put the pieces in the order that makes the joined result as large as possible, comparing two candidate orders directly rather than the pieces themselves
    sort(pieces.begin(), pieces.end(), [](const string& a, const string& b) {
        return a + b > b + a;               // "3" before "30" because 330 > 303
    });
    // <<< HOLE
    string out;
    for (const string& p : pieces) out += p;
    if (!out.empty() && out[0] == '0') return "0";
    return out;
}

// ---------------------------------------------------------------------------
// Demo harness.
//   n            then n durations
//   m            then m lines: time weight
//   k            then k pieces (digit strings)
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    if (!(cin >> n)) return 0;
    vector<long long> duration(n);
    for (long long& d : duration) cin >> d;
    cout << min_total_completion(duration) << "\n";

    int m;
    cin >> m;
    vector<Job> jobs(m);
    for (Job& job : jobs) cin >> job.time >> job.weight;
    cout << min_weighted_completion(jobs) << "\n";

    int k;
    cin >> k;
    vector<string> pieces(k);
    for (string& p : pieces) cin >> p;
    cout << largest_concatenation(pieces) << "\n";
    return 0;
}
