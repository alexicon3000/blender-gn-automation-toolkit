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
CATALOGUE_VERSION = "4.4"

# Resolve toolkit root so reference files can be located when exec'd via MCP
_TOOLKIT_DIR = os.path.dirname(__file__) if "__file__" in globals() else os.getcwd()
_REFERENCE_DIR = os.path.join(_TOOLKIT_DIR, "reference")
_ARCHIVE_REFERENCE_DIR = os.path.join(_TOOLKIT_DIR, "_GN-LLM-References")
_CATALOGUE_ENV_VAR = "GN_MCP_CATALOGUE_PATH"
_DEFAULT_COMPLETE_NAME = f"geometry_nodes_complete_{CATALOGUE_VERSION.replace('.', '_')}.json"
_DEFAULT_MIN_NAME = f"geometry_nodes_min_{CATALOGUE_VERSION.replace('.', '_')}.json"
_SOCKET_COMPAT_ENV_VAR = "GN_MCP_SOCKET_COMPAT_PATH"
_SOCKET_COMPAT_FILENAME = "socket_compat.csv"

_NODE_CATALOGUE = None
_NODE_CATALOGUE_INDEX = {}
_NODE_CATALOGUE_SOURCE = None
_NODE_CATALOGUE_MIN = None
_NODE_CATALOGUE_MIN_INDEX = {}
_NODE_CATALOGUE_MIN_SOURCE = None
_SOCKET_COMPAT = None
_SOCKET_COMPAT_SOURCE = None

def get_blender_version():
    """Return Blender version tuple and string."""
    return bpy.app.version, f"{bpy.app.version[0]}.{bpy.app.version[1]}"


def check_catalogue_version(catalogue_version=CATALOGUE_VERSION):
    """Check if current Blender matches catalogue version."""
    version_tuple, version_str = get_blender_version()
    major_minor = f"{version_tuple[0]}.{version_tuple[1]}"

    if major_minor != catalogue_version:
        print(f"WARNING: Catalogue is for Blender {catalogue_version}, "
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
    """Load node catalogue JSON (complete or minimal) and cache the result."""
    global _NODE_CATALOGUE, _NODE_CATALOGUE_INDEX, _NODE_CATALOGUE_SOURCE

    if _NODE_CATALOGUE and not force_reload and not path:
        return _NODE_CATALOGUE

    resolved = _resolve_catalogue_path(path, prefer_complete)
    if not resolved:
        raise FileNotFoundError(
            "Could not locate geometry node catalogue. Set GN_MCP_CATALOGUE_PATH or "
            "place geometry_nodes_complete/min files next to toolkit.py."
        )

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

    if not are_socket_types_compatible(from_id, to_id):
        return False, (
            "Socket types are incompatible: "
            f"{_describe_socket(from_socket)} -> {_describe_socket(to_socket)}"
        )

    source_field = _socket_supports_field(from_socket, is_output=True)
    dest_field = _socket_supports_field(to_socket, is_output=False)
    if source_field and dest_field is False:
        return False, (
            "Field output cannot connect to non-field input: "
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

def build_graph_from_json(obj_name, modifier_name, graph_json, clear_existing=True, collection=None):
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
            - node_group: The created/modified node group
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
        "node_group": None,
        "nodes": {},
        "errors": []
    }

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

    result["node_group"] = ng

    # Clear existing nodes if requested
    if clear_existing:
        ng.nodes.clear()
        # Re-create interface sockets
        ng.interface.clear()
        ng.interface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
        ng.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    # Create Group Input/Output nodes
    group_input = ng.nodes.new('NodeGroupInput')
    group_input.location = (-400, 0)
    result["nodes"]["__GROUP_INPUT__"] = group_input

    group_output = ng.nodes.new('NodeGroupOutput')
    group_output.location = (400, 0)
    result["nodes"]["__GROUP_OUTPUT__"] = group_output

    # Create nodes from spec
    x_offset = -200
    y_offset = 0

    for node_spec in graph_json.get("nodes", []):
        node_id = node_spec.get("id")
        node_type = node_spec.get("type")

        if not node_id or not node_type:
            result["errors"].append(f"Invalid node spec: {node_spec}")
            continue

        try:
            node = ng.nodes.new(node_type)
            # Keep Blender's natural node name and don't set a label
            # This ensures nodes display as "Grid", "Mesh to Points", etc.
            # The node_id is only used internally for the result["nodes"] lookup

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
    for node_id, settings in graph_json.get("node_settings", {}).items():
        node = result["nodes"].get(node_id)
        if not node:
            result["errors"].append(f"Settings for unknown node: {node_id}")
            continue

        for input_name, value in settings.items():
            try:
                set_node_input(node, input_name, value)
            except Exception as e:
                result["errors"].append(f"Failed to set {node_id}.{input_name}: {e}")

    # Create links
    for link_spec in graph_json.get("links", []):
        from_id = link_spec.get("from")
        from_socket_name = link_spec.get("from_socket") or link_spec.get("socket")
        to_id = link_spec.get("to")
        to_socket_name = link_spec.get("to_socket") or link_spec.get("socket")

        # Handle second socket name for "to" side if specified differently
        if "to_socket" in link_spec:
            to_socket_name = link_spec["to_socket"]

        from_node = result["nodes"].get(from_id)
        to_node = result["nodes"].get(to_id)

        if not from_node:
            result["errors"].append(f"Link from unknown node: {from_id}")
            continue
        if not to_node:
            result["errors"].append(f"Link to unknown node: {to_id}")
            continue

        # Find sockets by name
        from_socket = None
        for out in from_node.outputs:
            if out.name == from_socket_name:
                from_socket = out
                break

        if not from_socket:
            result["errors"].append(
                f"Output socket '{from_socket_name}' not found on {from_id}. "
                f"Available: {[o.name for o in from_node.outputs]}"
            )
            continue

        to_socket = None
        for inp in to_node.inputs:
            if inp.name == to_socket_name:
                to_socket = inp
                break

        if not to_socket:
            result["errors"].append(
                f"Input socket '{to_socket_name}' not found on {to_id}. "
                f"Available: {[i.name for i in to_node.inputs]}"
            )
            continue

        # Create and validate link
        try:
            link = safe_link(ng, from_socket, to_socket)
        except RuntimeError as e:
            result["errors"].append(str(e))

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


def full_geo_nodes_validation(obj_name, modifier_name, capture_screenshot=True):
    """Complete validation with graph checks, metrics, and screenshot."""
    result = {
        "status": "UNKNOWN",
        "object": obj_name,
        "modifier": modifier_name,
        "graph": {},
        "metrics": {},
        "issues": [],
        "screenshot_path": None
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

    result["status"] = "ISSUES_FOUND" if result["issues"] else "VALID"
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
print("=" * 60)
print("\nAvailable functions:")
print("  Building:")
print("    - build_graph_from_json(obj, mod, graph_json)")
print("    - mermaid_to_blender(obj, mod, mermaid_text)  # One-step!")
print("    - parse_mermaid_to_graph_json(mermaid_text)")
print("    - set_node_input(node, input_name, value)")
print("    - safe_link(node_group, from_socket, to_socket)")
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

    # Default type mappings for common short names
    default_type_map = {
        # Geometry nodes (short names)
        "MeshCone": "GeometryNodeMeshCone",
        "MeshCube": "GeometryNodeMeshCube",
        "MeshCylinder": "GeometryNodeMeshCylinder",
        "MeshGrid": "GeometryNodeMeshGrid",
        "MeshIcoSphere": "GeometryNodeMeshIcoSphere",
        "MeshLine": "GeometryNodeMeshLine",
        "MeshUVSphere": "GeometryNodeMeshUVSphere",
        "MeshCircle": "GeometryNodeMeshCircle",
        "SetPosition": "GeometryNodeSetPosition",
        "Transform": "GeometryNodeTransform",
        "JoinGeometry": "GeometryNodeJoinGeometry",
        "InstanceOnPoints": "GeometryNodeInstanceOnPoints",
        "MeshToPoints": "GeometryNodeMeshToPoints",
        "PointsToVertices": "GeometryNodePointsToVertices",
        "SubdivideMesh": "GeometryNodeSubdivideMesh",
        "SetMaterial": "GeometryNodeSetMaterial",
        "Viewer": "GeometryNodeViewer",
        "BoundingBox": "GeometryNodeBoundBox",
        "TranslateInstances": "GeometryNodeTranslateInstances",
        "RotateInstances": "GeometryNodeRotateInstances",
        "ScaleInstances": "GeometryNodeScaleInstances",
        "RealizeInstances": "GeometryNodeRealizeInstances",
        # Function nodes
        "RandomValue": "FunctionNodeRandomValue",
        "CombineXYZ": "ShaderNodeCombineXYZ",
        "SeparateXYZ": "ShaderNodeSeparateXYZ",
        "Math": "ShaderNodeMath",
        "VectorMath": "ShaderNodeVectorMath",
        "Compare": "FunctionNodeCompare",
        "BooleanMath": "FunctionNodeBooleanMath",
        # Special nodes
        "GroupInput": "NodeGroupInput",
        "GroupOutput": "NodeGroupOutput",
    }

    type_map = {**default_type_map, **(node_type_map or {})}

    # Track seen nodes and links
    seen_nodes = {}
    seen_links = set()

    # Special IDs that reference auto-created nodes (don't create new nodes for these)
    SPECIAL_NODE_IDS = {"__GROUP_INPUT__", "__GROUP_OUTPUT__"}

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
            if node_id in SPECIAL_NODE_IDS:
                seen_nodes[node_id] = None  # Mark as seen but don't create
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


# Version check
check_catalogue_version()
