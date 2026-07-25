#!/usr/bin/env python3
"""
Ordered vs unordered boundary generation, across implementations.

Two approaches:
  ordered   — cells in traversal order (recursive descent, or unranking
              position by position)
  unordered — the same set, produced by expanding a whole level at a time

Each is measured in pure Python, in NumPy (Python + array arithmetic), and
in C++, serially and split across threads. The C++ functions release the
GIL, so Python threads run them in genuine parallel; the NumPy path holds
the GIL for its bookkeeping, so it is also shown over processes.

Run:  PYTHONPATH=src/python python benchmarks/compare_implementations.py
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

import h3
import numpy as np

from h3_boundary import _h3_boundary_cpp as cpp
from h3_boundary import boundary_cell_ids as cpp_bulk_ids
from h3_boundary.utils import _mapped_faces, _boundary_child_ints
from h3_boundary.utils import boundary_cell_at
from h3_boundary.utils import boundary_cell_ids as bulk_numpy
from h3_boundary.utils import children_on_boundary_faces as trav_py

WORKERS = min(6, os.cpu_count() or 1)

# Pools are created once and reused: spinning one up per call costs ~1 ms,
# which would swamp the work being measured.
_THREADS = ThreadPoolExecutor(WORKERS)
_PROCS = None  # created lazily; fork cost is reported separately


# --- parallel helpers ------------------------------------------------------

def shards(total, n):
    return [(total * k // n, total * (k + 1) // n) for k in range(n)]


def ordered_cpp_threads(parent, target_res, total, workers=WORKERS):
    """Ordered, in parallel: each worker unranks its own index range."""
    parts = _THREADS.map(
        lambda s: cpp.boundary_range_ids(parent, target_res, s[0], s[1]),
        shards(total, workers),
    )
    return np.concatenate(list(parts))


def top_level_tasks(parent, target_res):
    """The parent's surviving children with their states — the natural way to
    split unordered work, since each subtree is independent.

    Note this caps parallelism at 6 units. Splitting a level deeper (24 tasks,
    then 78) measures *slower* than 6: each bulk expansion has fixed setup, and
    the per-task arrays stop being large enough to pay for it. Ordered work has
    no such limit because index ranges can be cut anywhere.
    """
    res_parent = h3.get_resolution(parent)
    parity = (res_parent + 1) % 2
    shift = (15 - (res_parent + 1)) * 3
    base = int(parent, 16) + (1 << 52) - (7 << shift)
    is_pent = h3.is_pentagon(parent)
    digits = (0, 2, 3, 4, 5, 6) if is_pent else (0, 1, 2, 3, 4, 5, 6)
    out = []
    for child_pos, digit in enumerate(digits):
        mapped = _mapped_faces(frozenset({1, 2, 3, 4, 5, 6}), parity, child_pos, is_pent)
        if mapped:
            out.append((format(base + (digit << shift), 'x'), set(mapped)))
    return out


def _bulk_task(args):
    cell, faces, target_res = args
    return bulk_numpy(cell, target_res, faces)


def unordered_numpy_threads(parent, target_res, workers=WORKERS):
    tasks = [(c, f, target_res) for c, f in top_level_tasks(parent, target_res)]
    return np.concatenate(list(_THREADS.map(_bulk_task, tasks)))


def unordered_numpy_procs(parent, target_res, workers=WORKERS):
    global _PROCS
    if _PROCS is None:
        _PROCS = ProcessPoolExecutor(workers)
    tasks = [(c, f, target_res) for c, f in top_level_tasks(parent, target_res)]
    return np.concatenate(list(_PROCS.map(_bulk_task, tasks)))


def unordered_cpp_threads(parent, target_res, workers=WORKERS):
    tasks = top_level_tasks(parent, target_res)
    parts = _THREADS.map(lambda t: cpp.boundary_cell_ids(t[0], target_res, t[1]), tasks)
    return np.concatenate(list(parts))


# --- harness ---------------------------------------------------------------

def t(fn, reps):
    fn()
    s = time.perf_counter()
    for _ in range(reps):
        out = fn()
    return out, (time.perf_counter() - s) * 1000 / reps


def as_set(out):
    if isinstance(out, np.ndarray):
        return set(out.tolist())
    return {int(c, 16) if isinstance(c, str) else int(c) for c in out}


def main():
    print(f"threads/processes: {WORKERS}\n")
    for res, target in [(3, 10), (2, 11), (2, 13)]:
        parent = h3.latlng_to_cell(37.7759, -122.4180, res)
        total = 3 ** (target - res + 1) - 3
        reps = 5 if total < 100_000 else 2
        ref = as_set(trav_py(parent, target))
        print(f"=== res {res} -> {target}: {total:,} cells ===")
        print(f"{'approach':<10} {'implementation':<34} {'ms':>9}   ok")

        rows = [
            ("ordered", "unranking loop, Python",
             *t(lambda: [boundary_cell_at(parent, target, i) for i in range(total)], 1)),
            ("ordered", "unranking loop, C++",
             *t(lambda: [cpp.boundary_range_ids(parent, target, i, i + 1)[0]
                         for i in range(total)], 1)),
            ("ordered", "recursive descent -> ids, Python",
             *t(lambda: np.array(_boundary_child_ints(parent, target), dtype=np.uint64), reps)),
            ("ordered", "recursive descent -> hex, C++",
             *t(lambda: cpp.children_on_boundary_faces(parent, target), reps)),
            ("ordered", "bulk + sort -> ids, C++",
             *t(lambda: cpp_bulk_ids(parent, target, sort=True), reps)),
            ("ordered", f"index shards -> ids, C++ x{WORKERS} threads",
             *t(lambda: ordered_cpp_threads(parent, target, total), reps)),
            ("unordered", "level expansion, NumPy",
             *t(lambda: bulk_numpy(parent, target), reps)),
            ("unordered", f"level expansion, NumPy x{WORKERS} threads",
             *t(lambda: unordered_numpy_threads(parent, target), reps)),
            ("unordered", f"level expansion, NumPy x{WORKERS} procs",
             *t(lambda: unordered_numpy_procs(parent, target), 1)),
            ("unordered", "level expansion, C++",
             *t(lambda: cpp.boundary_cell_ids(parent, target), reps)),
            ("unordered", f"level expansion, C++ x{WORKERS} threads",
             *t(lambda: unordered_cpp_threads(parent, target), reps)),
        ]

        for approach, name, out, ms in rows:
            ok = "ok" if as_set(out) == ref else "MISMATCH"
            print(f"{approach:<10} {name:<34} {ms:9.2f}   {ok}")
        print()


if __name__ == "__main__":
    main()
