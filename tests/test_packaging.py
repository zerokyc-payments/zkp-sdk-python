"""PEP 561: the package ships a py.typed marker (checked in the installed
distribution, and in the built wheel by CI)."""

from __future__ import annotations

from pathlib import Path

import zerokyc


def test_package_metadata():
    assert zerokyc.__version__ == "0.1.0"


def test_py_typed_marker_shipped_with_package():
    marker = Path(zerokyc.__file__).parent / "py.typed"
    assert marker.is_file(), "PEP 561 py.typed marker must ship with the package"


def test_py_typed_present_in_source_tree():
    source = Path(__file__).parent.parent / "src" / "zerokyc" / "py.typed"
    assert source.is_file()
