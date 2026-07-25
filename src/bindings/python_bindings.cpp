#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "h3_toolkit.hpp"
#include <h3api.h>
#include <optional>
#include <stdexcept>

namespace py = pybind11;

// Helper: Convert H3Index to hex string via H3's own formatter
static std::string h3_to_string(H3Index h) {
    char buf[17] = {0};
    h3ToString(h, buf, sizeof(buf));
    return std::string(buf);
}

// Helper: Convert hex string to H3Index, rejecting unparseable input
static H3Index string_to_h3(const std::string& s) {
    H3Index h = 0;
    if (stringToH3(s.c_str(), &h) != E_SUCCESS) {
        throw std::invalid_argument("invalid H3 index: '" + s + "'");
    }
    return h;
}

static std::set<int> py_trace_cell_to_ancestor_faces(
    const std::string& h_str,
    const std::set<int>& input_faces,
    std::optional<int> res_parent
) {
    H3Index h = string_to_h3(h_str);
    // Matches the Python default: None means the immediate parent.
    int rp = res_parent.value_or(getResolution(h) - 1);
    return h3_toolkit::trace_cell_to_ancestor_faces(h, input_faces, rp);
}

static std::vector<std::string> py_children_on_boundary_faces(
    const std::string& parent_str,
    int target_res,
    const std::set<int>& input_faces
) {
    H3Index parent = string_to_h3(parent_str);
    auto children = h3_toolkit::children_on_boundary_faces(parent, target_res, input_faces);

    std::vector<std::string> result;
    result.reserve(children.size());
    for (H3Index child : children) {
        result.push_back(h3_to_string(child));
    }
    return result;
}

static const std::set<int> ALL_FACES = {1, 2, 3, 4, 5, 6};

PYBIND11_MODULE(_h3_boundary_cpp, m) {
    m.doc() = "h3-boundary C++ bindings";
    // All functions run pure C++ after argument conversion, so the GIL is
    // released for the duration of each call.
    auto nogil = py::call_guard<py::gil_scoped_release>();

    m.def("trace_cell_to_ancestor_faces", &py_trace_cell_to_ancestor_faces,
          py::arg("h"),
          py::arg("input_faces") = ALL_FACES,
          py::arg("res_parent") = py::none(),
          nogil,
          "Trace which faces of an ancestor cell a given cell lies on.");

    m.def("trace_cell_to_parent_faces",
          [](const std::string& h_str, const std::set<int>& input_faces) {
              return h3_toolkit::trace_cell_to_parent_faces(string_to_h3(h_str), input_faces);
          },
          py::arg("h"),
          py::arg("input_faces") = ALL_FACES,
          nogil,
          "Trace which faces of the parent cell a given cell lies on.");

    m.def("children_on_boundary_faces", &py_children_on_boundary_faces,
          py::arg("parent"), py::arg("target_res"),
          py::arg("input_faces") = ALL_FACES,
          nogil,
          "Returns all children at target_res that lie on parent's boundary faces.");

    m.def("cell_to_coarsest_ancestor_on_faces",
          [](const std::string& h_str, const std::set<int>& input_faces) {
              return h3_to_string(
                  h3_toolkit::cell_to_coarsest_ancestor_on_faces(string_to_h3(h_str), input_faces));
          },
          py::arg("h"),
          py::arg("input_faces") = ALL_FACES,
          nogil,
          "Finds the coarsest ancestor where h still lies on specified faces.");

    m.def("cell_boundary",
          [](const std::string& cell_str) {
              return h3_toolkit::cell_boundary(string_to_h3(cell_str));
          },
          py::arg("cell"),
          nogil,
          "Returns cell boundary as list of (lon, lat) pairs.");

    m.def("cell_boundary_from_children",
          [](const std::string& parent_str, int target_res) {
              return h3_toolkit::cell_boundary_from_children(string_to_h3(parent_str), target_res);
          },
          py::arg("parent"), py::arg("target_res"),
          nogil,
          "Returns merged boundary polygon of all boundary children.");

    m.def("cell_boundary_from_children_with_count",
          [](const std::string& parent_str, int target_res) {
              H3Index parent = string_to_h3(parent_str);
              auto children = h3_toolkit::children_on_boundary_faces(parent, target_res, ALL_FACES);
              auto coords = children.empty()
                  ? h3_toolkit::cell_boundary(parent)
                  : h3_toolkit::merged_boundary_of_cells(children);
              return std::make_pair(std::move(coords),
                                    static_cast<int64_t>(children.size()));
          },
          py::arg("parent"), py::arg("target_res"),
          nogil,
          "Returns (merged boundary polygon, number of boundary children) in one traversal.");

    m.def("get_buffered_h3_polygon",
          [](const std::string& cell_str, double buffer_meters) {
              return h3_toolkit::get_buffered_h3_polygon(string_to_h3(cell_str), buffer_meters);
          },
          py::arg("cell"), py::arg("buffer_meters") = -1.0,
          nogil,
          "Returns buffered polygon of a single cell.");

    m.def("get_buffered_boundary_polygon",
          [](const std::string& cell_str, int intermediate_res, double buffer_meters, bool use_convex_hull) {
              return h3_toolkit::get_buffered_boundary_polygon(
                  string_to_h3(cell_str), intermediate_res, buffer_meters, use_convex_hull);
          },
          py::arg("cell"), py::arg("intermediate_res") = 10,
          py::arg("buffer_meters") = -1.0, py::arg("use_convex_hull") = false,
          nogil,
          "Returns a buffered polygon. use_convex_hull=True is fast, use_convex_hull=False (default) is accurate.");
}
