"""
Geometry utilities for H3-Toolkit (Pure Python/Shapely implementations).

This module provides geometry functions using Shapely for polygon operations.
These are the pure Python fallbacks when C++ bindings are not available.

Functions:
    - cell_boundary_to_geojson: Convert cell boundary to GeoJSON
    - get_boundary_cells: Get cells covering a polygon boundary
    - cell_boundary_from_children: Merge boundary children into polygon
    - get_buffered_h3_polygon: Buffer a cell's native boundary
    - get_buffered_boundary_polygon: Buffer boundary children polygon

All functions return GeoJSON-compatible output for easy visualization with
libraries like Folium, Leaflet, or Mapbox.

Note: For better performance, use the C++ versions (*_cpp suffix) when available.
"""
import warnings

import h3
import geojson
from math import cos, radians
from typing import Set, Dict, Any
from shapely.geometry import Polygon

# Import from package level to use C++ binding when available
def _get_children_on_boundary_faces():
    try:
        from ._h3_boundary_cpp import children_on_boundary_faces
        return children_on_boundary_faces
    except ImportError:
        from .utils import children_on_boundary_faces
        return children_on_boundary_faces


# Above this many cells, Boost's pairwise merge beats H3's own union, which
# turns out to be roughly cubic in cell count: 726 cells merge in 5 ms, 6,558
# in 3.3 s, 19,680 in 29 s, against 9 ms / 99 ms / 346 ms for the C++ path.
# Below the threshold H3's union wins on call overhead, so we switch rather
# than always preferring one.
_CPP_UNION_THRESHOLD = 1000


def _get_cpp_merge():
    try:
        from ._h3_boundary_cpp import merged_boundary_of_cells
        return merged_boundary_of_cells
    except ImportError:
        return None

def cell_boundary_to_geojson(h: str) -> Dict[str, Any]:
    """
    Returns the cell's own boundary as a GeoJSON Feature.

    Args:
        h: H3 cell index (hex string).

    Returns:
        GeoJSON Feature with a Polygon geometry (closed [lon, lat] ring) and
        a properties dict containing "h3_index".
    """
    # h3-py v4: cell_to_boundary returns ((lat, lon), ...) tuples
    boundary = h3.cell_to_boundary(h)
    # Convert to GeoJSON format: [[lon, lat], ...] and close the ring
    coords = [[pt[1], pt[0]] for pt in boundary]
    coords.append(coords[0])  # Close the polygon
    polygon = geojson.Polygon([coords])
    return geojson.Feature(geometry=polygon, properties={"h3_index": h})

def get_boundary_cells(polygon_geojson: Dict[str, Any], res: int) -> Dict[str, Set[int]]:
    """
    Identifies H3 cells at `res` that cover the polygon boundary and determine
    which of their faces align with the polygon's edge.

    Strategy:
    1. Polyfill the polygon to get the set of cells.
    2. Identify "edge cells" (cells with neighbors outside the set).
    3. For edge cells, mark faces as exposed.

    Note: cost scales with the polygon's *area* (the full polyfill is
    materialized), not its perimeter. The per-cell face sets are currently a
    placeholder — every edge cell is reported with all faces {1-6}; a refined
    per-face mapping is not implemented.

    Args:
        polygon_geojson: GeoJSON dictionary (Polygon).
        res: Target H3 resolution.

    Returns:
        Dict mapping H3 index (str) to a Set of exposed face indices, always
        {1, 2, 3, 4, 5, 6} in the current implementation.
    """
    # h3-py v4: Use polygon_to_cells with GeoJSON-style polygon
    # Extract coordinates from GeoJSON and convert to h3.LatLngPoly
    coords = polygon_geojson.get("coordinates", [[]])[0]
    
    # Convert from [lon, lat] to (lat, lon) for h3-py
    outer_ring = [(pt[1], pt[0]) for pt in coords]
    
    # Create H3 polygon and fill
    h3_poly = h3.LatLngPoly(outer_ring)
    cells = h3.polygon_to_cells(h3_poly, res)
    cells_set = set(cells)

    edge_cells = {}
    
    for c in cells_set:
        # Check all neighbors - if any neighbor is outside the set, cell is on boundary
        is_boundary = False
        neighbors = h3.grid_disk(c, 1)
        for n in neighbors:
            if n != c and n not in cells_set:
                is_boundary = True
                break
        
        if is_boundary:
            # Mark all faces as potentially exposed (refined mapping TBD)
            edge_cells[c] = {1, 2, 3, 4, 5, 6} 

    return edge_cells


def cell_boundary_from_children(parent: str, target_res: int) -> Dict[str, Any]:
    """
    Returns the geometric boundary (GeoJSON Polygon) of a parent cell,
    computed as the union of its boundary children at `target_res`.

    Merges with H3's native cells_to_h3shape for small boundaries and with
    Boost.Geometry (when the extension is built) for large ones — H3's union
    scales roughly cubically, so past a thousand or so cells the C++ path is
    orders of magnitude faster for an identical result.

    Args:
        parent: H3 cell index
        target_res: Resolution for boundary children (must be > parent resolution)

    Returns:
        GeoJSON Feature with the merged boundary polygon
    """
    # Get children_on_boundary_faces (C++ or Python)
    children_on_boundary_faces = _get_children_on_boundary_faces()

    # Get all boundary children
    boundary_children = children_on_boundary_faces(parent, target_res)

    if not boundary_children:
        # Fallback to parent boundary if no children found
        return cell_boundary_to_geojson(parent)

    # Large boundary: hand the merge to Boost rather than H3's union.
    if len(boundary_children) >= _CPP_UNION_THRESHOLD:
        cpp_merge = _get_cpp_merge()
        if cpp_merge is not None:
            coords = cpp_merge(list(boundary_children))
            if coords:
                geojson_coords = [[c[0], c[1]] for c in coords]
                if geojson_coords[0] != geojson_coords[-1]:
                    geojson_coords.append(geojson_coords[0])
                return geojson.Feature(
                    geometry=geojson.Polygon([geojson_coords]),
                    properties={
                        "h3_index": parent,
                        "child_resolution": target_res,
                        "num_boundary_cells": len(boundary_children),
                    },
                )

    # Use H3's native function - MUCH faster than Shapely unary_union
    try:
        h3_shape = h3.cells_to_h3shape(boundary_children)

        # Convert H3Shape to a list of LatLngPoly: cells_to_h3shape returns a
        # bare LatLngPoly (not iterable) when the union is a single polygon
        if isinstance(h3_shape, h3.LatLngPoly):
            polygons = [h3_shape]
        else:
            polygons = list(h3_shape)
        
        if not polygons:
            return cell_boundary_to_geojson(parent)
        
        # Take the largest polygon by area (matches the C++ backend)
        # Each LatLngPoly has .outer which is the outer ring
        largest = max(
            polygons,
            key=lambda p: Polygon([(pt[1], pt[0]) for pt in p.outer]).area,
        )
        
        # Convert to GeoJSON format [[lon, lat], ...]
        geojson_coords = [[pt[1], pt[0]] for pt in largest.outer]
        geojson_coords.append(geojson_coords[0])  # Close the ring
        
        polygon = geojson.Polygon([geojson_coords])
        
        return geojson.Feature(
            geometry=polygon, 
            properties={
                "h3_index": parent,
                "child_resolution": target_res,
                "num_boundary_cells": len(boundary_children)
            }
        )
        
    except Exception as e:
        # Fallback to Shapely if H3 method fails — warn so the ~10x slowdown
        # doesn't go unnoticed
        warnings.warn(
            f"h3.cells_to_h3shape failed ({e!r}); falling back to slower Shapely union",
            RuntimeWarning,
            stacklevel=2,
        )
        from shapely.ops import unary_union
        
        polygons = []
        for child in boundary_children:
            boundary = h3.cell_to_boundary(child)
            coords = [(pt[1], pt[0]) for pt in boundary]
            polygons.append(Polygon(coords))
        
        merged = unary_union(polygons)
        
        if merged.geom_type == 'Polygon':
            coords = [list(merged.exterior.coords)]
        elif merged.geom_type == 'MultiPolygon':
            largest = max(merged.geoms, key=lambda p: p.area)
            coords = [list(largest.exterior.coords)]
        else:
            return cell_boundary_to_geojson(parent)
        
        geojson_coords = [[c[0], c[1]] for c in coords[0]]
        polygon = geojson.Polygon([geojson_coords])
        
        return geojson.Feature(
            geometry=polygon, 
            properties={
                "h3_index": parent,
                "child_resolution": target_res,
                "num_boundary_cells": len(boundary_children)
            }
        )


def get_buffered_h3_polygon(cell: str, buffer_meters: float = None) -> Dict[str, Any]:
    """
    Returns a buffered polygon using pure Python/Shapely.
    
    This simply buffers the cell's native boundary. Fast but less accurate
    than computing actual boundary children.
    
    Args:
        cell: H3 cell index
        buffer_meters: Buffer distance in meters. If None, auto-calculated as
                      100% of intermediate resolution edge length.
                      
    Returns:
        GeoJSON Feature with the buffered polygon
    """
    res = h3.get_resolution(cell)
    intermediate_res = min(res + 4, 15)  # Use res+4 for buffer calculation
    
    # Auto-calculate buffer as 100% of intermediate edge length
    if buffer_meters is None:
        edge_km = h3.average_hexagon_edge_length(intermediate_res, unit='km')
        buffer_meters = edge_km * 1000 * 1.0
    
    # Get the cell boundary
    boundary = h3.cell_to_boundary(cell)
    coords = [(pt[1], pt[0]) for pt in boundary]  # (lon, lat) for shapely
    
    poly = Polygon(coords)
    
    # Convert buffer from meters to degrees (approximate); use the average
    # vertex latitude as reference (matches the C++ backend)
    lat = sum(pt[0] for pt in boundary) / len(boundary)
    meters_per_degree_lat = 111320
    meters_per_degree_lon = 111320 * abs(cos(radians(lat)))
    
    avg_meters_per_degree = (meters_per_degree_lat + meters_per_degree_lon) / 2
    buffer_degrees = buffer_meters / avg_meters_per_degree
    
    buffered = poly.buffer(buffer_degrees)
    
    # Convert back to GeoJSON
    geojson_coords = [[c[0], c[1]] for c in buffered.exterior.coords]
    polygon = geojson.Polygon([geojson_coords])
    
    return geojson.Feature(
        geometry=polygon,
        properties={
            "h3_index": cell,
            "buffer_meters": buffer_meters,
            "method": "buffered_python"
        }
    )


def get_buffered_boundary_polygon(
    cell: str, 
    intermediate_res: int = 10, 
    buffer_meters: float = None
) -> Dict[str, Any]:
    """
    Hybrid approach using pure Python: Get boundary at intermediate resolution, 
    then buffer the result with Shapely.
    
    This is more accurate than just buffering the parent cell, but slower.
    
    Args:
        cell: H3 cell index
        intermediate_res: Resolution to compute actual boundary (default 10).
                         Must be >= cell resolution.
        buffer_meters: Additional buffer in meters. If None, auto-calculated based
                      on difference between intermediate_res and res 15.
                      
    Returns:
        GeoJSON Feature with the buffered boundary polygon
    """
    res = h3.get_resolution(cell)
    
    # Ensure intermediate_res is valid
    intermediate_res = max(intermediate_res, res + 1)
    intermediate_res = min(intermediate_res, 15)
    
    # Get boundary at intermediate resolution (Python implementation)
    boundary_geojson = cell_boundary_from_children(cell, intermediate_res)
    
    # If no buffer needed (already at res 15), return as-is
    if intermediate_res >= 15 or buffer_meters == 0:
        return boundary_geojson
    
    # Auto-calculate buffer based on intermediate resolution edge length
    if buffer_meters is None:
        edge_km = h3.average_hexagon_edge_length(intermediate_res, unit='km')
        # Buffer by 100% of intermediate cell edge length for safety
        buffer_meters = edge_km * 1000 * 1.0
    
    # Convert GeoJSON to Shapely polygon
    coords = boundary_geojson['geometry']['coordinates'][0]
    poly = Polygon([(c[0], c[1]) for c in coords])
    
    # Convert buffer from meters to degrees
    centroid = poly.centroid
    lat = centroid.y
    meters_per_degree_lat = 111320
    meters_per_degree_lon = 111320 * abs(cos(radians(lat)))
    avg_meters_per_degree = (meters_per_degree_lat + meters_per_degree_lon) / 2
    buffer_degrees = buffer_meters / avg_meters_per_degree
    
    # Apply buffer
    buffered = poly.buffer(buffer_degrees)
    
    # Convert back to GeoJSON
    geojson_coords = [[c[0], c[1]] for c in buffered.exterior.coords]
    polygon = geojson.Polygon([geojson_coords])
    
    return geojson.Feature(
        geometry=polygon,
        properties={
            "h3_index": cell,
            "intermediate_res": intermediate_res,
            "buffer_meters": buffer_meters,
            "num_boundary_cells": boundary_geojson['properties']['num_boundary_cells'],
            "method": "buffered_boundary"
        }
    )
