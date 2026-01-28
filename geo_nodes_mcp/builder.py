"""
Builder for creating Geometry Nodes from graph_json specification.

Takes a JSON specification and creates the actual node graph in Blender,
with validation at each step.
"""

import bpy

from . import catalogue


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


def validate_socket_link(from_socket, to_socket):
    if not getattr(from_socket, 'is_output', False):
        return False, f"Source socket is not an output: {_describe_socket(from_socket)}"
    if getattr(to_socket, 'is_output', False):
        return False, f"Destination socket is not an input: {_describe_socket(to_socket)}"

    from_id = _socket_idname(from_socket)
    to_id = _socket_idname(to_socket)

    if not catalogue.are_socket_types_compatible(from_id, to_id):
        return False, (
            "Socket types are incompatible: "
            f"{_describe_socket(from_socket)} -> {_describe_socket(to_socket)}"
        )
    return True, None


def build_graph_from_json(obj_name, modifier_name, graph_json, clear_existing=True):
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
        "errors": []
    }

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
        from_socket_name = link_spec.get("socket") or link_spec.get("from_socket")
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
