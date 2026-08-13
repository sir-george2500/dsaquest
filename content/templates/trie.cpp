// ===========================================================================
// THE TRIE — one node per distinct prefix
//
// A rooted tree in which the path from the root to a node SPELLS that node.
// Two strings that begin the same way walk the same chain until they differ,
// which is what makes every prefix question a walk rather than a search.
//
//     insert("cat"), insert("car"), insert("card"), insert("dog")
//
//                  (root)
//                 c/     \d
//                 ca      do
//                 |       |
//                cat*  car* dog*
//                        |
//                      card*
//
//     4 words, 13 characters, 9 nodes — the shared "ca" is stored once.
//
// The star matters: a word may END inside another word's chain ("car" inside
// "card"), so a node needs a flag or a count saying "a word finishes here".
// Without it the trie can tell you that a prefix exists and never that a word
// does.
//
// Two counters per node pay for almost every problem in this family:
//     pass_[v]  how many inserted words go THROUGH v   -> prefix queries
//     end_[v]   how many inserted words STOP at v      -> exact queries
//
// Cost: O(|w|) per operation, independent of how many words are stored. That
// independence is the reason to reach for it — a hash map answers "is this
// word present" just as fast, and cannot answer "how many stored words start
// with this" at any price.
//
// Memory is the trap. One int child per alphabet letter per node is
// 26 * 4 = 104 bytes per node, so a million characters of input is about
// 99 MiB before you have stored anything else. Over an alphabet of 62 the same
// input needs 236 MiB and the submission dies on memory, not on time.
// ===========================================================================

#include <bits/stdc++.h>
using namespace std;

// ---------------------------------------------------------------------------
// 1. THE STRING TRIE.
//
//    Child 0 means "no such child": node 0 is the root and can never be
//    anybody's child, so zero is free to mean absent and the array needs no
//    fill loop. (Writers who use -1 must remember to fill; this convention
//    cannot be forgotten.)
// ---------------------------------------------------------------------------
struct Trie {
    static const int A = 26;
    vector<array<int, A>> child;
    vector<int> pass_;      // words passing through this node
    vector<int> end_;       // words ending exactly here

    Trie() { add_node(); }  // node 0 is the root, and stays empty

    int add_node() {
        child.push_back(array<int, A>{});   // value-initialised: all zero
        pass_.push_back(0);
        end_.push_back(0);
        return (int)child.size() - 1;
    }

    void insert(const string& w) {
        int v = 0;
        // >>> HOLE id=trie-insert prompt=Walk the word from the root, creating a node whenever the next letter has no child yet, counting the word through every node it passes and recording that it ends at the last one
        for (char ch : w) {
            int c = ch - 'a';
            if (child[v][c] == 0) child[v][c] = add_node();
            v = child[v][c];
            ++pass_[v];
        }
        ++end_[v];
        // <<< HOLE
    }

    // The node reached by spelling p, or 0 if the chain breaks.
    int walk(const string& p) const {
        int v = 0;
        for (char ch : p) {
            int c = ch - 'a';
            if (child[v][c] == 0) return 0;
            v = child[v][c];
        }
        return v;
    }

    // How many inserted words start with p. The counter was maintained during
    // insertion precisely so this does not have to enumerate anything.
    //
    // The price of letting 0 mean "absent" is that it also means "root", so an
    // EMPTY p reads as absent rather than as "every word". Non-empty queries
    // are the only ones this convention answers; if you need the empty one,
    // keep a separate total.
    int count_prefix(const string& p) const {
        // >>> HOLE id=trie-prefix-count prompt=Return how many inserted words begin with p, using the node that spelling p lands on and returning 0 when the chain breaks
        int v = walk(p);
        return v == 0 ? 0 : pass_[v];
        // <<< HOLE
    }

    int count_word(const string& w) const {
        int v = walk(w);
        return v == 0 ? 0 : end_[v];
    }

    // The longest prefix of w that is an inserted word — the "dictionary walk"
    // that spell-checkers and tokenisers are built on. Returns 0 if none is.
    int longest_stored_prefix(const string& w) const {
        int v = 0, best = 0;
        for (int i = 0; i < (int)w.size(); ++i) {
            int c = w[i] - 'a';
            if (child[v][c] == 0) break;
            v = child[v][c];
            if (end_[v] > 0) best = i + 1;
        }
        return best;
    }

    int node_count() const { return (int)child.size(); }
};

// ---------------------------------------------------------------------------
// 2. THE BINARY TRIE — the same structure over the bits of an integer.
//
//    Store each number as a 30-character string over the alphabet {0, 1},
//    most significant bit first. To maximise x XOR y, walk down from the top
//    and take the OPPOSITE bit whenever a child exists: a single high bit
//    outweighs every lower bit put together, so the greedy choice is forced.
//
//    This is why a trie is not "a data structure for words". It is a data
//    structure for SEQUENCES compared left to right, and bits are a sequence.
// ---------------------------------------------------------------------------
struct XorTrie {
    static const int BITS = 30;             // enough for values below 2^30
    vector<array<int, 2>> child;

    XorTrie() { child.push_back(array<int, 2>{}); }

    void insert(int x) {
        int v = 0;
        for (int b = BITS - 1; b >= 0; --b) {
            int bit = (x >> b) & 1;
            if (child[v][bit] == 0) {
                child.push_back(array<int, 2>{});
                child[v][bit] = (int)child.size() - 1;
            }
            v = child[v][bit];
        }
    }

    // Largest x XOR y over every stored y. Requires at least one insert.
    int best_xor(int x) const {
        int v = 0, acc = 0;
        // >>> HOLE id=xor-greedy prompt=Walk from the top bit down, following the child that differs from this bit of x whenever it exists and adding that bit's weight to acc, otherwise following the only child there is
        for (int b = BITS - 1; b >= 0; --b) {
            int bit = (x >> b) & 1;
            int want = bit ^ 1;
            if (child[v][want] != 0) {
                acc |= 1 << b;
                v = child[v][want];
            } else {
                v = child[v][bit];
            }
        }
        // <<< HOLE
        return acc;
    }
};

// ---------------------------------------------------------------------------
// Demo harness.
//   n           then n words        (lowercase)
//   q           then q query words  (prefix count, exact count, longest stored prefix)
//   m           then m non-negative integers, then one integer x
// ---------------------------------------------------------------------------
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    if (!(cin >> n)) return 0;

    Trie trie;
    for (int i = 0; i < n; ++i) {
        string w;
        cin >> w;
        trie.insert(w);
    }
    cout << trie.node_count() << "\n";

    int q;
    if (!(cin >> q)) return 0;
    for (int i = 0; i < q; ++i) {
        string w;
        cin >> w;
        cout << trie.count_prefix(w) << ' ' << trie.count_word(w) << ' '
             << trie.longest_stored_prefix(w) << "\n";
    }

    int m;
    if (!(cin >> m)) return 0;
    XorTrie xt;
    for (int i = 0; i < m; ++i) {
        int v;
        cin >> v;
        xt.insert(v);
    }
    int x;
    if (!(cin >> x)) return 0;
    cout << (m > 0 ? xt.best_xor(x) : 0) << "\n";

    return 0;
}
