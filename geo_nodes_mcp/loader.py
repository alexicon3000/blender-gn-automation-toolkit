"""
Loader script to inject geo_nodes_mcp functions into Blender.

This script is designed to be sent via execute_blender_code at the
start of a geometry nodes session. It defines all necessary functions
directly in Blender's Python environment.

Usage via MCP:
    1. Read this file
    2. Send contents to mcp__blender__execute_blender_code
    3. Functions are now available in Blender
"""

LOADER_CODE = '''
try:
    import bpy  # type: ignore
except ImportError:  # pragma: no cover - available only inside Blender
    bpy = None  # type: ignore
import os
import tempfile
from mathutils import Euler
import math

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
    result = {"vertex_count": 0, "min_z": None, "max_z": None, "ground_contact": None, "issues": []}

    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.to_mesh()

        if mesh and mesh.vertices:
            zs = [(obj.matrix_world @ v.co).z for v in mesh.vertices]
            result["vertex_count"] = len(mesh.vertices)
            result["min_z"] = round(min(zs), 4)
            result["max_z"] = round(max(zs), 4)
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
        path = os.path.join(tempfile.gettempdir(), "geo_nodes_validation.png")
        bpy.ops.screen.screenshot(filepath=path)
        result["screenshot_path"] = path

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


# ============================================================================
# SAFE BUILDING HELPERS
# ============================================================================

def get_output_by_type(node, socket_type):
    """Find output socket by type, not index."""
    for out in node.outputs:
        if out.type == socket_type:
            return out
    raise ValueError(f"No {socket_type} output on {node.name}")


def safe_link(node_group, from_socket, to_socket):
    """Create link and validate immediately."""
    link = node_group.links.new(from_socket, to_socket)
    if not link.is_valid:
        raise RuntimeError(
            f"Invalid link: {from_socket.node.name}.{from_socket.name} "
            f"({from_socket.type}) -> {to_socket.node.name}.{to_socket.name} "
            f"({to_socket.type})"
        )
    return link


# ============================================================================
# VERSION CHECK
# ============================================================================

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


def check_catalogue_version(catalogue_version="4.4"):
    """Check if current Blender matches catalogue version."""
    version_tuple, version_str = get_blender_version()
    major_minor = f"{version_tuple[0]}.{version_tuple[1]}"

    env_path = os.environ.get("GN_MCP_CATALOGUE_PATH")
    inferred = _catalogue_version_from_path(env_path)
    effective_version = inferred or catalogue_version

    if major_minor != effective_version:
        print(f"WARNING: Catalogue is for Blender {effective_version}, "
              f"but running {version_str}. Socket names may differ!")
        return False
    return True


# ============================================================================
# INITIALIZATION
# ============================================================================

print("geo_nodes_mcp validation toolkit loaded")
print(f"Blender version: {get_blender_version()[1]}")
print("Available functions:")
print("  - full_geo_nodes_validation(obj_name, modifier_name)")
print("  - capture_node_graph(obj_name, modifier_name)")
print("  - validate_graph_structure(node_group)")
print("  - validate_geometry_metrics(obj)")
print("  - safe_link(node_group, from_socket, to_socket)")
print("  - get_output_by_type(node, socket_type)")
print("  - switch_to_mcp_workspace()")
'''

def get_loader_code():
    """Return the code to inject into Blender."""
    return LOADER_CODE


if __name__ == "__main__":
    print(LOADER_CODE)
