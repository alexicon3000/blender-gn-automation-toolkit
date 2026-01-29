"""Shared fixtures for toolkit tests.

Provides bpy/mathutils mocks and a loaded toolkit namespace so all pure-Python
functions can be tested without Blender.
"""

import os
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_DIR = REPO_ROOT / "reference"


def _install_bpy_mock():
    """Install a minimal bpy mock into sys.modules."""
    bpy = types.ModuleType("bpy")
    bpy.app = types.SimpleNamespace(version=(5, 0, 1), version_string="5.0.1")
    bpy.data = types.SimpleNamespace(
        objects=types.SimpleNamespace(get=lambda n: None),
    )
    sys.modules["bpy"] = bpy
    return bpy


def _install_mathutils_mock():
    mathutils = types.ModuleType("mathutils")
    mathutils.Euler = lambda *a, **kw: None
    sys.modules["mathutils"] = mathutils
    return mathutils


def _load_toolkit(catalogue_version="5.0"):
    """Exec toolkit.py and return its globals namespace."""
    # Point at the correct catalogue files
    cat_name = f"geometry_nodes_complete_{catalogue_version.replace('.', '_')}.json"
    cat_path = REFERENCE_DIR / cat_name
    if cat_path.exists():
        os.environ["GN_MCP_CATALOGUE_PATH"] = str(cat_path)

    compat_name = f"socket_compat_{catalogue_version.replace('.', '_')}.csv"
    compat_path = REFERENCE_DIR / compat_name
    if not compat_path.exists():
        compat_path = REFERENCE_DIR / "socket_compat.csv"
    os.environ["GN_MCP_SOCKET_COMPAT_PATH"] = str(compat_path)

    toolkit_path = REPO_ROOT / "toolkit.py"
    with open(toolkit_path, "r", encoding="utf-8") as fh:
        code = compile(fh.read(), str(toolkit_path), "exec")

    ns = {"__file__": str(toolkit_path)}
    exec(code, ns)
    return ns


def _reset_toolkit_caches(ns):
    """Reset all module-level caches in the toolkit namespace."""
    ns["_NODE_CATALOGUE"] = None
    ns["_NODE_CATALOGUE_INDEX"] = {}
    ns["_NODE_CATALOGUE_SOURCE"] = None
    ns["_NODE_CATALOGUE_MIN"] = None
    ns["_NODE_CATALOGUE_MIN_INDEX"] = {}
    ns["_NODE_CATALOGUE_MIN_SOURCE"] = None
    ns["_SOCKET_COMPAT"] = None
    ns["_SOCKET_COMPAT_SOURCE"] = None
    ns["_MERMAID_TYPE_MAP"] = None


# Install mocks once at import time so toolkit exec works
_install_bpy_mock()
_install_mathutils_mock()

# Load toolkit once at module level
_TOOLKIT_NS = None


def _get_toolkit():
    global _TOOLKIT_NS
    if _TOOLKIT_NS is None:
        _TOOLKIT_NS = _load_toolkit("5.0")
    return _TOOLKIT_NS


@pytest.fixture
def toolkit():
    """Return the toolkit namespace with caches reset for test isolation.

    Each test gets a clean slate — caches are cleared before the test runs,
    ensuring no cross-test pollution from catalogue reloads or type map builds.
    """
    ns = _get_toolkit()
    _reset_toolkit_caches(ns)
    # Pre-load the 5.0 catalogue so tests start with expected state
    cat_path = REFERENCE_DIR / "geometry_nodes_complete_5_0.json"
    if cat_path.exists():
        ns["load_node_catalogue"](path=str(cat_path), force_reload=True)
    return ns


@pytest.fixture
def toolkit_44():
    """Return the toolkit namespace loaded with the 4.4 catalogue."""
    ns = _get_toolkit()
    _reset_toolkit_caches(ns)
    cat_path = REFERENCE_DIR / "geometry_nodes_complete_4_4.json"
    if cat_path.exists():
        ns["load_node_catalogue"](path=str(cat_path), force_reload=True)
    return ns
