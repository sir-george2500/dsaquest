# Source texts

Two books on this machine cover essentially the whole curriculum. Content
authors should work from them rather than from memory — a remembered identity
or complexity is exactly the kind of thing that is subtly wrong.

| file | what it is |
|---|---|
| `~/CManHandBook.pdf` | **Competitive Programmer's Handbook**, Antti Laaksonen, 296pp. The book `docs/game-design.md` already draws the curriculum from. |
| `~/Downloads/cpp.pdf` | **An Introduction to the USA Computing Olympiad**, Darren Yao, 82pp. Bronze/Silver. Gentler, and better for the early masters. |

## Page offsets — read these before citing a page

Both PDFs have front matter, so the printed page number is **not** the PDF page
number. Verified by reading the pages, not assumed:

* **CPH** — printed page 1 is PDF page 11. **PDF page = printed page + 10.**
* **USACO** — printed page 1 is PDF page 5. **PDF page = printed page + 4.**

The `Read` tool takes at most 20 PDF pages per call, so a long chapter needs
more than one call.

## CPH chapter map (PDF page ranges)

| chapter | printed | **PDF** | master |
|---|---|---|---|
| 1 Introduction | 3–16 | **13–26** | Foundations |
| 2 Time complexity | 17–24 | **27–34** | Foundations |
| 3 Sorting, 3.3 Binary search | 25–34 | **35–44** | Search |
| 4 Data structures | 35–46 | **45–56** | Structures |
| 5 Complete search | 47–56 | **57–66** | Foundations / DP |
| 6 Greedy algorithms | 57–64 | **67–74** | Greed ✓ |
| 7 Dynamic programming | 65–76 | **75–86** | DP |
| 8 Amortized analysis (two pointers, sliding window minimum) | 77–82 | **87–92** | Arrays ✓ |
| 9 Range queries (BIT, segment tree) | 83–94 | **93–104** | Structures |
| 10 Bit manipulation | 95–106 | **105–116** | Bits ✓ |
| 11 Basics of graphs | 109–116 | **119–126** | Graphs |
| 12 Graph traversal | 117–122 | **127–132** | Graphs |
| 13 Shortest paths | 123–132 | **133–142** | Graphs |
| 14 Tree algorithms | 133–140 | **143–150** | Trees |
| 15 Spanning trees, union-find | 141–148 | **151–158** | Graphs |
| 16 Directed graphs, topological sort | 149–156 | **159–166** | Graphs |
| 17 Strong connectivity | 157–162 | **167–172** | Graphs |
| 18 Tree queries, LCA | 163–172 | **173–182** | Trees |
| 19 Paths and circuits | 173–180 | **183–190** | Graphs |
| 20 Flows and cuts | 181–194 | **191–204** | Graphs |
| 21 Number theory | 197–206 | **207–216** | Mathematics |
| 22 Combinatorics | 207–216 | **217–226** | Mathematics |
| 23 Matrices | 217–224 | **227–234** | Mathematics |
| 24 Probability | 225–234 | **235–244** | Mathematics |
| 25 Game theory | 235–242 | **245–252** | Mathematics |
| 26 String algorithms | 243–250 | **253–260** | Strings |
| 27 Square root algorithms | 251–256 | **261–266** | — |
| 28 Segment trees revisited | 257–266 | **267–276** | Structures |

## USACO chapter map (PDF page ranges)

| chapter | printed | **PDF** | master |
|---|---|---|---|
| 2 Elementary techniques | 5–6 | **9–10** | Foundations |
| 3 Time/space complexity, constraints table | 7–9 | **11–13** | Foundations |
| 4 Built-in data structures | 10–17 | **14–21** | Structures |
| 5 Simulation | 19–21 | **23–25** | Foundations |
| 6 Complete search | 22–25 | **26–29** | Foundations |
| 8 Sorting and comparators | 29–31 | **33–35** | Greed ✓ |
| 9 Greedy algorithms | 32–35 | **36–39** | Greed ✓ |
| 10 Graph theory, floodfill, DSU, bipartite | 36–54 | **40–58** | Graphs |
| 11 Prefix sums, 2D prefix sums | 55–58 | **59–62** | Arrays ✓ |
| 12 Binary search on the answer | 59–62 | **63–66** | Search ✓ |
| 13 Elementary number theory | 63–65 | **67–69** | Mathematics |
| 14 Two pointers, line sweep, bitwise | 66–74 | **70–78** | Arrays ✓ / Bits ✓ |

## How to use them

Read your chapter, then author from it. The book gives you the *correct*
statement of each technique, its complexity, and its worked examples — the
things worth being exactly right about.

It does **not** give you this game's pedagogy. Secrets, watch-outs, drills and
the master's voice are ours. §21 of `docs/game-design.md` says what this design
refuses; a curriculum that is a transcription of a textbook chapter has missed
the point of the product.
