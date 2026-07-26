---
layout: default
title: Home
nav_order: 1
---

# h3-boundary
{: .no_toc }

Boundary cells and boundary polygons for Uber's H3 grid.
{: .fs-6 .fw-300 }

[Quick start](#quick-start){: .btn .btn-primary .mr-2 }
[View on GitHub](https://github.com/Khoshkhah/h3-toolkit){: .btn }

---

An H3 cell at one resolution contains thousands — or billions — of cells at finer resolutions. h3-boundary works with the ones **on its edge**: it lists them, traces their outline, and builds polygons that safely contain them. Cost scales with the boundary, never with the interior.

![A resolution-5 H3 cell traced at resolution 8: its 78 boundary cells highlighted, its 265 interior cells greyed out](assets/boundary_children.png)

```bash
pip install h3-boundary
```

---

## Quick start

Every function takes two resolutions: the cell you start from, and the finer `target_res` you want the answer in.

```python
import h3
import h3_boundary as h3b

cell = h3.latlng_to_cell(37.7759, -122.4180, 6)          # a resolution-6 cell

# 1. Its boundary cells — descendants at resolution 10 that lie on its edge
edge = h3b.children_on_boundary_faces(cell, target_res=10)
len(edge)                                                # 240, out of 2,401 descendants

# 2. Its true outline, as a GeoJSON Feature
outline = h3b.cell_boundary_from_children(cell, target_res=10)

# 3. A polygon guaranteed to contain every descendant — the one to filter with
safe = h3b.get_buffered_boundary_polygon(cell, intermediate_res=10)
```

Why the third one exists: the plain hexagon H3 draws for a cell is **not** where its descendants sit — they straddle it, as the figure above shows. Filter fine-resolution data with that hexagon and you silently lose the cells along the edge (about 7% of them). The buffered polygon cannot lose any, at any resolution. [Buffered Polygons](buffering.md) has the full story.

## Working at scale

Interiors explode; boundaries stay manageable. A resolution-2 cell has close to two billion descendants at resolution 13, but its boundary there holds only `3**(13 - 2 + 1) - 3` = 531,438 cells — and you never need to build even those to use them:

```python
big = h3.latlng_to_cell(37.7759, -122.4180, 2)
total = 3 ** (13 - 2 + 1) - 3                            # boundary size is a closed form

ids = h3b.boundary_cell_ids(big, target_res=13)          # all of them, as a uint64 array, in ~4 ms
mid = h3b.boundary_cell_at(big, target_res=13, n=total // 2)   # any single one, in microseconds
h3b.boundary_rank(big, mid)                              # the inverse — also a membership test
h3b.boundary_range(big, target_res=13, start=0, stop=100)      # any slice — stream it, or shard it
```

Disjoint slices reassemble into exactly the full boundary, so parallel workers need no coordination. [Boundary Indexing](indexing.md) explains how single cells are computed directly.

---

## Performance

Measured on Linux / Python 3.14; the C++ extension is used automatically when present.

| Operation | Boundary size | Time |
|---|---|---|
| Boundary cells — `children_on_boundary_faces` | 240 | 0.02 ms |
| Boundary cells, large — `boundary_cell_ids` | 531,438 | 4 ms |
| One cell by index — `boundary_cell_at` | any | 0.014 ms |
| Boundary polygon — `cell_boundary_from_children` | 240 | 1.6 ms |
| Buffered polygon, accurate | 240 | 6 ms |
| Buffered polygon, convex hull | 240 | 0.4 ms |

`boundary_cell_at` costs the same whether the boundary holds 78 cells or half a million.

---

## Guides

| Page | What's in it |
|---|---|
| [Interactive Demo](demo.html) | Boundary tracing and buffering, on a map |
| [Concepts](concepts.md) | How boundary tracing works |
| [Boundary Algorithms](algorithms.md) | Four ways to compute boundary cells, compared |
| [Boundary Indexing](indexing.md) | How the n-th boundary cell is computed directly |
| [Buffered Polygons](buffering.md) | Why buffering is needed, and what each mode guarantees |
| [API Reference](api_reference.md) | Every function |

## Notebooks

Three runnable demos live in [`notebook/`](https://github.com/Khoshkhah/h3-toolkit/tree/master/notebook) — clone the repo and open them with `jupyter notebook`:

| Notebook | What it shows |
|---|---|
| [`demo_generation.ipynb`](https://github.com/Khoshkhah/h3-toolkit/blob/master/notebook/demo_generation.ipynb) | Boundary tracing and buffering step by step, each stage drawn on a map |
| [`boundary_indexing_demo.ipynb`](https://github.com/Khoshkhah/h3-toolkit/blob/master/notebook/boundary_indexing_demo.ipynb) | Large boundaries: bulk ids, reaching one cell directly, sharding |
| [`buffered_polygon_demo.ipynb`](https://github.com/Khoshkhah/h3-toolkit/blob/master/notebook/buffered_polygon_demo.ipynb) | The three buffering modes compared, with a containment check for each |

## Installation

Ships as a source distribution. During install it compiles a C++ extension if `cmake`, a C++17 compiler and the Boost headers are present; otherwise it installs pure-Python and every function still works, just more slowly. Same results either way, verified by a parity test suite.

```python
import h3_boundary

h3_boundary.get_backend()        # 'cpp' or 'python'
h3_boundary.cpp_geom_available() # True if the C++ geometry functions exist
```

## License

MIT — see [LICENSE](https://github.com/Khoshkhah/h3-toolkit/blob/master/LICENSE).
