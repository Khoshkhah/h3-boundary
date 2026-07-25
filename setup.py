"""
Build machinery for the optional C++ extension.

All package metadata lives in pyproject.toml; this file only wires the CMake
build into setuptools. If cmake, Boost, or network access (FetchContent
downloads the h3 sources) are unavailable, the build degrades gracefully and
the package installs pure-Python — h3_boundary falls back at import time.
"""
import shutil
import subprocess
import sys
from pathlib import Path

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class CMakeBuild(build_ext):
    """Builds _h3_boundary_cpp via CMake instead of the default compiler."""

    def build_extension(self, ext):
        source_dir = Path(__file__).parent.resolve()
        build_dir = Path(self.build_temp).resolve()
        build_dir.mkdir(parents=True, exist_ok=True)

        configure = [
            "cmake",
            str(source_dir),
            "-DCMAKE_BUILD_TYPE=Release",
            "-DH3_BOUNDARY_PIP_BUILD=ON",
            # PYBIND11_FINDPYTHON forces pybind11's modern FindPython mode;
            # without it (and the classic PYTHON_EXECUTABLE) pybind11 searches
            # PATH and can build against the wrong interpreter.
            "-DPYBIND11_FINDPYTHON=ON",
            f"-DPython_EXECUTABLE={sys.executable}",
            f"-DPython3_EXECUTABLE={sys.executable}",
            f"-DPYTHON_EXECUTABLE={sys.executable}",
        ]
        try:
            pybind11_dir = subprocess.check_output(
                [sys.executable, "-m", "pybind11", "--cmakedir"], text=True
            ).strip()
            configure.append(f"-Dpybind11_DIR={pybind11_dir}")
        except (OSError, subprocess.CalledProcessError):
            pass  # CMake falls back to FetchContent for pybind11

        build = [
            "cmake", "--build", ".",
            "--target", "_h3_boundary_cpp",
            "--config", "Release", "-j",
        ]

        try:
            subprocess.check_call(configure, cwd=build_dir)
            subprocess.check_call(build, cwd=build_dir)
        except (OSError, subprocess.CalledProcessError) as e:
            print(f"C++ extension build skipped ({e}); installing pure-Python h3_boundary.")
            return

        built = [
            p for p in build_dir.glob("_h3_boundary_cpp*")
            if p.suffix in (".so", ".pyd", ".dylib")
        ]
        if not built:
            print("Warning: C++ extension not found after CMake build; installing pure-Python.")
            return

        # get_ext_fullpath points into build_lib for regular installs (so the
        # wheel picks the module up) and into the source tree for editable
        # installs. Keep CMake's filename — it already has the right ABI tag.
        dest = Path(self.get_ext_fullpath(ext.name)).parent
        dest.mkdir(parents=True, exist_ok=True)
        for f in built:
            shutil.copy2(f, dest)
            print(f"Installed C++ extension: {f.name}")


setup(
    # Registering the extension makes setuptools run build_ext and tag wheels
    # as platform-specific; sources are empty because CMake does the build.
    ext_modules=[Extension("h3_boundary._h3_boundary_cpp", sources=[])],
    cmdclass={"build_ext": CMakeBuild},
)
