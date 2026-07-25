---
layout: default
title: API Reference
nav_order: 3
---

# h3-boundary API Reference

Complete API documentation for h3-boundary.

## Table of Contents

- [Core Functions](#core-functions)
- [Geometry Functions](#geometry-functions)
- [Utility Functions](#utility-functions)
- [C++ API](#c-api)

---

## Core Functions

These functions have both Python and C++ implementations. The C++ version is used automatically when available.

### `trace_cell_to_ancestor_faces`

```python
trace_cell_to_ancestor_faces(
    h: str,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6},
    res_parent: int = None
) -> Set[int]
```

Traces which boundary faces of an ancestor cell the given cell lies on.

**Parameters:**
- `h`: H3 cell index (string)
- `input_faces`: Set of face numbers {1-6} to trace
- `res_parent`: Resolution of ancestor. If None, uses immediate parent

**Returns:** Set of face numbers at the ancestor's boundary

**Example:**
```python
from h3_boundary import trace_cell_to_ancestor_faces

cell = '8928308280fffff'  # Resolution 9
faces = trace_cell_to_ancestor_faces(cell, {1, 2, 3, 4, 5, 6}, res_parent=6)
print(faces)  # e.g., {2, 5}
```

---

### `trace_cell_to_parent_faces`

```python
trace_cell_to_parent_faces(
    h: str,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6}
) -> Set[int]
```

Convenience function that traces to the immediate parent (res - 1).

---

### `children_on_boundary_faces`

```python
children_on_boundary_faces(
    parent: str,
    target_res: int,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6}
) -> List[str]
```

Returns all children at `target_res` that lie on the parent's specified boundary faces.

**Parameters:**
- `parent`: Parent H3 cell index
- `target_res`: Resolution to descend to (parent resolution ≤ target_res ≤ 15; equal resolution returns `[parent]`)
- `input_faces`: Set of face numbers {1-6} to filter by

**Returns:** List of child H3 cell indices

**Raises:** `ValueError` if `target_res` is below the parent's resolution or above 15.

**Example:**
```python
from h3_boundary import children_on_boundary_faces

children = children_on_boundary_faces('86283082fffffff', 10)
print(f"Found {len(children)} boundary children")  # ~240 cells
```

**Performance:**
- Python: ~0.14ms
- C++: ~0.02ms (7x faster)

---

### `cell_to_coarsest_ancestor_on_faces`

```python
cell_to_coarsest_ancestor_on_faces(
    h: str,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6}
) -> str
```

Finds the coarsest ancestor (lowest resolution) where the cell still lies on at least one of the specified boundary faces.

**Returns:** H3 cell index of the coarsest ancestor

---

### `boundary_cell_ids`

```python
boundary_cell_ids(
    parent: str,
    target_res: int,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6}
) -> numpy.ndarray  # dtype uint64
```

All boundary children as a NumPy array of 64-bit H3 indexes, **unordered** — the fast path when you want the whole set rather than a sequence.

Because order is not required, cells are grouped by boundary state and expanded a level at a time with array arithmetic instead of one Python call per node, and no per-cell hex strings are built. That makes it faster than *both* traversals:

| Boundary size | `children_on_boundary_faces` (Python) | (C++) | `boundary_cell_ids` |
|---|---|---|---|
| 6,558 | 4.6 ms | 0.64 ms | 0.57 ms |
| 59,046 | 38 ms | 5.4 ms | 0.77 ms |
| 531,438 | 345 ms | 54 ms | **1.9 ms** |

```python
ids = boundary_cell_ids(parent, 13)          # numpy uint64 array
h3i.cell_to_latlng(int(ids[0]))              # feed h3.api.basic_int directly
hexes = [format(v, 'x') for v in ids]        # …or convert to strings if needed
```

Note the order differs from `children_on_boundary_faces`, and `boundary_rank` is defined against *that* function's order — use the ordered API when position matters. Requires NumPy, which Shapely already pulls in.

### `boundary_cell_at`

```python
boundary_cell_at(
    parent: str,
    target_res: int,
    n: int,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6}
) -> str
```

Returns the n-th boundary child **directly**, in O(depth) arithmetic — equivalent to `children_on_boundary_faces(parent, target_res)[n]` without enumerating the others. The boundary children form a positional numeral system (their index digits are the paths of a face-state automaton), which makes random access, sampling, and sharding possible on boundaries far too large to materialize. The boundary size is `3**(depth+1) - 3` for hexagon parents and `5 * (3**depth - 1) // 2` for pentagons.

```python
parent = h3.latlng_to_cell(37.77, -122.42, 2)
cell = boundary_cell_at(parent, 13, 265_717)   # one of 531,438 — no enumeration
```

**Raises:** `ValueError` for an out-of-range `target_res`, `IndexError` for `n` outside the boundary count.

### `boundary_rank`

```python
boundary_rank(parent: str, cell: str, input_faces: Set[int] = {1, 2, 3, 4, 5, 6}) -> int
```

Inverse of `boundary_cell_at`: the position of `cell` in the parent's boundary sequence (depth-first traversal order), in O(depth). Doubles as a membership test — raises `ValueError` if `cell` is not a descendant of `parent` or not on the traced boundary.

### `boundary_range`

```python
boundary_range(
    parent: str,
    target_res: int,
    start: int = 0,
    stop: int | None = None,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6}
) -> Iterator[str]
```

Yields boundary children `[start, stop)` in traversal order: seeks to `start` in O(depth), then streams forward at traversal speed (O(1) amortized per cell, O(depth) memory). This is the bulk counterpart of the indexing functions — use it to shard a boundary across workers with no coordination, or to stream a boundary too large to hold in memory.

```python
# Worker k of n generates only its own slice
for cell in boundary_range(parent, 13, bounds[k], bounds[k + 1]):
    process(cell)
```

Concatenating the slices reproduces `children_on_boundary_faces` exactly. Repeatedly calling `boundary_cell_at` instead would re-descend the tree per cell (~9x slower for bulk work).

`boundary_cell_at` and `boundary_rank` are pure Python. `boundary_range` uses the C++ extension when it is available (fetching cells in blocks, so it stays a lazy generator with bounded memory) and falls back to the pure-Python generator otherwise — roughly 14x apart on bulk work.

See [Boundary Algorithms](algorithms.md) for how these relate to the traversal and the boundary walk, with benchmarks.

---

## Geometry Functions

### Pure Python Functions

These use Shapely for geometry operations.

#### `cell_boundary_to_geojson`

```python
cell_boundary_to_geojson(h: str) -> Dict[str, Any]
```

Returns a GeoJSON Feature representing the cell boundary.

#### `cell_boundary_from_children`

```python
cell_boundary_from_children(parent: str, target_res: int) -> Dict[str, Any]
```

Returns the merged boundary polygon of all boundary children at `target_res`.

**Returns:** GeoJSON Feature with properties:
- `h3_index`: Parent cell index
- `child_resolution`: Target resolution used
- `num_boundary_cells`: Number of boundary children

#### `get_buffered_h3_polygon`

```python
get_buffered_h3_polygon(cell: str, buffer_meters: float = None) -> Dict[str, Any]
```

Returns a buffered polygon of the cell's native boundary.

**Parameters:**
- `cell`: H3 cell index
- `buffer_meters`: Buffer distance. If None, auto-calculates as 100% of edge length

**Returns:** GeoJSON Feature with properties:
- `h3_index`: Cell index
- `buffer_meters`: Buffer distance used
- `method`: "buffered_python"

#### `get_buffered_boundary_polygon`

```python
get_buffered_boundary_polygon(
    cell: str,
    intermediate_res: int = 10,
    buffer_meters: float = None
) -> Dict[str, Any]
```

Hybrid approach: computes boundary at intermediate resolution, then buffers.

**Returns:** GeoJSON Feature with properties:
- `h3_index`: Cell index
- `intermediate_res`: Resolution used for boundary
- `buffer_meters`: Buffer distance used
- `num_boundary_cells`: Number of cells in boundary computation
- `method`: "buffered_boundary"

---

### C++ Accelerated Functions

These use Boost.Geometry and provide significant speedups. All return GeoJSON-compatible output.

#### `cell_boundary_to_geojson_cpp`

```python
cell_boundary_to_geojson_cpp(cell: str) -> Dict[str, Any]
```

C++ version of cell boundary to GeoJSON.

#### `cell_boundary_from_children_cpp`

```python
cell_boundary_from_children_cpp(parent: str, target_res: int) -> Dict[str, Any]
```

C++ version using Boost.Geometry union operations (pairwise merge tree).

**Performance:** ~2.5ms at res 6 → 10. The pure-Python version is comparable (~1.3ms) because it delegates to H3's native `cells_to_h3shape`.

#### `get_buffered_h3_polygon_cpp`

```python
get_buffered_h3_polygon_cpp(cell: str, buffer_meters: float = None) -> Dict[str, Any]
```

C++ version of simple buffered polygon.

**Performance:** ~0.06ms (vs ~0.13ms Python, **2x faster**)

#### `get_buffered_boundary_polygon_cpp`

```python
get_buffered_boundary_polygon_cpp(
    cell: str,
    intermediate_res: int = 10,
    buffer_meters: float = None,
    use_convex_hull: bool = False
) -> Dict[str, Any]
```

C++ buffered polygon with configurable accuracy.

**Parameters:**
- `cell`: H3 cell index
- `intermediate_res`: Resolution for boundary computation (default: 10)
- `buffer_meters`: Buffer distance. If None, auto-calculates as 100% of edge length
- `use_convex_hull`:
  - `True`: Fast convex hull approximation (~0.4ms)
  - `False` (default): Accurate union of all cells (~7ms)

**Returns:** GeoJSON Feature with properties:
- `h3_index`: Cell index
- `intermediate_res`: Resolution used
- `buffer_meters`: Buffer distance used
- `method`: "buffered_boundary_cpp" or "buffered_boundary_cpp_hull"

**Example:**
```python
from h3_boundary import get_buffered_boundary_polygon_cpp

# Accurate mode (default)
result = get_buffered_boundary_polygon_cpp(
    '86283082fffffff',
    intermediate_res=10,
    use_convex_hull=False
)
print(result['properties']['method'])  # 'buffered_boundary_cpp'

# Fast mode
result = get_buffered_boundary_polygon_cpp(
    '86283082fffffff',
    intermediate_res=10,
    use_convex_hull=True
)
print(result['properties']['method'])  # 'buffered_boundary_cpp_hull'
```

---

## Utility Functions

### `get_backend`

```python
get_backend() -> str
```

Returns the current backend: `'cpp'` or `'python'`.

### `cpp_geom_available`

```python
cpp_geom_available() -> bool
```

Returns `True` if C++ geometry functions (Boost.Geometry) are available.

---

## C++ API

For direct C++ usage, include `h3_toolkit.hpp`:

```cpp
#include "h3_toolkit.hpp"

// Trace faces
std::set<int> faces = h3_toolkit::trace_cell_to_ancestor_faces(
    cell, input_faces, res_parent
);

// Get boundary children
std::vector<H3Index> children = h3_toolkit::children_on_boundary_faces(
    parent, target_res
);

// Get buffered polygon (returns vector of (lon, lat) pairs)
std::vector<std::pair<double, double>> polygon = 
    h3_toolkit::get_buffered_boundary_polygon(
        cell, 
        intermediate_res, 
        buffer_meters,
        use_convex_hull
    );
```

### Function Signatures

```cpp
namespace h3_toolkit {

std::set<int> trace_cell_to_ancestor_faces(
    H3Index h,
    const std::set<int>& input_faces,
    int res_parent
);

std::set<int> trace_cell_to_parent_faces(
    H3Index h,
    const std::set<int>& input_faces
);

std::vector<H3Index> children_on_boundary_faces(
    H3Index parent,
    int target_res,
    const std::set<int>& input_faces = {1,2,3,4,5,6}
);

H3Index cell_to_coarsest_ancestor_on_faces(
    H3Index h,
    const std::set<int>& input_faces = {1,2,3,4,5,6}
);

std::vector<std::pair<double, double>> cell_boundary(H3Index cell);

std::vector<std::pair<double, double>> cell_boundary_from_children(
    H3Index parent,
    int target_res
);

std::vector<std::pair<double, double>> get_buffered_h3_polygon(
    H3Index cell,
    double buffer_meters = -1.0
);

std::vector<std::pair<double, double>> get_buffered_boundary_polygon(
    H3Index cell,
    int intermediate_res = 10,
    double buffer_meters = -1.0,
    bool use_convex_hull = false
);

} // namespace h3_toolkit
```

---

## Performance Summary

| Function | Python | C++ |
|----------|--------|-----|
| `children_on_boundary_faces` | 0.14ms | 0.02ms |
| `cell_boundary_from_children` | 1.3ms | 2.5ms |
| `get_buffered_boundary_polygon` (accurate) | 5.9ms | 7.0ms |
| `get_buffered_boundary_polygon` (fast hull) | N/A | 0.4ms |
| `get_buffered_h3_polygon` | 0.13ms | 0.06ms |

*Benchmarks on a resolution 6 cell with intermediate resolution 10 (Linux, Python 3.14). The C++ backend is fastest for face tracing and hull mode; Python polygon merging is comparable because it uses H3's native `cells_to_h3shape`.*
