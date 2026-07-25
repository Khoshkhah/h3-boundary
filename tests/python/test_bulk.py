"""
Tests for boundary_cell_ids: unordered bulk generation as a uint64 array.

It must contain exactly the same cells as the ordered traversal — the order
is allowed to differ, nothing else is.
"""
import h3
import pytest

from h3_boundary import boundary_cell_ids, children_on_boundary_faces_ids
from h3_boundary.utils import children_on_boundary_faces
from h3_boundary.utils import (
    children_on_boundary_faces_ids as children_ids_py,
)

# When the extension is built the package exports the C++ version; the pure
# Python one must behave identically.
ID_IMPLS = [children_ids_py]
if children_on_boundary_faces_ids is not children_ids_py:
    ID_IMPLS.append(children_on_boundary_faces_ids)


@pytest.fixture(params=ID_IMPLS, ids=lambda f: getattr(f, "__module__", "cpp"))
def children_ids(request):
    return request.param

SF_RES6 = h3.latlng_to_cell(37.7759, -122.4180, 6)
SF_RES2 = h3.latlng_to_cell(37.7759, -122.4180, 2)
HEX_RES1 = next(
    c for r0 in h3.get_res0_cells() if not h3.is_pentagon(r0)
    for c in h3.cell_to_children(r0, 1) if not h3.is_pentagon(c)
)
PENT_RES0 = sorted(h3.get_pentagons(0))[0]
PENT_RES1 = sorted(h3.get_pentagons(1))[0]


def as_hex(ids):
    return {format(int(v), 'x') for v in ids}


@pytest.mark.parametrize("parent,target_res", [
    (SF_RES6, 7),
    (SF_RES6, 10),
    (HEX_RES1, 5),
    (PENT_RES0, 2),
    (PENT_RES0, 4),
    (PENT_RES1, 4),
])
def test_same_cells_as_traversal(parent, target_res):
    ids = boundary_cell_ids(parent, target_res)
    expected = children_on_boundary_faces(parent, target_res)
    assert as_hex(ids) == set(expected)
    assert len(ids) == len(expected)  # no duplicates


@pytest.mark.parametrize("parent,target_res", [
    (SF_RES6, 7),
    (SF_RES6, 10),
    (HEX_RES1, 5),
    (PENT_RES0, 2),
    (PENT_RES0, 4),
    (PENT_RES1, 4),
])
def test_ids_match_traversal_including_order(children_ids, parent, target_res):
    """The *_ids variants keep traversal order — only the type changes."""
    ids = children_ids(parent, target_res)
    assert str(ids.dtype) == "uint64"
    assert [format(int(v), 'x') for v in ids] == children_on_boundary_faces(parent, target_res)


@pytest.mark.parametrize("faces", [{1}, {2, 5}])
def test_ids_partial_faces(children_ids, faces):
    ids = children_ids(SF_RES6, 9, faces)
    assert [format(int(v), 'x') for v in ids] == \
        children_on_boundary_faces(SF_RES6, 9, faces)


def test_ids_equal_resolution(children_ids):
    ids = children_ids(SF_RES6, 6)
    assert [format(int(v), 'x') for v in ids] == [SF_RES6]


def test_ids_validation(children_ids):
    with pytest.raises(ValueError):
        children_ids(SF_RES6, 5)
    with pytest.raises(ValueError):
        children_ids(SF_RES6, 16)


@pytest.mark.parametrize("faces", [{1}, {3}, {2, 5}, {1, 2, 3}])
def test_partial_faces(faces):
    ids = boundary_cell_ids(SF_RES6, 9, faces)
    assert as_hex(ids) == set(children_on_boundary_faces(SF_RES6, 9, faces))


def test_dtype_and_h3_int_api_compatibility():
    import h3.api.basic_int as h3i
    ids = boundary_cell_ids(SF_RES6, 9)
    assert str(ids.dtype) == "uint64"
    # values are usable directly with h3's integer API
    for v in ids[:5]:
        assert h3i.is_valid_cell(int(v))
        assert h3i.get_resolution(int(v)) == 9


def test_closed_form_counts():
    for depth in range(1, 6):
        assert len(boundary_cell_ids(SF_RES6, 6 + depth)) == 3 ** (depth + 1) - 3
    for depth in range(1, 5):
        assert len(boundary_cell_ids(PENT_RES0, depth)) == 5 * (3 ** depth - 1) // 2


def test_large_boundary():
    """531,438 cells — the case the ordered traversal takes ~50x longer on."""
    ids = boundary_cell_ids(SF_RES2, 13)
    assert len(ids) == 3 ** 12 - 3
    assert len(set(ids.tolist())) == len(ids)  # all distinct


def test_equal_resolution():
    ids = boundary_cell_ids(SF_RES6, 6)
    assert as_hex(ids) == {SF_RES6}


def test_empty_faces():
    assert len(boundary_cell_ids(SF_RES6, 8, set())) == 0


def test_validation_errors():
    with pytest.raises(ValueError):
        boundary_cell_ids(SF_RES6, 5)
    with pytest.raises(ValueError):
        boundary_cell_ids(SF_RES6, 16)
