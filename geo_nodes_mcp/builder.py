"""
Builder for creating Geometry Nodes from graph_json specification.

Takes a JSON specification and creates the actual node graph in Blender,
with validation at each step.
"""

try:
    import bpy  # type: ignore
except ImportError:  # pragma: no cover - available only inside Blender
    bpy = None  # type: ignore

from . import catalogue
from . import validator


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
        return catalogue.get_socket_field_support(node_type, getattr(socket, 'name', ''), is_output=is_output)
    except FileNotFoundError:
        return None


def validate_socket_link(from_socket, to_socket):
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

    if not catalogue.are_socket_types_compatible(from_id, to_id):
        return False, (
            "Socket types are incompatible: "
            f"{_describe_socket(from_socket)} -> {_describe_socket(to_socket)}"
        )
    return True, None


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


def _gather_existing_nodes(node_group):
    """Map node.name to node for existing nodes (excluding group IO)."""
    mapping = {}
    for node in node_group.nodes:
        if node.bl_idname in {"NodeGroupInput", "NodeGroupOutput"}:
            continue
        mapping[node.name] = node
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


def build_graph_from_json(
    obj_name,
    modifier_name,
    graph_json,
    clear_existing=True,
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
            {"from": "n1", "socket": "Mesh", "to": "n2", "socket": "Geometry"}
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
        "errors": [],
        "preflight": None,
        "diff_summary": None,
    }

    preflight = validator.validate_graph_json_preflight(graph_json)
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

    if merge_existing:
        clear_existing = False

    # Clear existing nodes if requested
    if clear_existing:
        ng.nodes.clear()
        # Re-create interface sockets
        ng.interface.clear()
        ng.interface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
        ng.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

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
            node.name = node_id
            node.label = node_id
            result["nodes"][node_id] = node
            continue

        try:
            node = ng.nodes.new(node_type)
            node.name = node_id
            node.label = node_id

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

    result["success"] = len(result["errors"]) == 0
    return result


def layout_nodes(node_group, padding=50):
    """
    Auto-layout nodes in a graph from left to right based on dependencies.

    Simple topological sort layout.
    """
    nodes = list(node_group.nodes)

    # Find nodes with no inputs (starting nodes)
    # and build dependency graph
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
    y = 0
    max_height = 0

    for i, node in enumerate(sorted_nodes):
        node.location = (x, y)

        # Move to next column
        x += node.width + padding

        # Track max height for row wrapping (if needed in future)
        if node.height > max_height:
            max_height = node.height
