---
layout: default
title: Boundary Algorithms
nav_order: 5
---

# Boundary Algorithms
{: .no_toc }

Four ways to compute the boundary children of an H3 cell — what each one does, when to use it, and how they compare.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## The problem

Given a parent cell at some resolution and a finer target resolution, find the cells at the target resolution that lie **on the parent's boundary**.

The naive approach — generate every descendant and keep the ones touching the edge — is hopeless at depth: a resolution-3 cell has 823,543 descendants at resolution 10, but only 6,558 of them are on the boundary. Everything below is about reaching those 6,558 without paying for the other 817,000.

```
        ● ● ● ● ●            ● = boundary child (what we want)
      ● ○ ○ ○ ○ ○ ●          ○ = interior child (99.2% of the cells,
     ● ○ ○ ○ ○ ○ ○ ●              and none of the answer)
      ● ○ ○ ○ ○ ○ ●
        ● ● ● ● ●
```

---

## Which one should I use?

| If you want to… | Use | Why |
|---|---|---|
| Get the whole boundary | `children_on_boundary_faces` | Fastest; the default |
| Get one cell, or a random sample | `boundary_cell_at` | O(depth), ignores boundary size entirely |
| Know if a cell is on the boundary, and where | `boundary_rank` | O(depth) membership test + position |
| Split the work across workers | `boundary_range` | Each worker streams its own slice, no coordination |
| Just the count | `3**(depth+1) - 3` | Closed form, no computation at all |

Everything else on this page is background.

---

## 1. Table-driven traversal (the default)

**`children_on_boundary_faces(parent, target_res)`**

Walks *down* from the parent, but only into the parts of the tree that stay on the boundary.

The key fact: when a cell is subdivided into 7 children, which child touches which parent face depends on only two things — the **resolution parity** (H3's grid alternates orientation between levels) and the **child position** (0–6, where 0 is the center child, always interior). That relationship is fixed, so it is precomputed into lookup tables.

Each step is then a table lookup: "I am on parent faces {2, 5}; which of my children stay on the boundary, and on which faces?" Children that map to no face are dropped along with their entire subtree — that is where the 817,000 interior cells disappear.

- **Cost:** O(number of boundary cells) — optimal, since it must at least emit them
- **Trade-off:** correctness depends on the lookup tables being right (hence approaches 2 and 4 below, and the property tests)

## 2. Boundary walk

**`_h3_boundary_cpp.boundary_walk(parent, target_res)`** — verification tool, not part of the public API.

Uses no tables at all. Instead:

1. Snap a corner of the parent's polygon to the target resolution to land near the boundary.
2. Step to the first cell that is *inside* the parent and has a neighbor *outside* it — that is a boundary cell by definition.
3. Flood along the wall: from each boundary cell, its boundary neighbors are also boundary cells; keep going until the ring closes.

The membership test is pure arithmetic on the 64-bit index (a cell is a descendant iff its leading digits match the parent's), so "inside or outside?" costs nanoseconds.

One optimization matters: instead of testing each neighbor by computing *its* neighbors, the walk **certifies** them. The 6 neighbors come back in rotational order, so an inside neighbor sitting next to an outside neighbor must share an edge with that outside cell — it is boundary by construction. That means exactly one neighbor lookup per boundary cell.

- **Cost:** O(number of boundary cells), like the traversal, but with bigger constants (neighbor computation at runtime vs. a precomputed table lookup)
- **Why it exists:** it shares *no code and no tables* with approach 1, so when both agree, the tables are almost certainly right — including around pentagons

## 3. Rank / unrank indexing

**`boundary_cell_at(parent, target_res, n)`** · **`boundary_rank(parent, cell)`** · **`boundary_range(parent, target_res, start, stop)`**

The boundary children form a **positional number system**. Each one is the parent's index plus a string of base-7 digits, and a digit string is a boundary cell exactly when a small state machine accepts it — the state being "which parent faces am I still touching", with the lookup tables as its transitions.

Count how many valid digit strings extend from each state (a small recurrence) and you can convert between a **position** and a **cell**, the same way you convert a number to its digits:

```python
boundary_cell_at(parent, 13, 265_717)   # the 265,717th boundary cell — computed directly
boundary_rank(parent, some_cell)        # → 265_717, and raises if it isn't on the boundary
```

Neither one enumerates anything: they cost O(depth), so reaching into a 531,438-cell boundary is as cheap as a 240-cell one.

`boundary_range` is the bulk form: it seeks to `start`, then streams forward, skipping whole subtrees that fall before the slice. Concatenating disjoint ranges reproduces the traversal exactly, which is what makes sharding safe:

```python
# Worker k of n — no coordination, no shared state
for cell in boundary_range(parent, 13, bounds[k], bounds[k + 1]):
    process(cell)
```

- **Cost:** O(depth) per random access; O(depth) seek + O(1) per cell when streaming
- **Trade-off:** for plain full generation it is not faster than approach 1 — its value is the access patterns approach 1 cannot express
- **Full explanation:** [Boundary Indexing](indexing.md) walks through the counting formulas and a worked example

## 4. Brute force

Generate all 7^depth descendants, keep those with a neighbor outside the parent. Used only as ground truth in tests, since it is the one approach whose correctness is self-evident. Cost grows with the parent's *area*, so it is unusable past shallow depths.

---

## Benchmarks

Measured on Linux / Python 3.14, generating the **full** boundary. `*-cpp` rows use the compiled extension; `*-py` rows the pure-Python fallback.

| Approach | res 6→10 (240 cells) | res 3→10 (6,558) | res 2→11 (59,046) |
|---|---|---|---|
| 1. table-cpp | 0.02 ms | 0.88 ms | 5.7 ms |
| 1. table-py | 0.16 ms | 4.0 ms | 41 ms |
| 2. walk-cpp | 0.04 ms | 1.3 ms | 14 ms |
| 2. walk-py | 0.92 ms | 20 ms | 200 ms |
| 3. range-cpp | 0.04 ms | 0.55 ms | 5.6 ms |
| 3. range-py | 0.46 ms | 8.4 ms | 69 ms |
| 4. brute force | 7.7 ms | 3,100 ms | ~150 s (extrapolated) |

And the operations only approach 3 offers, where boundary size stops mattering:

| Operation | res 3→10 | res 2→13 (531,438 cells) |
|---|---|---|
| One cell at position *n* | 0.011 ms | 0.011 ms |
| A 100-cell slice | 0.019 ms | 0.025 ms |

All figures are measured except the last brute-force cell, which is extrapolated from its (linear in descendant count) cost at the smaller depths — running it takes about two and a half minutes.

Reading the table:

- **The C++ extension is worth ~8× on this work.** Without it everything still runs, just slower — the pure-Python column is the fallback path.
- **`range-cpp` matches or beats `table-cpp`** because it generates child indexes arithmetically rather than calling into H3 per node.
- **The walk's gap is constants, not complexity.** Same asymptotics; it computes at runtime what the tables precomputed.
- **Brute force is in a different class.** It scales with the parent's area, so it grows 7× per level while the others grow ~3×: by res 2→11 it is 27,000× slower than the traversal.
- **Random access is flat.** 0.011 ms whether the boundary has 6 thousand cells or half a million — that is the O(depth) behavior.

---

## The mathematics

The boundary cell count has an exact closed form:

$$B(\Delta) = 3^{\Delta+1} - 3 \quad \text{(hexagon parent)} \qquad B(\Delta) = \tfrac{5}{2}\left(3^{\Delta} - 1\right) \quad \text{(pentagon parent)}$$

with Δ = target_res − parent_res. So depth 1 → 6 cells, depth 4 → 240, depth 7 → 6,558, depth 12 → 531,438.

**Why 3?** Each level shrinks cells by √7 ≈ 2.646. If the boundary were a smooth curve its cell count would grow by that factor. It grows by exactly 3 because the boundary is a fractal — a Gosper island — of dimension

$$d = \frac{\ln 3}{\ln \sqrt7} = 2\log_7 3 \approx 1.1292, \qquad (\sqrt7)^{\,d} = 3$$

This also explains a tempting idea that does **not** work: "take the center child, measure the distance to the boundary, and take that ring." A ring is one-dimensional; the boundary is not. Measured at depth 7, the true boundary spans grid distances 457 to 571 from the center child — 114 rings, roughly ±10% of the radius — and no cheap estimate bounds it reliably. A corrected version (take the whole band, filter by parent membership) is correct but touches a third of the parent's area, making it ~700× slower than the traversal.

The polygon has a matching pattern: every boundary edge becomes 3 edges one level down, so the merged outline has 6·3^Δ edges — 163 vertices at depth 3, 487 at depth 4, exactly as the demo data shows.

---

## How correctness is enforced

The lookup tables are the one thing everything else rests on, so they are checked from three independent directions:

1. **Backend parity** — the C++ and pure-Python implementations must return identical results (including pentagon parents, partial face sets, and buffered polygons).
2. **The boundary walk** — approach 2 recomputes the answer geometrically, sharing no tables with approach 1.
3. **The closed-form counts** — pure combinatorics, derived from the fractal dimension, sharing nothing with any implementation.

Plus brute force as ground truth on small cases, and `rank(unrank(n)) == n` round-trips for the indexing functions. A wrong table entry would have to fool all of them simultaneously.

The comparison in this page is reproducible:

```bash
PYTHONPATH=src/python python benchmarks/compare_algorithms.py
```
