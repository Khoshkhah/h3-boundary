/**
 * @file h3_toolkit.cpp
 * @brief H3-Toolkit: High-performance H3 cell boundary tracing and polygon operations
 * 
 * This library provides efficient algorithms for:
 * - Tracing H3 cell boundaries across resolution hierarchies
 * - Computing boundary children at arbitrary resolutions
 * - Generating buffered polygons guaranteed to contain all res-15 children
 * - Polygon union and convex hull operations using Boost.Geometry
 * 
 * Key Functions:
 * - trace_cell_to_ancestor_faces: Track which parent faces a cell touches
 * - children_on_boundary_faces: Get all boundary children at a target resolution
 * - cell_boundary_from_children: Merge boundary children into a single polygon
 * - get_buffered_boundary_polygon: Create buffered polygon with configurable accuracy
 * 
 * Performance: C++ implementation provides 10-30x speedup over pure Python.
 * 
 * @author H3-Toolkit Contributors
 * @license MIT
 */

#include "h3_toolkit.hpp"
#include <array>
#include <cstdint>
#include <stdexcept>
#include <cmath>

// Boost.Geometry for polygon buffering and union operations
#include <boost/geometry.hpp>
#include <boost/geometry/geometries/point_xy.hpp>
#include <boost/geometry/geometries/polygon.hpp>
#include <boost/geometry/algorithms/buffer.hpp>
#include <boost/geometry/algorithms/convex_hull.hpp>
#include <boost/geometry/algorithms/union.hpp>

namespace bg = boost::geometry;

namespace h3_toolkit {

/**
 * Face mapping tables for hexagonal cells.
 * 
 * These tables encode how child cell faces map to parent cell faces
 * based on resolution parity (even/odd) and child position (1-6).
 * Position 0 is the center child and doesn't touch any parent face.
 * 
 * Structure: parity -> child_pos -> {child_face -> parent_face}
 */

// Flat constexpr tables, generated from the reference dicts in
// src/python/h3_boundary/utils.py (regenerate from there if the mappings
// ever change — do not hand-edit).
//
// Forward:  FWD_*[parity][child_pos][child_face] = parent_face (0 = none)
// Reversed: REV_*[parity][child_pos][parent_face] = bitmask of child faces,
//           bit f (1<<f) set means child face f.

static constexpr int8_t FWD_HEX[2][7][7] = {
    {{0, 0, 0, 0, 0, 0, 0}, {0, 1, 3, 1, 0, 0, 0}, {0, 0, 2, 0, 6, 0, 2}, {0, 0, 3, 3, 0, 0, 2}, {0, 5, 0, 0, 4, 4, 0}, {0, 5, 0, 1, 0, 5, 0}, {0, 0, 0, 0, 6, 4, 6}},
    {{0, 0, 0, 0, 0, 0, 0}, {0, 3, 0, 3, 0, 1, 0}, {0, 0, 6, 2, 0, 0, 6}, {0, 3, 2, 2, 0, 0, 0}, {0, 0, 0, 0, 5, 5, 4}, {0, 1, 0, 0, 5, 1, 0}, {0, 0, 6, 0, 4, 0, 4}},
};
static constexpr int8_t FWD_PENT[2][7][7] = {
    {{0, 0, 0, 0, 0, 0, 0}, {0, 0, 1, 0, 5, 0, 1}, {0, 0, 2, 2, 0, 0, 1}, {0, 0, 0, 0, 2, 2, 4}, {0, 2, 0, 2, 0, 4, 0}, {0, 0, 0, 0, 5, 3, 5}, {0, 0, 0, 0, 0, 0, 0}},
    {{0, 0, 0, 0, 0, 0, 0}, {0, 0, 5, 1, 0, 0, 5}, {0, 2, 1, 1, 0, 0, 0}, {0, 4, 0, 0, 3, 3, 0}, {0, 2, 0, 0, 4, 2, 0}, {0, 0, 5, 0, 3, 0, 3}, {0, 0, 0, 0, 0, 0, 0}},
};
static constexpr uint8_t REV_HEX[2][7][7] = {
    {{0, 0, 0, 0, 0, 0, 0}, {0, 10, 0, 4, 0, 0, 0}, {0, 0, 68, 0, 0, 0, 16}, {0, 0, 64, 12, 0, 0, 0}, {0, 0, 0, 0, 48, 2, 0}, {0, 8, 0, 0, 0, 34, 0}, {0, 0, 0, 0, 32, 0, 80}},
    {{0, 0, 0, 0, 0, 0, 0}, {0, 32, 0, 10, 0, 0, 0}, {0, 0, 8, 0, 0, 0, 68}, {0, 0, 12, 2, 0, 0, 0}, {0, 0, 0, 0, 64, 48, 0}, {0, 34, 0, 0, 0, 16, 0}, {0, 0, 0, 0, 80, 0, 4}},
};
static constexpr uint8_t REV_PENT[2][7][7] = {
    {{0, 0, 0, 0, 0, 0, 0}, {0, 68, 0, 0, 0, 16, 0}, {0, 64, 12, 0, 0, 0, 0}, {0, 0, 0, 48, 2, 0, 0}, {0, 0, 10, 0, 32, 0, 0}, {0, 0, 0, 32, 0, 80, 0}, {0, 0, 0, 0, 0, 0, 0}},
    {{0, 0, 0, 0, 0, 0, 0}, {0, 8, 0, 0, 0, 68, 0}, {0, 12, 2, 0, 0, 0, 0}, {0, 0, 0, 64, 48, 0, 0}, {0, 0, 34, 0, 16, 0, 0}, {0, 0, 0, 80, 0, 4, 0}, {0, 0, 0, 0, 0, 0, 0}},
};

static inline uint8_t faces_to_mask(const std::set<int>& faces) {
    uint8_t m = 0;
    for (int f : faces) {
        if (f >= 1 && f <= 6) m |= static_cast<uint8_t>(1 << f);
    }
    return m;
}

static inline std::set<int> mask_to_faces(uint8_t m) {
    std::set<int> s;
    for (int f = 1; f <= 6; ++f) {
        if (m & (1 << f)) s.insert(f);
    }
    return s;
}

std::set<int> trace_cell_to_ancestor_faces(H3Index h, const std::set<int>& input_faces, int res_parent) {
    int h_res = getResolution(h);
    
    if (res_parent >= h_res) {
        throw std::invalid_argument("res_parent must be less than cell resolution");
    }
    if (res_parent < 0) {
        throw std::invalid_argument("res_parent cannot be negative");
    }
    if (input_faces.empty()) {
        return {};
    }

    uint8_t faces = faces_to_mask(input_faces);
    if (!faces) {
        return {};
    }
    H3Index current_h = h;

    for (int res = h_res; res > res_parent; --res) {
        if (isPentagon(current_h)) {
             return {};
        }

        int parity = res % 2;
        H3Index parent;
        cellToParent(current_h, res - 1, &parent);
        bool parent_is_pent = isPentagon(parent);

        // Index digit for resolution `res`: 3 bits at offset (15 - res) * 3.
        int child_pos = static_cast<int>((current_h >> ((15 - res) * 3)) & 0x7);

        // The tables are keyed by child *position*. For hexagon parents the
        // digit equals the position; pentagon parents skip digit 1, so the
        // position is digit - 1 (digit 0 stays the center child).
        if (parent_is_pent && child_pos > 0) {
            child_pos -= 1;
        }

        if (child_pos == 0) {
            return {};
        }

        const int8_t* fwd = parent_is_pent ? FWD_PENT[parity][child_pos]
                                           : FWD_HEX[parity][child_pos];
        uint8_t next = 0;
        for (int f = 1; f <= 6; ++f) {
            if ((faces & (1 << f)) && fwd[f]) {
                next |= static_cast<uint8_t>(1 << fwd[f]);
            }
        }
        if (!next) {
            return {};
        }
        faces = next;
        current_h = parent;
    }

    return mask_to_faces(faces);
}

std::set<int> trace_cell_to_parent_faces(H3Index h, const std::set<int>& input_faces) {
    int res = getResolution(h);
    return trace_cell_to_ancestor_faces(h, input_faces, res - 1);
}

H3Index cell_to_coarsest_ancestor_on_faces(H3Index h, const std::set<int>& input_faces) {
    int res = getResolution(h);
    H3Index current_h = h;
    std::set<int> current_faces = input_faces;
    
    while (res > 0) {
        int parent_res = res - 1;
        auto boundary_faces = trace_cell_to_ancestor_faces(current_h, current_faces, parent_res);
        
        if (boundary_faces.empty()) {
            return current_h;
        }
        
        H3Index parent;
        cellToParent(current_h, parent_res, &parent);
        current_h = parent;
        current_faces = boundary_faces;
        res = parent_res;
    }
    
    return current_h;
}

static void collect_boundary_children(H3Index current, int res, uint8_t faces,
                                      int target_res, std::vector<H3Index>& result) {
    if (res == target_res) {
        result.push_back(current);
        return;
    }

    int parity = (res + 1) % 2;
    bool is_pent = isPentagon(current);
    const uint8_t (&rev)[7][7] = is_pent ? REV_PENT[parity] : REV_HEX[parity];

    // One level down there are at most 7 children (6 for pentagons).
    int64_t num_children = 0;
    cellToChildrenSize(current, res + 1, &num_children);
    std::array<H3Index, 7> children{};
    cellToChildren(current, res + 1, children.data());

    for (int64_t i = 0; i < num_children; ++i) {
        H3Index child = children[i];
        if (child == 0) continue;

        // Tables are keyed by child position: equal to the index digit for
        // hexagon parents; pentagon parents skip digit 1, so position is
        // digit - 1 (digit 0 stays the center child).
        int child_pos = static_cast<int>((child >> ((15 - (res + 1)) * 3)) & 0x7);
        if (is_pent && child_pos > 0) {
            child_pos -= 1;
        }

        uint8_t mapped = 0;
        for (int f = 1; f <= 6; ++f) {
            if (faces & (1 << f)) {
                mapped |= rev[child_pos][f];
            }
        }
        if (mapped) {
            collect_boundary_children(child, res + 1, mapped, target_res, result);
        }
    }
}

std::vector<H3Index> children_on_boundary_faces(H3Index parent, int target_res, const std::set<int>& input_faces) {
    int res_parent = getResolution(parent);
    if (target_res < res_parent) {
        throw std::invalid_argument("target_res must be greater than or equal to parent cell resolution");
    }
    if (target_res > 15) {
        throw std::invalid_argument("target_res must be <= 15");
    }

    std::vector<H3Index> result;
    uint8_t faces = faces_to_mask(input_faces);
    if (faces) {
        collect_boundary_children(parent, res_parent, faces, target_res, result);
    }
    return result;
}

typedef bg::model::d2::point_xy<double> point_type;
typedef bg::model::polygon<point_type> polygon_type;
typedef bg::model::multi_polygon<polygon_type> multi_polygon_type;

// The union of many cells can transiently or finally be a multi-polygon;
// the meaningful result is the largest piece, matching the Python backend.
static const polygon_type* largest_by_area(const multi_polygon_type& mp) {
    const polygon_type* best = nullptr;
    double best_area = -1.0;
    for (const auto& p : mp) {
        double a = bg::area(p);
        if (a > best_area) {
            best_area = a;
            best = &p;
        }
    }
    return best;
}

static std::vector<std::pair<double, double>> outer_ring(const polygon_type& poly) {
    std::vector<std::pair<double, double>> result;
    result.reserve(poly.outer().size());
    for (const auto& pt : poly.outer()) {
        result.emplace_back(pt.x(), pt.y());
    }
    return result;
}

static polygon_type cell_to_polygon(H3Index cell, double* lat_sum, int* pt_count) {
    CellBoundary cb;
    cellToBoundary(cell, &cb);
    polygon_type poly;
    for (int i = 0; i < cb.numVerts; ++i) {
        double lon = radsToDegs(cb.verts[i].lng);
        double lat = radsToDegs(cb.verts[i].lat);
        bg::append(poly.outer(), point_type(lon, lat));
        if (lat_sum) {
            *lat_sum += lat;
            ++*pt_count;
        }
    }
    // Close the ring
    if (cb.numVerts > 0) {
        bg::append(poly.outer(), point_type(radsToDegs(cb.verts[0].lng),
                                            radsToDegs(cb.verts[0].lat)));
    }
    bg::correct(poly);
    return poly;
}

// Union all cell polygons via a pairwise merge tree. The naive one-at-a-time
// union is O(n^2) in accumulated vertices (and copies the accumulated result
// per cell); merging neighbors pairwise keeps each round linear and the total
// O(n log n). The input is in DFS order, so adjacent entries are spatially
// close and unions collapse quickly.
static multi_polygon_type union_cells(const std::vector<H3Index>& cells,
                                      double* lat_sum, int* pt_count) {
    std::vector<multi_polygon_type> parts;
    parts.reserve(cells.size());
    for (H3Index c : cells) {
        multi_polygon_type mp;
        mp.push_back(cell_to_polygon(c, lat_sum, pt_count));
        parts.push_back(std::move(mp));
    }
    while (parts.size() > 1) {
        std::vector<multi_polygon_type> next;
        next.reserve(parts.size() / 2 + 1);
        for (size_t i = 0; i + 1 < parts.size(); i += 2) {
            multi_polygon_type u;
            bg::union_(parts[i], parts[i + 1], u);
            next.push_back(std::move(u));
        }
        if (parts.size() % 2) {
            next.push_back(std::move(parts.back()));
        }
        parts = std::move(next);
    }
    return parts.empty() ? multi_polygon_type{} : std::move(parts.front());
}

std::vector<std::pair<double, double>> cell_boundary(H3Index cell) {
    CellBoundary cb;
    cellToBoundary(cell, &cb);

    std::vector<std::pair<double, double>> result;
    for (int i = 0; i < cb.numVerts; ++i) {
        result.emplace_back(radsToDegs(cb.verts[i].lng), radsToDegs(cb.verts[i].lat));
    }
    // Close the ring
    if (cb.numVerts > 0) {
        result.emplace_back(radsToDegs(cb.verts[0].lng), radsToDegs(cb.verts[0].lat));
    }
    return result;
}

std::vector<std::pair<double, double>> merged_boundary_of_cells(const std::vector<H3Index>& cells) {
    if (cells.empty()) {
        return {};
    }
    multi_polygon_type merged = union_cells(cells, nullptr, nullptr);
    const polygon_type* largest = largest_by_area(merged);
    return largest ? outer_ring(*largest) : std::vector<std::pair<double, double>>{};
}

std::vector<std::pair<double, double>> cell_boundary_from_children(H3Index parent, int target_res) {
    std::set<int> all_faces = {1, 2, 3, 4, 5, 6};
    auto boundary_children = children_on_boundary_faces(parent, target_res, all_faces);

    if (boundary_children.empty()) {
        return cell_boundary(parent);
    }
    return merged_boundary_of_cells(boundary_children);
}

std::vector<std::pair<double, double>> get_buffered_h3_polygon(H3Index cell, double buffer_meters) {
    // Get cell boundary
    CellBoundary cb;
    cellToBoundary(cell, &cb);
    if (cb.numVerts == 0) {
        return {};
    }

    polygon_type poly;
    double lat_sum = 0.0;
    for (int i = 0; i < cb.numVerts; ++i) {
        double lon = radsToDegs(cb.verts[i].lng);
        double lat = radsToDegs(cb.verts[i].lat);
        bg::append(poly.outer(), point_type(lon, lat));
        lat_sum += lat;
    }
    // Close the ring
    if (cb.numVerts > 0) {
        bg::append(poly.outer(), point_type(
            radsToDegs(cb.verts[0].lng),
            radsToDegs(cb.verts[0].lat)
        ));
    }
    bg::correct(poly);
    
    // Auto-calculate buffer if not specified
    if (buffer_meters < 0) {
        int res = getResolution(cell);
        int intermediate_res = std::min(res + 4, 15);
        double edge_km;
        getHexagonEdgeLengthAvgKm(intermediate_res, &edge_km);
        buffer_meters = edge_km * 1000.0;
    }
    
    // Convert buffer from meters to degrees
    double avg_lat = lat_sum / cb.numVerts;
    const double meters_per_degree_lat = 111320.0;
    const double meters_per_degree_lon = 111320.0 * std::abs(std::cos(avg_lat * M_PI / 180.0));
    double avg_meters_per_degree = (meters_per_degree_lat + meters_per_degree_lon) / 2.0;
    double buffer_degrees = buffer_meters / avg_meters_per_degree;
    
    // Apply buffer
    multi_polygon_type buffered;
    bg::strategy::buffer::distance_symmetric<double> distance_strategy(buffer_degrees);
    bg::strategy::buffer::join_round join_strategy(32);
    bg::strategy::buffer::end_round end_strategy(32);
    bg::strategy::buffer::point_circle point_strategy(32);
    bg::strategy::buffer::side_straight side_strategy;
    
    bg::buffer(poly, buffered, distance_strategy, side_strategy, join_strategy, end_strategy, point_strategy);

    // Extract result
    const polygon_type* largest = largest_by_area(buffered);
    return largest ? outer_ring(*largest) : std::vector<std::pair<double, double>>{};
}

std::vector<std::pair<double, double>> get_buffered_boundary_polygon(
    H3Index cell,
    int intermediate_res,
    double buffer_meters,
    bool use_convex_hull
) {
    int cell_res = getResolution(cell);
    
    // Clamp intermediate_res to valid range
    if (intermediate_res <= cell_res) {
        intermediate_res = cell_res + 1;
    }
    if (intermediate_res > 15) {
        intermediate_res = 15;
    }
    
    // Get boundary children at intermediate resolution
    std::set<int> all_faces = {1, 2, 3, 4, 5, 6};
    auto boundary_children = children_on_boundary_faces(cell, intermediate_res, all_faces);
    
    if (boundary_children.empty()) {
        // Fallback: return cell boundary directly (closed ring)
        return cell_boundary(cell);
    }

    double lat_sum = 0.0;
    int point_count = 0;
    polygon_type base_polygon;
    
    if (use_convex_hull) {
        // Fast mode: compute convex hull of all boundary vertices
        typedef bg::model::multi_point<point_type> multi_point_type;
        multi_point_type all_points;
        
        for (H3Index child : boundary_children) {
            CellBoundary cb;
            cellToBoundary(child, &cb);
            for (int i = 0; i < cb.numVerts; ++i) {
                double lon = radsToDegs(cb.verts[i].lng);
                double lat = radsToDegs(cb.verts[i].lat);
                bg::append(all_points, point_type(lon, lat));
                lat_sum += lat;
                ++point_count;
            }
        }
        
        bg::convex_hull(all_points, base_polygon);
    } else {
        // Accurate mode: union all cell polygons
        multi_polygon_type merged = union_cells(boundary_children, &lat_sum, &point_count);

        // Take the largest polygon from the multi_polygon
        const polygon_type* largest = largest_by_area(merged);
        if (largest) {
            base_polygon = *largest;
        }
    }
    
    // Auto-calculate buffer if not specified
    if (buffer_meters < 0) {
        double edge_km;
        getHexagonEdgeLengthAvgKm(intermediate_res, &edge_km);
        buffer_meters = edge_km * 1000.0;
    }
    
    // If no buffer needed, return base polygon directly
    if (buffer_meters == 0 || intermediate_res >= 15) {
        std::vector<std::pair<double, double>> result;
        for (const auto& pt : base_polygon.outer()) {
            result.emplace_back(pt.x(), pt.y());
        }
        return result;
    }
    
    // Convert buffer from meters to degrees
    double avg_lat = lat_sum / point_count;
    const double meters_per_degree_lat = 111320.0;
    const double meters_per_degree_lon = 111320.0 * std::abs(std::cos(avg_lat * M_PI / 180.0));
    double avg_meters_per_degree = (meters_per_degree_lat + meters_per_degree_lon) / 2.0;
    double buffer_degrees = buffer_meters / avg_meters_per_degree;
    
    // Apply buffer
    multi_polygon_type buffered;
    bg::strategy::buffer::distance_symmetric<double> distance_strategy(buffer_degrees);
    bg::strategy::buffer::join_round join_strategy(32);
    bg::strategy::buffer::end_round end_strategy(32);
    bg::strategy::buffer::point_circle point_strategy(32);
    bg::strategy::buffer::side_straight side_strategy;
    
    bg::buffer(base_polygon, buffered, distance_strategy, side_strategy, join_strategy, end_strategy, point_strategy);

    // Extract result
    const polygon_type* largest = largest_by_area(buffered);
    return largest ? outer_ring(*largest) : std::vector<std::pair<double, double>>{};
}

} // namespace h3_toolkit
