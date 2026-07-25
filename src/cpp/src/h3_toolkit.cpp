/**
 * @file h3_toolkit.cpp
 * @brief C++ core of h3-boundary: H3 cell boundary tracing and polygon operations.
 *
 * Implements the API declared in h3_toolkit.hpp (full parameter docs live
 * there):
 * - Face tracing up the hierarchy and boundary-children enumeration down it,
 *   driven by flat constexpr face-mapping tables.
 * - Boundary polygons (Boost.Geometry union of boundary cells) and buffered
 *   polygons (convex hull or union, then buffer).
 *
 * The pure-Python reference implementation lives in
 * src/python/h3_boundary/{utils.py,geom.py}; tests/python/test_parity.py
 * keeps the two backends in lockstep.
 *
 * @license MIT
 */

#include "h3_toolkit.hpp"
#include <array>
#include <cstdint>
#include <deque>
#include <stdexcept>
#include <unordered_set>
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

/// Traces which of the ancestor's faces (at res_parent) the cell h lies on,
/// walking up one level at a time through the forward face tables.
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

/// Convenience overload of trace_cell_to_ancestor_faces for the immediate parent.
std::set<int> trace_cell_to_parent_faces(H3Index h, const std::set<int>& input_faces) {
    int res = getResolution(h);
    return trace_cell_to_ancestor_faces(h, input_faces, res - 1);
}

/// Walks up the hierarchy while the cell keeps tracing to at least one of the
/// requested faces; returns the last ancestor for which that held.
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

/// Enumerates all descendants of parent at target_res lying on the given
/// parent faces. Only the boundary subtree is visited, so cost scales with
/// the boundary length, not the parent's interior.
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

// Minimal open-addressing hash set for H3 indexes: linear probing,
// power-of-two capacity, 0 as the empty sentinel (0 is never a valid cell).
// Replaces std::unordered_set in the walk's hot loop — no per-node
// allocation, cache-friendly probes.
class FlatSet {
    std::vector<H3Index> slots_;
    size_t mask_;
    size_t count_ = 0;

    static size_t hash(H3Index v) {
        v ^= v >> 33;
        v *= 0xff51afd7ed558ccdULL;
        v ^= v >> 33;
        return static_cast<size_t>(v);
    }

    void grow() {
        std::vector<H3Index> old;
        old.swap(slots_);
        slots_.assign(old.size() * 2, 0);
        mask_ = slots_.size() - 1;
        for (H3Index v : old) {
            if (v) {
                size_t i = hash(v) & mask_;
                while (slots_[i]) i = (i + 1) & mask_;
                slots_[i] = v;
            }
        }
    }

public:
    explicit FlatSet(size_t expected) {
        size_t cap = 64;
        while (cap < expected * 2) cap <<= 1;
        slots_.assign(cap, 0);
        mask_ = cap - 1;
    }

    bool insert(H3Index v) {
        if ((count_ + 1) * 4 > slots_.size() * 3) grow();
        size_t i = hash(v) & mask_;
        while (slots_[i]) {
            if (slots_[i] == v) return false;
            i = (i + 1) & mask_;
        }
        slots_[i] = v;
        ++count_;
        return true;
    }

    bool contains(H3Index v) const {
        size_t i = hash(v) & mask_;
        while (slots_[i]) {
            if (slots_[i] == v) return true;
            i = (i + 1) & mask_;
        }
        return false;
    }

    size_t size() const { return count_; }

    std::vector<H3Index> to_vector() const {
        std::vector<H3Index> out;
        out.reserve(count_);
        for (H3Index v : slots_) {
            if (v) out.push_back(v);
        }
        return out;
    }
};

// ---------------------------------------------------------------------------
// Ranged boundary generation
// ---------------------------------------------------------------------------
// The boundary children of a cell form a positional numeral system: each one
// is a base-7 digit string accepted by the face-state automaton whose
// transitions are the REV_* tables. Counting accepted suffixes per state lets
// a descent skip whole subtrees that fall before `start`, so an arbitrary
// slice costs O(depth) to reach plus O(1) per emitted cell.

static constexpr int HEX_DIGITS[7] = {0, 1, 2, 3, 4, 5, 6};
static constexpr int PENT_DIGITS[6] = {0, 2, 3, 4, 5, 6};  // pentagons skip digit 1

/// Faces of the child at child_pos that remain on the traced boundary.
static inline uint8_t map_faces(uint8_t faces, const uint8_t rev[7][7], int child_pos) {
    uint8_t mapped = 0;
    for (int f = 1; f <= 6; ++f) {
        if (faces & (1 << f)) mapped |= rev[child_pos][f];
    }
    return mapped;
}

/// counts[k][mask] = boundary descendants k levels below a (non-pentagon)
/// node whose boundary state is `mask`. Parity is fixed by k and target_res.
static void fill_counts(int depth, int target_res,
                        std::vector<std::array<uint64_t, 128>>& counts) {
    counts.assign(depth + 1, std::array<uint64_t, 128>{});
    for (int m = 0; m < 128; ++m) counts[0][m] = 1;
    for (int k = 1; k <= depth; ++k) {
        int parity = (target_res - k + 1) % 2;
        for (int m = 0; m < 128; ++m) {
            uint64_t total = 0;
            for (int cp = 0; cp < 7; ++cp) {
                uint8_t mapped = map_faces(static_cast<uint8_t>(m), REV_HEX[parity], cp);
                if (mapped) total += counts[k - 1][mapped];
            }
            counts[k][m] = total;
        }
    }
}

namespace {
struct RangeCtx {
    int target_res;
    int64_t skip;
    int64_t take;
    const std::vector<std::array<uint64_t, 128>>* counts;
    std::vector<H3Index>* out;
};
}  // namespace

static void range_descend(H3Index v, int res, uint8_t faces, bool is_pent, RangeCtx& c) {
    if (c.take <= 0) return;
    if (res == c.target_res) {
        if (c.skip > 0) { --c.skip; return; }
        c.out->push_back(v);
        --c.take;
        return;
    }

    const int child_res = res + 1;
    const int parity = child_res % 2;
    const uint8_t (*rev)[7] = is_pent ? REV_PENT[parity] : REV_HEX[parity];
    const int shift = (15 - child_res) * 3;
    // Child with digit 0: bump the resolution field, clear the filler digit.
    const H3Index base = v + (1ULL << 52) - (7ULL << shift);
    const int* digits = is_pent ? PENT_DIGITS : HEX_DIGITS;
    const int ndigits = is_pent ? 6 : 7;
    const int below = c.target_res - child_res;

    for (int cp = 0; cp < ndigits; ++cp) {
        uint8_t mapped = map_faces(faces, rev, cp);
        if (!mapped) continue;
        if (c.skip > 0) {
            uint64_t count = (*c.counts)[below][mapped];
            if (static_cast<int64_t>(count) <= c.skip) {  // whole subtree precedes start
                c.skip -= static_cast<int64_t>(count);
                continue;
            }
        }
        range_descend(base + (static_cast<H3Index>(digits[cp]) << shift),
                      child_res, mapped, false, c);
        if (c.take <= 0) return;
    }
}

std::vector<H3Index> boundary_range(H3Index parent, int target_res,
                                    int64_t start, int64_t stop,
                                    const std::set<int>& input_faces) {
    int res_parent = getResolution(parent);
    if (target_res < res_parent) {
        throw std::invalid_argument("target_res must be greater than or equal to parent cell resolution");
    }
    if (target_res > 15) {
        throw std::invalid_argument("target_res must be <= 15");
    }

    std::vector<H3Index> out;
    uint8_t faces = faces_to_mask(input_faces);
    if (!faces) return out;

    const int depth = target_res - res_parent;
    const bool is_pent = isPentagon(parent);
    std::vector<std::array<uint64_t, 128>> counts;
    fill_counts(depth, target_res, counts);

    uint64_t total;
    if (depth == 0) {
        total = 1;
    } else if (is_pent) {
        total = 0;
        const int parity = (res_parent + 1) % 2;
        for (int cp = 0; cp < 6; ++cp) {
            uint8_t mapped = map_faces(faces, REV_PENT[parity], cp);
            if (mapped) total += counts[depth - 1][mapped];
        }
    } else {
        total = counts[depth][faces];
    }

    if (start < 0) start = 0;
    if (stop < 0 || static_cast<uint64_t>(stop) > total) stop = static_cast<int64_t>(total);
    int64_t take = stop - start;
    if (take <= 0) return out;

    out.reserve(static_cast<size_t>(take));
    RangeCtx ctx{target_res, start, take, &counts, &out};
    range_descend(parent, res_parent, faces, is_pent, ctx);
    return out;
}

/// Table-free boundary enumeration by wall-following; see header. Exists to
/// verify the table-driven traversal with an independent algorithm.
std::vector<H3Index> boundary_walk(H3Index parent, int target_res) {
    int parent_res = getResolution(parent);
    if (target_res < parent_res) {
        throw std::invalid_argument("target_res must be greater than or equal to parent cell resolution");
    }
    if (target_res > 15) {
        throw std::invalid_argument("target_res must be <= 15");
    }

    // O(1) descendant test: fill the digits finer than parent_res with 7s,
    // stamp the resolution field, compare with the parent index.
    const uint64_t digit_mask = (1ULL << (3 * (15 - parent_res))) - 1;
    const uint64_t res_field = 0xFULL << 52;
    const uint64_t res_stamp = static_cast<uint64_t>(parent_res) << 52;
    auto inside = [&](H3Index v) -> bool {
        return (((v | digit_mask) & ~res_field) | res_stamp) == parent;
    };

    // Unordered distance-1 neighbors (safe near pentagons).
    auto disk_neighbors = [](H3Index v, H3Index out[7]) -> int {
        H3Index disk[7] = {0};
        gridDisk(v, 1, disk);
        int n = 0;
        for (int i = 0; i < 7; ++i) {
            if (disk[i] != 0 && disk[i] != v) out[n++] = disk[i];
        }
        return n;
    };

    auto probe_is_boundary = [&](H3Index v) -> bool {
        if (!inside(v)) return false;
        H3Index nbrs[7];
        int n = disk_neighbors(v, nbrs);
        for (int i = 0; i < n; ++i) {
            if (!inside(nbrs[i])) return true;
        }
        return false;
    };

    // Start: snap a parent vertex to target_res, BFS the few steps to the wall.
    CellBoundary cb;
    cellToBoundary(parent, &cb);
    LatLng v0 = cb.verts[0];
    H3Index seed = 0;
    latLngToCell(&v0, target_res, &seed);

    std::unordered_set<H3Index> seen{seed};
    std::deque<H3Index> seek{seed};
    H3Index start = 0;
    while (!seek.empty()) {
        H3Index v = seek.front();
        seek.pop_front();
        if (probe_is_boundary(v)) {
            start = v;
            break;
        }
        H3Index nbrs[7];
        int n = disk_neighbors(v, nbrs);
        for (int i = 0; i < n; ++i) {
            if (seen.insert(nbrs[i]).second) seek.push_back(nbrs[i]);
        }
    }

    // Flood along the wall. The k=1 ring is rotationally ordered, so an
    // inside neighbor consecutive to an outside neighbor shares an edge with
    // that outside cell and is boundary by construction — one ring call per
    // boundary cell. Pentagon-distorted rings fall back to probing.
    // Boundary count grows ~sqrt(7) per level; the estimate just seeds the
    // flat set's capacity (it grows if undersized).
    size_t expected = 6;
    for (int r = parent_res; r < target_res - 1; ++r) expected = (expected * 8) / 3;
    FlatSet result(expected);
    result.insert(start);
    std::vector<H3Index> stack{start};
    while (!stack.empty()) {
        H3Index v = stack.back();
        stack.pop_back();
        H3Index ring[6] = {0};
        bool ordered = (gridRingUnsafe(v, 1, ring) == E_SUCCESS);
        if (ordered) {
            for (int i = 0; i < 6; ++i) {
                if (ring[i] == 0) { ordered = false; break; }
            }
        }
        if (ordered) {
            bool ins[6];
            for (int i = 0; i < 6; ++i) ins[i] = inside(ring[i]);
            for (int i = 0; i < 6; ++i) {
                if (ins[i] && (!ins[(i + 5) % 6] || !ins[(i + 1) % 6])
                        && result.insert(ring[i])) {
                    stack.push_back(ring[i]);
                }
            }
        } else {
            H3Index nbrs[7];
            int n = disk_neighbors(v, nbrs);
            for (int i = 0; i < n; ++i) {
                if (!result.contains(nbrs[i]) && probe_is_boundary(nbrs[i])) {
                    result.insert(nbrs[i]);
                    stack.push_back(nbrs[i]);
                }
            }
        }
    }

    return result.to_vector();
}

/// Returns the cell's own boundary as a closed (lon, lat) ring in degrees.
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

/// Unions the given cells and returns the exterior ring of the largest piece.
std::vector<std::pair<double, double>> merged_boundary_of_cells(const std::vector<H3Index>& cells) {
    if (cells.empty()) {
        return {};
    }
    multi_polygon_type merged = union_cells(cells, nullptr, nullptr);
    const polygon_type* largest = largest_by_area(merged);
    return largest ? outer_ring(*largest) : std::vector<std::pair<double, double>>{};
}

/// Boundary polygon of parent computed as the union of its boundary children
/// at target_res; falls back to the parent's own boundary if there are none.
std::vector<std::pair<double, double>> cell_boundary_from_children(H3Index parent, int target_res) {
    std::set<int> all_faces = {1, 2, 3, 4, 5, 6};
    auto boundary_children = children_on_boundary_faces(parent, target_res, all_faces);

    if (boundary_children.empty()) {
        return cell_boundary(parent);
    }
    return merged_boundary_of_cells(boundary_children);
}

/// Buffers the cell's own boundary. buffer_meters < 0 auto-calculates as
/// 100% of the edge length four resolutions finer (capped at 15).
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

/// Buffered polygon guaranteed to contain the cell's fine-resolution children:
/// boundary at intermediate_res (convex hull = fast, union = accurate), then
/// buffered by buffer_meters (< 0 = 100% of the intermediate edge length).
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
