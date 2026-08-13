// The extended template: everything in starter.cpp, plus the two additions that
// are worth their weight — a debug printer that vanishes in the judge, and a
// hash that does not lose to anti-hash tests.
//
// Compile locally with -DLOCAL to switch the debug printer on:
//     g++ -std=c++20 -O2 -DLOCAL -Wall -Wextra -Wshadow solution.cpp
//
// The judge never defines LOCAL, so debug(...) costs exactly nothing there.

#include <bits/stdc++.h>
using namespace std;

using ll = long long;
using ull = unsigned long long;

// ---------------------------------------------------------------------------
// debug(...) — prints "n = 5, v = {1, 2, 3}" to stderr, recursively, for any
// nesting of ranges, pairs and tuples. Compiles to nothing without -DLOCAL.
//
// A debug printer is the single highest-value thing in a template. It is the
// difference between reasoning about a wrong answer and looking at it.
// ---------------------------------------------------------------------------
#ifdef LOCAL
namespace dbg {

template <class T>
void print(const T& x);

inline void print(const string& s) { cerr << '"' << s << '"'; }
inline void print(const char* s) { cerr << '"' << s << '"'; }
inline void print(char c) { cerr << '\'' << c << '\''; }
inline void print(bool b) { cerr << (b ? "true" : "false"); }

template <class A, class B>
void print(const pair<A, B>& p) {
    cerr << '(';
    print(p.first);
    cerr << ", ";
    print(p.second);
    cerr << ')';
}

template <class... T>
void print(const tuple<T...>& t) {
    cerr << '(';
    bool first = true;
    apply(
        [&](const auto&... e) {
            ((cerr << (first ? "" : ", "), first = false, print(e)), ...);
        },
        t);
    cerr << ')';
}

template <class T>
void print(const T& x) {
    // `if constexpr` picks the branch at compile time, so a non-range type
    // never even instantiates the loop.
    if constexpr (ranges::range<T>) {
        cerr << '{';
        bool first = true;
        for (auto&& e : x) {
            if (!first) cerr << ", ";
            first = false;
            print(e);
        }
        cerr << '}';
    } else {
        cerr << x;
    }
}

inline void emit(const char*) { cerr << '\n'; }

template <class T, class... Rest>
void emit(const char* names, const T& value, const Rest&... rest) {
    // Advance past this argument's name in the stringified __VA_ARGS__,
    // respecting nesting so debug(f(a, b), c) splits in the right place.
    int depth = 0;
    const char* p = names;
    while (*p && (depth > 0 || *p != ',')) {
        if (*p == '(' || *p == '[' || *p == '{') ++depth;
        if (*p == ')' || *p == ']' || *p == '}') --depth;
        ++p;
    }
    cerr.write(names, p - names);
    cerr << " = ";
    print(value);
    if (*p == ',') {
        cerr << ", ";
        ++p;
        while (*p == ' ') ++p;
    }
    emit(p, rest...);
}

}  // namespace dbg

#define debug(...)                                        \
    (cerr << "[" << __LINE__ << "] ",                     \
     dbg::emit(#__VA_ARGS__ __VA_OPT__(, ) __VA_ARGS__))
#else
#define debug(...) ((void)0)
#endif

// ---------------------------------------------------------------------------
// A hash that survives adversarial input.
//
// libstdc++ hashes integers with the identity function. A problem setter who
// knows this can hand you keys that all collide, turning your O(n)
// unordered_map into O(n^2). This has decided real contests. Splitmix64 plus a
// clock-derived salt makes the collision set unpredictable.
//
// Use: safe_map<int, int> cnt;   instead of   unordered_map<int, int> cnt;
// ---------------------------------------------------------------------------
struct SafeHash {
    static ull splitmix64(ull x) {
        x += 0x9e3779b97f4a7c15ULL;
        x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
        x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
        return x ^ (x >> 31);
    }
    size_t operator()(ull x) const {
        static const ull SALT =
            chrono::steady_clock::now().time_since_epoch().count();
        return splitmix64(x + SALT);
    }
};

template <class K, class V>
using safe_map = unordered_map<K, V, SafeHash>;
template <class K>
using safe_set = unordered_set<K, SafeHash>;

// ---------------------------------------------------------------------------

void solve() {

}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int tests = 1;
    // cin >> tests;
    while (tests--) solve();
    return 0;
}
