"""Catalogue helpers for Geometry Nodes MCP tools.

Provides lazy loading of the reference JSON/CSV data so builders and
validators can query node metadata without duplicating IO logic.
"""

from __future__ import annotations

import json
import os
import csv
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

CATALOGUE_VERSION = os.environ.get("GN_MCP_CATALOGUE_VERSION", "4.4")
_DEFAULT_COMPLETE_NAME = f"geometry_nodes_complete_{CATALOGUE_VERSION.replace('.', '_')}.json"
_DEFAULT_MIN_NAME = f"geometry_nodes_min_{CATALOGUE_VERSION.replace('.', '_')}.json"
_CATALOGUE_ENV_VAR = "GN_MCP_CATALOGUE_PATH"
_SOCKET_COMPAT_ENV_VAR = "GN_MCP_SOCKET_COMPAT_PATH"
_SOCKET_COMPAT_VERSIONED = f"socket_compat_{CATALOGUE_VERSION.replace('.', '_')}.csv"
_SOCKET_COMPAT_FILENAME = "socket_compat.csv"

_PACKAGE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _PACKAGE_DIR.parent
_REFERENCE_DIR = _PROJECT_ROOT / "reference"
_ARCHIVE_REFERENCE_DIR = _PROJECT_ROOT / "_GN-LLM-References"


_NODE_CATALOGUE: Optional[List[Dict]] = None
_NODE_INDEX: Dict[str, Dict] = {}
_NODE_SOURCE: Optional[str] = None
_NODE_CATALOGUE_MIN: Optional[List[Dict]] = None
_NODE_INDEX_MIN: Dict[str, Dict] = {}
_NODE_SOURCE_MIN: Optional[str] = None
_SOCKET_COMPAT: Optional[Set[Tuple[str, str]]] = None
_SOCKET_COMPAT_SOURCE: Optional[str] = None


def _candidate_catalogue_paths(preferred_path: Optional[str], prefer_complete: bool) -> Iterable[Path]:
    names: List[str] = [_DEFAULT_COMPLETE_NAME, _DEFAULT_MIN_NAME]
    if not prefer_complete:
        names.reverse()

    env_path = os.environ.get(_CATALOGUE_ENV_VAR)
    archive_dir = _ARCHIVE_REFERENCE_DIR if _ARCHIVE_REFERENCE_DIR.is_dir() else None

    candidates: List[Path] = []
    if preferred_path:
        candidates.append(Path(preferred_path))
    if env_path:
        candidates.append(Path(env_path))

    for name in names:
        for base in (_REFERENCE_DIR, _PROJECT_ROOT, archive_dir):
            if not base:
                continue
            candidates.append(base / name)

    # As a final fallback, allow locating beside the package file itself
    for name in names:
        candidates.append(_PACKAGE_DIR / name)

    seen: set = set()
    for path in candidates:
        if not path:
            continue
        resolved = path.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        yield resolved


def _resolve_catalogue_path(preferred_path: Optional[str], prefer_complete: bool) -> Optional[Path]:
    for path in _candidate_catalogue_paths(preferred_path, prefer_complete):
        if path.exists():
            return path
    return None



def _read_catalogue_file(resolved: Path):
    with resolved.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, dict):
        nodes = data.get("nodes", [])
    elif isinstance(data, list):
        nodes = data
    else:
        raise ValueError(f"Unsupported catalogue format in {resolved}")

    index = {entry.get("identifier"): entry for entry in nodes if entry.get("identifier")}
    return nodes, index


def load_node_catalogue(path: Optional[str] = None, prefer_complete: bool = True, force_reload: bool = False):
    """Load and cache the node catalogue data structure."""
    global _NODE_CATALOGUE, _NODE_INDEX, _NODE_SOURCE

    if _NODE_CATALOGUE and not force_reload and not path:
        return _NODE_CATALOGUE

    resolved = _resolve_catalogue_path(path, prefer_complete)
    if not resolved:
        raise FileNotFoundError(
            "Could not locate geometry node catalogue. Set GN_MCP_CATALOGUE_PATH or "
            "place geometry_nodes_complete/min files in the repository."
        )

    nodes, index = _read_catalogue_file(resolved)

    _NODE_CATALOGUE = nodes
    _NODE_INDEX = index
    _NODE_SOURCE = str(resolved)
    return _NODE_CATALOGUE


def get_node_spec(node_type: str) -> Optional[Dict]:
    """Return the catalogue entry for a node identifier, or None."""
    load_node_catalogue()
    return _NODE_INDEX.get(node_type)


def get_socket_spec(node_type: str, socket_name: str, is_output: bool = True) -> Optional[Dict]:
    """Return socket metadata for the given node."""
    spec = get_node_spec(node_type)
    if not spec:
        return None

    sockets = spec.get("outputs" if is_output else "inputs", [])
    for socket in sockets:
        if socket.get("name") == socket_name:
            return socket
    return None


def get_catalogue_source() -> Optional[str]:
    """Return the resolved catalogue path currently in use."""
    return _NODE_SOURCE


def load_min_node_catalogue(path: Optional[str] = None, force_reload: bool = False):
    """Load the minimal node catalogue for sockets that include supports_field."""
    global _NODE_CATALOGUE_MIN, _NODE_INDEX_MIN, _NODE_SOURCE_MIN

    if _NODE_CATALOGUE_MIN and not force_reload and not path:
        return _NODE_CATALOGUE_MIN

    resolved = _resolve_catalogue_path(path, prefer_complete=False)
    if not resolved:
        return None

    nodes, index = _read_catalogue_file(resolved)
    _NODE_CATALOGUE_MIN = nodes
    _NODE_INDEX_MIN = index
    _NODE_SOURCE_MIN = str(resolved)
    return _NODE_CATALOGUE_MIN


def get_min_node_spec(node_type: str) -> Optional[Dict]:
    load_min_node_catalogue()
    return _NODE_INDEX_MIN.get(node_type)


def get_min_socket_spec(node_type: str, socket_name: str, is_output: bool = True) -> Optional[Dict]:
    spec = get_min_node_spec(node_type)
    if not spec:
        return None
    sockets = spec.get("outputs" if is_output else "inputs", [])
    for socket in sockets:
        if socket.get("name") == socket_name:
            return socket
    return None


def get_socket_field_support(node_type: str, socket_name: str, is_output: bool = True) -> Optional[bool]:
    """Return whether a socket supports fields if data exists."""
    socket_spec = get_socket_spec(node_type, socket_name, is_output)
    supports = socket_spec.get("supports_field") if socket_spec else None
    if supports is not None:
        return supports

    min_spec = get_min_socket_spec(node_type, socket_name, is_output)
    if min_spec is not None:
        return min_spec.get("supports_field")
    return None


def _candidate_socket_paths(preferred_path: Optional[str]) -> Iterable[Path]:
    env_path = os.environ.get(_SOCKET_COMPAT_ENV_VAR)
    bases = [_REFERENCE_DIR, _PROJECT_ROOT, _ARCHIVE_REFERENCE_DIR]

    candidates: List[Path] = []
    if preferred_path:
        candidates.append(Path(preferred_path))
    if env_path:
        candidates.append(Path(env_path))

    for base in bases:
        if base:
            candidates.append(Path(base) / _SOCKET_COMPAT_VERSIONED)
            candidates.append(Path(base) / _SOCKET_COMPAT_FILENAME)

    seen: set = set()
    for path in candidates:
        if not path:
            continue
        resolved = path.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        yield resolved


def _resolve_socket_path(preferred_path: Optional[str]) -> Optional[Path]:
    for path in _candidate_socket_paths(preferred_path):
        if path.exists():
            return path
    return None


def load_socket_compatibility(path: Optional[str] = None, force_reload: bool = False):
    """Load allowed socket type pairs from CSV."""
    global _SOCKET_COMPAT, _SOCKET_COMPAT_SOURCE

    if _SOCKET_COMPAT is not None and not force_reload and not path:
        return _SOCKET_COMPAT

    resolved = _resolve_socket_path(path)
    if not resolved:
        raise FileNotFoundError(
            "Could not locate socket_compat.csv. Set GN_MCP_SOCKET_COMPAT_PATH or "
            "place the file in the repository."
        )

    compat_pairs: Set[Tuple[str, str]] = set()
    with resolved.open('r', encoding='utf-8') as handle:
        reader = csv.reader(handle)
        next(reader, None)  # skip header
        for row in reader:
            if len(row) < 2:
                continue
            compat_pairs.add((row[0].strip(), row[1].strip()))

    _SOCKET_COMPAT = compat_pairs
    _SOCKET_COMPAT_SOURCE = str(resolved)
    return _SOCKET_COMPAT


def are_socket_types_compatible(from_idname: str, to_idname: str) -> bool:
    """Check whether a socket type pair is allowed."""
    compat = load_socket_compatibility()
    return (from_idname, to_idname) in compat if compat else False


def get_socket_compat_source() -> Optional[str]:
    """Return the resolved socket compatibility CSV path."""
    return _SOCKET_COMPAT_SOURCE


__all__ = [
    "load_node_catalogue",
    "get_node_spec",
    "get_socket_spec",
    "get_catalogue_source",
    "load_min_node_catalogue",
    "get_min_node_spec",
    "get_min_socket_spec",
    "get_socket_field_support",
    "load_socket_compatibility",
    "are_socket_types_compatible",
    "get_socket_compat_source",
]
