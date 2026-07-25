---
layout: default
title: Buffered Polygons
nav_order: 7
---

# Buffered Polygons
{: .no_toc }

One polygon that safely contains a cell and everything inside it — and the three ways to get one.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## Why a cell's own outline is not enough

An H3 cell's `cell_to_boundary` is a plain hexagon. Its *descendants*, however, do not tile that hexagon — they tile a slightly wobbly shape that crosses the hexagon's edges in both directions. You can see it in the figure on the [home page](index.md): the orange res-8 cells straddle the blue res-5 outline rather than sitting neatly inside it.

So if you use the parent's hexagon as a filter — "is this fine cell inside my region?" — you will wrongly exclude cells that genuinely belong to it. A **buffered polygon** fixes this: take the shape, push its edges outward by a safe margin, and you have one polygon guaranteed to contain every descendant.

That is what these functions produce. All of them return a GeoJSON `Feature`, ready for Folium, Leaflet, or a spatial database.

---

## The three functions

### `get_buffered_boundary_polygon(cell, intermediate_res=10, buffer_meters=None)`

The accurate one, and the one to reach for by default. It traces the cell's real boundary at `intermediate_res`, merges those cells into a polygon, then buffers it.

```python
poly = h3b.get_buffered_boundary_polygon(cell, intermediate_res=10)
poly["properties"]["buffer_meters"]   # 75.86 — the margin that was applied
```

### `get_buffered_boundary_polygon_cpp(..., use_convex_hull=True)`

Same thing, but replaces the union with a **convex hull** of the boundary vertices. About 20× faster and far simpler in shape, at the cost of also covering ground the cell does not occupy — a hull cannot follow the hexagon's concave wobble.

Use it when a slightly generous polygon is acceptable: pre-filtering candidates before an exact test, drawing an overview, or bounding a query.

### `get_buffered_h3_polygon(cell, buffer_meters=None)`

The cheap one: it buffers the cell's **own hexagon**, never looking at any children. Fast (~0.2 ms) and small, but see the containment table below — it is an approximation of the cell, not a container for its descendants.

---

## What each one actually guarantees

Measured on a resolution-6 parent, testing whether every vertex of all 16,807 descendants at resolution 11 falls inside the polygon:

| Function | Time | Vertices | Area vs exact | Children left outside |
|---|---|---|---|---|
| `get_buffered_boundary_polygon` (union) | 6.0 ms | 3,033 | 1.07× | **0 of 16,807** |
| `get_buffered_boundary_polygon_cpp` (union) | 7.6 ms | 1,937 | 1.06× | **0 of 16,807** |
| `get_buffered_boundary_polygon_cpp` (hull) | 0.4 ms | 61 | 1.21× | **0 of 16,807** |
| `get_buffered_h3_polygon` | 0.2 ms | 71 | 1.05× | 896 of 16,807 |

Two things to take from this:

- **Both boundary-based modes contain everything**, and they hold up away from the equator too — the same test at the equator, mid-latitude, Stockholm and 75°N leaves zero children outside in each case.
- **`get_buffered_h3_polygon` does not.** About 5% of fine descendants fall outside it, because the fractal boundary reaches further out than the nominal hexagon plus its margin. It is the right tool for "roughly where is this cell", and the wrong one for "does this cell contain that point".

The hull's cost shows up as **area**, not as misses: 21% larger than the exact footprint, against 6–7% for the union.

---

## Choosing the buffer distance

Left as `None`, the margin is computed for you:

- `get_buffered_boundary_polygon` uses 100% of the edge length at `intermediate_res` — the margin that makes containment hold no matter how much finer the descendants go.
- `get_buffered_h3_polygon` uses the edge length four resolutions below the cell.

Pass `buffer_meters` explicitly to override, and `0` to skip buffering entirely and get the merged boundary itself.

`intermediate_res` is the other dial: higher means the traced boundary hugs the true shape more closely (and the auto-margin shrinks accordingly), at the cost of more cells to merge. The default of 10 suits parents around resolution 5–7; for much coarser parents, raise it.

---

## Caveats

- **Metres are converted to degrees** using a single scale factor for the polygon, averaging the latitude and longitude scales. The containment tests above pass at every latitude tried, but the buffer is not exactly circular on the ground — treat `buffer_meters` as a close approximation rather than a survey-grade distance.
- **Cells crossing the antimeridian are not handled.** Coordinates stay in [-180, 180], so a polygon spanning the date line will be drawn as a band across the whole map. This affects a small number of cells in the Pacific.
- **`use_convex_hull` is C++-only.** The pure-Python `get_buffered_boundary_polygon` always unions; if the extension is not built, the fast mode is unavailable. Check with `cpp_geom_available()`.

---

## See it

`notebook/buffered_polygon_demo.ipynb` renders all three on one map, together with the exact boundary, and reproduces the containment table above.
