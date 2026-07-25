#!/usr/bin/env python3
"""
Regenerates docs/assets/buffering.png — the two-panel figure for the
Buffered Polygons page.

Left:  why a cell's own hexagon is not a container — descendants straddle it.
Right: the three polygons that try to bound it, and which ones succeed.

Requires matplotlib (dev-only; not needed to use the package).

    PYTHONPATH=src/python python docs/generate_buffering_figure.py
"""
from math import cos, radians

import h3
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
from shapely.geometry import Point, Polygon, shape

import h3_boundary as h3b

PARENT_RES = 6
FINE_RES = 9          # descendants to draw (343 — dense enough to see, sparse enough to read)
INTERMEDIATE = 9      # resolution the boundary is traced at
OUT = "docs/assets/buffering.png"

INSIDE = "#d8dbe0"
STRADDLE = "#f0883e"
HEXAGON = "#238636"
EXACT = "#1f6feb"
UNION = "#f85149"
HULL = "#a371f7"
SIMPLE = "#6e7781"


def ring(cell):
    return [(lng, lat) for lat, lng in h3.cell_to_boundary(cell)]


def frame(ax, parent, lat):
    xs = [p[0] for p in ring(parent)]
    ys = [p[1] for p in ring(parent)]
    padx = (max(xs) - min(xs)) * 0.16
    pady = (max(ys) - min(ys)) * 0.16
    ax.set_xlim(min(xs) - padx, max(xs) + padx)
    ax.set_ylim(min(ys) - pady, max(ys) + pady)
    ax.set_aspect(1 / cos(radians(lat)))
    ax.axis("off")


def main():
    parent = h3.latlng_to_cell(37.7759, -122.4180, PARENT_RES)
    lat, _ = h3.cell_to_latlng(parent)
    hexagon = Polygon(ring(parent))

    children = h3.cell_to_children(parent, FINE_RES)
    straddling = [c for c in children
                  if any(not hexagon.contains(Point(x, y)) for x, y in ring(c))]
    contained = [c for c in children if c not in set(straddling)]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.4, 5.6), dpi=130)

    # ---- left: the problem -------------------------------------------------
    for c in contained:
        ax1.add_patch(MplPolygon(ring(c), closed=True, facecolor=INSIDE,
                                 edgecolor="#eceef1", linewidth=0.3))
    for c in straddling:
        ax1.add_patch(MplPolygon(ring(c), closed=True, facecolor=STRADDLE,
                                 edgecolor="#b3600f", linewidth=0.4))
    ax1.add_patch(MplPolygon(ring(parent), closed=True, facecolor="none",
                             edgecolor=HEXAGON, linewidth=2.6))
    frame(ax1, parent, lat)
    ax1.set_title("The cell's own hexagon is not a container", fontsize=12, pad=8)
    ax1.legend(handles=[
        plt.Line2D([], [], color=HEXAGON, lw=2.4, label=f"the cell (res {PARENT_RES})"),
        MplPolygon([(0, 0)], facecolor=STRADDLE, edgecolor="#b3600f",
                   label=f"descendants crossing it ({len(straddling)})"),
        MplPolygon([(0, 0)], facecolor=INSIDE, edgecolor="#eceef1",
                   label=f"descendants inside ({len(contained)})"),
    ], loc="upper center", bbox_to_anchor=(0.5, -0.01), ncol=3, frameon=False,
        fontsize=9, handlelength=1.4, columnspacing=1.2, handletextpad=0.5)

    # ---- right: the three polygons -----------------------------------------
    exact = shape(h3b.cell_boundary_from_children(parent, INTERMEDIATE)["geometry"])
    union = shape(h3b.get_buffered_boundary_polygon(parent, INTERMEDIATE)["geometry"])
    simple = shape(h3b.get_buffered_h3_polygon(parent)["geometry"])
    hull = None
    if h3b.cpp_geom_available():
        hull = shape(h3b.get_buffered_boundary_polygon_cpp(
            parent, INTERMEDIATE, None, True)["geometry"])

    ax2.add_patch(MplPolygon(list(exact.exterior.coords), closed=True,
                             facecolor=EXACT, alpha=0.13, edgecolor=EXACT, linewidth=1.6))
    if hull is not None:
        ax2.add_patch(MplPolygon(list(hull.exterior.coords), closed=True, facecolor="none",
                                 edgecolor=HULL, linewidth=2.0))
    ax2.add_patch(MplPolygon(list(union.exterior.coords), closed=True, facecolor="none",
                             edgecolor=UNION, linewidth=2.0, linestyle=(0, (5, 3))))
    ax2.add_patch(MplPolygon(list(simple.exterior.coords), closed=True, facecolor="none",
                             edgecolor=SIMPLE, linewidth=1.6, linestyle=(0, (2, 3))))

    # mark descendants the simple buffer misses
    missed = [c for c in children
              if any(not simple.contains(Point(x, y)) for x, y in ring(c))]
    for c in missed:
        ax2.add_patch(MplPolygon(ring(c), closed=True, facecolor=STRADDLE,
                                 edgecolor="#b3600f", linewidth=0.4, alpha=0.95))

    frame(ax2, parent, lat)
    ax2.set_title("Three ways to bound it", fontsize=12, pad=8)
    handles = [
        MplPolygon([(0, 0)], facecolor=EXACT, alpha=0.3, edgecolor=EXACT,
                   label=f"exact boundary (res {INTERMEDIATE})"),
        plt.Line2D([], [], color=UNION, lw=2, ls="--", label="buffered union — contains all"),
    ]
    if hull is not None:
        handles.append(plt.Line2D([], [], color=HULL, lw=2, label="buffered hull — contains all"))
    handles += [
        plt.Line2D([], [], color=SIMPLE, lw=1.6, ls=":", label="cell buffer — too tight"),
        MplPolygon([(0, 0)], facecolor=STRADDLE, edgecolor="#b3600f",
                   label=f"outside the cell buffer ({len(missed)})"),
    ]
    ax2.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.01),
               ncol=3, frameon=False, fontsize=9, handlelength=1.4,
               columnspacing=1.2, handletextpad=0.5)

    fig.tight_layout()
    fig.savefig(OUT, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT}: {len(straddling)}/{len(children)} straddle the hexagon, "
          f"{len(missed)} outside the cell buffer")


if __name__ == "__main__":
    main()
