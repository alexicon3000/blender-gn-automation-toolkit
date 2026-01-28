"""
Validation functions for Geometry Nodes.

Provides programmatic and visual validation of geometry node graphs,
including graph structure checks, numerical metrics, and screenshot capture.
"""

try:
    import bpy  # type: ignore
except ImportError:  # pragma: no cover - available only inside Blender
    bpy = None  # type: ignore
import os
import tempfile
from mathutils import Euler
import math

from . import catalogue

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
    spec = catalogue.get_node_spec(node_type) if node_type else None
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
        if resolved_type not in {"NodeGroupInput", "NodeGroupOutput"} and not catalogue.get_node_spec(resolved_type):
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

    # Add implicit Group I/O nodes
    node_types.setdefault("__GROUP_INPUT__", "NodeGroupInput")
    node_types.setdefault("__GROUP_OUTPUT__", "NodeGroupOutput")

    group_output_ids = {
        node_id for node_id, node_type in node_types.items()
        if node_type == "NodeGroupOutput"
    }

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
            source_field = catalogue.get_socket_field_support(from_type, from_socket, is_output=True)
            dest_field = catalogue.get_socket_field_support(to_type, to_socket, is_output=False)
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

    has_group_output_link = any(
        link.get("to") in group_output_ids or link.get("to") == "__GROUP_OUTPUT__"
        for link in links
    )
    _add_check(
        "group_output_linked",
        True,
        "No link targets Group Output (__GROUP_OUTPUT__)" if not has_group_output_link else None,
    )

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
            socket_spec = catalogue.get_socket_spec(node_type, input_name, is_output=False)
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


def generate_full_graph_report(node_group, node_id_map=None):
    """Generate a full graph report with nodes, sockets, and link details."""
    report = {
        "name": node_group.name,
        "node_count": len(node_group.nodes),
        "link_count": len(node_group.links),
        "node_id_map": node_id_map or {},
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


def _socket_id(socket):
    if hasattr(socket, 'bl_idname') and socket.bl_idname:
        return socket.bl_idname
    bl_rna = getattr(socket, 'bl_rna', None)
    if bl_rna and hasattr(bl_rna, 'identifier'):
        return bl_rna.identifier
    return socket.__class__.__name__


def validate_graph_structure(node_group):
    """
    Analyze a node group's structure and detect issues.

    Args:
        node_group: A bpy.types.GeometryNodeTree

    Returns:
        Dict with node_count, link_count, nodes, links, invalid_links, issues
    """
    result = {
        "name": node_group.name,
        "node_count": len(node_group.nodes),
        "link_count": len(node_group.links),
        "nodes": [],
        "links": [],
        "invalid_links": [],
        "issues": []
    }

    # Catalog nodes
    for n in sorted(node_group.nodes, key=lambda x: x.location.x):
        result["nodes"].append({
            "name": n.name,
            "type": n.bl_idname,
            "location": (n.location.x, n.location.y)
        })

    # Catalog and validate links
    for link in node_group.links:
        link_info = {
            "from_node": link.from_node.name,
            "from_socket": link.from_socket.name,
            "from_type": link.from_socket.type,
            "to_node": link.to_node.name,
            "to_socket": link.to_socket.name,
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
    """
    Measure numerical properties of the resulting geometry.

    Args:
        obj: A Blender object with evaluated geometry
        tolerance: Acceptable deviation from ground plane (default 0.001)

    Returns:
        Dict with vertex_count, face_count, min_z, max_z, ground_contact, issues
    """
    result = {
        "vertex_count": 0,
        "face_count": 0,
        "min_z": None,
        "max_z": None,
        "height_range": None,
        "ground_contact": None,
        "issues": []
    }

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
                result["issues"].append(
                    f"Ground contact FAILED: min_z = {min(zs):.4f} (expected ~0)"
                )

        obj_eval.to_mesh_clear()

    except Exception as e:
        result["issues"].append(f"Metrics error: {str(e)}")

    return result


def full_validation(obj_name, modifier_name, capture_screenshot=True, include_report=False, node_id_map=None):
    """
    Complete validation of a geometry nodes setup.

    Combines graph structure validation, numerical metrics, and optional
    screenshot capture into a single comprehensive report.

    Args:
        obj_name: Name of the object with geometry nodes
        modifier_name: Name of the geometry nodes modifier
        capture_screenshot: Whether to capture workspace screenshot

    Returns:
        Dict with status, graph, metrics, issues, screenshot_path
    """
    from . import workspace

    result = {
        "status": "UNKNOWN",
        "object": obj_name,
        "modifier": modifier_name,
        "graph": {},
        "metrics": {},
        "issues": [],
        "screenshot_path": None,
        "full_report": None
    }

    # Get object and modifier
    obj = bpy.data.objects.get(obj_name)
    if not obj:
        result["issues"].append(f"Object '{obj_name}' not found")
        result["status"] = "ERROR"
        return result

    mod = obj.modifiers.get(modifier_name)
    if not mod or not mod.node_group:
        result["issues"].append(f"Modifier '{modifier_name}' not found or empty")
        result["status"] = "ERROR"
        return result

    ng = mod.node_group

    # Validate graph structure
    graph_result = validate_graph_structure(ng)
    result["graph"] = graph_result
    result["issues"].extend(graph_result["issues"])

    # Validate geometry metrics
    metrics_result = validate_geometry_metrics(obj)
    result["metrics"] = metrics_result
    result["issues"].extend(metrics_result["issues"])

    # Capture screenshot if requested
    if capture_screenshot:
        # Switch to validation workspace and configure views
        workspace.switch_to_mcp_workspace()
        workspace.configure_validation_views(obj_name, modifier_name)

        # Capture full workspace
        path = os.path.join(tempfile.gettempdir(), "geo_nodes_validation.png")
        bpy.ops.screen.screenshot(filepath=path)
        result["screenshot_path"] = path

    if include_report:
        result["full_report"] = generate_full_graph_report(ng, node_id_map=node_id_map)

    # Determine final status
    if result["issues"]:
        result["status"] = "ISSUES_FOUND"
    else:
        result["status"] = "VALID"

    return result


def full_graph_report(obj_name, modifier_name, node_id_map=None):
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

    result["report"] = generate_full_graph_report(mod.node_group, node_id_map=node_id_map)
    result["status"] = "OK"
    return result


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
