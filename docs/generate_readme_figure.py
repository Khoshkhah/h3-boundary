#!/usr/bin/env python3
"""
Regenerates docs/assets/boundary_children.png — the README figure.

Shows a parent cell with its boundary children highlighted and its interior
children greyed out, which is the whole point of the library: only the ring is
computed. Requires matplotlib (a dev-only dependency, not needed to use the
package).

Run from the repo root:
    PYTHONPATH=src/python python docs/generate_readme_figure.py
"""
from math import cos, radians

import h3
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

import h3_boundary as h3b

PARENT_RES = 5
TARGET_RES = 8
OUT = "docs/assets/boundary_children.png"

INTERIOR = "#d8dbe0"
INTERIOR_EDGE = "#eceef1"
BOUNDARY = "#f0883e"
BOUNDARY_EDGE = "#b3600f"
PARENT_EDGE = "#1f6feb"


def ring(cell):
    """Cell boundary as [(lng, lat), ...]."""
    return [(lng, lat) for lat, lng in h3.cell_to_boundary(cell)]


def main():
    parent = h3.latlng_to_cell(37.7759, -122.4180, PARENT_RES)
    depth = TARGET_RES - PARENT_RES

    all_children = h3.cell_to_children(parent, TARGET_RES)
    boundary = set(h3b.children_on_boundary_faces(parent, TARGET_RES))
    interior = [c for c in all_children if c not in boundary]

    assert len(boundary) == 3 ** (depth + 1) - 3, len(boundary)
    assert len(all_children) == 7 ** depth

    fig, ax = plt.subplots(figsize=(7.0, 6.2), dpi=130)

    for cell in interior:
        ax.add_patch(MplPolygon(ring(cell), closed=True,
                                facecolor=INTERIOR, edgecolor=INTERIOR_EDGE, linewidth=0.3))
    for cell in boundary:
        ax.add_patch(MplPolygon(ring(cell), closed=True,
                                facecolor=BOUNDARY, edgecolor=BOUNDARY_EDGE, linewidth=0.4))
    ax.add_patch(MplPolygon(ring(parent), closed=True,
                            facecolor="none", edgecolor=PARENT_EDGE, linewidth=2.4))

    lat, lng = h3.cell_to_latlng(parent)
    xs = [p[0] for p in ring(parent)]
    ys = [p[1] for p in ring(parent)]
    pad = (max(xs) - min(xs)) * 0.04
    ax.set_xlim(min(xs) - pad, max(xs) + pad)
    ax.set_ylim(min(ys) - pad, max(ys) + pad)
    # Keep hexagons hexagonal: one degree of longitude is shorter than one of latitude.
    ax.set_aspect(1 / cos(radians(lat)))
    ax.axis("off")

    ax.set_title(
        f"A resolution-{PARENT_RES} cell traced at resolution {TARGET_RES}",
        fontsize=13, pad=10, color="#27262b",
    )

    # The legend carries the counts, so no separate caption is needed. It also
    # explains the blue outline: the parent's own boundary is a plain hexagon,
    # while its children tile a fractal that straddles it.
    handles = [
        plt.Line2D([], [], color=PARENT_EDGE, linewidth=2.2,
                   label=f"parent cell (res {PARENT_RES})"),
        MplPolygon([(0, 0)], facecolor=BOUNDARY, edgecolor=BOUNDARY_EDGE,
                   label=f"boundary children ({len(boundary)}) — computed"),
        MplPolygon([(0, 0)], facecolor=INTERIOR, edgecolor=INTERIOR_EDGE,
                   label=f"interior children ({len(interior)}) — never generated"),
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.01),
              ncol=3, frameon=False, fontsize=9.5, handlelength=1.5,
              columnspacing=1.4, handletextpad=0.6)

    fig.tight_layout()
    fig.savefig(OUT, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT}: {len(boundary)} boundary of {len(all_children)} children")


if __name__ == "__main__":
    main()
