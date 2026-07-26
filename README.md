# h3-boundary

**Trace the boundary of an H3 cell — the cells along its edge, the polygon they form, and a polygon guaranteed to contain them.**

[![PyPI](https://img.shields.io/pypi/v/h3-boundary.svg)](https://pypi.org/project/h3-boundary/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<p align="center">
  <img src="https://raw.githubusercontent.com/Khoshkhah/h3-toolkit/master/docs/assets/boundary_children.png"
       alt="A resolution-5 H3 cell with its 78 boundary children at resolution 8 highlighted, and its 265 interior children greyed out"
       width="720">
</p>

```bash
pip install h3-boundary
```

## Why

**Finding a cell's edge cells is expensive the obvious way.** A resolution-2 cell has close to two billion descendants at resolution 13, and only 531,438 of them lie on its edge. Generating everything to filter for the edge is hopeless; h3-boundary walks only the edge itself.

**The hexagon H3 draws for a cell is not its true footprint.** Children straddle that hexagon instead of tiling it — the two shapes differ by 13% of their area. Filter fine-grained data with the hexagon and you silently drop cells along the edge: 1,278 out of 16,807 in the example above. h3-boundary gives you shapes you can filter with safely.

## Usage

### The cells along the edge

Every call takes **two resolutions**: the cell you start from, and the finer resolution you want the answer in. A resolution-6 cell contains 2,401 cells at resolution 10 — of which 240 lie on its edge.

```python
import h3_boundary as h3b

cell = "86283082fffffff"                              # a resolution-6 cell

edge = h3b.children_on_boundary_faces(cell, target_res=10)
len(edge)                                             # 240 resolution-10 cells
```

Ask for a finer `target_res` and you get a finer tracing of the same edge: resolution 12 gives 2,184 cells, resolution 15 gives 59,046. The count is always `3**(target_res - cell_res + 1) - 3`.

For large boundaries, `boundary_cell_ids` returns the same cells as a NumPy `uint64` array — far faster, since it skips building a hex string per cell. It is unordered by default; pass `sort=True` for traversal order.

### Reaching into a huge boundary

You do not have to build a boundary to use it. Any single cell is computable directly, in about 14 microseconds, no matter how large the boundary is.

```python
import h3

big = h3.latlng_to_cell(37.7759, -122.4180, 2)       # a resolution-2 cell
total = 3 ** (13 - 2 + 1) - 3                        # 531,438 edge cells at resolution 13

middle = h3b.boundary_cell_at(big, target_res=13, n=total // 2)   # the middle one, computed directly
h3b.boundary_rank(big, middle)                                    # the inverse — and a membership test
h3b.boundary_range(big, target_res=13, start=0, stop=100)         # the first hundred, to stream or shard
```

Disjoint ranges reassemble into exactly the full traversal, so workers can split a boundary with no coordination.

### The boundary as a polygon

```python
h3b.cell_boundary_from_children(cell, target_res=10)   # GeoJSON Feature — the real outline
```

### A polygon that contains everything

```python
h3b.get_buffered_boundary_polygon(cell, intermediate_res=10)
```

This is the one to filter with: it is guaranteed to contain every descendant of the cell, at any resolution. A convex-hull mode trades a little extra area for roughly 20× the speed.

## Documentation

Guides, benchmarks and the full API: **[khoshkhah.github.io/h3-toolkit](https://khoshkhah.github.io/h3-toolkit/)**

Three runnable notebooks live in [`notebook/`](https://github.com/Khoshkhah/h3-toolkit/tree/master/notebook) — boundary tracing on a map, working with half-million-cell boundaries, and the buffering modes compared.

## Installation details

The package ships as a source distribution. During install it compiles a C++ extension if `cmake`, a C++17 compiler and the Boost headers are available; otherwise it installs pure-Python and every function still works, just more slowly.

```python
import h3_boundary

h3_boundary.get_backend()         # 'cpp' or 'python'
h3_boundary.cpp_geom_available()  # True if the C++ geometry functions are present
```

Development install:

```bash
git clone https://github.com/Khoshkhah/h3-toolkit.git
cd h3-toolkit
conda env create -f environment.yml && conda activate h3-toolkit
pip install -e .

pytest tests/python -v            # includes C++/Python parity tests
```

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](https://github.com/Khoshkhah/h3-toolkit/blob/master/CONTRIBUTING.md).

## License

MIT — see [LICENSE](https://github.com/Khoshkhah/h3-toolkit/blob/master/LICENSE).

Built on [Uber H3](https://h3geo.org/), [Boost.Geometry](https://www.boost.org/doc/libs/release/libs/geometry/) and [pybind11](https://github.com/pybind/pybind11).
