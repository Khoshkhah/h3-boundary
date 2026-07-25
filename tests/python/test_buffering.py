"""
Containment tests for the buffered polygons.

The library's headline promise is that a buffered boundary polygon contains
every descendant of the cell. That is what these assert — directly, by testing
every vertex of every descendant — rather than trusting the buffer arithmetic.

Also pins the known limitation of get_buffered_h3_polygon, which buffers the
cell's nominal hexagon and therefore does *not* contain them.
"""
import h3
import pytest
from shapely.geometry import Point, Polygon, shape

import h3_boundary as h3b

# One cell per latitude band: the metres-to-degrees conversion is the part
# most likely to break away from the equator.
PARENTS = [
    pytest.param(h3.latlng_to_cell(0.5, 10.0, 6), id="equator"),
    pytest.param(h3.latlng_to_cell(37.8, -122.4, 6), id="mid-lat"),
    pytest.param(h3.latlng_to_cell(59.3, 18.1, 6), id="stockholm"),
    pytest.param(h3.latlng_to_cell(75.0, 20.0, 6), id="high-lat"),
]

INTERMEDIATE = 9
FINE = 10  # 2,401 descendants — enough to catch a gap, fast enough for CI


def outside_count(feature, parent, fine=FINE):
    poly = shape(feature["geometry"])
    return sum(
        1
        for child in h3.cell_to_children(parent, fine)
        if any(not poly.contains(Point(lng, lat))
               for lat, lng in h3.cell_to_boundary(child))
    )


@pytest.mark.parametrize("parent", PARENTS)
def test_buffered_boundary_contains_all_descendants(parent):
    feature = h3b.get_buffered_boundary_polygon(parent, INTERMEDIATE)
    assert outside_count(feature, parent) == 0


@pytest.mark.parametrize("parent", PARENTS)
def test_buffered_boundary_cpp_contains_all_descendants(parent):
    pytest.importorskip("h3_boundary._h3_boundary_cpp")
    if not h3b.cpp_geom_available():
        pytest.skip("C++ geometry not built")
    for use_hull in (False, True):
        feature = h3b.get_buffered_boundary_polygon_cpp(
            parent, INTERMEDIATE, None, use_hull
        )
        assert outside_count(feature, parent) == 0, f"use_convex_hull={use_hull}"


@pytest.mark.parametrize("parent", PARENTS)
def test_buffered_boundary_need_not_contain_the_drawn_hexagon(parent):
    """A deliberately surprising one, pinned so nobody "fixes" it.

    The guarantee is about *descendants*, not about cell_to_boundary's
    hexagon. That hexagon is an approximation of the true footprint and pokes
    outside it in places, so a polygon built from the real boundary can
    exclude slivers of it while still containing every descendant.
    """
    hexagon = Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(parent)])
    buffered = shape(h3b.get_buffered_boundary_polygon(parent, INTERMEDIATE)["geometry"])
    outside = hexagon.difference(buffered).area / hexagon.area
    assert outside < 0.05, "hexagon should stick out only marginally"
    # …while every actual descendant is still inside — the property that matters
    assert outside_count(
        h3b.get_buffered_boundary_polygon(parent, INTERMEDIATE), parent
    ) == 0


def test_cell_buffer_does_not_guarantee_containment():
    """Pins a documented limitation, so it can't regress into a false promise.

    get_buffered_h3_polygon buffers the nominal hexagon, which descendants
    straddle by ~0.19x the cell's edge length — far more than its default
    margin — so some fall outside. Supplying that margin fixes it.
    """
    parent = h3.latlng_to_cell(37.8, -122.4, 6)
    assert outside_count(h3b.get_buffered_h3_polygon(parent), parent) > 0

    edge_m = h3.average_hexagon_edge_length(6, unit="m")
    generous = h3b.get_buffered_h3_polygon(parent, 0.25 * edge_m)
    assert outside_count(generous, parent) == 0


@pytest.mark.parametrize("parent", PARENTS[:2])
def test_hull_contains_union(parent):
    """The fast mode is a superset of the accurate one, never a subset."""
    if not h3b.cpp_geom_available():
        pytest.skip("C++ geometry not built")
    union = shape(h3b.get_buffered_boundary_polygon_cpp(parent, INTERMEDIATE, None, False)["geometry"])
    hull = shape(h3b.get_buffered_boundary_polygon_cpp(parent, INTERMEDIATE, None, True)["geometry"])
    assert hull.area >= union.area
    # Not an exact containment check: the two are buffered independently, so
    # round joins leave slivers on the order of 1e-6 of the area.
    assert union.difference(hull).area < union.area * 1e-4


def test_zero_buffer_returns_the_boundary_itself():
    parent = h3.latlng_to_cell(37.8, -122.4, 6)
    zero = shape(h3b.get_buffered_boundary_polygon(parent, INTERMEDIATE, 0)["geometry"])
    exact = shape(h3b.cell_boundary_from_children(parent, INTERMEDIATE)["geometry"])
    assert zero.symmetric_difference(exact).area < exact.area * 1e-9
