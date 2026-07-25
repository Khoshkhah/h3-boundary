"""
Tests for boundary_cell_at / boundary_rank: direct O(depth) random access to
boundary children, exactly reproducing the traversal's depth-first order.
"""
import h3
import pytest

from h3_boundary import boundary_cell_at, boundary_rank
from h3_boundary.utils import children_on_boundary_faces

SF_RES6 = h3.latlng_to_cell(37.7759, -122.4180, 6)
HEX_RES1 = next(
    c for r0 in h3.get_res0_cells() if not h3.is_pentagon(r0)
    for c in h3.cell_to_children(r0, 1) if not h3.is_pentagon(c)
)
PENT_RES0 = sorted(h3.get_pentagons(0))[0]
PENT_RES1 = sorted(h3.get_pentagons(1))[0]

CASES = [
    (SF_RES6, 8),
    (SF_RES6, 10),
    (HEX_RES1, 4),
    (PENT_RES0, 3),
    (PENT_RES1, 4),
]


@pytest.mark.parametrize("parent,target_res", CASES)
def test_unrank_reproduces_traversal_order(parent, target_res):
    cells = children_on_boundary_faces(parent, target_res)
    unranked = [boundary_cell_at(parent, target_res, i) for i in range(len(cells))]
    assert unranked == cells


@pytest.mark.parametrize("parent,target_res", CASES)
def test_rank_is_inverse_of_unrank(parent, target_res):
    cells = children_on_boundary_faces(parent, target_res)
    assert [boundary_rank(parent, c) for c in cells] == list(range(len(cells)))


@pytest.mark.parametrize("faces", [{1}, {2, 5}])
def test_partial_faces(faces):
    cells = children_on_boundary_faces(SF_RES6, 9, faces)
    assert [boundary_cell_at(SF_RES6, 9, i, faces) for i in range(len(cells))] == cells
    assert [boundary_rank(SF_RES6, c, faces) for c in cells] == list(range(len(cells)))


def test_random_access_without_enumeration():
    """The whole point: reach into a boundary too large to materialize here.
    res 2 -> 13 has 3^12 - 3 = 531,438 boundary cells."""
    parent = h3.latlng_to_cell(37.7759, -122.4180, 2)
    total = 3 ** 12 - 3
    for n in (0, 1, total // 2, total - 1):
        cell = boundary_cell_at(parent, 13, n)
        assert h3.get_resolution(cell) == 13
        assert boundary_rank(parent, cell) == n
    with pytest.raises(IndexError):
        boundary_cell_at(parent, 13, total)


def test_equal_resolution():
    assert boundary_cell_at(SF_RES6, 6, 0) == SF_RES6
    assert boundary_rank(SF_RES6, SF_RES6) == 0


def test_out_of_range_index():
    with pytest.raises(IndexError):
        boundary_cell_at(SF_RES6, 8, 3 ** 3 - 3)  # count is exactly 3^3 - 3
    with pytest.raises(IndexError):
        boundary_cell_at(SF_RES6, 8, -1)


def test_rank_rejects_non_boundary_cell():
    center = h3.cell_to_center_child(SF_RES6, 9)
    with pytest.raises(ValueError):
        boundary_rank(SF_RES6, center)


def test_rank_rejects_non_descendant():
    other = h3.latlng_to_cell(59.33, 18.06, 9)  # Stockholm, not under SF cell
    with pytest.raises(ValueError):
        boundary_rank(SF_RES6, other)


def test_validation_errors():
    with pytest.raises(ValueError):
        boundary_cell_at(SF_RES6, 5, 0)  # below parent res
    with pytest.raises(ValueError):
        boundary_cell_at(SF_RES6, 16, 0)  # above 15
