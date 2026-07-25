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
- [GitHub Repository](https://github.com/Khoshkhah/h3-toolkit)

## Overview

h3-boundary extends Uber's H3 library with efficient algorithms for computing cell boundaries across resolution hierarchies and generating buffered polygons.

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

## License

MIT License - see [LICENSE](https://github.com/Khoshkhah/h3-toolkit/blob/master/LICENSE)
