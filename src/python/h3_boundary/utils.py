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


def _boundary_child_ints(
    parent: str,
    target_res: int,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6},
) -> List[int]:
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
    return result


def children_on_boundary_faces(
    parent: str,
    target_res: int,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6},
) -> List[str]:
    return [format(v, 'x') for v in _boundary_child_ints(parent, target_res, input_faces)]


children_on_boundary_faces.__doc__ = _boundary_child_ints.__doc__


def children_on_boundary_faces_ids(
    parent: str,
    target_res: int,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6},
):
    """
    Same cells and same order as :func:`children_on_boundary_faces`, returned
    as a NumPy array of 64-bit H3 indexes instead of hex strings.

    Formatting hex strings dominates bulk calls — about 80% of the time for a
    half-million-cell boundary — so this is several times faster when the
    caller can work with integers (h3-py's ``h3.api.basic_int``, a dataframe
    column, a database join). Use :func:`boundary_cell_ids` instead if the
    order does not matter; it is faster still.

    Args:
        parent: Parent H3 cell index (hex string).
        target_res: Resolution of the boundary children
            (parent resolution <= target_res <= 15).
        input_faces: Parent face numbers {1-6} to cover; defaults to all six.

    Returns:
        ``numpy.ndarray`` of dtype uint64, in traversal order.

    Raises:
        ValueError: If `target_res` is below the parent's resolution or
            above 15.
    """
    import numpy as np  # kept out of import time; guaranteed via shapely

    return np.array(
        _boundary_child_ints(parent, target_res, input_faces), dtype=np.uint64
    )


def boundary_cell_ids(
    parent: str,
    target_res: int,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6},
):
    """
    Returns all boundary children as a NumPy array of 64-bit H3 indexes,
    unordered — the fast path when you want the whole set rather than a
    sequence.

    Dropping the ordering requirement is what makes this fast: cells can be
    grouped by boundary state and expanded a whole level at a time with array
    arithmetic, instead of one Python call per node. The saving grows with the
    boundary — roughly 8x at depth 7 and 180x at depth 11 versus
    :func:`children_on_boundary_faces`, and faster than the C++ traversal too,
    because no per-cell hex strings are built.

    The cells are grouped by boundary state, so the order differs from
    :func:`children_on_boundary_faces`; use that function (or
    :func:`boundary_range`) when position matters, and note that
    :func:`boundary_rank` is defined against *its* order, not this one.

    Args:
        parent: Parent H3 cell index (hex string).
        target_res: Resolution of the boundary children
            (parent resolution <= target_res <= 15).
        input_faces: Parent face numbers {1-6} to cover; defaults to all six.

    Returns:
        ``numpy.ndarray`` of dtype uint64 holding every boundary child.
        Pass to h3-py's integer API (``h3.api.basic_int``) directly, or use
        ``[format(v, 'x') for v in ids]`` for hex strings.

    Raises:
        ValueError: If `target_res` is below the parent's resolution or
            above 15.
    """
    import numpy as np  # kept out of import time; guaranteed via shapely

    res_parent = h3.get_resolution(parent)
    if target_res < res_parent:
        raise ValueError("target_res must be greater than or equal to parent cell resolution.")
    if target_res > 15:
        raise ValueError("target_res must be <= 15.")

    faces = frozenset(input_faces)
    if not faces:
        return np.empty(0, dtype=np.uint64)

    root_is_pent = h3.is_pentagon(parent)
    # state -> array of cell indexes currently in that state
    groups = {faces: np.array([int(parent, 16)], dtype=np.uint64)}

    for res in range(res_parent, target_res):
        child_res = res + 1
        parity = child_res % 2
        shift = (15 - child_res) * 3
        # Only the root can be a pentagon: every child that survives has a
        # non-zero digit, and non-center children of a pentagon are hexagons.
        is_pent = root_is_pent and res == res_parent
        digits = (0, 2, 3, 4, 5, 6) if is_pent else (0, 1, 2, 3, 4, 5, 6)
        # Child with digit 0: bump the resolution field, clear the filler digit.
        bump = np.uint64((1 << 52) - (7 << shift))

        new_groups: Dict = {}
        for state, cells in groups.items():
            base = cells + bump
            for child_pos, digit in enumerate(digits):
                mapped = _mapped_faces(state, parity, child_pos, is_pent)
                if not mapped:
                    continue
                new_groups.setdefault(mapped, []).append(base + np.uint64(digit << shift))
        groups = {
            state: parts[0] if len(parts) == 1 else np.concatenate(parts)
            for state, parts in new_groups.items()
        }

    if not groups:
        return np.empty(0, dtype=np.uint64)
    parts = list(groups.values())
    return parts[0] if len(parts) == 1 else np.concatenate(parts)


# =============================================================================
# Direct indexing of boundary children (rank / unrank)
# =============================================================================
# The boundary children form a positional numeral system: each cell is a
# base-7 digit string accepted by the face-state automaton whose transitions
# are the reversed tables above. Counting accepted suffixes per state lets us
# jump straight to the n-th boundary cell (and back) in O(depth) arithmetic,
# with no traversal — random access, sampling, and sharding over boundaries
# that are far too large to enumerate.

_HEX_DIGITS = (0, 1, 2, 3, 4, 5, 6)
_PENT_DIGITS = (0, 2, 3, 4, 5, 6)

# (faces, remaining_depth, child_parity, is_pent) -> count of boundary
# descendants. Bounded: ~dozens of reachable face-sets x 15 depths x 2 x 2.
_SUBTREE_COUNTS: Dict = {}


def _mapped_faces(faces: frozenset, parity: int, child_pos: int, is_pent: bool) -> frozenset:
    """Faces of the child at `child_pos` that lie on the traced boundary."""
    table = (
        _reversed_boundary_face_mapping_pent if is_pent
        else _reversed_boundary_face_mapping_hex
    )[parity]
    child_mapping = table.get(child_pos)
    if not child_mapping:
        return frozenset()
    out = set()
    for f in faces:
        child_faces = child_mapping.get(f)
        if child_faces:
            out |= child_faces
    return frozenset(out)


def _subtree_count(faces: frozenset, res: int, target_res: int, is_pent: bool) -> int:
    """Number of boundary descendants at target_res below a cell at `res`
    whose boundary state is `faces`."""
    if res == target_res:
        return 1
    parity = (res + 1) % 2
    key = (faces, target_res - res, parity, is_pent)
    count = _SUBTREE_COUNTS.get(key)
    if count is None:
        count = 0
        digits = _PENT_DIGITS if is_pent else _HEX_DIGITS
        for child_pos in range(len(digits)):
            mapped = _mapped_faces(faces, parity, child_pos, is_pent)
            if mapped:
                count += _subtree_count(mapped, res + 1, target_res, False)
        _SUBTREE_COUNTS[key] = count
    return count


def boundary_cell_at(
    parent: str,
    target_res: int,
    n: int,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6},
) -> str:
    """
    Returns the n-th boundary child directly, without enumerating the others.

    Equivalent to ``children_on_boundary_faces(parent, target_res,
    input_faces)[n]`` but computed in O(target_res - parent_res) arithmetic,
    so it works on boundaries far too large to materialize. Together with
    :func:`boundary_rank` it forms a bijection between ``range(count)`` and
    the boundary cells, in depth-first traversal order.

    Args:
        parent: Parent H3 cell index (hex string).
        target_res: Resolution of the boundary children
            (parent resolution <= target_res <= 15).
        n: Zero-based index into the boundary sequence.
        input_faces: Parent face numbers {1-6} to cover; defaults to all six.

    Returns:
        H3 index (hex string) of boundary child number `n`.

    Raises:
        ValueError: If `target_res` is out of range.
        IndexError: If `n` is outside ``range(count)``.
    """
    res_parent = h3.get_resolution(parent)
    if target_res < res_parent:
        raise ValueError("target_res must be greater than or equal to parent cell resolution.")
    if target_res > 15:
        raise ValueError("target_res must be <= 15.")

    faces = frozenset(input_faces)
    is_pent = h3.is_pentagon(parent)
    total = _subtree_count(faces, res_parent, target_res, is_pent) if faces else 0
    if not 0 <= n < total:
        raise IndexError(f"boundary index {n} out of range for {total} boundary cells")

    v = int(parent, 16)
    for res in range(res_parent, target_res):
        child_res = res + 1
        parity = child_res % 2
        shift = (15 - child_res) * 3
        base = v + (1 << 52) - (7 << shift)
        digits = _PENT_DIGITS if is_pent else _HEX_DIGITS
        for child_pos, digit in enumerate(digits):
            mapped = _mapped_faces(faces, parity, child_pos, is_pent)
            if not mapped:
                continue
            count = _subtree_count(mapped, child_res, target_res, False)
            if n < count:
                v = base + (digit << shift)
                faces = mapped
                is_pent = False
                break
            n -= count
    return format(v, 'x')


def _next_boundary_child(
    base: int, faces: frozenset, is_pent: bool, child_res: int, from_pos: int
):
    """First boundary child at position >= from_pos.

    Returns (child_index, child_faces, next_pos) or None. `base` is the
    child-with-digit-0 index (resolution field bumped, filler digit cleared).
    """
    parity = child_res % 2
    shift = (15 - child_res) * 3
    digits = _PENT_DIGITS if is_pent else _HEX_DIGITS
    for child_pos in range(from_pos, len(digits)):
        mapped = _mapped_faces(faces, parity, child_pos, is_pent)
        if mapped:
            return base + (digits[child_pos] << shift), mapped, child_pos + 1
    return None


def boundary_range(
    parent: str,
    target_res: int,
    start: int = 0,
    stop: Optional[int] = None,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6},
):
    """
    Yields boundary children ``[start, stop)`` in traversal order.

    Seeks to `start` in O(depth) (as :func:`boundary_cell_at` does), then
    streams forward at traversal speed — O(1) amortized per cell, O(depth)
    memory. This is the bulk counterpart of the indexing functions: workers
    can each generate their own slice of a boundary with no coordination and
    no shared state, and concatenating the slices reproduces
    :func:`children_on_boundary_faces` exactly.

    Args:
        parent: Parent H3 cell index (hex string).
        target_res: Resolution of the boundary children
            (parent resolution <= target_res <= 15).
        start: First index to yield (clamped to 0).
        stop: One past the last index; None (default) means the end.
        input_faces: Parent face numbers {1-6} to cover; defaults to all six.

    Yields:
        H3 indexes (hex strings), in the same order as
        ``children_on_boundary_faces(parent, target_res, input_faces)``.

    Raises:
        ValueError: If `target_res` is out of range.
    """
    res_parent = h3.get_resolution(parent)
    if target_res < res_parent:
        raise ValueError("target_res must be greater than or equal to parent cell resolution.")
    if target_res > 15:
        raise ValueError("target_res must be <= 15.")

    faces = frozenset(input_faces)
    is_pent = h3.is_pentagon(parent)
    total = _subtree_count(faces, res_parent, target_res, is_pent) if faces else 0
    if stop is None or stop > total:
        stop = total
    start = max(start, 0)
    remaining = stop - start
    if remaining <= 0:
        return

    # Seek to `start`, recording resume points: each frame is the branch state
    # of one level, so streaming can continue from where the descent left off.
    stack = []  # (base, parent_faces, parent_is_pent, next_pos, child_res)
    v = int(parent, 16)
    n = start
    for res in range(res_parent, target_res):
        child_res = res + 1
        shift = (15 - child_res) * 3
        base = v + (1 << 52) - (7 << shift)
        pos = 0
        while True:
            step = _next_boundary_child(base, faces, is_pent, child_res, pos)
            child_v, mapped, next_pos = step
            count = _subtree_count(mapped, child_res, target_res, False)
            if n < count:
                stack.append((base, faces, is_pent, next_pos, child_res))
                v, faces, is_pent = child_v, mapped, False
                break
            n -= count
            pos = next_pos

    while True:
        yield format(v, 'x')
        remaining -= 1
        if remaining <= 0:
            return

        # Advance to the next leaf: unwind to the nearest level with an
        # unvisited branch, then descend leftmost from there.
        step = None
        while stack:
            base, p_faces, p_is_pent, next_pos, child_res = stack.pop()
            step = _next_boundary_child(base, p_faces, p_is_pent, child_res, next_pos)
            if step:
                child_v, mapped, next_pos = step
                stack.append((base, p_faces, p_is_pent, next_pos, child_res))
                v, faces, is_pent = child_v, mapped, False
                break
        if not step:
            return

        for res in range(child_res, target_res):
            next_res = res + 1
            shift = (15 - next_res) * 3
            base = v + (1 << 52) - (7 << shift)
            child_v, mapped, next_pos = _next_boundary_child(
                base, faces, is_pent, next_res, 0
            )
            stack.append((base, faces, is_pent, next_pos, next_res))
            v, faces, is_pent = child_v, mapped, False


def boundary_rank(
    parent: str,
    cell: str,
    input_faces: Set[int] = {1, 2, 3, 4, 5, 6},
) -> int:
    """
    Inverse of :func:`boundary_cell_at`: the position of `cell` in the
    boundary sequence of `parent` at the cell's resolution.

    Also serves as an O(depth) membership test — raises if the cell is not
    on the traced boundary at all.

    Args:
        parent: Parent H3 cell index (hex string).
        cell: A descendant of `parent` (hex string).
        input_faces: Parent face numbers {1-6}; must match the value used
            with boundary_cell_at / children_on_boundary_faces.

    Returns:
        Zero-based index n such that
        ``boundary_cell_at(parent, res(cell), n, input_faces) == cell``.

    Raises:
        ValueError: If `cell` is not a descendant of `parent`, or is not on
            the traced boundary.
    """
    res_parent = h3.get_resolution(parent)
    target_res = h3.get_resolution(cell)
    if target_res < res_parent:
        raise ValueError("cell resolution must be >= parent resolution.")

    v_cell = int(cell, 16)
    digit_mask = (1 << (3 * (15 - res_parent))) - 1
    ancestor = ((v_cell | digit_mask) & ~(0xF << 52)) | (res_parent << 52)
    if ancestor != int(parent, 16):
        raise ValueError(f"{cell} is not a descendant of {parent}")

    faces = frozenset(input_faces)
    is_pent = h3.is_pentagon(parent)
    rank = 0
    for res in range(res_parent, target_res):
        child_res = res + 1
        parity = child_res % 2
        shift = (15 - child_res) * 3
        cell_digit = (v_cell >> shift) & 0x7
        digits = _PENT_DIGITS if is_pent else _HEX_DIGITS
        descended = False
        for child_pos, digit in enumerate(digits):
            mapped = _mapped_faces(faces, parity, child_pos, is_pent)
            if digit == cell_digit:
                if not mapped:
                    raise ValueError(f"{cell} is not on the traced boundary of {parent}")
                faces = mapped
                descended = True
                break
            if mapped:
                rank += _subtree_count(mapped, child_res, target_res, False)
        if not descended:
            raise ValueError(f"{cell} is not on the traced boundary of {parent}")
        is_pent = False
    return rank
