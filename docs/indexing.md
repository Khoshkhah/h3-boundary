---
layout: default
title: Boundary Indexing
nav_order: 6
---

# Boundary Indexing
{: .no_toc }

How to compute the *n*-th boundary cell directly — no searching, no enumeration — and how to go back the other way.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## The idea in one picture

A resolution-3 cell has **78** boundary children at resolution 6. Normally you would generate all 78 to get one of them. Instead:

```python
boundary_cell_at(parent, 6, 50)   # → '8628309a7ffffff', the 50th one, computed directly
boundary_rank(parent, cell)       # → 50, the way back
```

Both take about **15 arithmetic operations**, regardless of how big the boundary is. Reaching into a 531,438-cell boundary costs the same as a 78-cell one.

This works because the boundary cells form a **counting system**. Once you can count how many cells lie below any point in the tree, you can navigate straight to cell number *n* the same way you find the 50th page of a book by looking at the chapter lengths — never reading the pages you skip.

---

## Three definitions

### 1. An H3 index is an address

An H3 index is a 64-bit number, and part of it is a list of **digits** — one digit (0–6) per resolution level, saying which of the 7 children you took at that level:

```
832830fffffffff  →  resolution 3, base cell 20, digits [0, 6, 0]
8628309a7ffffff  →  resolution 6, base cell 20, digits [0, 6, 0, 4, 6, 4]
                                                        └ parent ┘  └ new ┘
```

The second cell is a descendant of the first: same base cell, same first three digits, plus three more. Unused levels are filled with 7s.

**So finding a boundary cell means choosing Δ digits**, where Δ = target resolution − parent resolution. Nothing else.

### 2. A boundary child touches the parent's edge

Every cell has 6 faces (edges), numbered 1–6. A descendant is a *boundary child* if it touches at least one of the parent's faces.

### 3. The state: which faces you still touch

Walking down level by level, the only thing you need to remember is **which of the parent's faces the current cell still touches**. That is the *state*.

Start at the parent: state = {1,2,3,4,5,6} (all faces). Each step down, the lookup tables say what the state becomes. If the state becomes empty, that cell and everything under it is interior — pruned.

Only four state sizes ever occur:

| State size | What it is | How many of its 7 children survive |
|---|---|---|
| 6 faces | the parent itself (start only) | 6 |
| 3 faces | one of the parent's six outer children | 4 |
| 2 faces | a cell near a corner | 3 |
| 1 face | a cell along an edge | 2 |

The center child (digit 0) always maps to the empty state — it is strictly inside — which is why it never appears.

---

## The counting rule

Here is the part that makes everything work. Let **N<sub>k</sub>(d)** = how many boundary cells lie *d* levels below a cell whose state has *k* faces.

Reading the four rows of the table above gives a small system:

$$N_1(d) = N_1 + N_2 \qquad N_2(d) = N_1 + N_2 + N_3 \qquad N_3(d) = N_1 + N_2 + 2N_3$$

(right sides evaluated at *d*−1; all start at N(0) = 1). Solving it gives closed forms:

$$N_1(d) = \frac{3^d+1}{2} \qquad N_2(d) = 3^d \qquad N_3(d) = \frac{3^{d+1}-1}{2} \qquad N_6(d) = 3^{d+1}-3$$

| d | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|
| **N₁** edge | 2 | 5 | 14 | 41 | 122 | 365 | 1,094 |
| **N₂** corner | 3 | 9 | 27 | 81 | 243 | 729 | 2,187 |
| **N₃** outer | 4 | 13 | 40 | 121 | 364 | 1,093 | 3,280 |
| **N₆** whole boundary | 6 | 24 | 78 | 240 | 726 | 2,184 | 6,558 |

The last row is the total boundary size, `3^(Δ+1) - 3`. (For a pentagon parent it is `5·(3^Δ − 1)/2`.)

**The point:** you never have to count anything. Given a state and a remaining depth, the number of cells below is a formula.

---

## Unranking: from a number to a cell

> Find boundary cell number *n*.

The algorithm, in words:

1. Start at the parent, state = all 6 faces, and a counter `remaining = n`.
2. Look at the surviving children, left to right. For each, its subtree holds N<sub>k</sub>(d) cells.
3. If `remaining` is **bigger** than that subtree, the answer isn't in there — subtract it and move to the next child.
4. If `remaining` is **smaller**, the answer *is* in there — take that digit, adopt that child's state, go down one level.
5. Repeat until you reach the target resolution. The digits you took **are** the answer.

### Worked example

Parent `832830fffffffff` (resolution 3) → resolution 6. The boundary has 3⁴ − 3 = **78** cells. Find **n = 50**.

**Level 1 (res 4).** Six surviving children, each an outer (3-face) cell holding N₃(2) = **13** cells:

```
child 1: 13 cells  →  50 ≥ 13, skip.  remaining = 50 − 13 = 37
child 2: 13 cells  →  37 ≥ 13, skip.  remaining = 37 − 13 = 24
child 3: 13 cells  →  24 ≥ 13, skip.  remaining = 24 − 13 = 11
child 4: 13 cells  →  11 < 13. It's in here!
```
→ **digit 4**, new state {1,4,5} (3 faces), remaining = **11**

**Level 2 (res 5).** Four survivors, with 1, 3, 3 and 2 faces → N₁(1)=2, N₃(1)=4, N₃(1)=4, N₂(1)=3:

```
child 1: 2 cells  →  11 ≥ 2, skip.  remaining = 9
child 4: 4 cells  →   9 ≥ 4, skip.  remaining = 5
child 5: 4 cells  →   5 ≥ 4, skip.  remaining = 1
child 6: 3 cells  →   1 < 3. It's in here!
```
→ **digit 6**, new state {4,6}, remaining = **1**

**Level 3 (res 6).** Three survivors, each a single cell (depth 0):

```
child 2: 1 cell  →  1 ≥ 1, skip.  remaining = 0
child 4: 1 cell  →  0 < 1. Found it.
```
→ **digit 4**, remaining = 0

**Digits chosen: 4, 6, 4.** Append them to the parent's digits `[0, 6, 0]`:

```
[0, 6, 0] + [4, 6, 4]  =  8628309a7ffffff
```

And indeed `children_on_boundary_faces(parent, 6)[50]` is `8628309a7ffffff`. Three steps, no enumeration.

---

## Ranking: from a cell to its number

The exact reverse: read the cell's digits, and at each level **add up the subtrees you skipped over** to reach that digit.

Same example, `8628309a7ffffff` (digits 4, 6, 4):

| Level | Digit | Branches skipped before it | Added |
|---|---|---|---|
| res 4 | 4 | 13 + 13 + 13 | +39 |
| res 5 | 6 | 2 + 4 + 4 | +10 |
| res 6 | 4 | 1 | +1 |
| | | **total** | **50** ✓ |

Back to 50, as expected. Two useful side effects:

- **Membership test.** If the cell's digit at any level leads to an empty state, the cell is interior — `boundary_rank` raises instead of returning a number.
- **Round-trip guarantee.** `rank(unrank(n)) == n` for every *n*, which is exactly what the test suite asserts.

---

## Ranges: seek once, then stream

Calling `boundary_cell_at` in a loop works but re-descends from the parent every time. `boundary_range` seeks to the start position once, then walks forward, skipping any subtree that falls entirely before the range:

```python
for cell in boundary_range(parent, 13, 100_000, 100_500):
    process(cell)     # 500 cells out of 531,438, without touching the rest
```

Because disjoint ranges reassemble into exactly the traversal's output, workers can split a boundary with no coordination at all:

```python
# worker k of n
lo, hi = total * k // n, total * (k + 1) // n
for cell in boundary_range(parent, target_res, lo, hi):
    ...
```

---

## What it costs

| Operation | Work | Measured |
|---|---|---|
| `boundary_cell_at` | Δ steps × ≤7 branch checks | 0.011 ms |
| `boundary_rank` | same | 0.011 ms |
| `boundary_range` (slice) | Δ-step seek + O(1) per cell | 0.025 ms for 100 cells |

Δ is at most 15, so **every** lookup is bounded by roughly 100 arithmetic operations. The boundary's size never enters the cost — 0.011 ms whether it holds 78 cells or 531,438.

---

## Generating the whole boundary: three ways

### 1. Unrank every position (don't)

Unranking answers "give me cell *n*". Asking it for every *n* in turn works, but each call starts again from the parent, so the Δ-step descent is repeated N times — and nothing is shared between neighbouring cells even though they have almost identical digit strings.

### 2. Recursive descent — ordered

This is what `children_on_boundary_faces` does, and it is the same walk the counting rule is built on, just without the counting. Start at the parent with state {1..6}; for each surviving child, recurse; when you reach the target resolution, emit the cell:

```
parent {1,2,3,4,5,6}
├── digit 0 → {}  pruned — the centre child and everything under it
├── digit 1 → {1,2,3} ──┬── digit 1 → {1,3,5} → … emit
│                       ├── digit 2 → {3}     → … emit
│                       ├── digit 3 → {1,2,3} → … emit
│                       └── digit 5 → {1,5}   → … emit
├── digit 2 → {2,4,6} ── … (4 survivors each, as the table above says)
⋮
└── digit 6 → {4,5,6} ── …
```

Because the walk goes depth-first, cells come out in a fixed order — and that order *is* the definition of rank. Each cell's digit prefix is built once and shared by everything below it, which is exactly the work the unranking loop repeats. That alone is worth ~500×.

### 3. Level expansion — unordered ("bulk")

If you don't need the order, the same state machine can advance **a whole level at once**. Group the live cells by state, then add the digit to the entire group in one operation:

```
level k:    state {1,4,5}: [ 12,000 cells ]      state {4,6}: [ 8,000 cells ]
                     │                                  │
                     │  one array add per valid digit   │
                     ▼                                  ▼
level k+1:  state {1,3}:   [ 30,000 cells ]      state {5}:   [ 18,000 cells ]
```

Every cell in a group has the same state, so it has the same valid digits — one addition over the whole group replaces one step per cell. That is `boundary_cell_ids`. The catch is that cells from different branches end up mixed together in the groups, so the traversal order is gone.

### Every implementation, measured

Both approaches, each written three ways, on the same machine (6 threads):

| Approach | Implementation | 6,558 cells | 59,046 | 531,438 |
|---|---|---|---|---|
| ordered | unranking, one call per cell (Python) | 71 ms | 799 ms | 8,696 ms |
| ordered | unranking, one call per cell (C++) | 78 ms | 888 ms | 9,725 ms |
| ordered | recursive descent (Python) | 3.9 ms | 40 ms | 357 ms |
| ordered | recursive descent (C++) | 0.15 ms | 1.3 ms | 13.3 ms |
| ordered | recursive descent (C++, 6 threads) | 0.53 ms | 0.69 ms | **2.2 ms** |
| **bulk** | level expansion (NumPy) | 0.50 ms | 0.90 ms | 4.5 ms |
| **bulk** | level expansion (NumPy, 6 threads) | 2.5 ms | 4.9 ms | 29 ms |
| **bulk** | level expansion (NumPy, 6 processes) | 3.4 ms | 3.4 ms | 6.5 ms |
| **bulk** | level expansion (C++) | **0.03 ms** | **0.23 ms** | 2.0 ms |
| **bulk** | level expansion (C++, 6 threads) | 0.57 ms | 0.72 ms | **1.2 ms** |

Four things this shows:

1. **Unranking in a loop is the wrong tool for bulk work, in any language.** C++ is no faster than Python here (78 ms vs 71 ms) — the cost is one call per cell, not the arithmetic inside it. Use it for *some* cells.
2. **Bulk beats ordered at every size**, once both are in the same language: 0.03 ms vs 0.15 ms at 6.5k cells, 2.0 ms vs 13.3 ms at half a million. Buckets of cells advancing together beat one recursion step per cell.
3. **NumPy is the fastest option without a compiler** — within 2× of C++ at large sizes — but its per-operation overhead makes it slower than C++ by 15× when the arrays are small.
4. **Parallelism pays only for the biggest boundaries.** Below ~100k cells, thread hand-off costs more than the work saved. At 531k it gives 6× on the ordered path (13.3 → 2.2 ms) and 1.6× on bulk (2.0 → 1.2 ms). NumPy gains nothing from threads (it holds the GIL for the bookkeeping between array ops) and needs processes to parallelize at all — the C++ functions release the GIL, so plain threads work.

Reproduce with `python benchmarks/compare_implementations.py`.

### How each one is parallelized

**The library never starts threads or processes for you.** Every function here is serial, and that is deliberate: callers are often already inside a pool (a worker process, Dask, Spark, a request handler), so a library that quietly spawned six threads per call would oversubscribe the machine, and it cannot know whether a given boundary is large enough for parallelism to pay at all. What the library does provide is the two things only it can: primitives that split cleanly, and C++ functions that **release the GIL**, so ordinary Python threads run them genuinely in parallel.

Neither approach parallelizes the recursion itself — the work is *split up front*, and the two split differently.

**Ordered: by index range.** This is where the counting rule earns its keep. Worker *k* takes `[lo, hi)`, seeks straight to `lo` in Δ steps, and streams its slice; no worker needs to know what the others produced, and concatenating the slices in order reproduces the traversal exactly.

```python
lo, hi = total * k // n, total * (k + 1) // n
part = boundary_range_ids(parent, target_res, lo, hi)
```

Shards are equal-sized by construction and you can have as many as you like.

**Bulk: by subtree.** There are no positions to slice, so the split is structural — the parent's 6 surviving children, each expanded independently with its own face state. That caps the useful parallelism at 6, and splitting deeper backfires, because each bulk task has fixed setup and the arrays stop being big enough to pay for it:

| Bulk split (531,438 cells) | Time |
|---|---|
| serial | 3.3 ms |
| 6 tasks (one level down) | **2.1 ms** |
| 24 tasks (two levels) | 3.7 ms |
| 78 tasks (three levels) | 5.4 ms |

So the two trade places under parallelism: bulk is far ahead serially, but ordered keeps scaling — with 12 index shards it reaches 1.8 ms, past the best bulk number. Bulk is the right default; index sharding is what you want when you have cores to spend.

### Which to use

- **some cells** → `boundary_cell_at` / `boundary_range`
- **all of them, order irrelevant** → `boundary_cell_ids` (C++ when built, NumPy otherwise)
- **all of them, in order** → `children_on_boundary_faces` (see [Boundary Algorithms](algorithms.md))

---

## Full API

```python
from h3_boundary import boundary_cell_at, boundary_rank, boundary_range

boundary_cell_at(parent, target_res, n, input_faces={1,2,3,4,5,6}) -> str
boundary_rank(parent, cell, input_faces={1,2,3,4,5,6}) -> int
boundary_range(parent, target_res, start=0, stop=None, input_faces={1,2,3,4,5,6}) -> Iterator[str]
```

For a whole boundary at once:

```python
from h3_boundary import boundary_cell_ids   # unordered, NumPy uint64 array

boundary_cell_ids(parent, target_res, input_faces={1,2,3,4,5,6}) -> numpy.ndarray
```

- `input_faces` restricts the traversal to part of the boundary; it must match across calls for ranks to line up.
- `boundary_cell_at` raises `IndexError` outside `range(count)`; `boundary_rank` raises `ValueError` for non-descendants and interior cells.
- All three work with or without the C++ extension (`boundary_range` uses it when present).

**Ranks refer to traversal order** — the order `children_on_boundary_faces` returns. `boundary_cell_ids` groups its cells by state instead, so positions in *that* array mean nothing to `boundary_rank`; don't mix the two.

## How it is verified

- The unranked sequence `[boundary_cell_at(p, r, i) for i in range(count)]` equals `children_on_boundary_faces(p, r)` **element for element**, for hexagon and pentagon parents, full and partial face sets.
- `rank(unrank(n)) == n`, including inside the 531,438-cell resolution 2 → 13 boundary.
- Shards from `boundary_range` concatenate to the traversal exactly — no gaps, no overlaps, no reordering.
- The totals match the closed form `3^(Δ+1) − 3` independently of any implementation.

See [Boundary Algorithms](algorithms.md) for how this compares with the other approaches.
