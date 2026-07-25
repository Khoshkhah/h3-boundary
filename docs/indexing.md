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

The one thing this is *not* best at: generating the whole boundary. Indexing re-descends from the parent for each cell, while the bulk functions share that work between cells — at 531,438 cells they are far ahead:

| Whole boundary | Time |
|---|---|
| `boundary_cell_ids` (unordered, uint64) | 1.9 ms |
| `children_on_boundary_faces_ids` (ordered, uint64) | 12 ms |
| `children_on_boundary_faces` (ordered, hex strings) | 56 ms |
| `boundary_cell_at` in a loop | ~5,900 ms (0.011 ms x 531,438) |

Use indexing when you want *some* cells; use the bulk functions when you want *all* of them.

---

## Full API

```python
from h3_boundary import boundary_cell_at, boundary_rank, boundary_range

boundary_cell_at(parent, target_res, n, input_faces={1,2,3,4,5,6}) -> str
boundary_rank(parent, cell, input_faces={1,2,3,4,5,6}) -> int
boundary_range(parent, target_res, start=0, stop=None, input_faces={1,2,3,4,5,6}) -> Iterator[str]
```

- `input_faces` restricts the traversal to part of the boundary; it must match across calls for ranks to line up.
- `boundary_cell_at` raises `IndexError` outside `range(count)`; `boundary_rank` raises `ValueError` for non-descendants and interior cells.
- All three work with or without the C++ extension (`boundary_range` uses it when present).

**Ranks refer to traversal order.** They index the sequence produced by `children_on_boundary_faces` and `children_on_boundary_faces_ids`. `boundary_cell_ids` returns the same cells grouped by state instead, so positions there are unrelated — don't mix the two.

## How it is verified

- The unranked sequence `[boundary_cell_at(p, r, i) for i in range(count)]` equals `children_on_boundary_faces(p, r)` **element for element**, for hexagon and pentagon parents, full and partial face sets.
- `rank(unrank(n)) == n`, including inside the 531,438-cell resolution 2 → 13 boundary.
- Shards from `boundary_range` concatenate to the traversal exactly — no gaps, no overlaps, no reordering.
- The totals match the closed form `3^(Δ+1) − 3` independently of any implementation.

See [Boundary Algorithms](algorithms.md) for how this compares with the other approaches.
