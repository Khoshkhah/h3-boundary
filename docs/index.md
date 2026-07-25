---
layout: default
title: Home
nav_order: 1
---

# h3-boundary Documentation

H3 cell boundary tracing and buffered polygons across resolution hierarchies, with optional C++ acceleration.

## Quick Links

- [Interactive Demo](demo.html)
- [API Reference](api_reference.md)
- [Concepts](concepts.md)
- [Boundary Algorithms](algorithms.md) — the four approaches, compared
- [Boundary Indexing](indexing.md) — compute the n-th boundary cell directly
- [GitHub Repository](https://github.com/Khoshkhah/h3-toolkit)

## Overview

h3-boundary extends Uber's H3 library with efficient algorithms for computing cell boundaries across resolution hierarchies and generating buffered polygons.

![A resolution-5 H3 cell with its 78 boundary children at resolution 8 highlighted, and its 265 interior children greyed out](assets/boundary_children.png)

### Key Features

**Boundary-only traversal**
- Enumerate boundary children without materializing the parent's interior
- Cost scales with the perimeter, not the area

**Dual backend**
- Pure Python (Shapely) everywhere; pybind11/Boost.Geometry C++ extension compiled automatically when a toolchain is available
- Identical results, enforced by a parity test suite (including pentagons)
- GeoJSON-compatible output

## Installation

```bash
pip install h3-boundary
```

The C++ extension compiles automatically when `cmake`, a C++17 compiler, and the Boost headers are available; otherwise the package installs pure-Python. For development:

```bash
git clone https://github.com/Khoshkhah/h3-toolkit.git
cd h3-toolkit
conda env create -f environment.yml
conda activate h3-toolkit
pip install -e .
```

## Quick Start

```python
import h3_boundary as h3b

cell = '86283082fffffff'  # Resolution 6 cell

# Get boundary children
children = h3b.children_on_boundary_faces(cell, 10)
print(f"Found {len(children)} boundary children")

# …or as a NumPy uint64 array — much faster for large boundaries
ids = h3b.boundary_cell_ids(cell, 10)                # unordered
ids = h3b.boundary_cell_ids(cell, 10, sort=True)     # traversal order

# Reach one cell directly, without generating the rest (O(depth))
h3b.boundary_cell_at(cell, 10, 100)

# Buffered polygon guaranteed to contain all res-15 children
result = h3b.get_buffered_boundary_polygon(cell, intermediate_res=10)

# Returns GeoJSON Feature
print(result['properties']['buffer_meters'])
```

## Performance

| Function | Python | C++ |
|----------|--------|-----|
| `children_on_boundary_faces` | 0.14ms | 0.02ms |
| `cell_boundary_from_children` | 1.3ms | 2.5ms |
| `get_buffered_boundary_polygon` (accurate) | 5.9ms | 7.0ms |
| `get_buffered_boundary_polygon` (fast hull) | — | 0.4ms |

Resolution-6 cell, intermediate resolution 10. See the [API Reference](api_reference.md) for details.

## Documentation

- [API Reference](api_reference.md) - Complete function reference
- [Concepts](concepts.md) - How boundary tracing works
- [Boundary Algorithms](algorithms.md) - Four approaches introduced and benchmarked
- [Boundary Indexing](indexing.md) - Direct access to the n-th boundary cell, explained from scratch

## License

MIT License - see [LICENSE](https://github.com/Khoshkhah/h3-toolkit/blob/master/LICENSE)
