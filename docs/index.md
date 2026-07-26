---
layout: default
title: Home
nav_order: 1
---

# h3-boundary
{: .no_toc }

Work with the boundary of an H3 cell: which cells are on it, what shape it is, and how to contain it safely.
{: .fs-6 .fw-300 }

[Get started](#the-three-things-it-does){: .btn .btn-primary .mr-2 }
[View on GitHub](https://github.com/Khoshkhah/h3-toolkit){: .btn }

---

A big H3 cell contains a lot of small ones — a resolution-2 cell has close to two billion descendants at resolution 13. This library gives you the ones **on its edge** (531,438 of them, here) without generating the rest.

![A resolution-5 H3 cell with its 78 boundary children at resolution 8 highlighted, and its 265 interior children greyed out](assets/boundary_children.png)

```bash
pip install h3-boundary
```

---

## The three things it does

### 1. Which cells are on the boundary?

```python
import h3_boundary as h3b

cell = '86283082fffffff'                    # resolution 6

h3b.children_on_boundary_faces(cell, 10)    # the 240 edge cells, of 2,401 descendants
h3b.boundary_cell_ids(cell, 10)             # the same cells as uint64, unordered — much faster
h3b.boundary_cell_ids(cell, 10, sort=True)  # ...in the same order as the first call
```

Boundaries grow fast — a resolution-2 cell has 531,438 of them at resolution 13 — so you can also take only the part you need:

```python
import h3

big   = h3.latlng_to_cell(37.7759, -122.4180, 2)   # a resolution-2 cell
total = 3 ** (13 - 2 + 1) - 3                      # 531,438 edge cells — a closed form

middle = h3b.boundary_cell_at(big, 13, total // 2) # the middle cell, computed directly
h3b.boundary_rank(big, middle)                     # the inverse — also a membership test
h3b.boundary_range(big, 13, 0, 100)                # the first hundred — a slice, or a worker's share
```

→ [Boundary Algorithms](algorithms.md) compares the ways of computing these; [Boundary Indexing](indexing.md) explains how a single cell is reached directly.

### 2. What shape is the boundary?

```python
h3b.cell_boundary_from_children(cell, 10)   # GeoJSON polygon of the real outline
```

This is not H3's own hexagon for the cell. The small cells straddle that hexagon rather than tiling it, so the two shapes differ by **13% of their area**.

### 3. A shape that safely contains everything?

```python
h3b.get_buffered_boundary_polygon(cell, intermediate_res=10)
```

Use this to **filter**. Because of that straddle, testing fine-resolution data against the plain hexagon silently drops the cells on the edge — **1,278 of 16,807** at resolution 11, about 7.6%. This polygon contains every descendant, at any resolution.

→ [Buffered Polygons](buffering.md) explains why, and what each mode guarantees.

---

## Performance

Resolution-6 cell, Linux, Python 3.14. The C++ extension is used automatically when present.

| | Cells | Time |
|---|---|---|
| Boundary cells — `children_on_boundary_faces` | 240 | 0.02 ms |
| Boundary cells, large — `boundary_cell_ids` | 531,438 | 4 ms |
| One cell by index — `boundary_cell_at` | — | 0.014 ms |
| Boundary polygon — `cell_boundary_from_children` | 240 | 1.6 ms |
| Buffered polygon, accurate | 240 | 6 ms |
| Buffered polygon, convex hull | 240 | 0.4 ms |

`boundary_cell_at` costs the same whether the boundary holds 78 cells or half a million.

---

## Documentation

| Page | What's in it |
|---|---|
| [Interactive Demo](demo.html) | Boundary tracing and buffering, on a map |
| [Concepts](concepts.md) | How boundary tracing works |
| [Boundary Algorithms](algorithms.md) | Four ways to compute boundary cells, compared |
| [Boundary Indexing](indexing.md) | How the n-th cell is computed directly |
| [Buffered Polygons](buffering.md) | Why buffering is needed, and what each mode guarantees |
| [API Reference](api_reference.md) | Every function |

## Notebooks

Three runnable demos live in [`notebook/`](https://github.com/Khoshkhah/h3-toolkit/tree/master/notebook) — clone the repo and open them with `jupyter notebook`:

| Notebook | What it shows |
|---|---|
| [`demo_generation.ipynb`](https://github.com/Khoshkhah/h3-toolkit/blob/master/notebook/demo_generation.ipynb) | Boundary tracing and buffering step by step, each stage drawn on a map |
| [`boundary_indexing_demo.ipynb`](https://github.com/Khoshkhah/h3-toolkit/blob/master/notebook/boundary_indexing_demo.ipynb) | Large boundaries: bulk ids, reaching one cell directly, sharding — and 300 cells sampled from a 531,438-cell boundary without generating the rest |
| [`buffered_polygon_demo.ipynb`](https://github.com/Khoshkhah/h3-toolkit/blob/master/notebook/buffered_polygon_demo.ipynb) | The three buffering modes compared, with a containment check for each |

## Installation

Ships as a source distribution. On install it compiles a C++ extension if `cmake`, a C++17 compiler and the Boost headers are present; otherwise it installs pure-Python and everything still works, just slower.

```python
import h3_boundary

h3_boundary.get_backend()        # 'cpp' or 'python'
h3_boundary.cpp_geom_available() # True if the C++ geometry functions exist
```

## License

MIT — see [LICENSE](https://github.com/Khoshkhah/h3-toolkit/blob/master/LICENSE).
