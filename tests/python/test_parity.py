"""
Parity tests: the C++ backend must match the pure-Python reference implementation.

Written BEFORE the divergence fixes (plan Phase 3). These tests encode the
*intended* common semantics, so several are expected to FAIL against the
current code — each such test notes its known bug:

- pentagon parents: C++ has no reversed pentagon table and indexes hex tables
  by raw index digit instead of child position (off-by-one on pentagons)
- target_res == parent_res: Python returns [parent], C++ throws
- target_res > 15: neither backend validates (both should raise ValueError)
- trace functions: C++ bindings declare no defaults for input_faces/res_parent
- use_convex_hull default: True in the raw binding, False in the wrapper
- polygon selection: C++ returns merged[0] (arbitrary), not the largest polygon
"""
import h3
import pytest
from shapely.geometry import Polygon, shape

from h3_boundary import utils as py_utils
from h3_boundary import geom as py_geom

cpp = pytest.importorskip("h3_boundary._h3_boundary_cpp")
import h3_boundary as h3b

SF_RES6 = h3.latlng_to_cell(37.7759, -122.4180, 6)
HEX_RES0 = next(c for c in h3.get_res0_cells() if not h3.is_pentagon(c))
HEX_RES1 = next(c for c in h3.cell_to_children(HEX_RES0, 1) if not h3.is_pentagon(c))
PENT_RES0 = sorted(h3.get_pentagons(0))[0]
PENT_RES1 = sorted(h3.get_pentagons(1))[0]
HIGH_LAT_RES6 = h3.latlng_to_cell(75.0, 20.0, 6)  # Svalbard-ish
ALL_FACES = {1, 2, 3, 4, 5, 6}


def as_poly(feature) -> Polygon:
    return shape(feature["geometry"] if "geometry" in feature else feature)


def iou(a: Polygon, b: Polygon) -> float:
    union = a.union(b).area
    return a.intersection(b).area / union if union else 0.0


def ring_of(coords):
    """Coordinate list from a raw binding result (list of (lon, lat))."""
    return [tuple(c) for c in coords]


# ---------------------------------------------------------------------------
# children_on_boundary_faces: cell-set parity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("parent,target_res", [
    (SF_RES6, 8),
    (SF_RES6, 10),
    (HEX_RES1, 4),
    (HEX_RES0, 3),
])
def test_children_parity_hexagon(parent, target_res):
    py_result = set(py_utils.children_on_boundary_faces(parent, target_res))
    cpp_result = set(cpp.children_on_boundary_faces(parent, target_res))
    assert cpp_result == py_result


@pytest.mark.parametrize("faces", [{1}, {2, 5}, {3, 4, 6}])
def test_children_parity_face_subsets(faces):
    py_result = set(py_utils.children_on_boundary_faces(SF_RES6, 9, faces))
    cpp_result = set(cpp.children_on_boundary_faces(SF_RES6, 9, faces))
    assert cpp_result == py_result


@pytest.mark.parametrize("parent,target_res", [
    (PENT_RES0, 1),
    (PENT_RES0, 2),
    (PENT_RES0, 3),
    (PENT_RES1, 3),
])
def test_children_parity_pentagon_all_faces(parent, target_res):
    # Passes today only by coincidence: with all 6 faces the pentagon and hex
    # reversed tables select the same children (values coincide, keys differ).
    py_result = set(py_utils.children_on_boundary_faces(parent, target_res))
    cpp_result = set(cpp.children_on_boundary_faces(parent, target_res))
    assert cpp_result == py_result


@pytest.mark.parametrize("faces", [{1}, {3}, {2, 5}])
def test_children_parity_pentagon_partial_faces(faces):
    # KNOWN BUG (red until Phase 3): C++ indexes the hex reversed table by raw
    # index digit on pentagon parents instead of the pentagon table by child
    # position, so partial face sets select different children.
    py_result = set(py_utils.children_on_boundary_faces(PENT_RES0, 2, faces))
    cpp_result = set(cpp.children_on_boundary_faces(PENT_RES0, 2, faces))
    assert cpp_result == py_result


def test_children_ground_truth():
    """Both backends must equal brute force: a boundary child is a child with
    at least one neighbor outside the parent's descendants (all-faces case).
    Same definition as benchmarks/verify_boundary.py, but two-sided."""
    parent, target_res = HEX_RES1, 3
    descendants = set(h3.cell_to_children(parent, target_res))
    truth = {
        c for c in descendants
        if any(n not in descendants for n in h3.grid_ring(c, 1))
    }
    assert set(py_utils.children_on_boundary_faces(parent, target_res)) == truth
    assert set(cpp.children_on_boundary_faces(parent, target_res)) == truth


def test_children_equal_resolution_returns_parent():
    # KNOWN BUG (red until Phase 3): C++ throws on target_res == parent res;
    # the Python reference returns [parent].
    assert py_utils.children_on_boundary_faces(SF_RES6, 6) == [SF_RES6]
    assert cpp.children_on_boundary_faces(SF_RES6, 6) == [SF_RES6]


def test_children_target_res_above_15_raises():
    # KNOWN BUG (red until Phase 3): neither backend validates the upper bound
    # today; both must raise ValueError instead of producing garbage.
    with pytest.raises(ValueError):
        py_utils.children_on_boundary_faces(SF_RES6, 16)
    with pytest.raises(ValueError):
        cpp.children_on_boundary_faces(SF_RES6, 16)


def test_children_below_parent_res_raises_both():
    with pytest.raises(ValueError):
        py_utils.children_on_boundary_faces(SF_RES6, 5)
    with pytest.raises(ValueError):
        cpp.children_on_boundary_faces(SF_RES6, 5)


# ---------------------------------------------------------------------------
# trace functions
# ---------------------------------------------------------------------------

HEX_CHILD_OF_PENT = next(
    c for c in h3.cell_to_children(PENT_RES0, 1) if not h3.is_pentagon(c)
)
TRACE_CELLS = [
    h3.latlng_to_cell(37.7759, -122.4180, 9),
    h3.latlng_to_cell(59.33, 18.06, 7),  # Stockholm
    # KNOWN BUG (red until Phase 3): C++ indexes the forward pentagon table by
    # raw digit, Python by child position — traces through a pentagon diverge.
    HEX_CHILD_OF_PENT,
    next(c for c in h3.cell_to_children(HEX_CHILD_OF_PENT, 3)
         if not h3.is_pentagon(c)),
]


@pytest.mark.parametrize("cell", TRACE_CELLS)
def test_trace_ancestor_parity(cell):
    res = h3.get_resolution(cell)
    for res_parent in range(max(0, res - 3), res):
        py_result = py_utils.trace_cell_to_ancestor_faces(cell, ALL_FACES, res_parent)
        cpp_result = cpp.trace_cell_to_ancestor_faces(cell, ALL_FACES, res_parent)
        assert cpp_result == py_result, f"res_parent={res_parent}"


@pytest.mark.parametrize("cell", TRACE_CELLS)
def test_trace_parent_parity(cell):
    assert (cpp.trace_cell_to_parent_faces(cell, ALL_FACES)
            == py_utils.trace_cell_to_parent_faces(cell, ALL_FACES))


@pytest.mark.parametrize("cell", TRACE_CELLS)
def test_coarsest_ancestor_parity(cell):
    assert (cpp.cell_to_coarsest_ancestor_on_faces(cell)
            == py_utils.cell_to_coarsest_ancestor_on_faces(cell))


def test_trace_functions_defaults():
    # KNOWN BUG (red until Phase 3): the C++ bindings declare no defaults for
    # input_faces/res_parent, so the same call raises TypeError on the compiled
    # backend only.
    cell = TRACE_CELLS[0]
    assert py_utils.trace_cell_to_ancestor_faces(cell) == cpp.trace_cell_to_ancestor_faces(cell)
    assert py_utils.trace_cell_to_parent_faces(cell) == cpp.trace_cell_to_parent_faces(cell)


# ---------------------------------------------------------------------------
# geometry parity
# ---------------------------------------------------------------------------

def test_cell_boundary_closed_and_matches_h3():
    coords = ring_of(cpp.cell_boundary(SF_RES6))
    assert coords[0] == coords[-1], "ring must be closed"
    expected = Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(SF_RES6)])
    assert iou(Polygon(coords), expected) > 0.999


@pytest.mark.parametrize("parent,target_res", [(SF_RES6, 8), (SF_RES6, 10)])
def test_boundary_from_children_parity(parent, target_res):
    # KNOWN BUG (red until Phase 3 in multi-polygon cases): C++ returns
    # merged[0] from the union, Python returns the largest polygon.
    py_poly = as_poly(py_geom.cell_boundary_from_children(parent, target_res))
    cpp_poly = as_poly(h3b.cell_boundary_from_children_cpp(parent, target_res))
    assert py_poly.is_valid and cpp_poly.is_valid
    assert iou(py_poly, cpp_poly) > 0.999


@pytest.mark.parametrize("cell", [SF_RES6, HIGH_LAT_RES6])
def test_buffered_h3_polygon_parity(cell):
    # Different buffer engines (Shapely vs Boost) — compare loosely, and
    # require both to contain the original cell.
    py_poly = as_poly(py_geom.get_buffered_h3_polygon(cell))
    cpp_poly = as_poly(h3b.get_buffered_h3_polygon_cpp(cell))
    raw_cell = Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(cell)])
    assert py_poly.is_valid and cpp_poly.is_valid
    assert py_poly.contains(raw_cell) and cpp_poly.contains(raw_cell)
    assert iou(py_poly, cpp_poly) > 0.97


@pytest.mark.parametrize("cell", [SF_RES6, HIGH_LAT_RES6])
def test_buffered_boundary_polygon_parity(cell):
    py_poly = as_poly(py_geom.get_buffered_boundary_polygon(cell, 9))
    cpp_poly = as_poly(h3b.get_buffered_boundary_polygon_cpp(cell, 9))
    boundary = as_poly(py_geom.cell_boundary_from_children(cell, 9))
    assert py_poly.is_valid and cpp_poly.is_valid
    assert py_poly.contains(boundary) and cpp_poly.contains(boundary)
    assert iou(py_poly, cpp_poly) > 0.97


def test_buffered_boundary_rings_closed():
    for hull in (True, False):
        coords = ring_of(cpp.get_buffered_boundary_polygon(SF_RES6, 9, -1.0, hull))
        assert coords[0] == coords[-1], f"unclosed ring (use_convex_hull={hull})"


def test_use_convex_hull_default_is_accurate():
    # KNOWN BUG (red until Phase 3): raw binding defaults to use_convex_hull=True
    # while the documented wrapper default is False (accurate union).
    default = Polygon(ring_of(cpp.get_buffered_boundary_polygon(SF_RES6, 9, -1.0)))
    accurate = Polygon(ring_of(cpp.get_buffered_boundary_polygon(SF_RES6, 9, -1.0, False)))
    assert iou(default, accurate) > 0.999
