"""
Validation functions for Geometry Nodes.

Provides programmatic and visual validation of geometry node graphs,
including graph structure checks, numerical metrics, and screenshot capture.
"""

import bpy
import os
import tempfile
from mathutils import Euler
import math


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


def full_validation(obj_name, modifier_name, capture_screenshot=True):
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
        "screenshot_path": None
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

    # Determine final status
    if result["issues"]:
        result["status"] = "ISSUES_FOUND"
    else:
        result["status"] = "VALID"

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

    if result['issues']:
        print(f"\nISSUES ({len(result['issues'])}):")
        for issue in result['issues']:
            print(f"  - {issue}")
    else:
        print(f"\nNo issues detected!")
