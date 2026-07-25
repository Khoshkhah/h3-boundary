# h3-boundary

**H3 cell boundary tracing and buffered polygons across resolution hierarchies, with optional C++ acceleration.**

h3-boundary extends [Uber's H3 library](https://h3geo.org/) with efficient algorithms for computing cell boundaries across resolution hierarchies and generating buffered polygons that guarantee containment of all child cells.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<p align="center">
  <img src="https://raw.githubusercontent.com/Khoshkhah/h3-toolkit/master/docs/assets/boundary_children.png"
       alt="A resolution-5 H3 cell with its 78 boundary children at resolution 8 highlighted, and its 265 interior children greyed out"
       width="720">
</p>

```python
children = h3b.children_on_boundary_faces(cell, target_res)   # just the ring
```

## Features

- **Boundary-only traversal**: enumerate the children on a parent's boundary without materializing its interior — cost scales with the perimeter, not the area
- **Face tracing**: track which parent/ancestor faces a cell touches, in both directions of the hierarchy
- **Buffered polygons**: fast (convex hull) or accurate (union) polygons guaranteed to contain all fine-resolution children
- **Dual backend**: pure Python (Shapely) everywhere, with a pybind11/Boost.Geometry C++ extension compiled automatically when a toolchain is available — same results, verified by a parity test suite (including pentagons)

| Function | Description |
|----------|-------------|
| `children_on_boundary_faces` | Boundary children of a cell, as hex strings |
| `boundary_cell_ids` | The same cells as a NumPy `uint64` array — the fast path for big boundaries |
| `boundary_cell_at` / `boundary_rank` | The *n*-th boundary cell directly, and back again, in O(depth) |
| `boundary_range` | Stream or shard a slice of a boundary |
| `trace_cell_to_ancestor_faces` | Which ancestor faces a cell touches |
| `cell_to_coarsest_ancestor_on_faces` | Coarsest ancestor still touching given faces |
| `cell_boundary_from_children` | Merge boundary children into a single polygon |
| `get_buffered_boundary_polygon` | Buffered polygon with configurable accuracy |
| `get_buffered_h3_polygon` | Simple buffered cell polygon |

## Documentation

Visit the **[Full Documentation](https://khoshkhah.github.io/h3-toolkit/)** to explore:
- **Interactive Demo**: Visualize boundary tracing and buffering
- **Concepts**: Learn about H3 hierarchy and face mappings
- **API Reference**: Detailed documentation of all functions

You can also run the demos locally:
```bash
jupyter notebook notebook/demo_generation.ipynb        # boundary tracing & buffering, mapped
jupyter notebook notebook/boundary_indexing_demo.ipynb # large boundaries: ids, indexing, sharding
jupyter notebook notebook/buffered_polygon_demo.ipynb  # buffered polygon modes compared
```

## Installation

```bash
pip install h3-boundary
```

The package is published as a source distribution. During installation the C++ extension is compiled automatically if `cmake`, a C++17 compiler, the Boost headers, and network access (the H3 sources are fetched at build time) are available. If any of these are missing, installation still succeeds and the package runs pure-Python — check with:

```python
import h3_boundary
print(h3_boundary.get_backend())        # 'cpp' or 'python'
print(h3_boundary.cpp_geom_available()) # True if C++ geometry (*_cpp) exists
```

### From source

```bash
git clone https://github.com/Khoshkhah/h3-toolkit.git
cd h3-toolkit

# Recommended environment (conda)
conda env create -f environment.yml
conda activate h3-toolkit

pip install -e .
```

## Quick Start

```python
import h3_boundary as h3b

cell = '86283082fffffff'  # Resolution 6 cell in San Francisco

# Children on the parent's boundary at resolution 10 (~240 cells,
# instead of ~2.8 million interior children)
children = h3b.children_on_boundary_faces(cell, 10)

# Merged boundary polygon (GeoJSON Feature)
boundary = h3b.cell_boundary_from_children(cell, 10)

# Buffered polygon guaranteed to contain all res-15 children
buffered = h3b.get_buffered_boundary_polygon(cell, intermediate_res=10)
print(buffered['properties']['buffer_meters'])
```

### Large boundaries

Boundaries grow fast — a resolution-2 cell has 531,438 boundary children at resolution 13 (the closed form is `3**(depth+1) - 3`). Two tools make that practical:

```python
import h3

big = h3.latlng_to_cell(37.7759, -122.4180, 2)   # 531,438 boundary children at res 13

# The whole set, as 64-bit ids — ~1.4 ms for half a million cells.
# Skips hex-string formatting, which otherwise dominates.
ids = h3b.boundary_cell_ids(big, 13)
ids = h3b.boundary_cell_ids(big, 13, sort=True)   # traversal order, if you need it

# Or reach in without generating anything: O(depth), independent of size
one    = h3b.boundary_cell_at(big, 13, 265_717)   # the 265,717th cell, in ~0.01 ms
n      = h3b.boundary_rank(big, one)              # → 265717 (and validates membership)
window = list(h3b.boundary_range(big, 13, 1000, 1100))   # a 100-cell slice
```

`boundary_range` also makes sharding trivial — disjoint ranges reassemble into exactly the traversal's output, so workers need no coordination. See [Boundary Indexing](https://khoshkhah.github.io/h3-toolkit/indexing.html) for how this works and [Boundary Algorithms](https://khoshkhah.github.io/h3-toolkit/algorithms.html) for the comparison of approaches.

### Buffered polygon modes (C++ extension)

```python
# Fast mode (convex hull) — ~0.4 ms
fast_poly = h3b.get_buffered_boundary_polygon_cpp(cell, 10, use_convex_hull=True)

# Accurate mode (union of boundary cells) — default
accurate_poly = h3b.get_buffered_boundary_polygon_cpp(cell, 10)
```

All geometry functions exist in two flavors returning identical GeoJSON: plain (pure Python/Shapely, always available) and `*_cpp` (Boost.Geometry, only when the extension compiled — guard with `cpp_geom_available()`).

## Performance

Measured on a resolution-6 cell with `intermediate_res=10` (Linux, Python 3.14):

| Function | Python | C++ |
|----------|--------|-----|
| `children_on_boundary_faces` | 0.14 ms | 0.02 ms |
| `cell_boundary_from_children` | 1.3 ms | 2.5 ms |
| `get_buffered_boundary_polygon` (accurate) | 5.9 ms | 7.0 ms |
| `get_buffered_boundary_polygon` (fast hull) | — | 0.4 ms |
| `get_buffered_h3_polygon` | 0.13 ms | 0.06 ms |

The C++ backend shines for face tracing / boundary enumeration and the fast hull mode; for polygon merging the pure-Python path is equally fast because it delegates to H3's native `cells_to_h3shape`.

Producing a whole boundary, where the cell count is what matters:

| Boundary size | `children_on_boundary_faces` (hex) | `boundary_cell_ids(sort=True)` | `boundary_cell_ids()` |
|---|---|---|---|
| 6,558 | 0.56 ms | 0.09 ms | **0.02 ms** |
| 59,046 | 5.8 ms | 0.65 ms | **0.11 ms** |
| 531,438 | 57 ms | 8.2 ms | **1.4 ms** |

Two things account for the gap: hex strings cost a `format()` per cell (~80% of the time at scale), and unordered output can be produced a whole level at a time with array arithmetic rather than cell by cell. Single-cell access via `boundary_cell_at` is ~0.011 ms regardless of boundary size.

## How It Works

### Boundary face tracing

H3 cells have 6 faces (edges), numbered 1–6. When a cell is subdivided, child faces map to parent faces depending only on the resolution parity (H3's aperture-7 grid alternates orientation between levels) and the child position (0–6, where 0 is the interior center child). h3-boundary encodes these relationships in precomputed lookup tables — forward tables to trace a cell up the hierarchy, reversed tables to enumerate boundary children down it, with separate tables for pentagons. This is what lets it walk only the boundary subtree.

### Buffered polygons

Two modes:

1. **Convex hull (fast)**: hull of all boundary-cell vertices, then buffer
2. **Union (accurate)**: union of all boundary-cell polygons, then buffer

The buffer distance defaults to 100% of the intermediate-resolution edge length, which guarantees the result contains all res-15 children of the cell.

## Project Structure

```
h3-toolkit/                      # repository (PyPI package: h3-boundary)
├── CMakeLists.txt               # C++ build (fetches H3, links Boost)
├── pyproject.toml               # package metadata
├── setup.py                     # CMake <-> setuptools bridge
├── src/
│   ├── cpp/                     # C++ core (h3_toolkit.hpp / .cpp)
│   ├── bindings/                # pybind11 module _h3_boundary_cpp
│   └── python/h3_boundary/      # Python package
│       ├── __init__.py          # backend selection + C++ GeoJSON wrappers
│       ├── utils.py             # face tracing (pure Python reference)
│       └── geom.py              # geometry (Shapely)
├── tests/
│   ├── python/test_utils.py     # unit tests
│   ├── python/test_parity.py    # C++ vs Python parity suite
│   └── cpp/                     # C++ smoke test
├── benchmarks/                  # Python + C++ benchmarks
├── notebook/                    # Jupyter demos (tracing, indexing, buffering)
└── docs/                        # documentation site
```

## Development

```bash
# Build the C++ extension
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j4
cp _h3_boundary_cpp*.so ../src/python/h3_boundary/

# Run tests
pytest tests/python -v
./build/h3_toolkit_test
```

See [CONTRIBUTING.md](https://github.com/Khoshkhah/h3-toolkit/blob/master/CONTRIBUTING.md) for guidelines.

## License

MIT License — see [LICENSE](https://github.com/Khoshkhah/h3-toolkit/blob/master/LICENSE).

## Acknowledgments

- [Uber H3](https://h3geo.org/) — the H3 hexagonal hierarchical spatial index
- [Boost.Geometry](https://www.boost.org/doc/libs/release/libs/geometry/) — polygon operations
- [pybind11](https://github.com/pybind/pybind11) — Python bindings for C++
