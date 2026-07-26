# H3-Boundary

**Boundary cells and boundary polygons for Uber's H3 grid.**

[![PyPI](https://img.shields.io/pypi/v/h3-boundary.svg)](https://pypi.org/project/h3-boundary/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An H3 cell at one resolution contains thousands — or billions — of cells at finer resolutions. H3-Boundary works with the ones **on its edge**: it lists them, traces their outline, and builds polygons that safely contain them. Cost scales with the boundary, never with the interior.

<p align="center">
  <img src="https://raw.githubusercontent.com/Khoshkhah/h3-boundary/master/docs/assets/boundary_children.png"
       alt="A resolution-5 H3 cell traced at resolution 8: its 78 boundary cells highlighted, its 265 interior cells greyed out"
       width="720">
</p>

<p align="center"><em>A resolution-5 cell traced at resolution 8: 78 boundary cells computed, 265 interior cells never generated.</em></p>

```bash
pip install h3-boundary
```

## Quick start

Start from any H3 cell. Here we index downtown San Francisco at resolution 6 — a district-sized cell of about 36 km² — using `latlng_to_cell` from [h3-py](https://uber.github.io/h3-py/), which H3-Boundary already depends on.

```python
import h3
import h3_boundary as h3b

cell = h3.latlng_to_cell(lat=37.7759, lng=-122.4180, res=6)

# 1. Its boundary cells: the descendants at resolution 10 (block-sized cells)
#    that lie on its edge
edge = h3b.children_on_boundary_faces(cell, target_res=10)
len(edge)                                                # 240, out of 2,401 descendants

# 2. Its true outline, as a GeoJSON Feature
outline = h3b.cell_boundary_from_children(cell, target_res=10)

# 3. A polygon guaranteed to contain every descendant — the one to filter with
safe = h3b.get_buffered_boundary_polygon(cell, intermediate_res=10)
```

Why the third one exists: the plain hexagon H3 draws for a cell is **not** where its descendants sit — they straddle it, as the figure above shows. Filter fine-resolution data with that hexagon and you silently lose the cells along the edge (about 7% of them). The buffered polygon cannot lose any, at any resolution.

## Working at scale

Interiors explode; boundaries stay manageable. A resolution-2 cell has close to two billion descendants at resolution 13, but its boundary there holds only `3**(13 - 2 + 1) - 3` = 531,438 cells — and you never need to build even those to use them:

```python
big = h3.latlng_to_cell(lat=37.7759, lng=-122.4180, res=2)   # a country-sized cell (~87,000 km²)
total = 3 ** (13 - 2 + 1) - 3                                # boundary size is a closed form

ids = h3b.boundary_cell_ids(big, target_res=13)          # all of them, as a uint64 array, in ~4 ms
mid = h3b.boundary_cell_at(big, target_res=13, n=total // 2)   # any single one, in microseconds
h3b.boundary_rank(big, mid)                              # the inverse — also a membership test
h3b.boundary_range(big, target_res=13, start=0, stop=100)      # any slice — stream it, or shard it
```

Disjoint slices reassemble into exactly the full boundary, so parallel workers need no coordination.

## Output formats

- **Cells**: hex strings (`children_on_boundary_faces`) or NumPy `uint64` arrays (`boundary_cell_ids`) — ready for h3-py, dataframes, or database joins.
- **Polygons**: GeoJSON Features — ready for folium, Leaflet, or PostGIS.

The package ships as a source distribution: it compiles a C++ extension during install when a toolchain is available (`cmake`, C++17, Boost headers) and falls back to pure Python otherwise. Same results either way, verified by a parity test suite.

## Documentation

**[khoshkhah.github.io/h3-boundary](https://khoshkhah.github.io/h3-boundary/)** — concepts, algorithm comparisons, benchmarks, and the full API.

Three runnable notebooks live in [`notebook/`](https://github.com/Khoshkhah/h3-boundary/tree/master/notebook): boundary tracing on a map, working with half-million-cell boundaries, and the buffering modes compared.

## Development

```bash
git clone https://github.com/Khoshkhah/h3-boundary.git
cd h3-boundary
conda env create -f environment.yml && conda activate h3-boundary
pip install -e .
pytest tests/python -v
```

Contributions welcome — see [CONTRIBUTING.md](https://github.com/Khoshkhah/h3-boundary/blob/master/CONTRIBUTING.md).

## License

MIT — see [LICENSE](https://github.com/Khoshkhah/h3-boundary/blob/master/LICENSE). Built on [Uber H3](https://h3geo.org/), [Boost.Geometry](https://www.boost.org/doc/libs/release/libs/geometry/) and [pybind11](https://github.com/pybind/pybind11).
