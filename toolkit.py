"""
Geometry Nodes MCP Toolkit - Portable Single-File Version

A complete toolkit for building and validating Blender Geometry Nodes via LLM/MCP.
Can be used with Claude Code, ChatGPT Pro, RooCode, Cline, or any tool that can
execute Python in Blender.

Usage:
    # Option 1: Read and exec in Blender via MCP
    exec(open("/path/to/toolkit.py").read())

    # Option 2: Direct execution in Blender scripting
    # Just run this file in Blender's Text Editor

After loading, all functions are available in Blender's Python environment.

Version: 0.1.0
Compatible with: Blender 4.4+
"""

import bpy
import os
import tempfile
import math
import json
import csv
from mathutils import Euler

# ============================================================================
# VERSION AND CONFIGURATION
# ============================================================================

TOOLKIT_VERSION = "0.1.0"

# Resolve toolkit root so reference files can be located when exec'd via MCP
_TOOLKIT_DIR = os.path.dirname(__file__) if "__file__" in globals() else os.getcwd()
_REFERENCE_DIR = os.path.join(_TOOLKIT_DIR, "reference")
_ARCHIVE_REFERENCE_DIR = os.path.join(_TOOLKIT_DIR, "_GN-LLM-References")
_CATALOGUE_ENV_VAR = "GN_MCP_CATALOGUE_PATH"
_SOCKET_COMPAT_ENV_VAR = "GN_MCP_SOCKET_COMPAT_PATH"
_SOCKET_COMPAT_FILENAME = "socket_compat.csv"

def _detect_catalogue_version():
    """Auto-detect catalogue version: env var > bpy.app.version > newest on disk.

    When running outside Blender (no bpy.app.version), scans reference/ for the
    newest available catalogue rather than hard-coding a fallback version.
    """
    env_ver = os.environ.get("GN_MCP_CATALOGUE_VERSION")
    if env_ver:
        return env_ver
    try:
        v = bpy.app.version
        return f"{v[0]}.{v[1]}"
    except Exception:
        # Outside Blender: find newest catalogue on disk
        return _find_newest_catalogue_version() or "5.0"


def _find_newest_catalogue_version():
    """Scan reference/ for catalogue files and return the newest version string."""
    import re
    pattern = re.compile(r"geometry_nodes_complete_(\d+)_(\d+)\.json$")
    newest = None
    newest_tuple = (0, 0)
    for base in [_REFERENCE_DIR, _ARCHIVE_REFERENCE_DIR]:
        if not base or not os.path.isdir(base):
            continue
        for fname in os.listdir(base):
            m = pattern.match(fname)
            if m:
                ver_tuple = (int(m.group(1)), int(m.group(2)))
                if ver_tuple > newest_tuple:
                    newest_tuple = ver_tuple
                    newest = f"{m.group(1)}.{m.group(2)}"
    return newest

CATALOGUE_VERSION = _detect_catalogue_version()
_DEFAULT_COMPLETE_NAME = f"geometry_nodes_complete_{CATALOGUE_VERSION.replace('.', '_')}.json"
_DEFAULT_MIN_NAME = f"geometry_nodes_min_{CATALOGUE_VERSION.replace('.', '_')}.json"
_SOCKET_COMPAT_VERSIONED = f"socket_compat_{CATALOGUE_VERSION.replace('.', '_')}.csv"

_NODE_CATALOGUE = None
_NODE_CATALOGUE_INDEX = {}
_NODE_CATALOGUE_SOURCE = None
_NODE_CATALOGUE_MIN = None
_NODE_CATALOGUE_MIN_INDEX = {}
_NODE_CATALOGUE_MIN_SOURCE = None
_SOCKET_COMPAT = None
_SOCKET_COMPAT_SOURCE = None
_MERMAID_TYPE_MAP = None
_NODE_ALIASES = None
_NODE_ALIASES_SOURCE = None

def get_blender_version():
    """Return Blender version tuple and string."""
    return bpy.app.version, f"{bpy.app.version[0]}.{bpy.app.version[1]}"


def _catalogue_version_from_path(path):
    if not path:
        return None
    basename = os.path.basename(path)
    parts = basename.replace(".json", "").split("_")
    if len(parts) >= 4 and parts[-2].isdigit() and parts[-1].isdigit():
        return f"{parts[-2]}.{parts[-1]}"
    return None


def check_catalogue_version(catalogue_version=CATALOGUE_VERSION):
    """Check if current Blender matches catalogue version."""
    version_tuple, version_str = get_blender_version()
    major_minor = f"{version_tuple[0]}.{version_tuple[1]}"

    env_path = os.environ.get(_CATALOGUE_ENV_VAR)
    inferred = _catalogue_version_from_path(env_path)
    effective_version = inferred or catalogue_version

    if major_minor != effective_version:
        print(f"WARNING: Catalogue is for Blender {effective_version}, "
              f"but running {version_str}. Socket names may differ!")
        return False
    return True


# ============================================================================
# CATALOGUE HELPERS - Lazy loading of reference data
# ============================================================================

def _candidate_catalogue_paths(preferred_path=None, prefer_complete=True):
    """Yield candidate catalogue paths in priority order."""
    names = [_DEFAULT_COMPLETE_NAME, _DEFAULT_MIN_NAME]
    if not prefer_complete:
        names.reverse()

    env_path = os.environ.get(_CATALOGUE_ENV_VAR)
    archive_dir = _ARCHIVE_REFERENCE_DIR if os.path.isdir(_ARCHIVE_REFERENCE_DIR) else None

    candidates = []
    if preferred_path:
        candidates.append(preferred_path)
    if env_path:
        candidates.append(env_path)

    for name in names:
        for base in (_REFERENCE_DIR, _TOOLKIT_DIR, archive_dir):
            if not base:
                continue
            path = os.path.join(base, name)
            candidates.append(path)

    # Also allow matching files located beside the toolkit file
    for name in names:
        candidates.append(os.path.join(_TOOLKIT_DIR, name))

    seen = set()
    for path in candidates:
        if path and path not in seen:
            seen.add(path)
            yield path


def _resolve_catalogue_path(preferred_path=None, prefer_complete=True):
    """Return the first catalogue path that exists on disk."""
    for path in _candidate_catalogue_paths(preferred_path, prefer_complete):
        if os.path.exists(path):
            return path
    return None


def _read_catalogue_file(resolved_path):
    with open(resolved_path, 'r', encoding='utf-8') as fh:
        data = json.load(fh)

    if isinstance(data, dict):
        nodes = data.get('nodes', [])
    elif isinstance(data, list):
        nodes = data
    else:
        raise ValueError(f"Unsupported catalogue format in {resolved_path}")

    index = {entry.get('identifier'): entry for entry in nodes if entry.get('identifier')}
    return nodes, index


def load_node_catalogue(path=None, prefer_complete=True, force_reload=False):
    """Load node catalogue JSON (complete or minimal) and cache the result.

    When a different catalogue is loaded (or force_reload=True), dependent caches
    like _MERMAID_TYPE_MAP are invalidated so they rebuild from the new data.
    """
    global _NODE_CATALOGUE, _NODE_CATALOGUE_INDEX, _NODE_CATALOGUE_SOURCE
    global _MERMAID_TYPE_MAP

    if _NODE_CATALOGUE and not force_reload and not path:
        return _NODE_CATALOGUE

    resolved = _resolve_catalogue_path(path, prefer_complete)
    if not resolved:
        raise FileNotFoundError(
            "Could not locate geometry node catalogue. Set GN_MCP_CATALOGUE_PATH or "
            "place geometry_nodes_complete/min files next to toolkit.py."
        )

    # Invalidate dependent caches when catalogue changes
    if resolved != _NODE_CATALOGUE_SOURCE:
        _MERMAID_TYPE_MAP = None

    nodes, index = _read_catalogue_file(resolved)

    _NODE_CATALOGUE = nodes
    _NODE_CATALOGUE_INDEX = index
    _NODE_CATALOGUE_SOURCE = resolved
    return _NODE_CATALOGUE


def get_node_spec(node_type, path=None):
    """Return the catalogue entry for a node identifier, or None."""
    load_node_catalogue(path)
    return _NODE_CATALOGUE_INDEX.get(node_type)


def get_catalogue_source():
    """Return the resolved catalogue path currently in use."""
    return _NODE_CATALOGUE_SOURCE


def get_socket_spec(node_type, socket_name, is_output=True):
    """Return metadata for a socket from the catalogue."""
    spec = get_node_spec(node_type)
    if not spec:
        return None

    sockets = spec.get('outputs' if is_output else 'inputs', [])
    for socket in sockets:
        if socket.get('name') == socket_name:
            return socket
    return None


def load_node_aliases(path=None, force_reload=False):
    """Load node alias mappings for improved keyword search.

    Returns a dict mapping node identifier -> list of aliases.
    """
    global _NODE_ALIASES, _NODE_ALIASES_SOURCE

    if _NODE_ALIASES is not None and not force_reload and not path:
        return _NODE_ALIASES

    # Determine path
    if path:
        resolved = path
    else:
        # Check env var first
        env_path = os.environ.get("GN_MCP_ALIASES_PATH")
        if env_path:
            resolved = env_path
        else:
            # Default: look in reference/ directory
            resolved = os.path.join(_REFERENCE_DIR, "node_aliases.json")

    if not os.path.exists(resolved):
        _NODE_ALIASES = {}
        _NODE_ALIASES_SOURCE = None
        return _NODE_ALIASES

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Filter out metadata keys like "_comment"
        _NODE_ALIASES = {k: v for k, v in data.items() if not k.startswith("_")}
        _NODE_ALIASES_SOURCE = resolved
    except (json.JSONDecodeError, OSError) as e:
        print(f"[load_node_aliases] Failed to load {resolved}: {e}")
        _NODE_ALIASES = {}
        _NODE_ALIASES_SOURCE = None

    return _NODE_ALIASES


def get_node_metadata(node_type):
    """Return high-level metadata (label/category/description) for a node."""
    spec = get_node_spec(node_type)
    if not spec:
        return None

    return {
        "identifier": spec.get("identifier"),
        "label": spec.get("label"),
        "category": spec.get("category"),
        "description": spec.get("description"),
    }


def find_nodes_by_keyword(keyword, limit=10):
    """Search catalogue labels/descriptions/aliases for a keyword (case-insensitive).

    Searches node identifiers, labels, categories, descriptions, and any
    aliases defined in reference/node_aliases.json.
    """
    if not keyword:
        return []

    keyword = keyword.lower()
    matches = []
    aliases = load_node_aliases()

    for spec in load_node_catalogue():
        identifier = spec.get("identifier", "")
        haystack_parts = [
            identifier,
            spec.get("label", ""),
            spec.get("category", ""),
            spec.get("description", ""),
        ]
        # Add aliases for this node to the searchable text
        node_aliases = aliases.get(identifier, [])
        haystack_parts.extend(node_aliases)

        haystack = " ".join(part for part in haystack_parts if part).lower()
        if keyword in haystack:
            matches.append({
                "identifier": identifier,
                "label": spec.get("label"),
                "category": spec.get("category"),
                "description": spec.get("description"),
            })
            if limit and len(matches) >= limit:
                break

    return matches


def load_min_node_catalogue(path=None, force_reload=False):
    """Load the minimal node catalogue (GeometryNode* only)."""
    global _NODE_CATALOGUE_MIN, _NODE_CATALOGUE_MIN_INDEX, _NODE_CATALOGUE_MIN_SOURCE

    if _NODE_CATALOGUE_MIN and not force_reload and not path:
        return _NODE_CATALOGUE_MIN

    resolved = _resolve_catalogue_path(path, prefer_complete=False)
    if not resolved:
        return None

    nodes, index = _read_catalogue_file(resolved)
    _NODE_CATALOGUE_MIN = nodes
    _NODE_CATALOGUE_MIN_INDEX = index
    _NODE_CATALOGUE_MIN_SOURCE = resolved
    return _NODE_CATALOGUE_MIN


def get_min_node_spec(node_type):
    load_min_node_catalogue()
    return _NODE_CATALOGUE_MIN_INDEX.get(node_type)


def get_min_socket_spec(node_type, socket_name, is_output=True):
    spec = get_min_node_spec(node_type)
    if not spec:
        return None
    sockets = spec.get('outputs' if is_output else 'inputs', [])
    for socket in sockets:
        if socket.get('name') == socket_name:
            return socket
    return None


def get_socket_field_support(node_type, socket_name, is_output=True):
    """Return whether a socket supports fields (True/False) if known."""
    socket_spec = get_socket_spec(node_type, socket_name, is_output)
    supports = socket_spec.get('supports_field') if socket_spec else None
    if supports is not None:
        return supports

    min_spec = get_min_socket_spec(node_type, socket_name, is_output)
    if min_spec is not None:
        return min_spec.get('supports_field')
    return None


# ============================================================================
# SOCKET COMPATIBILITY HELPERS
# ============================================================================

def _candidate_socket_paths(preferred_path=None):
    """Yield candidate socket compatibility CSV paths."""
    env_path = os.environ.get(_SOCKET_COMPAT_ENV_VAR)
    bases = [_REFERENCE_DIR, _TOOLKIT_DIR, _ARCHIVE_REFERENCE_DIR]

    candidates = []
    if preferred_path:
        candidates.append(preferred_path)
    if env_path:
        candidates.append(env_path)
    for base in bases:
        if base:
            candidates.append(os.path.join(base, _SOCKET_COMPAT_VERSIONED))
            candidates.append(os.path.join(base, _SOCKET_COMPAT_FILENAME))

    seen = set()
    for path in candidates:
        if path and path not in seen:
            seen.add(path)
            yield path


def _resolve_socket_path(preferred_path=None):
    for path in _candidate_socket_paths(preferred_path):
        if os.path.exists(path):
            return path
    return None


def load_socket_compatibility(path=None, force_reload=False):
    """Load allowed socket type pairs from CSV, cached for reuse."""
    global _SOCKET_COMPAT, _SOCKET_COMPAT_SOURCE

    if _SOCKET_COMPAT is not None and not force_reload and not path:
        return _SOCKET_COMPAT

    resolved = _resolve_socket_path(path)
    if not resolved:
        raise FileNotFoundError(
            "Could not locate socket_compat.csv. Set GN_MCP_SOCKET_COMPAT_PATH or "
            "place socket_compat.csv next to toolkit.py."
        )

    compat_pairs = set()
    with open(resolved, 'r', encoding='utf-8') as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        for row in reader:
            if len(row) < 2:
                continue
            compat_pairs.add((row[0].strip(), row[1].strip()))

    _SOCKET_COMPAT = compat_pairs
    _SOCKET_COMPAT_SOURCE = resolved
    return _SOCKET_COMPAT


def get_socket_compat_source():
    """Return the resolved socket compatibility CSV path."""
    return _SOCKET_COMPAT_SOURCE


def are_socket_types_compatible(from_idname, to_idname):
    """Return True if the socket type pair is allowed by the matrix."""
    compat = load_socket_compatibility()
    if not compat:
        return False
    return (from_idname, to_idname) in compat


def _socket_idname(socket):
    if hasattr(socket, 'bl_idname') and socket.bl_idname:
        return socket.bl_idname
    bl_rna = getattr(socket, 'bl_rna', None)
    if bl_rna and hasattr(bl_rna, 'identifier'):
        return bl_rna.identifier
    return socket.__class__.__name__


def _describe_socket(socket):
    node_name = getattr(socket.node, 'name', '<node>') if hasattr(socket, 'node') else '<node>'
    return f"{node_name}.{getattr(socket, 'name', '<socket>')} ({_socket_idname(socket)})"


def _socket_supports_field(socket, is_output=True):
    node = getattr(socket, 'node', None)
    node_type = getattr(node, 'bl_idname', None) if node else None
    if not node_type:
        return None
    try:
        return get_socket_field_support(node_type, getattr(socket, 'name', ''), is_output=is_output)
    except FileNotFoundError:
        return None


def validate_socket_link(from_socket, to_socket):
    """Validate socket direction and type compatibility before linking."""
    if not getattr(from_socket, 'is_output', False):
        return False, f"Source socket is not an output: {_describe_socket(from_socket)}"
    if getattr(to_socket, 'is_output', False):
        return False, f"Destination socket is not an input: {_describe_socket(to_socket)}"

    from_id = _socket_idname(from_socket)
    to_id = _socket_idname(to_socket)

    source_field = _socket_supports_field(from_socket, is_output=True)
    dest_field = _socket_supports_field(to_socket, is_output=False)
    if source_field and dest_field is False:
        return False, (
            "Field output cannot connect to non-field input: "
            f"{_describe_socket(from_socket)} -> {_describe_socket(to_socket)}"
        )

    if not are_socket_types_compatible(from_id, to_id):
        return False, (
            "Socket types are incompatible: "
            f"{_describe_socket(from_socket)} -> {_describe_socket(to_socket)}"
        )

    return True, None


# ============================================================================
# SOCKET HELPERS - Avoid index-based socket access
# ============================================================================

def get_output_by_type(node, socket_type):
    """
    Find output socket by TYPE, not index.

    This avoids the common mistake of using wrong output indices
    on nodes with multiple output types (like FunctionNodeRandomValue).

    Args:
        node: A Blender node
        socket_type: Socket type string ('VECTOR', 'FLOAT', 'INT', etc.)

    Returns:
        The first output socket matching the type

    Raises:
        ValueError if no matching socket found
    """
    for out in node.outputs:
        if out.type == socket_type:
            return out
    raise ValueError(f"No {socket_type} output on node '{node.name}' "
                     f"(available: {[o.type for o in node.outputs]})")


def get_input_by_type(node, socket_type):
    """Find input socket by TYPE, not index."""
    for inp in node.inputs:
        if inp.type == socket_type:
            return inp
    raise ValueError(f"No {socket_type} input on node '{node.name}' "
                     f"(available: {[i.type for i in node.inputs]})")


def get_output_by_name(node, socket_name):
    """Find output socket by name."""
    for out in node.outputs:
        if out.name == socket_name:
            return out
    raise ValueError(f"No output '{socket_name}' on node '{node.name}' "
                     f"(available: {[o.name for o in node.outputs]})")


def get_input_by_name(node, socket_name):
    """Find input socket by name."""
    for inp in node.inputs:
        if inp.name == socket_name:
            return inp
    raise ValueError(f"No input '{socket_name}' on node '{node.name}' "
                     f"(available: {[i.name for i in node.inputs]})")


# ============================================================================
# SAFE LINKING - Validates connections immediately
# ============================================================================

def safe_link(node_group, from_socket, to_socket):
    """
    Create a link and validate immediately.

    Args:
        node_group: The node tree to create link in
        from_socket: Source socket (must be output)
        to_socket: Destination socket (must be input)

    Returns:
        The created link

    Raises:
        RuntimeError if link is invalid
    """
    ok, error = validate_socket_link(from_socket, to_socket)
    if not ok:
        raise RuntimeError(error)

    link = node_group.links.new(from_socket, to_socket)
    if not link.is_valid:
        raise RuntimeError(
            f"Invalid link: {from_socket.node.name}.{from_socket.name} "
            f"({from_socket.type}) -> {to_socket.node.name}.{to_socket.name} "
            f"({to_socket.type})"
        )
    return link


def set_node_input(node, input_name, value):
    """
    Set a node input's default value by name.

    Handles different value types (scalar, vector, color).

    Args:
        node: The node to modify
        input_name: Name of the input socket
        value: Value to set (can be scalar, list, or tuple)

    Returns:
        True if successful

    Raises:
        KeyError if input not found
    """
    if input_name not in node.inputs:
        available = [inp.name for inp in node.inputs if inp.name]
        raise KeyError(f"Input '{input_name}' not found on {node.name}. "
                       f"Available: {available}")

    inp = node.inputs[input_name]

    # Handle vector/color types
    if isinstance(value, (list, tuple)):
        if hasattr(inp, 'default_value') and hasattr(inp.default_value, '__len__'):
            for i, v in enumerate(value):
                inp.default_value[i] = v
        else:
            inp.default_value = value[0]  # Use first element for scalars
    else:
        inp.default_value = value

    return True


# ============================================================================
# COLLECTION HELPERS - Safe isolation for testing
# ============================================================================

def get_or_create_collection(name, parent=None):
    """Get or create a collection by name.

    Args:
        name: Collection name
        parent: Parent collection (defaults to scene collection)

    Returns:
        The collection
    """
    if name in bpy.data.collections:
        return bpy.data.collections[name]

    coll = bpy.data.collections.new(name)
    if parent is None:
        bpy.context.scene.collection.children.link(coll)
    else:
        parent.children.link(coll)
    return coll


def clear_collection(name, remove_orphans=True):
    """Remove all objects from a collection without affecting other collections.

    Args:
        name: Collection name
        remove_orphans: If True, also purge orphan data after clearing

    Returns:
        Number of objects removed
    """
    if name not in bpy.data.collections:
        return 0

    coll = bpy.data.collections[name]
    count = len(coll.objects)

    # Remove objects from this collection
    for obj in list(coll.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    if remove_orphans:
        bpy.ops.outliner.orphans_purge(do_recursive=True)

    return count


def link_object_to_collection(obj, collection_name):
    """Link an object to a specific collection, removing from others.

    Args:
        obj: The object to link
        collection_name: Target collection name (created if needed)

    Returns:
        The collection
    """
    coll = get_or_create_collection(collection_name)

    # Unlink from all current collections
    for c in obj.users_collection:
        c.objects.unlink(obj)

    # Link to target collection
    coll.objects.link(obj)
    return coll


# ============================================================================
# GRAPH JSON BUILDER - Declarative node graph creation
# ============================================================================

SPECIAL_NODE_TYPES = {
    "__GROUP_INPUT__": "NodeGroupInput",
    "__GROUP_OUTPUT__": "NodeGroupOutput",
}


def _serialize_value(value):
    if value is None:
        return None
    if isinstance(value, (int, float, bool, str)):
        return value
    try:
        return [
            _serialize_value(v)
            for v in list(value)
        ]
    except Exception:
        return str(value)


def _node_type_for_id(node_id, node_type=None):
    if node_id in SPECIAL_NODE_TYPES:
        return SPECIAL_NODE_TYPES[node_id]
    return node_type


def _socket_names_for_node(node_type, is_output=True, node_id=None):
    if node_type in {"NodeGroupInput", "NodeGroupOutput"} or node_id in SPECIAL_NODE_TYPES:
        return None
    spec = get_node_spec(node_type) if node_type else None
    if not spec:
        return set()
    sockets = spec.get("outputs" if is_output else "inputs", [])
    return {socket.get("name") for socket in sockets if socket.get("name")}


def _validate_value(socket_type, value):
    if socket_type in {"VECTOR", "FLOAT_VECTOR", "INT_VECTOR"}:
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            return False, "Expected 3-element vector"
        return True, None
    if socket_type in {"RGBA", "COLOR"}:
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            return False, "Expected 4-element color"
        return True, None
    if socket_type == "BOOLEAN":
        if not isinstance(value, bool):
            return False, "Expected boolean"
        return True, None
    if socket_type == "INT":
        if not isinstance(value, int):
            return False, "Expected integer"
        return True, None
    if socket_type in {"FLOAT", "VALUE"}:
        if not isinstance(value, (int, float)):
            return False, "Expected number"
        return True, None
    if socket_type == "STRING":
        if not isinstance(value, str):
            return False, "Expected string"
        return True, None
    if socket_type == "GEOMETRY":
        return False, "Cannot set defaults for Geometry sockets"
    return True, None


def _socket_id(socket):
    if hasattr(socket, 'bl_idname') and socket.bl_idname:
        return socket.bl_idname
    bl_rna = getattr(socket, 'bl_rna', None)
    if bl_rna and hasattr(bl_rna, 'identifier'):
        return bl_rna.identifier
    return socket.__class__.__name__


def generate_full_graph_report(node_group, node_id_map=None, last_graph_json=None, last_diff_summary=None):
    """Generate a full graph report with nodes, sockets, and link details."""
    report = {
        "name": node_group.name,
        "node_count": len(node_group.nodes),
        "link_count": len(node_group.links),
        "node_id_map": node_id_map or {},
        "last_graph_json": last_graph_json,
        "last_diff_summary": last_diff_summary,
        "nodes": [],
        "links": [],
    }

    for node in node_group.nodes:
        node_info = {
            "name": node.name,
            "type": node.bl_idname,
            "label": node.label,
            "inputs": [],
            "outputs": [],
        }

        for inp in node.inputs:
            node_info["inputs"].append({
                "name": inp.name,
                "type": inp.type,
                "identifier": _socket_id(inp),
                "default_value": _serialize_value(getattr(inp, "default_value", None)),
                "is_linked": inp.is_linked,
            })

        for out in node.outputs:
            node_info["outputs"].append({
                "name": out.name,
                "type": out.type,
                "identifier": _socket_id(out),
                "is_linked": out.is_linked,
            })

        report["nodes"].append(node_info)

    for link in node_group.links:
        report["links"].append({
            "from_node": link.from_node.name,
            "from_socket": link.from_socket.name,
            "from_type": link.from_socket.type,
            "to_node": link.to_node.name,
            "to_socket": link.to_socket.name,
            "to_type": link.to_socket.type,
            "valid": link.is_valid,
        })

    return report


# ============================================================================
# GRAPH EXPORT - Read back node graphs as graph_json
# ============================================================================

def export_node_group_to_json(node_group, include_positions=True, include_defaults=True):
    """Export a Blender node group to graph_json format.

    This is the inverse of build_graph_from_json() — it reads an existing node
    graph and produces a JSON structure that can be used to rebuild it or
    understand its current state.

    Args:
        node_group: The bpy node group to export (e.g., modifier.node_group)
        include_positions: If True, include node x/y positions in output
        include_defaults: If True, include non-default socket values in node_settings

    Returns:
        Dict with 'nodes', 'links', 'node_settings', and optionally 'positions':
        {
            "nodes": [{"id": "grid", "type": "GeometryNodeMeshGrid", "label": "Grid"}, ...],
            "links": [{"from": "grid", "from_socket": "Mesh", "to": "to_points", "to_socket": "Mesh"}, ...],
            "node_settings": {"grid": {"Vertices X": 10, "Vertices Y": 10}, ...},
            "positions": {"grid": [0, 0], "to_points": [200, 0], ...}  # if include_positions=True
        }

        The 'label' field shows what the user sees in Blender's UI, while 'id' is
        the programmatic handle used for links and settings.
    """
    result = {
        "nodes": [],
        "links": [],
        "node_settings": {},
    }

    node_positions = {}
    if include_positions:
        result["positions"] = {}

    # Build node list and settings
    for node in node_group.nodes:
        # Use gn_mcp_id if present (set by build_graph_from_json), else node.name
        node_id = node.get(_NODE_ID_PROP, node.name)

        # Skip Group Input/Output — they're implicit in graph_json
        if node.bl_idname == "NodeGroupInput":
            # But record it so links can reference __GROUP_INPUT__
            continue
        if node.bl_idname == "NodeGroupOutput":
            continue
        # Skip Frame nodes — they're exported separately in the "frames" key
        if node.bl_idname == "NodeFrame":
            continue

        # Get the display label: node.label if set, else node.name (Blender's UI name)
        # This helps LLMs understand what the user sees vs the programmatic ID
        display_label = node.label if node.label else node.name

        result["nodes"].append({
            "id": node_id,
            "type": node.bl_idname,
            "label": display_label,
        })

        node_positions[node_id] = [node.location.x, node.location.y]
        if include_positions:
            result["positions"][node_id] = list(node_positions[node_id])

        # Collect non-default input values
        if include_defaults:
            settings = _extract_node_settings(node)
            if settings:
                result["node_settings"][node_id] = settings

    # Build link list
    for link in node_group.links:
        if not link.from_node or not link.to_node:
            continue

        from_node = link.from_node
        to_node = link.to_node

        # Map node names to IDs
        from_id = from_node.get(_NODE_ID_PROP, from_node.name)
        to_id = to_node.get(_NODE_ID_PROP, to_node.name)

        # Handle Group Input/Output specially
        if from_node.bl_idname == "NodeGroupInput":
            from_id = "__GROUP_INPUT__"
        if to_node.bl_idname == "NodeGroupOutput":
            to_id = "__GROUP_OUTPUT__"

        result["links"].append({
            "from": from_id,
            "from_socket": link.from_socket.name,
            "to": to_id,
            "to_socket": link.to_socket.name,
        })

    # Export frames
    frames = _export_frames(node_group, node_positions)
    if frames:
        result["frames"] = frames

    return result


def _export_frames(node_group, node_positions=None):
    """Export Frame nodes from a node group.

    Args:
        node_group: The node group to export frames from
        node_positions: Dict mapping node IDs to [x, y] positions (excludes frames)

    Returns:
        List of frame specs, or empty list if no frames
    """
    frames = []
    node_positions = dict(node_positions or {})

    # Ensure we have coordinates for every regular node even if the caller
    # did not request positions in the export payload.
    for node in node_group.nodes:
        if node.bl_idname in {"NodeGroupInput", "NodeGroupOutput", "NodeFrame"}:
            continue
        node_id = node.get(_NODE_ID_PROP, node.name)
        node_positions.setdefault(node_id, [node.location.x, node.location.y])

    # Get frame IDs so we can exclude them from containment checks
    frame_ids = set()
    for node in node_group.nodes:
        if node.bl_idname == "NodeFrame":
            frame_ids.add(node.get(_FRAME_ID_PROP, node.name))

    for node in node_group.nodes:
        if node.bl_idname != "NodeFrame":
            continue

        frame_id = node.get(_FRAME_ID_PROP, node.name)

        # Determine which nodes are visually inside this frame
        # by checking if node positions fall within frame bounds
        frame_x = node.location.x
        frame_y = node.location.y
        frame_w = node.width
        frame_h = node.height

        contained_nodes = []
        for nid, pos in node_positions.items():
            # Skip other frames
            if nid in frame_ids:
                continue
            nx, ny = pos
            # Check if node center is inside frame bounds
            # Frame y is top, extends downward; node y is also top
            if (frame_x <= nx <= frame_x + frame_w and
                frame_y - frame_h <= ny <= frame_y):
                contained_nodes.append(nid)

        frame_spec = {
            "id": frame_id,
            "label": node.label or "",
            "nodes": contained_nodes,
        }

        # Add color if custom color is enabled
        if node.use_custom_color:
            frame_spec["color"] = [node.color[0], node.color[1], node.color[2], 1.0]

        # Add shrink state
        if node.shrink:
            frame_spec["shrink"] = True

        # Add description from custom property
        desc = node.get("description", "")
        if desc:
            frame_spec["text"] = desc

        frames.append(frame_spec)

    return frames


def _extract_node_settings(node):
    """Extract non-default input values from a node.

    Returns a dict of {input_name: value} for inputs that have been modified
    from their defaults, or None if no settings to report.
    """
    settings = {}

    for inp in node.inputs:
        # Skip linked inputs — their value comes from the connection
        if inp.is_linked:
            continue

        # Skip inputs without default_value (e.g., Geometry sockets)
        if not hasattr(inp, "default_value"):
            continue

        value = inp.default_value
        serialized = _serialize_value(value)

        # Include all settable values (we can't easily detect "default" vs "modified"
        # without catalogue metadata, so include everything)
        if serialized is not None:
            settings[inp.name] = serialized

    return settings if settings else None


def export_modifier_to_json(obj_name, modifier_name, include_positions=True, include_defaults=True):
    """Export a geometry nodes modifier to graph_json format.

    Convenience wrapper around export_node_group_to_json() that looks up the
    object and modifier by name.

    Args:
        obj_name: Name of the object with the modifier
        modifier_name: Name of the geometry nodes modifier

    Returns:
        Dict with 'success', 'graph_json', and 'error' keys
    """
    obj = bpy.data.objects.get(obj_name)
    if not obj:
        return {"success": False, "graph_json": None, "error": f"Object '{obj_name}' not found"}

    modifier = obj.modifiers.get(modifier_name)
    if not modifier:
        return {"success": False, "graph_json": None, "error": f"Modifier '{modifier_name}' not found"}

    if modifier.type != "NODES":
        return {"success": False, "graph_json": None, "error": f"Modifier '{modifier_name}' is not a Geometry Nodes modifier"}

    if not modifier.node_group:
        return {"success": False, "graph_json": None, "error": f"Modifier '{modifier_name}' has no node group"}

    graph_json = export_node_group_to_json(
        modifier.node_group,
        include_positions=include_positions,
        include_defaults=include_defaults,
    )

    return {
        "success": True,
        "graph_json": graph_json,
        "node_group_name": modifier.node_group.name,
        "error": None,
    }


def validate_graph_json_preflight(graph_json):
    """Fail-fast validation of graph_json before touching Blender."""
    result = {
        "status": "OK",
        "issues": [],
        "checks": [],
    }

    def _add_check(name, ok, detail=None):
        result["checks"].append({
            "name": name,
            "ok": ok,
            "detail": detail,
        })
        if not ok:
            if detail:
                result["issues"].append(detail)
            else:
                result["issues"].append(name)

    nodes = graph_json.get("nodes", [])
    links = graph_json.get("links", [])
    node_settings = graph_json.get("node_settings", {})

    _add_check("has_nodes", bool(nodes), "graph_json has no nodes" if not nodes else None)
    _add_check("has_links", bool(links), "graph_json has no links" if not links else None)

    node_types = {}
    duplicate_ids = set()
    unknown_types = []
    invalid_nodes = []
    for node in nodes:
        node_id = node.get("id")
        node_type = node.get("type")
        if not node_id or not node_type:
            invalid_nodes.append(node)
            continue
        if node_id in node_types:
            duplicate_ids.add(node_id)
            continue
        resolved_type = _node_type_for_id(node_id, node_type)
        node_types[node_id] = resolved_type
        if resolved_type not in {"NodeGroupInput", "NodeGroupOutput"} and not get_node_spec(resolved_type):
            unknown_types.append((node_id, resolved_type))

    _add_check(
        "node_specs_valid",
        not invalid_nodes,
        f"Invalid node specs: {invalid_nodes}" if invalid_nodes else None,
    )
    _add_check(
        "unique_node_ids",
        not duplicate_ids,
        f"Duplicate node IDs: {sorted(duplicate_ids)}" if duplicate_ids else None,
    )
    _add_check(
        "known_node_types",
        not unknown_types,
        f"Unknown node types: {unknown_types}" if unknown_types else None,
    )

    node_types.setdefault("__GROUP_INPUT__", "NodeGroupInput")
    node_types.setdefault("__GROUP_OUTPUT__", "NodeGroupOutput")

    link_node_errors = []
    socket_errors = []
    field_errors = []
    for link in links:
        from_id = link.get("from")
        to_id = link.get("to")
        from_socket = link.get("from_socket") or link.get("socket")
        to_socket = link.get("to_socket") or link.get("socket")

        if from_id not in node_types:
            link_node_errors.append(f"Link from unknown node: {from_id}")
            continue
        if to_id not in node_types:
            link_node_errors.append(f"Link to unknown node: {to_id}")
            continue

        from_type = node_types[from_id]
        to_type = node_types[to_id]
        from_names = _socket_names_for_node(from_type, is_output=True, node_id=from_id)
        to_names = _socket_names_for_node(to_type, is_output=False, node_id=to_id)

        if from_names is not None and from_socket not in from_names:
            socket_errors.append(
                f"Unknown output socket '{from_socket}' on node '{from_id}'"
            )
        if to_names is not None and to_socket not in to_names:
            socket_errors.append(
                f"Unknown input socket '{to_socket}' on node '{to_id}'"
            )

        if from_names is not None and to_names is not None:
            source_field = get_socket_field_support(from_type, from_socket, is_output=True)
            dest_field = get_socket_field_support(to_type, to_socket, is_output=False)
            if source_field and dest_field is False:
                field_errors.append(
                    f"Field output cannot connect to non-field input: {from_id}.{from_socket} -> {to_id}.{to_socket}"
                )

    _add_check("links_reference_known_nodes", not link_node_errors,
               "; ".join(link_node_errors) if link_node_errors else None)
    _add_check("link_sockets_exist", not socket_errors,
               "; ".join(socket_errors) if socket_errors else None)
    _add_check("link_field_compat", not field_errors,
               "; ".join(field_errors) if field_errors else None)

    settings_errors = []
    for node_id, settings in node_settings.items():
        if node_id not in node_types:
            settings_errors.append(f"Settings for unknown node: {node_id}")
            continue
        if node_id in SPECIAL_NODE_TYPES:
            settings_errors.append(f"Settings provided for special node: {node_id}")
            continue

        node_type = node_types[node_id]
        for input_name, value in settings.items():
            socket_spec = get_socket_spec(node_type, input_name, is_output=False)
            if not socket_spec:
                settings_errors.append(
                    f"Unknown input socket '{input_name}' on node '{node_id}'"
                )
                continue
            socket_type = socket_spec.get("type")
            ok, error = _validate_value(socket_type, value)
            if not ok:
                settings_errors.append(
                    f"Invalid value for {node_id}.{input_name} ({socket_type}): {error}"
                )

    _add_check("node_settings_valid", not settings_errors,
               "; ".join(settings_errors) if settings_errors else None)

    if result["issues"]:
        result["status"] = "ERROR"

    return result

def _normalize_link_spec(link_spec):
    from_id = link_spec.get("from")
    to_id = link_spec.get("to")
    from_socket_name = link_spec.get("from_socket") or link_spec.get("socket")
    to_socket_name = link_spec.get("to_socket") or link_spec.get("socket")
    if "to_socket" in link_spec:
        to_socket_name = link_spec["to_socket"]
    return from_id, from_socket_name, to_id, to_socket_name


def _link_key(from_id, from_socket_name, to_id, to_socket_name):
    return (from_id, from_socket_name, to_id, to_socket_name)

_NODE_ID_PROP = "gn_mcp_id"


def _gather_existing_nodes(node_group):
    """Map node.name to node for existing nodes (excluding group IO)."""
    mapping = {}
    for node in node_group.nodes:
        if node.bl_idname in {"NodeGroupInput", "NodeGroupOutput"}:
            continue
        key = node.get(_NODE_ID_PROP, node.name)
        mapping[key] = node
    return mapping


def _gather_existing_links(node_group):
    """Map existing links keyed by from/to node names and socket names."""
    links = {}
    for link in node_group.links:
        if not link.from_node or not link.to_node:
            continue
        key = _link_key(
            link.from_node.name,
            link.from_socket.name,
            link.to_node.name,
            link.to_socket.name,
        )
        links[key] = link
    return links


# ============================================================================
# FRAME SUPPORT - Visual organization for node graphs
# ============================================================================

_FRAME_ID_PROP = "gn_mcp_frame_id"
_FRAME_PADDING = 40  # Padding around contained nodes


def _calculate_frame_bounds(nodes, padding=_FRAME_PADDING):
    """Calculate bounding box for a list of nodes.

    Returns (x, y, width, height) where x,y is the top-left corner.
    Blender node locations are at top-left, y increases upward.
    """
    if not nodes:
        return (0, 0, 200, 100)

    # node.dimensions may not be available until UI updates, so use estimates
    # Typical node width ~150-180px, height ~100-200px depending on sockets
    NODE_WIDTH_ESTIMATE = 150
    NODE_HEIGHT_ESTIMATE = 150

    # Get bounds considering estimated node dimensions
    min_x = min(n.location.x for n in nodes)
    max_x = max(n.location.x + getattr(n, 'width', NODE_WIDTH_ESTIMATE) for n in nodes)
    max_y = max(n.location.y for n in nodes)  # top
    min_y = min(n.location.y - NODE_HEIGHT_ESTIMATE for n in nodes)  # bottom

    # Add padding
    x = min_x - padding
    y = max_y + padding + 30  # Extra for frame header
    width = (max_x - min_x) + 2 * padding
    height = (max_y - min_y) + 2 * padding + 30

    return (x, y, width, height)


def _create_frame(node_group, frame_spec, node_map):
    """Create a Frame node from a frame spec.

    Args:
        node_group: The node group to add the frame to
        frame_spec: Dict with id, label, color, nodes, shrink, text
        node_map: Dict mapping node IDs to actual node objects

    Returns:
        The created Frame node, or None if creation failed
    """
    frame_id = frame_spec.get("id", "frame")
    label = frame_spec.get("label", "")
    color = frame_spec.get("color")  # [R, G, B, A] or None
    node_ids = frame_spec.get("nodes", [])
    shrink = frame_spec.get("shrink", False)
    text = frame_spec.get("text", "")

    # Get the actual node objects for this frame
    contained_nodes = [node_map[nid] for nid in node_ids if nid in node_map]

    # Create the frame
    frame = node_group.nodes.new("NodeFrame")
    frame[_FRAME_ID_PROP] = frame_id

    # Set label
    if label:
        frame.label = label

    # Set color
    if color and len(color) >= 3:
        frame.use_custom_color = True
        # Blender's frame.color is RGB, not RGBA
        frame.color = (color[0], color[1], color[2])

    # Set shrink
    frame.shrink = shrink

    # Set text/description
    # Note: frame.text in Blender requires a Text datablock, not a string.
    # We store the text in a custom property instead for simplicity.
    if text:
        frame["description"] = text

    # Calculate and set bounds based on contained nodes
    if contained_nodes:
        x, y, width, height = _calculate_frame_bounds(contained_nodes)
        frame.location = (x, y)
        frame.width = width
        frame.height = height

        for node in contained_nodes:
            try:
                node.parent = frame
            except Exception as e:
                print(f"[_create_frame] Could not parent {getattr(node, 'name', 'unknown')}: {e}")
    else:
        # Default placement when no nodes listed yet
        frame.location = (0.0, 0.0)
        frame.width = 300.0
        frame.height = 160.0

    return frame


def _clear_managed_frames(node_group):
    """Remove previously created frames that carry the MCP frame marker."""
    if not hasattr(node_group, "nodes"):
        return

    frames_to_remove = []
    for node in list(node_group.nodes):
        if getattr(node, "bl_idname", "") != "NodeFrame":
            continue

        keys_fn = getattr(node, "keys", None)
        node_keys = []
        if callable(keys_fn):
            try:
                node_keys = list(keys_fn())
            except Exception:
                node_keys = []

        if _FRAME_ID_PROP in node_keys:
            frames_to_remove.append(node)

    for frame in frames_to_remove:
        try:
            node_group.nodes.remove(frame)
        except Exception:
            pass


def _apply_frames(node_group, node_map, frames_spec, errors):
    """Create all frames specified in graph_json.

    Args:
        node_group: The node group to add frames to
        node_map: Dict mapping node IDs to actual node objects
        frames_spec: List of frame specs from graph_json["frames"]
        errors: List to append errors to
    """
    _clear_managed_frames(node_group)

    if not frames_spec:
        return

    # Check for duplicate frame IDs
    seen_ids = set()
    for frame_spec in frames_spec:
        frame_id = frame_spec.get("id", "frame")
        if frame_id in seen_ids:
            errors.append(f"Duplicate frame ID '{frame_id}' - skipping duplicate")
            continue
        seen_ids.add(frame_id)
        try:
            _create_frame(node_group, frame_spec, node_map)
        except Exception as e:
            errors.append(f"Failed to create frame '{frame_id}': {e}")


# ============================================================================
# AUTO-FRAMING - Automatic visual organization
# ============================================================================

def auto_frame_graph(node_group, strategy="connectivity", apply=False):
    """Generate frame specs by analyzing node graph structure.

    This helper analyzes an existing node graph and generates frame specifications
    that can be used to visually organize the graph. LLMs can use this as a starting
    point and customize the results before applying.

    Args:
        node_group: The Blender node group to analyze
        strategy: How to group nodes:
            - "connectivity": Group connected subgraphs (default)
            - "type": Group by node type prefix (GeometryNode*, FunctionNode*, etc.)
        apply: If True, create the frames in the node group immediately.
               If False (default), just return the frame specs.

    Returns:
        List of frame specs that can be added to graph_json["frames"] or
        passed to _apply_frames(). Each spec has:
            - id: Auto-generated frame ID
            - label: Descriptive label based on strategy
            - nodes: List of node IDs contained in the frame
            - color: Suggested color based on group type

    Example:
        >>> frames = auto_frame_graph(node_group, strategy="connectivity")
        >>> print(frames)
        [{"id": "group_1", "label": "Connected Group 1", "nodes": ["grid", "cone"], ...}]

        >>> # Apply frames directly
        >>> auto_frame_graph(node_group, strategy="type", apply=True)
    """
    if strategy == "connectivity":
        frames = _auto_frame_by_connectivity(node_group)
    elif strategy == "type":
        frames = _auto_frame_by_type(node_group)
    else:
        raise ValueError(f"Unknown auto-frame strategy: {strategy}. Use 'connectivity' or 'type'.")

    if apply and frames:
        # Build node_map for frame creation
        node_map = {}
        for node in node_group.nodes:
            if node.bl_idname in {"NodeGroupInput", "NodeGroupOutput", "NodeFrame"}:
                continue
            node_id = node.get(_NODE_ID_PROP, node.name)
            node_map[node_id] = node

        errors = []
        _apply_frames(node_group, node_map, frames, errors)
        if errors:
            print(f"[auto_frame_graph] Errors: {errors}")

    return frames


def _auto_frame_by_connectivity(node_group):
    """Group nodes by connectivity using BFS to find connected subgraphs.

    Returns a list of frame specs, one per connected component (excluding
    single-node components which don't need framing).
    """
    # Build adjacency list (undirected — we want visual grouping)
    adjacency = {}

    # Get all non-special nodes
    nodes_by_id = {}
    for node in node_group.nodes:
        if node.bl_idname in {"NodeGroupInput", "NodeGroupOutput", "NodeFrame"}:
            continue
        node_id = node.get(_NODE_ID_PROP, node.name)
        nodes_by_id[node_id] = node
        adjacency[node_id] = set()

    # Build edges from links
    for link in node_group.links:
        if not link.from_node or not link.to_node:
            continue

        from_id = link.from_node.get(_NODE_ID_PROP, link.from_node.name)
        to_id = link.to_node.get(_NODE_ID_PROP, link.to_node.name)

        # Skip links to/from group IO
        if link.from_node.bl_idname == "NodeGroupInput":
            continue
        if link.to_node.bl_idname == "NodeGroupOutput":
            continue

        if from_id in adjacency and to_id in adjacency:
            adjacency[from_id].add(to_id)
            adjacency[to_id].add(from_id)

    # BFS to find connected components
    visited = set()
    components = []

    for start_id in adjacency:
        if start_id in visited:
            continue

        # BFS from this node
        component = []
        queue = [start_id]
        while queue:
            node_id = queue.pop(0)
            if node_id in visited:
                continue
            visited.add(node_id)
            component.append(node_id)
            for neighbor in adjacency[node_id]:
                if neighbor not in visited:
                    queue.append(neighbor)

        if component:
            components.append(component)

    # Generate frame specs for components with >1 node
    frames = []
    colors = [
        [0.2, 0.4, 0.8, 0.8],  # Blue
        [0.2, 0.7, 0.4, 0.8],  # Green
        [0.8, 0.5, 0.2, 0.8],  # Orange
        [0.7, 0.2, 0.7, 0.8],  # Purple
        [0.7, 0.7, 0.2, 0.8],  # Yellow
        [0.2, 0.7, 0.7, 0.8],  # Cyan
    ]

    for i, component in enumerate(components):
        if len(component) < 2:
            continue  # Don't frame single nodes

        frame_id = f"group_{i + 1}"
        label = f"Connected Group {i + 1}"

        # Try to infer a better label from node types
        types = [nodes_by_id[nid].bl_idname for nid in component if nid in nodes_by_id]
        if all("Instance" in t for t in types):
            label = "Instancing"
        elif all("Mesh" in t for t in types):
            label = "Mesh Processing"
        elif all("Curve" in t for t in types):
            label = "Curve Processing"
        elif all("Math" in t or "Vector" in t for t in types):
            label = "Math Operations"

        frames.append({
            "id": frame_id,
            "label": label,
            "nodes": component,
            "color": colors[i % len(colors)],
        })

    return frames


def _auto_frame_by_type(node_group):
    """Group nodes by their type prefix (GeometryNode*, FunctionNode*, etc.).

    Returns a list of frame specs, one per node type category.
    """
    # Categorize nodes by type prefix
    categories = {
        "Mesh": {"prefix": "Mesh", "color": [0.2, 0.6, 0.8, 0.8], "nodes": []},
        "Curve": {"prefix": "Curve", "color": [0.8, 0.5, 0.2, 0.8], "nodes": []},
        "Instance": {"prefix": "Instance", "color": [0.2, 0.7, 0.4, 0.8], "nodes": []},
        "Math": {"prefix": "Math", "color": [0.7, 0.7, 0.2, 0.8], "nodes": []},
        "Vector": {"prefix": "Vector", "color": [0.6, 0.4, 0.8, 0.8], "nodes": []},
        "Geometry": {"prefix": "Geometry", "color": [0.3, 0.5, 0.7, 0.8], "nodes": []},
        "Attribute": {"prefix": "Attribute", "color": [0.7, 0.3, 0.5, 0.8], "nodes": []},
        "Input": {"prefix": "Input", "color": [0.4, 0.7, 0.4, 0.8], "nodes": []},
        "Other": {"prefix": None, "color": [0.5, 0.5, 0.5, 0.8], "nodes": []},
    }

    for node in node_group.nodes:
        if node.bl_idname in {"NodeGroupInput", "NodeGroupOutput", "NodeFrame"}:
            continue

        node_id = node.get(_NODE_ID_PROP, node.name)
        bl_idname = node.bl_idname

        # Find matching category
        matched = False
        for cat_name, cat_data in categories.items():
            if cat_name == "Other":
                continue
            if cat_data["prefix"] and cat_data["prefix"] in bl_idname:
                cat_data["nodes"].append(node_id)
                matched = True
                break

        if not matched:
            categories["Other"]["nodes"].append(node_id)

    # Generate frame specs for non-empty categories with >1 node
    frames = []
    for cat_name, cat_data in categories.items():
        if len(cat_data["nodes"]) < 2:
            continue

        frames.append({
            "id": f"type_{cat_name.lower()}",
            "label": f"{cat_name} Nodes",
            "nodes": cat_data["nodes"],
            "color": cat_data["color"],
        })

    return frames


def _diff_graph(node_group, graph_json):
    nodes_spec = {node["id"]: node for node in graph_json.get("nodes", []) if node.get("id")}
    existing_nodes = _gather_existing_nodes(node_group)

    nodes_to_add = [node_id for node_id in nodes_spec if node_id not in existing_nodes]
    nodes_to_update = [node_id for node_id in nodes_spec if node_id in existing_nodes]
    nodes_to_remove = [node_id for node_id in existing_nodes if node_id not in nodes_spec]

    desired_links = {}
    for link_spec in graph_json.get("links", []):
        from_id, from_socket, to_id, to_socket = _normalize_link_spec(link_spec)
        if not from_id or not to_id:
            continue
        desired_links[_link_key(from_id, from_socket, to_id, to_socket)] = link_spec

    existing_links = _gather_existing_links(node_group)

    links_to_add = [key for key in desired_links if key not in existing_links]
    links_to_keep = [key for key in desired_links if key in existing_links]
    links_to_remove = [key for key in existing_links if key not in desired_links]

    return {
        "nodes_to_add": nodes_to_add,
        "nodes_to_update": nodes_to_update,
        "nodes_to_remove": nodes_to_remove,
        "links_to_add": links_to_add,
        "links_to_keep": links_to_keep,
        "links_to_remove": links_to_remove,
    }


def _apply_node_settings(node_map, node_settings, errors):
    for node_id, settings in node_settings.items():
        node = node_map.get(node_id)
        if not node:
            errors.append(f"Settings for unknown node: {node_id}")
            continue

        for input_name, value in settings.items():
            try:
                set_node_input(node, input_name, value)
            except Exception as e:
                errors.append(f"Failed to set {node_id}.{input_name}: {e}")


def _remove_links(node_group, links_to_remove):
    if not links_to_remove:
        return
    existing_links = _gather_existing_links(node_group)
    for key in links_to_remove:
        link = existing_links.get(key)
        if link:
            node_group.links.remove(link)


def _remove_conflicting_links(node_group, target_node, target_socket_name):
    for link in list(node_group.links):
        if link.to_node == target_node and link.to_socket.name == target_socket_name:
            node_group.links.remove(link)


def _apply_links(node_group, node_map, graph_json, errors):
    for link_spec in graph_json.get("links", []):
        from_id, from_socket_name, to_id, to_socket_name = _normalize_link_spec(link_spec)

        from_node = node_map.get(from_id)
        to_node = node_map.get(to_id)

        if not from_node:
            errors.append(f"Link from unknown node: {from_id}")
            continue
        if not to_node:
            errors.append(f"Link to unknown node: {to_id}")
            continue

        from_socket = next((out for out in from_node.outputs if out.name == from_socket_name), None)
        if not from_socket:
            errors.append(
                f"Output socket '{from_socket_name}' not found on {from_id}. "
                f"Available: {[o.name for o in from_node.outputs]}"
            )
            continue

        to_socket = next((inp for inp in to_node.inputs if inp.name == to_socket_name), None)
        if not to_socket:
            errors.append(
                f"Input socket '{to_socket_name}' not found on {to_id}. "
                f"Available: {[i.name for i in to_node.inputs]}"
            )
            continue

        _remove_conflicting_links(node_group, to_node, to_socket_name)

        try:
            safe_link(node_group, from_socket, to_socket)
        except RuntimeError as e:
            errors.append(str(e))


def _assign_interface_default(socket, value):
    """Apply default/min/max metadata to a group interface socket."""
    if value is None:
        return
    try:
        default = socket.default_value
    except AttributeError:
        default = None

    if isinstance(value, (list, tuple)) and hasattr(default, "__len__"):
        for idx, val in enumerate(value):
            if idx < len(default):
                default[idx] = val
    elif default is not None:
        socket.default_value = value


_INTERFACE_PROP_MAP = {
    "description": "description",
    "min": "min_value",
    "max": "max_value",
    "soft_min": "soft_min",
    "soft_max": "soft_max",
    "subtype": "subtype",
    "attribute_domain": "attribute_domain",
    "hide_value": "hide_value",
}


def _configure_group_interface(node_group, graph_json):
    """Create group interface sockets based on graph_json spec."""
    interface = node_group.interface
    input_specs = list(graph_json.get("group_inputs") or [])
    output_specs = list(graph_json.get("group_outputs") or [])

    def _ensure_geometry(specs, default_name):
        for spec in specs:
            sock_type = spec.get("type") or spec.get("socket_type")
            if sock_type == "NodeSocketGeometry":
                return specs
        return [{"name": default_name, "type": "NodeSocketGeometry"}, *specs]

    input_specs = _ensure_geometry(input_specs, "Geometry")
    output_specs = _ensure_geometry(output_specs, "Geometry")

    interface.clear()

    def _apply_specs(specs, direction):
        for spec in specs:
            name = spec.get("name") or ("Input" if direction == 'INPUT' else "Output")
            sock_type = spec.get("type") or spec.get("socket_type") or "NodeSocketFloat"
            socket = interface.new_socket(name=name, in_out=direction, socket_type=sock_type)
            if "default" in spec:
                _assign_interface_default(socket, spec.get("default"))
            for key, attr in _INTERFACE_PROP_MAP.items():
                if key in spec and hasattr(socket, attr):
                    setattr(socket, attr, spec[key])

    _apply_specs(input_specs, 'INPUT')
    _apply_specs(output_specs, 'OUTPUT')


def _find_interface_socket(node_group, name, in_out):
    interface = getattr(node_group, "interface", None)
    if interface is not None:
        items = getattr(interface, "items_tree", None)
        if items:
            for item in items:
                if getattr(item, "item_type", None) == 'SOCKET' and getattr(item, "in_out", None) == in_out and item.name == name:
                    return item

    sockets = node_group.inputs if in_out == 'INPUT' else node_group.outputs
    if hasattr(sockets, "get"):
        return sockets.get(name)
    for sock in sockets:
        if sock.name == name:
            return sock
    return None


def ensure_group_input(node_group, name, socket_type='NodeSocketFloat', *, default=None, **metadata):
    """Ensure a Group Input socket exists and update its metadata."""
    interface = getattr(node_group, "interface", None)
    if interface is None:
        raise ValueError("Node group has no interface; cannot create group inputs")

    socket = _find_interface_socket(node_group, name, 'INPUT')
    if socket is None:
        socket = interface.new_socket(name=name, in_out='INPUT', socket_type=socket_type)
    elif socket_type and getattr(socket, "socket_type", None) and socket.socket_type != socket_type:
        socket.socket_type = socket_type

    if default is not None:
        _assign_interface_default(socket, default)

    for key, attr in _INTERFACE_PROP_MAP.items():
        if key in metadata and hasattr(socket, attr):
            setattr(socket, attr, metadata[key])

    return socket


def ensure_group_output(node_group, name, socket_type='NodeSocketFloat', *, default=None, **metadata):
    """Ensure a Group Output socket exists and update its metadata."""
    interface = getattr(node_group, "interface", None)
    if interface is None:
        raise ValueError("Node group has no interface; cannot create group outputs")

    socket = _find_interface_socket(node_group, name, 'OUTPUT')
    if socket is None:
        socket = interface.new_socket(name=name, in_out='OUTPUT', socket_type=socket_type)
    elif socket_type and getattr(socket, "socket_type", None) and socket.socket_type != socket_type:
        socket.socket_type = socket_type

    if default is not None:
        _assign_interface_default(socket, default)

    for key, attr in _INTERFACE_PROP_MAP.items():
        if key in metadata and hasattr(socket, attr):
            setattr(socket, attr, metadata[key])

    return socket


def build_graph_from_json(
    obj_name,
    modifier_name,
    graph_json,
    clear_existing=True,
    collection=None,
    merge_existing=False,
    remove_extras=False,
    return_diff=True,
):
    """
    Build a geometry node graph from a JSON specification.

    Args:
        obj_name: Name of object to add modifier to (created if doesn't exist)
        modifier_name: Name for the geometry nodes modifier
        graph_json: Dict with 'nodes', 'links', and optional 'node_settings'
        clear_existing: If True, clear any existing nodes in the group
        collection: Optional collection name to place object in (created if needed)

    Returns:
        Dict with:
            - success: bool
            - node_group_name: Name of the created/modified node group
            - nodes: Dict mapping node IDs to actual nodes
            - errors: List of any errors encountered

    Expected graph_json format:
    {
        "nodes": [
            {"id": "n1", "type": "GeometryNodeMeshCone"},
            {"id": "n2", "type": "GeometryNodeSetPosition"}
        ],
        "links": [
            {"from": "n1", "from_socket": "Mesh", "to": "n2", "to_socket": "Geometry"}
        ],
        "node_settings": {
            "n1": {"Vertices": 32},
            "n2": {"Offset": [0, 0, 1]}
        }
    }
    """
    result = {
        "success": False,
        "node_group_name": None,
        "nodes": {},
        "errors": [],
        "preflight": None,
        "diff_summary": None,
    }

    preflight = validate_graph_json_preflight(graph_json)
    result["preflight"] = preflight
    if preflight["status"] != "OK":
        result["errors"].extend(preflight["issues"])
        return result

    # Get or create object
    obj = bpy.data.objects.get(obj_name)
    if not obj:
        # Create a simple mesh object
        bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
        obj = bpy.context.active_object
        obj.name = obj_name

    # Link to collection if specified
    if collection:
        link_object_to_collection(obj, collection)

    # Get or create modifier
    mod = obj.modifiers.get(modifier_name)
    if not mod:
        mod = obj.modifiers.new(name=modifier_name, type='NODES')

    # Get or create node group
    ng = mod.node_group
    if ng is None:
        ng = bpy.data.node_groups.new(name=modifier_name, type='GeometryNodeTree')
        mod.node_group = ng

    result["node_group_name"] = ng.name

    if merge_existing:
        clear_existing = False

    # Clear existing nodes if requested
    if clear_existing:
        ng.nodes.clear()
        _configure_group_interface(ng, graph_json)
    elif graph_json.get("group_inputs") or graph_json.get("group_outputs"):
        _configure_group_interface(ng, graph_json)

    # Ensure Group Input/Output nodes exist
    group_input = next((node for node in ng.nodes if node.bl_idname == 'NodeGroupInput'), None)
    if not group_input:
        group_input = ng.nodes.new('NodeGroupInput')
    group_input.location = (-400, 0)
    result["nodes"]["__GROUP_INPUT__"] = group_input

    group_output = next((node for node in ng.nodes if node.bl_idname == 'NodeGroupOutput'), None)
    if not group_output:
        group_output = ng.nodes.new('NodeGroupOutput')
    group_output.location = (400, 0)
    result["nodes"]["__GROUP_OUTPUT__"] = group_output

    existing_nodes = _gather_existing_nodes(ng)
    diff_summary = _diff_graph(ng, graph_json) if merge_existing else None
    if return_diff:
        result["diff_summary"] = diff_summary

    # Create nodes from spec
    x_offset = -200
    y_offset = 0

    for node_spec in graph_json.get("nodes", []):
        node_id = node_spec.get("id")
        node_type = node_spec.get("type")

        if not node_id or not node_type:
            result["errors"].append(f"Invalid node spec: {node_spec}")
            continue

        if merge_existing and node_id in existing_nodes:
            node = existing_nodes[node_id]
            # Store ID in custom property for export, but don't touch label
            node[_NODE_ID_PROP] = node_id
            result["nodes"][node_id] = node
            continue

        try:
            node = ng.nodes.new(node_type)
            # Store ID in custom property for export, but don't touch label
            # This keeps Blender's natural node names (Grid, Cone, etc.) in the UI
            node[_NODE_ID_PROP] = node_id

            # Auto-layout (simple horizontal arrangement)
            node.location = (x_offset, y_offset)
            x_offset += 200
            if x_offset > 200:
                x_offset = -200
                y_offset -= 200

            result["nodes"][node_id] = node

        except Exception as e:
            result["errors"].append(f"Failed to create node '{node_id}' ({node_type}): {e}")

    # Apply node settings
    _apply_node_settings(result["nodes"], graph_json.get("node_settings", {}), result["errors"])
    # Remove extras if requested
    if merge_existing and remove_extras and diff_summary:
        for node_id in diff_summary["nodes_to_remove"]:
            node = existing_nodes.get(node_id)
            if node:
                ng.nodes.remove(node)
        _remove_links(ng, diff_summary["links_to_remove"])

    # Create links
    _apply_links(ng, result["nodes"], graph_json, result["errors"])

    # Create frames for visual organization
    _apply_frames(ng, result["nodes"], graph_json.get("frames", []), result["errors"])

    result["success"] = len(result["errors"]) == 0
    return result


# ============================================================================
# WORKSPACE MANAGEMENT
# ============================================================================

def get_or_create_mcp_workspace():
    """Get existing MCP Validation workspace or create it ONCE."""
    for ws in bpy.data.workspaces:
        if ws.name.startswith("MCP Validation"):
            return ws

    geo_ws = bpy.data.workspaces.get("Geometry Nodes") or bpy.data.workspaces.get("Layout")
    if not geo_ws:
        return None

    bpy.context.window.workspace = geo_ws
    bpy.ops.workspace.duplicate()

    for ws in bpy.data.workspaces:
        if ws.name.endswith(".001") or ws.name.endswith(".002"):
            if "Geometry" in ws.name or "Layout" in ws.name:
                ws.name = "MCP Validation"
                bpy.context.window.workspace = ws
                screen = bpy.context.screen
                for area in screen.areas:
                    if area.type == 'DOPESHEET_EDITOR':
                        area.type = 'CONSOLE'
                    elif area.type == 'SPREADSHEET':
                        area.type = 'VIEW_3D'
                return ws
    return None


def switch_to_mcp_workspace():
    """Switch to MCP Validation workspace (reuses existing)."""
    ws = get_or_create_mcp_workspace()
    if ws:
        bpy.context.window.workspace = ws
    return ws


def configure_validation_views(obj_name, modifier_name):
    """Configure all views for validation."""
    screen = bpy.context.screen
    obj = bpy.data.objects.get(obj_name)
    if not obj:
        return False, f"Object '{obj_name}' not found"

    mod = obj.modifiers.get(modifier_name)
    if not mod or not mod.node_group:
        return False, f"Modifier '{modifier_name}' not found"

    ng = mod.node_group
    view3d_areas = [a for a in screen.areas if a.type == 'VIEW_3D']

    for i, area in enumerate(view3d_areas[:2]):
        space = area.spaces[0]
        r3d = space.region_3d
        space.shading.type = 'SOLID'
        space.shading.light = 'MATCAP'
        try:
            space.shading.studio_light = 'check_normal+y.exr'
        except:
            pass

        if i == 0:
            r3d.view_perspective = 'PERSP'
            r3d.view_rotation = Euler((math.radians(70), 0, math.radians(30))).to_quaternion()
            r3d.view_distance = 35
            r3d.view_location = (0, 0, 4)
        elif i == 1:
            r3d.view_perspective = 'ORTHO'
            r3d.view_rotation = Euler((math.radians(90), 0, 0)).to_quaternion()
            r3d.view_distance = 25
            r3d.view_location = (0, 0, 5)

    for area in screen.areas:
        if area.type == 'NODE_EDITOR':
            space = area.spaces[0]
            space.node_tree = ng
            space.pin = True
            for region in area.regions:
                if region.type == 'WINDOW':
                    with bpy.context.temp_override(area=area, region=region):
                        bpy.ops.node.view_all()
                    break
            break

    return True, "Views configured"


# ============================================================================
# VALIDATION
# ============================================================================

def validate_graph_structure(node_group):
    """Analyze node group structure and detect issues."""
    result = {
        "name": node_group.name,
        "node_count": len(node_group.nodes),
        "link_count": len(node_group.links),
        "nodes": [],
        "links": [],
        "invalid_links": [],
        "issues": []
    }

    for n in sorted(node_group.nodes, key=lambda x: x.location.x):
        result["nodes"].append({"name": n.name, "type": n.bl_idname})

    for link in node_group.links:
        link_info = {
            "from": f"{link.from_node.name}.{link.from_socket.name}",
            "to": f"{link.to_node.name}.{link.to_socket.name}",
            "from_type": link.from_socket.type,
            "to_type": link.to_socket.type,
            "valid": link.is_valid
        }
        result["links"].append(link_info)
        if not link.is_valid:
            result["invalid_links"].append(link_info)
            result["issues"].append(
                f"Invalid link: {link.from_node.name}.{link.from_socket.name} "
                f"({link.from_socket.type}) -> {link.to_node.name}.{link.to_socket.name} "
                f"({link.to_socket.type})"
            )

    return result


def validate_geometry_metrics(obj, tolerance=0.001):
    """Measure numerical properties of resulting geometry."""
    result = {"vertex_count": 0, "face_count": 0, "min_z": None, "max_z": None,
              "height_range": None, "ground_contact": None, "issues": []}

    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.to_mesh()

        if mesh and mesh.vertices:
            zs = [(obj.matrix_world @ v.co).z for v in mesh.vertices]
            result["vertex_count"] = len(mesh.vertices)
            result["face_count"] = len(mesh.polygons)
            result["min_z"] = round(min(zs), 4)
            result["max_z"] = round(max(zs), 4)
            result["height_range"] = round(max(zs) - min(zs), 4)
            result["ground_contact"] = abs(min(zs)) < tolerance
            if not result["ground_contact"]:
                result["issues"].append(f"Ground contact FAILED: min_z = {min(zs):.4f}")

        obj_eval.to_mesh_clear()
    except Exception as e:
        result["issues"].append(f"Metrics error: {str(e)}")

    return result


def full_geo_nodes_validation(
    obj_name,
    modifier_name,
    capture_screenshot=True,
    include_report=False,
    node_id_map=None,
    last_graph_json=None,
    last_diff_summary=None,
):
    """Complete validation with graph checks, metrics, and screenshot."""
    result = {
        "status": "UNKNOWN",
        "object": obj_name,
        "modifier": modifier_name,
        "graph": {},
        "metrics": {},
        "issues": [],
        "screenshot_path": None,
        "full_report": None,
    }

    obj = bpy.data.objects.get(obj_name)
    if not obj:
        result["issues"].append(f"Object '{obj_name}' not found")
        result["status"] = "ERROR"
        return result

    mod = obj.modifiers.get(modifier_name)
    if not mod or not mod.node_group:
        result["issues"].append(f"Modifier '{modifier_name}' not found")
        result["status"] = "ERROR"
        return result

    ng = mod.node_group

    # Graph validation
    graph_result = validate_graph_structure(ng)
    result["graph"] = graph_result
    result["issues"].extend(graph_result["issues"])

    # Geometry metrics
    metrics_result = validate_geometry_metrics(obj)
    result["metrics"] = metrics_result
    result["issues"].extend(metrics_result["issues"])

    # Screenshot
    if capture_screenshot:
        switch_to_mcp_workspace()
        configure_validation_views(obj_name, modifier_name)
        local_view_before = is_local_view_active()
        frame_object_in_viewport(obj_name, use_local_view=True)
        path = os.path.join(tempfile.gettempdir(), "geo_nodes_validation.png")
        bpy.ops.screen.screenshot(filepath=path)
        result["screenshot_path"] = path
        if not local_view_before:
            exit_local_view()

    if include_report:
        result["full_report"] = generate_full_graph_report(
            ng,
            node_id_map=node_id_map,
            last_graph_json=last_graph_json,
            last_diff_summary=last_diff_summary,
        )

    result["status"] = "ISSUES_FOUND" if result["issues"] else "VALID"
    return result


def full_graph_report(obj_name, modifier_name, node_id_map=None, last_graph_json=None, last_diff_summary=None):
    """Generate a full graph report for a specific object/modifier."""
    result = {
        "status": "UNKNOWN",
        "object": obj_name,
        "modifier": modifier_name,
        "issues": [],
        "report": None,
    }

    obj = bpy.data.objects.get(obj_name)
    if not obj:
        result["issues"].append(f"Object '{obj_name}' not found")
        result["status"] = "ERROR"
        return result

    mod = obj.modifiers.get(modifier_name)
    if not mod or not mod.node_group:
        result["issues"].append(f"Modifier '{modifier_name}' not found")
        result["status"] = "ERROR"
        return result

    result["report"] = generate_full_graph_report(
        mod.node_group,
        node_id_map=node_id_map,
        last_graph_json=last_graph_json,
        last_diff_summary=last_diff_summary,
    )
    result["status"] = "OK"
    return result


def capture_node_graph(obj_name, modifier_name):
    """Capture fullscreen node graph screenshot."""
    obj = bpy.data.objects.get(obj_name)
    if not obj:
        return None
    mod = obj.modifiers.get(modifier_name)
    if not mod or not mod.node_group:
        return None

    ng = mod.node_group
    node_area = None
    for area in bpy.context.screen.areas:
        if area.type == 'NODE_EDITOR':
            node_area = area
            break

    if not node_area:
        return None

    space = node_area.spaces[0]
    space.node_tree = ng
    space.pin = True

    window_region = next((r for r in node_area.regions if r.type == 'WINDOW'), None)
    if not window_region:
        return None

    with bpy.context.temp_override(area=node_area, region=window_region):
        bpy.ops.screen.screen_full_area(use_hide_panels=True)

    for area in bpy.context.screen.areas:
        if area.type == 'NODE_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    with bpy.context.temp_override(area=area, region=region):
                        bpy.ops.node.view_all()
                    break
            break

    path = os.path.join(tempfile.gettempdir(), f"node_graph_{ng.name}.png")
    bpy.ops.screen.screenshot(filepath=path)

    for area in bpy.context.screen.areas:
        if area.type == 'NODE_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    with bpy.context.temp_override(area=area, region=region):
                        bpy.ops.screen.screen_full_area(use_hide_panels=True)
                    break
            break

    return path


def frame_object_in_viewport(obj_name, use_local_view=True):
    """Frame the viewport on an object before taking screenshots.

    Call this before taking viewport screenshots to ensure the object
    is visible and centered. Optionally enters local view to isolate
    the object from the rest of the scene.

    Args:
        obj_name: Name of the object to frame
        use_local_view: If True, enter local view to isolate the object

    Returns:
        True if framing succeeded, False otherwise
    """
    obj = bpy.data.objects.get(obj_name)
    if not obj:
        return False

    # Deselect all, then select and activate target object
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            space = area.spaces.active
            for region in area.regions:
                if region.type == 'WINDOW':
                    with bpy.context.temp_override(area=area, region=region):
                        if use_local_view:
                            # Enter local view to isolate the object if not already
                            if not getattr(space, 'local_view', False):
                                bpy.ops.view3d.localview()
                        bpy.ops.view3d.view_selected()
                    return True
    return False


def is_local_view_active():
    """Return True if any 3D Viewport is currently in local view."""
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            space = area.spaces.active
            if getattr(space, 'local_view', False):
                return True
    return False


def exit_local_view():
    """Exit local view if currently active.

    Call this after taking screenshots to return to normal view.

    Returns:
        True if exited local view, False if not in local view
    """
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            space = area.spaces.active
            if getattr(space, 'local_view', False):
                for region in area.regions:
                    if region.type == 'WINDOW':
                        with bpy.context.temp_override(area=area, region=region):
                            bpy.ops.view3d.localview()
                        return True
    return False


# ============================================================================
# LAYOUT HELPERS
# ============================================================================

def layout_nodes(node_group, padding=50):
    """Auto-layout nodes in a graph from left to right based on dependencies."""
    nodes = list(node_group.nodes)

    # Build dependency graph
    in_degree = {n.name: 0 for n in nodes}
    out_edges = {n.name: [] for n in nodes}

    for link in node_group.links:
        if link.to_node.name in in_degree:
            in_degree[link.to_node.name] += 1
        if link.from_node.name in out_edges:
            out_edges[link.from_node.name].append(link.to_node.name)

    # Topological sort
    queue = [n for n in nodes if in_degree[n.name] == 0]
    sorted_nodes = []

    while queue:
        node = queue.pop(0)
        sorted_nodes.append(node)
        for neighbor_name in out_edges[node.name]:
            in_degree[neighbor_name] -= 1
            if in_degree[neighbor_name] == 0:
                neighbor = node_group.nodes.get(neighbor_name)
                if neighbor:
                    queue.append(neighbor)

    # Position nodes
    x = 0
    for node in sorted_nodes:
        node.location = (x, 0)
        x += node.width + padding


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def list_available_nodes():
    """List all geometry node types available in this Blender version."""
    import inspect
    nodes = []

    for name in dir(bpy.types):
        if name.startswith("GeometryNode") or name.startswith("FunctionNode"):
            cls = getattr(bpy.types, name)
            if inspect.isclass(cls) and issubclass(cls, bpy.types.Node):
                nodes.append(name)

    return sorted(nodes)


def inspect_node_sockets(node_type):
    """Inspect a node type's inputs and outputs without creating it permanently."""
    try:
        nt = bpy.data.node_groups.new("_INSPECT_", "GeometryNodeTree")
        node = nt.nodes.new(node_type)

        result = {
            "type": node_type,
            "label": node.bl_label if hasattr(node, 'bl_label') else node.name,
            "inputs": [{"name": s.name, "type": s.type} for s in node.inputs],
            "outputs": [{"name": s.name, "type": s.type} for s in node.outputs]
        }

        bpy.data.node_groups.remove(nt, do_unlink=True)
        return result
    except Exception as e:
        try:
            bpy.data.node_groups.remove(nt, do_unlink=True)
        except:
            pass
        return {"error": str(e)}


def print_validation_report(result):
    """Pretty-print a validation result."""
    print("=" * 60)
    print(f"VALIDATION REPORT: {result['status']}")
    print("=" * 60)
    print(f"\nObject: {result['object']}")
    print(f"Modifier: {result['modifier']}")

    if result.get('graph'):
        g = result['graph']
        print(f"\nGRAPH:")
        print(f"  Nodes: {g.get('node_count', 'N/A')}")
        print(f"  Links: {g.get('link_count', 'N/A')}")
        print(f"  Invalid links: {len(g.get('invalid_links', []))}")

    if result.get('metrics'):
        m = result['metrics']
        print(f"\nMETRICS:")
        for k, v in m.items():
            if k != 'issues':
                print(f"  {k}: {v}")

    if result.get('screenshot_path'):
        print(f"\nScreenshot: {result['screenshot_path']}")

    if result.get('preflight'):
        print("\nPREFLIGHT CHECKLIST:")
        for check in result['preflight'].get('checks', []):
            status = "OK" if check.get('ok') else "FAIL"
            detail = check.get('detail')
            if detail:
                print(f"  [{status}] {check.get('name')}: {detail}")
            else:
                print(f"  [{status}] {check.get('name')}")

    if result['issues']:
        print(f"\nISSUES ({len(result['issues'])}):")
        for issue in result['issues']:
            print(f"  - {issue}")
    else:
        print(f"\nNo issues detected!")


# ============================================================================
# INITIALIZATION
# ============================================================================

print("=" * 60)
print(f"Geometry Nodes MCP Toolkit v{TOOLKIT_VERSION}")
print(f"Blender version: {get_blender_version()[1]}")
print(f"Catalogue version: {CATALOGUE_VERSION}")
print("=" * 60)
print("\nAvailable functions:")
print("  Building:")
print("    - build_graph_from_json(obj, mod, graph_json)")
print("    - mermaid_to_blender(obj, mod, mermaid_text)  # One-step!")
print("    - parse_mermaid_to_graph_json(mermaid_text)")
print("    - set_node_input(node, input_name, value)")
print("    - safe_link(node_group, from_socket, to_socket)")
print("  Export (read-back):")
print("    - export_modifier_to_json(obj, mod)  # Get current graph state!")
print("    - export_node_group_to_json(node_group)")
print("  Socket helpers:")
print("    - get_output_by_type(node, type)")
print("    - get_input_by_type(node, type)")
print("    - get_output_by_name(node, name)")
print("    - get_input_by_name(node, name)")
print("  Validation:")
print("    - full_geo_nodes_validation(obj, mod)")
print("    - validate_graph_structure(node_group)")
print("    - validate_geometry_metrics(obj)")
print("    - print_validation_report(result)")
print("  Visual:")
print("    - capture_node_graph(obj, mod)")
print("    - frame_object_in_viewport(obj)  # Call before screenshots!")
print("    - switch_to_mcp_workspace()")
print("    - configure_validation_views(obj, mod)")
print("  Collections:")
print("    - get_or_create_collection(name)")
print("    - clear_collection(name)  # Safe cleanup without destroying scene")
print("    - link_object_to_collection(obj, collection_name)")
print("  Utilities:")
print("    - list_available_nodes()")
print("    - inspect_node_sockets(node_type)")
print("    - layout_nodes(node_group)")
print("    - check_catalogue_version(version)")
print("=" * 60)

# ============================================================================
# MERMAID PARSER - Convert Mermaid flowchart to graph_json
# ============================================================================

# Prefixes stripped from identifiers to create short Mermaid names.
# Order matters: longest/most-specific first to avoid partial matches.
_MERMAID_IDENT_PREFIXES = ["GeometryNode", "FunctionNode", "ShaderNode"]

# Manual overrides for nodes not in the catalogue (or special pseudo-nodes).
_MERMAID_MANUAL_OVERRIDES = {
    "GroupInput": "NodeGroupInput",
    "GroupOutput": "NodeGroupOutput",
}


def _build_mermaid_type_map():
    """Build a short-name → identifier map from the loaded node catalogue.

    Keys are generated two ways (both stored, no conflicts in practice):
    1. Label with spaces removed  ("Combine XYZ" → "CombineXYZ")
    2. Identifier with known prefix stripped ("GeometryNodeMeshCone" → "MeshCone")

    Full identifiers are also accepted as keys (identity mapping).
    The result is cached in ``_MERMAID_TYPE_MAP`` after the first call.
    """
    global _MERMAID_TYPE_MAP
    if _MERMAID_TYPE_MAP is not None:
        return _MERMAID_TYPE_MAP

    type_map = dict(_MERMAID_MANUAL_OVERRIDES)

    try:
        catalogue = load_node_catalogue()
    except FileNotFoundError:
        _MERMAID_TYPE_MAP = type_map
        return _MERMAID_TYPE_MAP

    for node in catalogue:
        ident = node["identifier"]
        label = node.get("label", "")

        # Key from label (spaces removed)
        if label:
            key_label = label.replace(" ", "")
            type_map.setdefault(key_label, ident)

        # Key from identifier with prefix stripped
        for pfx in _MERMAID_IDENT_PREFIXES:
            if ident.startswith(pfx):
                key_stripped = ident[len(pfx):]
                type_map.setdefault(key_stripped, ident)
                break

        # Full identifier always valid (identity)
        type_map[ident] = ident

    _MERMAID_TYPE_MAP = type_map
    return _MERMAID_TYPE_MAP


def parse_mermaid_to_graph_json(mermaid_text, node_type_map=None):
    """
    Parse a Mermaid flowchart into graph_json format.

    Supports the convention from the workflow doc:
    - flowchart LR only (left-to-right)
    - Node syntax: n1["Label"] or n1(Label)
    - Edge labels as socket names: n1 -->|socket| n2

    Args:
        mermaid_text: Mermaid flowchart string
        node_type_map: Optional dict mapping short labels to full Blender types
                       e.g. {"MeshCone": "GeometryNodeMeshCone"}
                       If not provided, tries to infer from common patterns.

    Returns:
        Dict with 'nodes', 'links', 'node_settings' (empty by default),
        plus 'parse_warnings' for any issues detected.

    Example input:
        flowchart LR
          n1["MeshCone"] -->|Mesh| n2["SetPosition"]
          n2 -->|Geometry| out["GroupOutput"]

    Example output:
        {
            "nodes": [
                {"id": "n1", "type": "GeometryNodeMeshCone"},
                {"id": "n2", "type": "GeometryNodeSetPosition"}
            ],
            "links": [
                {"from": "n1", "from_socket": "Mesh", "to": "n2", "to_socket": "Geometry"}
            ],
            "node_settings": {},
            "parse_warnings": []
        }
    """
    import re

    result = {
        "nodes": [],
        "links": [],
        "node_settings": {},
        "parse_warnings": []
    }

    # Build type map from catalogue (cached after first call).
    # User-supplied node_type_map overrides take precedence.
    type_map = {**_build_mermaid_type_map(), **(node_type_map or {})}

    # Track seen nodes and links
    seen_nodes = {}
    seen_links = set()

    # Special IDs map to the auto-created group input/output nodes.
    SPECIAL_NODE_TYPES = {
        "__GROUP_INPUT__": "NodeGroupInput",
        "__GROUP_OUTPUT__": "NodeGroupOutput",
    }

    def _mark_special_node(node_id):
        if node_id in SPECIAL_NODE_TYPES:
            seen_nodes[node_id] = SPECIAL_NODE_TYPES[node_id]
            return True
        return False

    lines = mermaid_text.strip().split('\n')

    for line in lines:
        line = line.strip()

        # Skip empty lines, comments, and flowchart directive
        if not line or line.startswith('%%') or line.startswith('flowchart'):
            continue

        # First, extract ALL node definitions from the line
        # Pattern: n1["Label"] or n1(Label) or n1[Label]
        node_pattern = r'(\w+)\s*[\[\(]["\']*([^"\'\]\)]+)["\']*[\]\)]'
        for match in re.finditer(node_pattern, line):
            node_id = match.group(1)
            label = match.group(2).strip()

            if node_id in seen_nodes:
                continue

            # Skip special node IDs - they reference auto-created Group I/O nodes
            if _mark_special_node(node_id):
                continue

            # Try to resolve the Blender type
            blender_type = type_map.get(label)
            if not blender_type:
                # Try adding common prefixes
                if label.startswith("GeometryNode") or label.startswith("FunctionNode") or label.startswith("ShaderNode"):
                    blender_type = label
                else:
                    # Try GeometryNode prefix
                    blender_type = f"GeometryNode{label}"
                    result["parse_warnings"].append(
                        f"Node '{node_id}' label '{label}' not in type map, assuming '{blender_type}'"
                    )

            seen_nodes[node_id] = blender_type
            result["nodes"].append({
                "id": node_id,
                "type": blender_type
            })

        # Now find ALL edges in the line (there can be multiple: a --> b --> c)
        # Pattern for edge with socket: something -->|Socket| something
        # We need to handle inline node definitions too

        # Find all arrows in the line
        # This handles: n1["Label"] -->|Socket| n2["Label"]
        edge_with_socket = r'(\w+)(?:\s*[\[\(][^\]\)]+[\]\)])?\s*-->\s*\|([^|]+)\|\s*(\w+)'
        edge_without_socket = r'(\w+)(?:\s*[\[\(][^\]\)]+[\]\)])?\s*-->\s*(\w+)'

        # Find edges with socket labels first
        for match in re.finditer(edge_with_socket, line):
            from_id = match.group(1)
            socket_name = match.group(2).strip()
            to_id = match.group(3)

            # Common socket name mappings (output -> input)
            # When output socket name differs from expected input socket name
            socket_input_map = {
                "Mesh": {"InstanceOnPoints": "Instance", "MeshToPoints": "Mesh"},
                "Points": {"InstanceOnPoints": "Points"},
                "Instances": {"GroupOutput": "Geometry", "__GROUP_OUTPUT__": "Geometry"},
            }

            # Determine the input socket name
            to_socket = socket_name
            if socket_name in socket_input_map:
                # Check for special IDs first
                if to_id in socket_input_map[socket_name]:
                    to_socket = socket_input_map[socket_name][to_id]
                else:
                    # Look up the target node's expected input name
                    to_node_type = seen_nodes.get(to_id, "") or ""
                    short_type = to_node_type.replace("GeometryNode", "").replace("NodeGroup", "")
                    if short_type in socket_input_map[socket_name]:
                        to_socket = socket_input_map[socket_name][short_type]

            if _mark_special_node(from_id):
                pass
            if _mark_special_node(to_id):
                pass

            link_key = (from_id, socket_name, to_id)
            if link_key not in seen_links:
                seen_links.add(link_key)
                result["links"].append({
                    "from": from_id,
                    "from_socket": socket_name,
                    "to": to_id,
                    "to_socket": to_socket
                })

        # Find edges without socket labels (use default "Geometry")
        # But avoid duplicates from socket-labeled edges
        for match in re.finditer(edge_without_socket, line):
            from_id = match.group(1)
            to_id = match.group(2)

            # Check if this edge was already captured with a socket label
            already_captured = any(
                l["from"] == from_id and l["to"] == to_id
                for l in result["links"]
            )

            if _mark_special_node(from_id):
                pass
            if _mark_special_node(to_id):
                pass

            if not already_captured:
                link_key = (from_id, "Geometry", to_id)
                if link_key not in seen_links:
                    seen_links.add(link_key)
                    result["links"].append({
                        "from": from_id,
                        "from_socket": "Geometry",
                        "to": to_id,
                        "to_socket": "Geometry"
                    })

    return result


def mermaid_to_blender(obj_name, modifier_name, mermaid_text, node_type_map=None, node_settings=None):
    """
    High-level function: Parse Mermaid and build in Blender in one step.

    Args:
        obj_name: Name of object to add modifier to
        modifier_name: Name for the geometry nodes modifier
        mermaid_text: Mermaid flowchart string
        node_type_map: Optional dict mapping short labels to full Blender types
        node_settings: Optional dict of node settings to apply

    Returns:
        Dict with build result plus parse_warnings from Mermaid parsing
    """
    # Parse Mermaid to graph_json
    graph_json = parse_mermaid_to_graph_json(mermaid_text, node_type_map)

    # Add any provided settings
    if node_settings:
        graph_json["node_settings"] = node_settings

    # Build in Blender
    result = build_graph_from_json(obj_name, modifier_name, graph_json)

    # Add parse warnings to result
    result["parse_warnings"] = graph_json.get("parse_warnings", [])

    return result


# ============================================================================
# INCREMENTAL API - Imperative node building with auto-linking
# ============================================================================

def resolve_node_type(name_or_alias):
    """Resolve a label, alias, or identifier to a Blender node type.

    Tries in order:
    1. Exact identifier match (from Mermaid type map, which includes full identifiers)
    2. Label with spaces removed (e.g., "Mesh Cone" -> "MeshCone" -> identifier)
    3. Alias lookup (e.g., "scatter" -> GeometryNodeDistributePointsOnFaces)
    4. Case-insensitive alias match

    Args:
        name_or_alias: Node label, alias, or full Blender identifier

    Returns:
        Blender node identifier string, or None if not found

    Examples:
        >>> resolve_node_type("Grid")
        'GeometryNodeMeshGrid'
        >>> resolve_node_type("scatter")
        'GeometryNodeDistributePointsOnFaces'
        >>> resolve_node_type("GeometryNodeMeshCone")
        'GeometryNodeMeshCone'
    """
    if not name_or_alias:
        return None

    # Build type map from catalogue (includes identifiers, labels, stripped prefixes)
    type_map = _build_mermaid_type_map()

    # 1. Direct match in type map (exact case)
    if name_or_alias in type_map:
        return type_map[name_or_alias]

    # 2. Try with spaces removed (label form)
    no_spaces = name_or_alias.replace(" ", "")
    if no_spaces in type_map:
        return type_map[no_spaces]

    # 3. Try aliases (exact match first)
    aliases = load_node_aliases()
    for identifier, alias_list in aliases.items():
        if name_or_alias in alias_list:
            return identifier

    # 4. Case-insensitive alias match
    name_lower = name_or_alias.lower()
    for identifier, alias_list in aliases.items():
        if name_lower in [a.lower() for a in alias_list]:
            return identifier

    return None


def _normalize_setting_name(name):
    """Normalize a setting name for matching.

    Converts: data_type -> datatype, Size X -> sizex, radius-bottom -> radiusbottom
    """
    return name.lower().replace(" ", "").replace("_", "").replace("-", "")


# Node attributes that are safe to set directly (not via inputs)
# These are common enum/mode properties on geometry nodes
_SAFE_NODE_ATTRIBUTES = {
    "operation",      # ShaderNodeMath, ShaderNodeVectorMath
    "data_type",      # FunctionNodeRandomValue, GeometryNodeSwitch, etc.
    "mode",           # Various nodes
    "domain",         # Attribute nodes
    "input_type",     # Various nodes
    "blend_type",     # ShaderNodeMix
    "clamp_result",   # ShaderNodeMath
    "use_clamp",      # Various nodes
}


def add_node(node_group, name, **settings):
    """Add a node by name/alias and apply optional settings.

    This is the primary function for incremental graph building. It resolves
    the node type from labels, aliases, or full identifiers, creates the node,
    and optionally sets input values or node attributes.

    Args:
        node_group: The node tree to add to (from modifier.node_group)
        name: Node label, alias, or identifier (e.g., "Grid", "scatter",
              "GeometryNodeMeshCone")
        **settings: Values to set. Tries in order:
            1. Input socket by exact name
            2. Input socket by normalized name (data_type -> "Data Type")
            3. Node attribute (operation, data_type, mode, etc.)

    Returns:
        The created Blender node

    Raises:
        ValueError: If node type cannot be resolved or setting cannot be applied

    Examples:
        >>> grid = add_node(ng, "Grid", size_x=5, size_y=5)
        >>> points = add_node(ng, "scatter", density=10)  # alias works
        >>> math = add_node(ng, "Math", operation='ADD', value=2.0)
        >>> rand = add_node(ng, "Random Value", data_type='FLOAT_VECTOR')
    """
    node_type = resolve_node_type(name)
    if not node_type:
        # Provide helpful error with suggestions
        suggestions = find_nodes_by_keyword(name, limit=3)
        suggestion_text = ""
        if suggestions:
            labels = [s["label"] for s in suggestions]
            suggestion_text = f" Did you mean: {', '.join(labels)}?"
        raise ValueError(f"Unknown node type: '{name}'.{suggestion_text}")

    node = node_group.nodes.new(node_type)

    # Apply settings to node inputs or attributes
    for key, value in settings.items():
        setting_applied = False
        key_normalized = _normalize_setting_name(key)

        # 1. Try exact input name match
        for inp in node.inputs:
            if inp.name == key:
                try:
                    set_node_input(node, inp.name, value)
                    setting_applied = True
                    break
                except (KeyError, TypeError) as e:
                    raise ValueError(f"Failed to set input '{key}' on {node.name}: {e}")

        # 2. Try normalized input name match
        if not setting_applied:
            for inp in node.inputs:
                inp_normalized = _normalize_setting_name(inp.name)
                if inp_normalized == key_normalized:
                    try:
                        set_node_input(node, inp.name, value)
                        setting_applied = True
                        break
                    except (KeyError, TypeError) as e:
                        raise ValueError(f"Failed to set input '{inp.name}' on {node.name}: {e}")

        # 3. Try node attribute (for enums like operation, data_type, mode)
        if not setting_applied:
            # Check if it's a known safe attribute or exists on the node
            attr_name = key.lower().replace("-", "_")
            if attr_name in _SAFE_NODE_ATTRIBUTES or hasattr(node, attr_name):
                if hasattr(node, attr_name):
                    try:
                        setattr(node, attr_name, value)
                        setting_applied = True
                    except (AttributeError, TypeError) as e:
                        raise ValueError(f"Failed to set attribute '{attr_name}' on {node.name}: {e}")

        if not setting_applied:
            available_inputs = [inp.name for inp in node.inputs if inp.name]
            available_attrs = [a for a in _SAFE_NODE_ATTRIBUTES if hasattr(node, a)]
            raise ValueError(
                f"Setting '{key}' not found on {node.name} ({node_type}). "
                f"Available inputs: {available_inputs}. "
                f"Available attributes: {available_attrs}"
            )

    return node


def auto_link(node_group, from_node, to_node, to_socket=None):
    """Link two nodes, auto-detecting compatible sockets.

    When to_socket is not specified, finds the best compatible unlinked
    socket pair. Prefers sockets with matching names (e.g., Geometry→Geometry)
    before falling back to the first compatible pair.

    Args:
        node_group: The node tree
        from_node: Source node (output side)
        to_node: Destination node (input side)
        to_socket: Optional specific input socket name on to_node

    Returns:
        The created link

    Raises:
        ValueError: If no compatible sockets found or socket name invalid

    Examples:
        >>> auto_link(ng, grid, points)          # finds Mesh -> Mesh
        >>> auto_link(ng, points, instance)      # finds Points -> Points
        >>> auto_link(ng, cone, instance, "Instance")  # explicit input
    """
    if to_socket:
        # Find the specific input socket (try exact match, then normalized)
        to_sock = None
        to_socket_normalized = _normalize_setting_name(to_socket)
        for inp in to_node.inputs:
            if inp.name == to_socket:
                to_sock = inp
                break
            if _normalize_setting_name(inp.name) == to_socket_normalized:
                to_sock = inp
                # Don't break - prefer exact match if found later

        if not to_sock:
            available = [inp.name for inp in to_node.inputs if inp.name]
            raise ValueError(
                f"Input socket '{to_socket}' not found on {to_node.name}. "
                f"Available: {available}"
            )

        # Find a compatible output socket, preferring name match
        best_output = None
        for out in from_node.outputs:
            valid, _ = validate_socket_link(out, to_sock)
            if valid:
                if out.name == to_sock.name:
                    # Perfect name match - use immediately
                    return safe_link(node_group, out, to_sock)
                if best_output is None:
                    best_output = out

        if best_output:
            return safe_link(node_group, best_output, to_sock)

        # No compatible output found
        available_outputs = [f"{o.name} ({_socket_idname(o)})" for o in from_node.outputs]
        raise ValueError(
            f"No compatible output on {from_node.name} for input '{to_socket}' "
            f"({_socket_idname(to_sock)}). Available outputs: {available_outputs}"
        )

    # Auto-detect: find best compatible unlinked pair
    # Priority: 1) Same name match, 2) First compatible pair
    candidates = []

    for out in from_node.outputs:
        for inp in to_node.inputs:
            if inp.is_linked:
                continue
            valid, _ = validate_socket_link(out, inp)
            if valid:
                # Score: 2 for exact name match, 1 for compatible
                score = 2 if out.name == inp.name else 1
                candidates.append((score, out, inp))

    if candidates:
        # Sort by score descending, pick best
        candidates.sort(key=lambda x: x[0], reverse=True)
        _, best_out, best_inp = candidates[0]
        return safe_link(node_group, best_out, best_inp)

    # Build diagnostic message
    from_sockets = [f"{o.name} ({_socket_idname(o)})" for o in from_node.outputs]
    to_sockets = [f"{i.name} ({_socket_idname(i)})" for i in to_node.inputs if not i.is_linked]
    raise ValueError(
        f"No compatible sockets between {from_node.name} and {to_node.name}. "
        f"Outputs: {from_sockets}. Unlinked inputs: {to_sockets}"
    )


def connect_to_output(node_group, node, socket_name="Geometry"):
    """Connect a node to the Group Output.

    Finds the Group Output node and wires the specified output socket
    to a compatible input on it.

    Args:
        node_group: The node tree
        node: Source node to connect
        socket_name: Output socket name on source node (default: "Geometry")

    Returns:
        The created link

    Raises:
        ValueError: If Group Output not found, socket not found, or no compatible input

    Examples:
        >>> connect_to_output(ng, instance)                # default Geometry
        >>> connect_to_output(ng, math_node, "Value")      # specific socket
    """
    # Find Group Output node
    output_node = None
    for n in node_group.nodes:
        if n.bl_idname == "NodeGroupOutput":
            output_node = n
            break

    if not output_node:
        raise ValueError("No Group Output node found in node group")

    # Find the specified output socket
    out_socket = None
    for out in node.outputs:
        if out.name == socket_name:
            out_socket = out
            break

    if not out_socket:
        available = [o.name for o in node.outputs]
        raise ValueError(
            f"Output socket '{socket_name}' not found on {node.name}. "
            f"Available: {available}"
        )

    # Find matching input on Group Output (prefer unlinked)
    for inp in output_node.inputs:
        valid, _ = validate_socket_link(out_socket, inp)
        if valid and not inp.is_linked:
            return safe_link(node_group, out_socket, inp)

    # Try any compatible input (even if linked)
    for inp in output_node.inputs:
        valid, _ = validate_socket_link(out_socket, inp)
        if valid:
            return safe_link(node_group, out_socket, inp)

    raise ValueError(
        f"No compatible input on Group Output for {node.name}.{socket_name} "
        f"({_socket_idname(out_socket)})"
    )


def describe_node_group(node_group, include_defaults=False):
    """Return a compact snapshot of the node group's current state.

    Designed for the "build → describe → adjust" loop with LLM agents.
    Much lighter than full_geo_nodes_validation() — no screenshots, no metrics.

    Args:
        node_group: The Blender node tree to describe
        include_defaults: If True, include current default values for unlinked inputs

    Returns:
        Dict with:
        - nodes: List of {name, type, label, inputs_set, outputs_linked}
        - links: List of {from_node, from_socket, to_node, to_socket}
        - warnings: List of issues detected (missing output, invalid links, etc.)
        - unlinked_required: List of inputs that have no link and no non-default value
        - has_output: Whether Group Output has a geometry connection
        - node_count: Total number of nodes
        - link_count: Total number of links

    Examples:
        >>> state = describe_node_group(ng)
        >>> if not state["has_output"]:
        ...     print("Warning: Graph has no output connection")
        >>> for warn in state["warnings"]:
        ...     print(f"Issue: {warn}")
    """
    result = {
        "nodes": [],
        "links": [],
        "warnings": [],
        "unlinked_required": [],
        "has_output": False,
        "node_count": 0,
        "link_count": 0,
    }

    if not node_group:
        result["warnings"].append("No node group provided")
        return result

    # Track nodes
    group_output = None
    group_input = None

    for node in node_group.nodes:
        node_info = {
            "name": node.name,
            "type": node.bl_idname,
            "label": node.label or node.name,
        }

        # Track which inputs have been set (linked or non-default value)
        inputs_set = []
        for inp in node.inputs:
            if inp.is_linked:
                inputs_set.append(inp.name)
            elif include_defaults and hasattr(inp, 'default_value'):
                inputs_set.append(f"{inp.name}={_serialize_value(inp.default_value)}")

        # Track which outputs are connected
        outputs_linked = [out.name for out in node.outputs if out.is_linked]

        node_info["inputs_set"] = inputs_set
        node_info["outputs_linked"] = outputs_linked

        result["nodes"].append(node_info)

        # Identify special nodes
        if node.bl_idname == "NodeGroupOutput":
            group_output = node
        elif node.bl_idname == "NodeGroupInput":
            group_input = node

    result["node_count"] = len(result["nodes"])

    # Track links
    for link in node_group.links:
        link_info = {
            "from_node": link.from_node.name,
            "from_socket": link.from_socket.name,
            "to_node": link.to_node.name,
            "to_socket": link.to_socket.name,
        }
        result["links"].append(link_info)

        # Check link validity
        if not link.is_valid:
            result["warnings"].append(
                f"Invalid link: {link.from_node.name}.{link.from_socket.name} → "
                f"{link.to_node.name}.{link.to_socket.name}"
            )

    result["link_count"] = len(result["links"])

    # Check Group Output connectivity
    if group_output:
        geometry_connected = False
        for inp in group_output.inputs:
            if inp.is_linked and "Geometry" in inp.name:
                geometry_connected = True
                break
        result["has_output"] = geometry_connected
        if not geometry_connected:
            result["warnings"].append(
                "Group Output has no Geometry connection — modifier will produce nothing"
            )
    else:
        result["warnings"].append("No Group Output node found")

    # Find unlinked required inputs
    # Only flag the FIRST unlinked geometry input per node (the primary one)
    # Skip nodes that explicitly accept optional geometry (Join Geometry, Switch, etc.)
    _OPTIONAL_GEOMETRY_NODES = {
        "GeometryNodeJoinGeometry",  # All inputs are optional
        "GeometryNodeSwitch",        # Conditional - may not use both
        "GeometryNodeIndexSwitch",   # Only one active at a time
        "GeometryNodeMenuSwitch",    # Only one active at a time
        "GeometryNodeViewer",        # Debug node, geometry optional
    }

    for node in node_group.nodes:
        if node.bl_idname in ("NodeGroupInput", "NodeGroupOutput"):
            continue
        if node.bl_idname in _OPTIONAL_GEOMETRY_NODES:
            continue

        # Find the first geometry input - if unlinked, flag it
        for inp in node.inputs:
            socket_type = _socket_idname(inp)
            if "Geometry" in socket_type:
                if not inp.is_linked:
                    result["unlinked_required"].append(f"{node.name}.{inp.name}")
                break  # Only check the first geometry input

    return result


def print_node_group_state(node_group, include_defaults=False):
    """Pretty-print the current state of a node group.

    Convenience wrapper around describe_node_group() for console output.

    Args:
        node_group: The Blender node tree to describe
        include_defaults: If True, include current default values
    """
    state = describe_node_group(node_group, include_defaults)

    print(f"\n=== Node Group State ===")
    print(f"Nodes: {state['node_count']}  Links: {state['link_count']}  Output: {'✓' if state['has_output'] else '✗'}")

    if state["warnings"]:
        print(f"\nWarnings ({len(state['warnings'])}):")
        for w in state["warnings"]:
            print(f"  ⚠ {w}")

    if state["unlinked_required"]:
        print(f"\nUnlinked required inputs:")
        for u in state["unlinked_required"]:
            print(f"  • {u}")

    print(f"\nNodes:")
    for n in state["nodes"]:
        inputs_str = f" [{', '.join(n['inputs_set'])}]" if n['inputs_set'] else ""
        outputs_str = f" → [{', '.join(n['outputs_linked'])}]" if n['outputs_linked'] else ""
        print(f"  {n['name']} ({n['type']}){inputs_str}{outputs_str}")

    if state["links"]:
        print(f"\nLinks:")
        for lnk in state["links"]:
            print(f"  {lnk['from_node']}.{lnk['from_socket']} → {lnk['to_node']}.{lnk['to_socket']}")


# Version check
check_catalogue_version()
