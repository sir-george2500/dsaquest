// ===========================================================================
// HASHING & FREQUENCY COUNTING
//
// One idea: walk the data once, and keep a record of what you have already
// passed. The invariant is what makes it correct:
//
//     When index i is examined, the map holds the tally of EXACTLY a[0..i-1].
//
// So every lookup is a question about strictly earlier elements, and a[i] is
// inserted only after its own answer has been recorded. Break that ordering and
// an element pairs with itself.
//
// A map knows HOW MANY, never WHERE. If adjacency or position is part of the
// condition, this is the wrong pattern.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 0. HARDENED HASH — paste this into anything keyed by an integer.
//
//    libstdc++ hashes an integer with the IDENTITY function, and the bucket
//    count is a known prime. A test can therefore feed keys that all land in
//    one bucket and turn your O(n) into O(n^2). splitmix64 plus a clock seed
//    means the setter cannot know where your keys will land.
// ---------------------------------------------------------------------------
struct FastHash {
    static uint64_t splitmix64(uint64_t x) {
        x += 0x9e3779b97f4a7c15ULL;
        x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
        x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
        return x ^ (x >> 31);
    }
    size_t operator()(uint64_t x) const {
        static const uint64_t SEED =
            (uint64_t)chrono::steady_clock::now().time_since_epoch().count();
        return (size_t)splitmix64(x + SEED);
    }
};

template <class K, class V>
using hmap = unordered_map<K, V, FastHash>;
template <class K>
using hset = unordered_set<K, FastHash>;

// ---------------------------------------------------------------------------
// 1. SEEN-SET and COMPLEMENT LOOKUP.
//
//    Every element needs exactly one partner. Ask for the partner; do not
//    search for it. Note the order: find, THEN insert.
// ---------------------------------------------------------------------------
bool has_duplicate(const vector<int>& a) {
    hset<int> seen;
    seen.reserve(a.size() * 2);          // pay for the buckets once
    for (int x : a)
        if (!seen.insert(x).second)      // insert reports "was it new?" - one lookup
            return true;
    return false;
}

// Returns the indices of a pair summing to target, or {-1, -1}.
pair<int, int> two_sum(const vector<int>& a, long long target) {
    hmap<long long, int> pos;            // value -> index of an earlier occurrence
    pos.reserve(a.size() * 2);

    // >>> HOLE id=complement-order prompt=For each element ask for the one partner that would complete it, looking only at what came before, and only afterwards make this element available to the ones still to come
    for (int i = 0; i < (int)a.size(); ++i) {
        long long need = target - a[i];
        auto it = pos.find(need);        // QUERY the prefix a[0..i-1] ...
        if (it != pos.end()) return {it->second, i};
        pos[a[i]] = i;                   // ... only then extend it
    }
    // <<< HOLE
    return {-1, -1};
}

// ---------------------------------------------------------------------------
// 2. FREQUENCY COUNTING.
//
//    count_pairs_with_sum is the shape worth memorising: for each element, add
//    the number of EARLIER elements that complete it. Never enumerate pairs,
//    and never accumulate them in an int - n equal values give ~n^2/2 pairs.
// ---------------------------------------------------------------------------
long long count_pairs_with_sum(const vector<int>& a, long long target) {
    hmap<long long, long long> cnt;
    cnt.reserve(a.size() * 2);

    // >>> HOLE id=pair-count prompt=Total every pair summing to target in one pass, crediting each element with how many earlier elements complete it — never enumerate the pairs themselves
    long long pairs = 0;
    for (int x : a) {
        auto it = cnt.find(target - x);
        if (it != cnt.end()) pairs += it->second;
        ++cnt[x];                        // operator[] value-initialises to 0 here,
    }                                    // which is what we want - unlike in a read
    // <<< HOLE
    return pairs;
}

// Most frequent value; ties broken by the smaller value.
// The tie-break is not cosmetic: unordered_map iteration order is unspecified,
// so without it the program is not deterministic.
pair<int, long long> most_frequent(const vector<int>& a) {
    hmap<int, long long> cnt;
    cnt.reserve(a.size() * 2);
    for (int x : a) ++cnt[x];

    int best = 0;
    long long best_count = 0;
    for (const auto& [value, c] : cnt)
        if (c > best_count || (c == best_count && value < best)) {
            best = value;
            best_count = c;
        }
    return {best, best_count};
}

// ---------------------------------------------------------------------------
// 3. GROUPING BY A CANONICAL KEY.
//
//    "Equal up to some transformation" => build the key that the transformation
//    preserves, then bucket by it. Here: the 26-letter signature, so anagrams
//    share a key in O(len) instead of O(len log len) for a sorted copy.
//
//    The '#' separators matter: without them the counts 1,11 and 11,1 collapse
//    to the same string.
// ---------------------------------------------------------------------------
static string anagram_key(const string& w) {
    array<int, 26> cnt{};                // {} zero-initialises; without it, garbage
    for (unsigned char ch : w) {
        if (ch < 'a' || ch > 'z') continue;   // guard: c - 'a' on 'A' is a NEGATIVE index
        ++cnt[ch - 'a'];
    }
    // >>> HOLE id=anagram-key prompt=Flatten the 26 counts into one string that two words share exactly when they are anagrams — counts of 1,11 and 11,1 must not collide
    string key;
    for (int i = 0; i < 26; ++i) {
        key += '#';
        key += to_string(cnt[i]);
    }
    // <<< HOLE
    return key;
}

vector<vector<string>> group_anagrams(const vector<string>& words) {
    unordered_map<string, vector<string>> buckets;   // std::hash<string> is fine: it is not identity
    for (const string& w : words) buckets[anagram_key(w)].push_back(w);

    vector<vector<string>> out;
    out.reserve(buckets.size());
    for (auto& [key, group] : buckets) {
        (void)key;
        sort(group.begin(), group.end());
        out.push_back(std::move(group));
    }
    sort(out.begin(), out.end());        // buckets come out in unspecified order
    return out;
}

// ---------------------------------------------------------------------------
// 4. ARRAY COUNTER — when the alphabet is small and bounded, the map is a
//    mistake. An array index is an O(1) with no hash, no allocation, no
//    adversarial case, and it fits in cache.
//
//    Rule of thumb: value range <= a few million => array. Otherwise hash map.
// ---------------------------------------------------------------------------
int first_unique_char(const string& s) {
    array<int, 26> cnt{};
    for (unsigned char ch : s)
        if (ch >= 'a' && ch <= 'z') ++cnt[ch - 'a'];

    for (int i = 0; i < (int)s.size(); ++i) {
        unsigned char ch = (unsigned char)s[i];
        if (ch >= 'a' && ch <= 'z' && cnt[ch - 'a'] == 1) return i;
    }
    return -1;
}

// ---------------------------------------------------------------------------
// Demo harness: reads  n target / n values / m / m lowercase words.
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    long long target;
    if (!(cin >> n >> target)) return 0;

    vector<int> a(n);
    for (int& x : a) cin >> x;

    auto [pi, pj] = two_sum(a, target);
    auto [mode, mode_count] = most_frequent(a);

    cout << "two_sum: " << pi << " " << pj << "\n";
    cout << "duplicate: " << (has_duplicate(a) ? "yes" : "no") << "\n";
    cout << "mode: " << mode << " x" << mode_count << "\n";
    cout << "pairs_summing_to_target: " << count_pairs_with_sum(a, target) << "\n";

    int m;
    if (!(cin >> m)) return 0;
    vector<string> words(m);
    for (string& w : words) cin >> w;

    for (const auto& group : group_anagrams(words)) {
        cout << "group:";
        for (const string& w : group) cout << " " << w;
        cout << "\n";
    }
    if (m > 0)
        cout << "first_unique(" << words[0] << "): " << first_unique_char(words[0]) << "\n";

    return 0;
}
