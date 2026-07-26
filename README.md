# h3-boundary

**Work with the boundary of an H3 cell: which cells are on it, what shape it is, and how to contain it safely.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<p align="center">
  <img src="https://raw.githubusercontent.com/Khoshkhah/h3-toolkit/master/docs/assets/boundary_children.png"
       alt="A resolution-5 H3 cell with its 78 boundary children at resolution 8 highlighted, and its 265 interior children greyed out"
       width="720">
</p>

A big H3 cell contains a lot of small ones. This library gives you the ones **on its edge** — without generating the millions inside.

```bash
pip install h3-boundary
```

---

## The three things it does

### 1. Which cells are on the boundary?

```python
import h3_boundary as h3b

cell = '86283082fffffff'                              # resolution 6

h3b.children_on_boundary_faces(cell, 10)              # 240 cells (not the 2.8M inside)
h3b.boundary_cell_ids(cell, 10)                       # same, as a NumPy uint64 array
```

Boundaries get big — a resolution-2 cell has **531,438** of them at resolution 13. So you can also take just the part you need, without building the rest:

```python
h3b.boundary_cell_at(big_cell, 13, 265_717)           # the n-th cell, in ~0.014 ms
h3b.boundary_rank(big_cell, some_cell)                # its position — also a membership test
h3b.boundary_range(big_cell, 13, 1000, 1100)          # a slice, or one worker's share
```

### 2. What shape is the boundary?

```python
h3b.cell_boundary_from_children(cell, 10)             # GeoJSON polygon of the real outline
```

Not the same as H3's own hexagon for that cell — the hexagon is **13% off** the true shape, because the small cells straddle it.

### 3. A shape that safely contains everything?

```python
h3b.get_buffered_boundary_polygon(cell, intermediate_res=10)
```

Use this to **filter**. Test fine-resolution data against a cell's plain hexagon and you silently lose ~7% of it along the edges; this polygon is guaranteed to contain every descendant, at any resolution.

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

`boundary_cell_at` costs the same whether the boundary holds 78 cells or half a million — it computes the answer directly instead of counting to it.

---

## Installation notes

The package ships as a source distribution. On install it compiles a C++ extension if `cmake`, a C++17 compiler and the Boost headers are present; if not, it installs pure-Python and everything still works, just slower.

```python
h3_boundary.get_backend()        # 'cpp' or 'python'
h3_boundary.cpp_geom_available() # True if the C++ geometry functions exist
```

From source:

```bash
git clone https://github.com/Khoshkhah/h3-toolkit.git
cd h3-toolkit
conda env create -f environment.yml && conda activate h3-toolkit
pip install -e .
```

---

## Documentation

Full docs: **[khoshkhah.github.io/h3-toolkit](https://khoshkhah.github.io/h3-toolkit/)**

| Page | What's in it |
|---|---|
| [Concepts](https://khoshkhah.github.io/h3-toolkit/concepts.html) | How boundary tracing works |
| [Boundary Algorithms](https://khoshkhah.github.io/h3-toolkit/algorithms.html) | Four ways to compute boundary cells, compared |
| [Boundary Indexing](https://khoshkhah.github.io/h3-toolkit/indexing.html) | How the n-th cell is computed directly |
| [Buffered Polygons](https://khoshkhah.github.io/h3-toolkit/buffering.html) | Why buffering is needed, and what each mode guarantees |
| [API Reference](https://khoshkhah.github.io/h3-toolkit/api_reference.html) | Every function |

Runnable demos:

```bash
jupyter notebook notebook/demo_generation.ipynb        # tracing and buffering, on a map
jupyter notebook notebook/boundary_indexing_demo.ipynb # large boundaries: ids, indexing, sharding
jupyter notebook notebook/buffered_polygon_demo.ipynb  # the buffering modes compared
```

---

## Development

```bash
mkdir -p build && cd build && cmake -DCMAKE_BUILD_TYPE=Release .. && make -j4
cp _h3_boundary_cpp*.so ../src/python/h3_boundary/

pytest tests/python -v      # includes C++/Python parity tests
./build/h3_toolkit_test
```

See [CONTRIBUTING.md](https://github.com/Khoshkhah/h3-toolkit/blob/master/CONTRIBUTING.md).

## License

MIT — see [LICENSE](https://github.com/Khoshkhah/h3-toolkit/blob/master/LICENSE).

Built on [Uber H3](https://h3geo.org/), [Boost.Geometry](https://www.boost.org/doc/libs/release/libs/geometry/) and [pybind11](https://github.com/pybind/pybind11).
