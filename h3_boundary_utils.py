# h3_boundary_utils.py

import h3
from typing import Set, List

# This dictionary defines face transitions for child cells with respect to their parent's face boundaries.
# Organized by resolution parity (even/odd) and child position (1–6). Position 0 is the center child.

# map child face to parent face
_boundary_face_mapping_hex = {
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

# Reversed version of _boundary_face_mapping_hex
# map parent face to child faces
_reversed_boundary_face_mapping_hex = {
    0: {  # Even resolutions
        1: {1: {1, 3}, 3: {2}},
        2: {2: {2, 6}, 6: {4}},
        3: {2: {6}, 3: {2,3}},
        4: {4: {4, 5}, 5: {1}},
        5: {5: {1,5}, 1: {3}},
        6: {4: {5}, 6: {4,6}},
        0: {}
    },
    1: {  # Odd resolutions
        1: {3: {1,3}, 1: {5}},
        2: {6: {2,6}, 2: {3}},
        3: {2: {2,3}, 3: {1}},
        4: {5: {4,5}, 4: {6}},
        5: {1: {1,5}, 5: {4}},
        6: {4: {4,6}, 6: {2}},
        0: {}
    }
}


_boundary_face_mapping_pent = {
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


# Reversed version of _boundary_face_mapping_pent
_reversed_boundary_face_mapping_pent = {
    0: {  # Odd resolutions
        1: {1: {2, 6}, 5: {4}},
        2: {1: {6}, 2: {2,3}},
        3: {4: {1}, 3: {4,5}},
        4: {4: {5}, 2: {1,3}},
        5: {5: {4,6}, 3: {5}},
        6:{},
        0:{},
        },
    
    1: {  # Odd resolutions
        1: {5: {2, 6}, 1: {3}},
        2: {2: {1}, 1: {2,3}},
        3: {3: {6}, 4: {4,5}},
        4: {4: {4}, 2: {1,5}},
        5: {5: {2}, 3: {4,6}},
        6:{},
        0:{},
        }
     
}

def trace_cell_to_ancestor_faces(
    h: int,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6},
    res_parent: int | None = None
) -> Set[int]:
    """
    Traces which of the given `input_faces` the target H3 cell lies on for an ancestor
    cell at a coarser resolution.

    At each resolution level, the function uses predefined face mappings to determine
    how boundary faces map between child and parent cells. If the current cell is
    a center child (position 0), no boundary face persists upward.

    Args:
        h: Target H3 cell index.
        input_faces: Subset of face numbers {1–6} to trace upward.
        res_parent: Resolution of the ancestor cell. If None, defaults to immediate parent.

    Returns:
        Set of face numbers (1–6) that the target cell maps to at the ancestor's boundary.
        Returns empty set if no traceable boundary remains or if the child is a center.

    Raises:
        ValueError: If `res_parent` is invalid (e.g., <0 or ≥ h's resolution).
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

    for res in range(h_res, res_parent, -1):
        if h3.is_pentagon(h):
            return set()

        parity = res % 2
        child_pos = h3.cell_to_child_pos(h, res - 1)
        parent = h3.cell_to_parent(h, res - 1)
        parent_is_pent = h3.is_pentagon(parent)

        if child_pos == 0:
            return set()

        face_map = (_boundary_face_mapping_pent if parent_is_pent else _boundary_face_mapping_hex)[parity].get(child_pos, {})
        mapped_faces = {face_map[f] for f in input_faces if f in face_map}

        if not mapped_faces:
            return set()

        input_faces = mapped_faces
        h = parent

    return input_faces

def trace_cell_to_parent_faces(
    h: int,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6},
) -> Set[int]:
    """
    Traces which boundary faces the target cell lies on with respect to its parent cell.

    Args:
        h: Target H3 cell.
        input_faces: Face numbers {1–6} to trace.

    Returns:
        Set of face numbers that `h` lies on at the parent boundary.
    """
    parent_res = h3.get_resolution(h) - 1
    return trace_cell_to_ancestor_faces(h, input_faces, res_parent=parent_res)

def cell_to_coarsest_ancestor_on_faces(
    h: int,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6},
) -> int:
    """
    Finds the coarsest ancestor (lowest resolution) such that the target cell `h`
    lies on at least one of the specified `input_faces`.

    The function moves up the cell hierarchy as long as boundary face overlap exists.
    It stops when the mapping fails, returning the last ancestor where the condition held.

    Args:
        h: The target H3 cell.
        input_faces: Set of face numbers {1–6} to check boundary overlap.

    Returns:
        The coarsest ancestor cell (H3 index) where the target still lies on
        at least one of the input boundary faces.
    """
    res = h3.get_resolution(h)

    while res > 0:
        parent_res = res - 1
        boundary_faces = trace_cell_to_ancestor_faces(h, input_faces, res_parent=parent_res)
        # or boundary_faces = trace_cell_to_parent_faces(h, input_faces)
        if not boundary_faces:
            return h

        h = h3.cell_to_parent(h, parent_res)
        input_faces = boundary_faces
        res = parent_res

    return h


def children_on_boundary_faces(
    parent: int,
    target_res: int,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6},
) -> List[int]:
    """
    Returns all children of the given parent cell at `target_res` resolution
    that lie on the parent's specified boundary `input_faces`.

    This version uses precomputed reverse face mappings to avoid tracing every child.

    Args:
        parent: Parent H3 cell index.
        target_res: Resolution to descend to.
        input_faces: Set of face numbers {1–6} indicating which boundaries to include.

    Returns:
        List of child H3 cells that lie on the specified boundary faces.

    Raises:
        ValueError: If target_res is not deeper than parent resolution.
    """
    res_parent = h3.get_resolution(parent)
    if target_res < res_parent:
        raise ValueError("target_res must be greater than parent cell resolution.")

    def _children_by_face(current: int, res: int, faces: Set[int]) -> List[int]:
        if res == target_res:
            return [current]

        parity = (res+1) % 2
        result = []
        is_pent = h3.is_pentagon(current)
        reverse_mapping = (
            _reversed_boundary_face_mapping_pent if is_pent
            else _reversed_boundary_face_mapping_hex
        )[parity]

        for child in h3.cell_to_children(current, res + 1):
            child_pos = h3.cell_to_child_pos(child, res)

            # Get the child face if it matches input_faces via reverse mapping
            mapped_faces = set()
            for parent_face in faces:
                if parent_face in reverse_mapping[child_pos].keys():
                    mapped_faces.update(reverse_mapping[child_pos][parent_face])
            #print(f"{mapped_faces}, parity = {parity}, child_pos = {child_pos}, is_pent = {is_pent}")

            if mapped_faces:
                result.extend(_children_by_face(child, res + 1, mapped_faces))
        return result

    return _children_by_face(parent, res_parent, input_faces)

