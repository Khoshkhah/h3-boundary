#!/usr/bin/env python3
"""
Compare algorithms for finding a cell's boundary children at a target resolution.

Algorithms:
- table-py / table-cpp: the library's table-driven boundary-subtree descent
- walk:        find one boundary cell near a parent vertex, then flood along
               the wall (only public h3 API, no lookup tables)
- ring-band:   rings around the center child within a distance band estimated
               from sample points on the parent outline, filtered by parent
               membership + outside neighbor (corrected "center + distance" idea)
- ring-single: the best single grid_ring around the center child — reported
               with its coverage, since it cannot be exact for depth >= 2
- brute:       enumerate all children, keep those with an outside neighbor
               (ground truth; only run when the child count is small enough)

Run:  PYTHONPATH=src/python python benchmarks/compare_algorithms.py
"""
import time
from collections import Counter, deque

import h3
import h3.api.basic_int as h3i

from h3_boundary import utils as table_py

try:
    from h3_boundary import _h3_boundary_cpp as table_cpp
except ImportError:
    table_cpp = None

RES_FIELD = 0xF << 52


def make_inside(parent: str):
    """O(1) arithmetic test: is cell v (int) a descendant of parent?"""
    parent_res = h3.get_resolution(parent)
    digit_mask = (1 << (3 * (15 - parent_res))) - 1
    want = int(parent, 16)

    def inside(v: int) -> bool:
        return ((v | digit_mask) & ~RES_FIELD) | (parent_res << 52) == want

    return inside


def neighbors(c: str):
    try:
        return h3.grid_ring(c, 1)
    except Exception:  # pentagon distortion fallback
        return [n for n in h3.grid_disk(c, 1) if n != c]


def boundary_brute(parent: str, target_res: int) -> set:
    cells = h3.cell_to_children(parent, target_res)
    cset = set(cells)
    return {c for c in cells if any(n not in cset for n in neighbors(c))}


def boundary_walk(parent: str, target_res: int) -> set:
    inside = make_inside(parent)
    bcache = {}

    def is_boundary(c: str) -> bool:
        r = bcache.get(c)
        if r is None:
            # short-circuit: outside cells never pay for a neighbor ring
            r = inside(int(c, 16)) and any(
                not inside(int(n, 16)) for n in neighbors(c)
            )
            bcache[c] = r
        return r

    # Seed near a parent vertex, then BFS the few steps to a boundary cell.
    lat, lng = h3.cell_to_boundary(parent)[0]
    seed = h3.latlng_to_cell(lat, lng, target_res)
    seen, q, start = {seed}, deque([seed]), None
    while q:
        c = q.popleft()
        if is_boundary(c):
            start = c
            break
        for n in neighbors(c):
            if n not in seen:
                seen.add(n)
                q.append(n)

    # Flood restricted to boundary cells: the contour of a simply-connected
    # polyhex is edge-connected, so this reaches the whole boundary.
    result, q = {start}, deque([start])
    while q:
        c = q.popleft()
        for n in neighbors(c):
            if n not in result and is_boundary(n):
                result.add(n)
                q.append(n)
    return result


def boundary_walk_fast(parent: str, target_res: int) -> set:
    """Optimized walk: integer API end-to-end and exactly one grid_ring call
    per boundary cell.

    Instead of probing each inside-neighbor's own ring to test whether it is
    boundary, neighbors are *certified* from the current cell's ring: the k=1
    ring is rotationally ordered, so an inside neighbor sitting next to an
    outside neighbor shares an edge with that outside cell and is therefore
    boundary. Consecutive wall cells always share an outside cell (the three
    cells at a hex vertex are pairwise adjacent, and a contour vertex always
    has an outside cell), so certification alone reaches the whole wall.
    """
    parent_res = h3.get_resolution(parent)
    digit_mask = (1 << (3 * (15 - parent_res))) - 1
    res_stamp = parent_res << 52
    nres_field = ~RES_FIELD
    want = int(parent, 16)

    def inside(v: int) -> bool:
        return ((v | digit_mask) & nres_field) | res_stamp == want

    def probe_is_boundary(v: int) -> bool:
        return inside(v) and any(not inside(n) for n in h3i.grid_ring(v, 1))

    # Start: BFS from a vertex-snapped seed to the first boundary cell.
    lat, lng = h3.cell_to_boundary(parent)[0]
    seed = h3i.latlng_to_cell(lat, lng, target_res)
    seen, q, start = {seed}, deque([seed]), None
    while q:
        v = q.popleft()
        if probe_is_boundary(v):
            start = v
            break
        for n in h3i.grid_ring(v, 1):
            if n not in seen:
                seen.add(n)
                q.append(n)

    result, q = {start}, deque([start])
    while q:
        v = q.popleft()
        ring = h3i.grid_ring(v, 1)
        if len(ring) == 6:
            ins = [inside(n) for n in ring]
            for i in range(6):
                n = ring[i]
                if (ins[i] and n not in result
                        and (not ins[i - 1] or not ins[(i + 1) % 6])):
                    result.add(n)
                    q.append(n)
        else:
            # pentagon distortion: ring order not guaranteed, probe instead
            for n in ring:
                if n not in result and probe_is_boundary(n):
                    result.add(n)
                    q.append(n)
    return {format(v, 'x') for v in result}


def outline_distance_samples(parent: str, target_res: int, per_edge: int = 4):
    """Grid distances from the center child to cells at sample points on the
    parent outline — estimates the band the boundary lives in."""
    center = h3.cell_to_center_child(parent, target_res)
    verts = h3.cell_to_boundary(parent)
    dists = []
    n = len(verts)
    for i in range(n):
        (lat1, lng1), (lat2, lng2) = verts[i], verts[(i + 1) % n]
        for t in range(per_edge):
            f = t / per_edge
            lat, lng = lat1 + (lat2 - lat1) * f, lng1 + (lng2 - lng1) * f
            dists.append(
                h3.grid_distance(center, h3.latlng_to_cell(lat, lng, target_res))
            )
    return center, dists


def boundary_ring_band(parent: str, target_res: int, margin: int = 3) -> set:
    inside = make_inside(parent)
    center, dists = outline_distance_samples(parent, target_res)
    k_lo, k_hi = max(1, min(dists) - margin), max(dists) + margin

    result = set()
    for k in range(k_lo, k_hi + 1):
        for c in h3.grid_ring(center, k):
            if inside(int(c, 16)) and any(
                not inside(int(n, 16)) for n in neighbors(c)
            ):
                result.add(c)
    return result


def ring_single_coverage(parent: str, target_res: int, truth: set):
    """Best single ring around the center child vs. the true boundary."""
    center, dists = outline_distance_samples(parent, target_res)
    best = None
    for k in {d for d in dists}:
        ring = set(h3.grid_ring(center, k))
        hit = len(ring & truth)
        if best is None or hit > best[1]:
            best = (k, hit, len(ring - truth))
    k, hit, false_pos = best
    return k, hit / len(truth), false_pos


def bench(fn, reps=1):
    start = time.perf_counter()
    for _ in range(reps):
        out = fn()
    return out, (time.perf_counter() - start) * 1000 / reps


def main():
    sf = (37.7759, -122.4180)
    scenarios = [
        (h3.latlng_to_cell(*sf, 6), 10),  # depth 4
        (h3.latlng_to_cell(*sf, 3), 8),   # depth 5
        (h3.latlng_to_cell(*sf, 3), 10),  # depth 7 (the motivating example)
    ]

    for parent, target in scenarios:
        depth = target - h3.get_resolution(parent)
        n_children = 7 ** depth
        print(f"\n=== parent res {h3.get_resolution(parent)} -> {target} "
              f"(depth {depth}, {n_children:,} children) ===")

        truth, t_ref = bench(lambda: set(table_py.children_on_boundary_faces(parent, target)))
        rows = [("table-py (current)", truth, t_ref)]

        if table_cpp is not None:
            out, t = bench(lambda: set(table_cpp.children_on_boundary_faces(parent, target)), reps=5)
            rows.append(("table-cpp (current)", out, t))

        out, t = bench(lambda: boundary_walk(parent, target))
        rows.append(("walk", out, t))

        out, t = bench(lambda: boundary_walk_fast(parent, target), reps=3)
        rows.append(("walk-fast", out, t))

        out, t = bench(lambda: boundary_ring_band(parent, target))
        rows.append(("ring-band", out, t))

        if n_children <= 20_000:
            out, t = bench(lambda: boundary_brute(parent, target))
            rows.append(("brute (ground truth)", out, t))

        print(f"{'algorithm':<22} {'cells':>7} {'ms':>10}  matches table-py")
        for name, out, t in rows:
            print(f"{name:<22} {len(out):>7} {t:>10.2f}  {out == truth}")

        k, cov, fp = ring_single_coverage(parent, target, truth)
        print(f"{'ring-single (k=%d)' % k:<22} {'-':>7} {'-':>10}  "
              f"covers {cov:.0%} of boundary, {fp} cells outside parent")


if __name__ == "__main__":
    main()
