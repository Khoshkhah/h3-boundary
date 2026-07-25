"""
Core face-tracing functions for H3 boundary computation (pure Python).

Face model: every H3 cell has six boundary faces (edges), numbered 1-6.
(Pentagons have five; the tables simply never map anything to a sixth
pentagon face.) When a cell is subdivided, each child either lies strictly
inside the parent or touches one or more of the parent's faces. Which child
faces land on which parent faces depends only on:

- the *resolution parity* of the child level (H3's aperture-7 subdivision
  alternates orientation between even and odd resolutions), and
- the *child position* (0-6 as returned by h3.cell_to_child_pos; 0 is the
  center child, which never touches the parent boundary).

That relationship is encoded in the four lookup tables below — forward
(child face -> parent face, used to trace a cell upward) and reversed
(parent face -> child faces, used to enumerate boundary children downward),
for hexagons and pentagons. The C++ backend's constexpr tables in
src/cpp/src/h3_toolkit.cpp are generated from these dicts; if the mappings
ever change, regenerate them from here.
"""
import h3
from typing import Set, List, Dict, Optional

# Face mappings
# Organized by resolution parity (even/odd) and child position (1–6). Position 0 is center.

_boundary_face_mapping_hex: Dict[int, Dict[int, Dict[int, int]]] = {
    0: {  # Even resolutions
        0: {},
        1: {2: 3, 3: 1, 1: 1},
        2: {4: 6, 2: 2, 6: 2},
        3: {6: 2, 2: 3, 3: 3},
        4: {1: 5, 4: 4, 5: 4},
        5: {1: 5, 3: 1, 5: 5},
        6: {4: 6, 5: 4, 6: 6},
    },
    1: {  # Odd resolutions
        0: {},
        1: {3: 3, 1: 3, 5: 1},
        2: {2: 6, 6: 6, 3: 2},
        3: {2: 2, 1: 3, 3: 2},
        4: {4: 5, 5: 5, 6: 4},
        5: {1: 1, 4: 5, 5: 1},
        6: {4: 4, 2: 6, 6: 4},
    }
}

_reversed_boundary_face_mapping_hex: Dict[int, Dict[int, Dict[int, Set[int]]]] = {
    0: {  # Even resolutions
        1: {1: {1, 3}, 3: {2}},
        2: {2: {2, 6}, 6: {4}},
        3: {2: {6}, 3: {2, 3}},
        4: {4: {4, 5}, 5: {1}},
        5: {5: {1, 5}, 1: {3}},
        6: {4: {5}, 6: {4, 6}},
        0: {}
    },
    1: {  # Odd resolutions
        1: {3: {1, 3}, 1: {5}},
        2: {6: {2, 6}, 2: {3}},
        3: {2: {2, 3}, 3: {1}},
        4: {5: {4, 5}, 4: {6}},
        5: {1: {1, 5}, 5: {4}},
        6: {4: {4, 6}, 6: {2}},
        0: {}
    }
}

_boundary_face_mapping_pent: Dict[int, Dict[int, Dict[int, int]]] = {
    0: {  # Even resolutions
        0: {},
        1: {4: 5, 2: 1, 6: 1},
        2: {6: 1, 3: 2, 2: 2},
        3: {5: 2, 4: 2, 6: 4},
        4: {3: 2, 5: 4, 1: 2},
        5: {5: 3, 6: 5, 4: 5},
        6: {},
    },
    1: {  # Odd resolutions
        0: {},
        1: {2: 5, 6: 5, 3: 1},
        2: {3: 1, 2: 1, 1: 2},
        3: {1: 4, 4: 3, 5: 3},
        4: {1: 2, 5: 2, 4: 4},
        5: {2: 5, 4: 3, 6: 3},
        6: {},
    }
}

_reversed_boundary_face_mapping_pent: Dict[int, Dict[int, Dict[int, Set[int]]]] = {
    0: {  # Even resolutions
        1: {1: {2, 6}, 5: {4}},
        2: {1: {6}, 2: {2, 3}},
        3: {4: {1}, 3: {4, 5}},
        4: {4: {5}, 2: {1, 3}},
        5: {5: {4, 6}, 3: {5}},
        6: {},
        0: {},
    },
    1: {  # Odd resolutions
        1: {5: {2, 6}, 1: {3}},
        2: {2: {1}, 1: {2, 3}},
        3: {3: {6}, 4: {4, 5}},
        4: {4: {4}, 2: {1, 5}},
        5: {5: {2}, 3: {4, 6}},
        6: {},
        0: {},
    }
}


def trace_cell_to_ancestor_faces(
    h: str,  # H3 index (str)
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6},
    res_parent: Optional[int] = None
) -> Set[int]:
    """
    Traces which of the given `input_faces` the target H3 cell lies on for an ancestor
    cell at a coarser resolution.

    Args:
        h: Target H3 cell index (hex string).
        input_faces: Subset of face numbers {1–6} to trace upward.
        res_parent: Resolution of the ancestor cell. If None, defaults to immediate parent.

    Returns:
        Set of face numbers (1–6) that the target cell maps to at the ancestor's boundary.
        Returns empty set if no traceable boundary remains.

    Raises:
        ValueError: If `res_parent` is invalid.
    """
    h_res = h3.get_resolution(h)
    if res_parent is None:
        res_parent = h_res - 1

    if res_parent >= h_res:
        raise ValueError(f"res_parent ({res_parent}) must be less than cell resolution ({h_res}).")
    if res_parent < 0:
        raise ValueError("res_parent cannot be negative.")
    if not input_faces:
        return set()

    current_h = h
    for res in range(h_res, res_parent, -1):
        if h3.is_pentagon(current_h):
            return set()

        parity = res % 2
        # cell_to_child_pos returns 0-6. 0 is center.
        # Note: h3-py v4+ might have different API, assuming typical behavior or v3 compatibility.
        # But cell_to_child_pos is strict.
        child_pos = h3.cell_to_child_pos(current_h, res - 1)
        parent = h3.cell_to_parent(current_h, res - 1)
        parent_is_pent = h3.is_pentagon(parent)

        if child_pos == 0:
            return set()

        mapping_dict = _boundary_face_mapping_pent if parent_is_pent else _boundary_face_mapping_hex
        face_map = mapping_dict[parity].get(child_pos, {})
        
        mapped_faces = {face_map[f] for f in input_faces if f in face_map}

        if not mapped_faces:
            return set()

        input_faces = mapped_faces
        current_h = parent

    return input_faces


def trace_cell_to_parent_faces(
    h: str,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6},
) -> Set[int]:
    """
    Traces which boundary faces the cell lies on with respect to its immediate parent.

    Equivalent to ``trace_cell_to_ancestor_faces(h, input_faces, res - 1)``.

    Args:
        h: Target H3 cell index (hex string).
        input_faces: Subset of the cell's face numbers {1-6} to trace.

    Returns:
        Set of parent face numbers (1-6) the cell lies on; empty set if the
        cell does not touch the parent's boundary (e.g. it is a center child
        or a pentagon).
    """
    parent_res = h3.get_resolution(h) - 1
    return trace_cell_to_ancestor_faces(h, input_faces, res_parent=parent_res)


def cell_to_coarsest_ancestor_on_faces(
    h: str,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6},
) -> str:
    """
    Finds the coarsest ancestor whose boundary the cell still lies on.

    Walks up the resolution hierarchy as long as the cell keeps tracing to at
    least one of the requested faces, and returns the last ancestor for which
    that held.

    Args:
        h: Target H3 cell index (hex string).
        input_faces: Subset of face numbers {1-6} to trace upward.

    Returns:
        H3 index (hex string) of the coarsest such ancestor. Returns `h`
        itself if the cell does not lie on its parent's boundary at all.
    """
    res = h3.get_resolution(h)
    current_h = h

    while res > 0:
        parent_res = res - 1
        boundary_faces = trace_cell_to_ancestor_faces(current_h, input_faces, res_parent=parent_res)
        
        if not boundary_faces:
            return current_h

        current_h = h3.cell_to_parent(current_h, parent_res)
        input_faces = boundary_faces
        res = parent_res

    return current_h


def children_on_boundary_faces(
    parent: str,
    target_res: int,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6},
) -> List[str]:
    """
    Returns all descendants of `parent` at `target_res` that lie on the
    parent's specified boundary faces.

    Only the boundary subtree is traversed (via the reversed face-mapping
    tables), so cost scales with the number of boundary cells — roughly
    6 * sqrt(7)^(target_res - parent_res) — not with the parent's full
    interior (7^(target_res - parent_res)).

    Args:
        parent: Parent H3 cell index (hex string).
        target_res: Resolution of the returned children. Must satisfy
            parent resolution <= target_res <= 15. Equal resolution returns
            [parent].
        input_faces: Parent face numbers {1-6} to cover. Defaults to all six,
            i.e. the parent's complete boundary ring.

    Returns:
        List of H3 indexes (hex strings) at `target_res`, in depth-first
        order along the boundary.

    Raises:
        ValueError: If `target_res` is below the parent's resolution or
            above 15.
    """
    res_parent = h3.get_resolution(parent)
    if target_res < res_parent:
        raise ValueError("target_res must be greater than or equal to parent cell resolution.")
    if target_res > 15:
        raise ValueError("target_res must be <= 15.")

    result: List[int] = []

    # The recursion works on integer indexes and generates children
    # arithmetically (bump the resolution field, set the new digit) instead of
    # calling into h3 per node — the traversal itself needs no FFI at all.
    # Only the root can be a pentagon: children that recurse always have a
    # non-zero digit, and non-center pentagon children are hexagons.
    def _collect(v: int, res: int, faces: Set[int], is_pent: bool) -> None:
        if res == target_res:
            result.append(v)
            return

        child_res = res + 1
        reverse_mapping = (
            _reversed_boundary_face_mapping_pent if is_pent
            else _reversed_boundary_face_mapping_hex
        )[child_res % 2]

        shift = (15 - child_res) * 3
        # Child with digit 0: resolution field +1, filler 7 at the new digit
        # position replaced by 0.
        base = v + (1 << 52) - (7 << shift)
        # Pentagon children skip digit 1; enumerate() then yields the child
        # *position*, which is what the tables are keyed by.
        digits = (0, 2, 3, 4, 5, 6) if is_pent else (0, 1, 2, 3, 4, 5, 6)

        for child_pos, digit in enumerate(digits):
            child_mapping = reverse_mapping.get(child_pos)
            if not child_mapping:
                continue
            mapped_faces = set()
            for parent_face in faces:
                child_faces = child_mapping.get(parent_face)
                if child_faces:
                    mapped_faces |= child_faces
            if mapped_faces:
                _collect(base + (digit << shift), child_res, mapped_faces, False)

    _collect(int(parent, 16), res_parent, input_faces, h3.is_pentagon(parent))
    return [format(v, 'x') for v in result]
