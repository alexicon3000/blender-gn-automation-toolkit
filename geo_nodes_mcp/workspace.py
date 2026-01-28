"""
Workspace management for MCP validation.

Provides functions to set up and switch between validation workspaces
in Blender without creating duplicates.
"""

import bpy
from mathutils import Euler
import math


def get_or_create_mcp_workspace():
    """
    Get existing MCP Validation workspace or create it ONCE.
    Returns the workspace, does not create duplicates.
    """
    # Check if any MCP workspace exists - reuse it
    for ws in bpy.data.workspaces:
        if ws.name.startswith("MCP Validation"):
            return ws

    # None exists - create one from Geometry Nodes template
    geo_ws = bpy.data.workspaces.get("Geometry Nodes")
    if not geo_ws:
        # Fallback to Layout if Geometry Nodes doesn't exist
        geo_ws = bpy.data.workspaces.get("Layout")
    if not geo_ws:
        return None

    bpy.context.window.workspace = geo_ws
    bpy.ops.workspace.duplicate()

    # Find and rename the new one
    for ws in bpy.data.workspaces:
        if ws.name.endswith(".001") or ws.name.endswith(".002"):
            if "Geometry" in ws.name or "Layout" in ws.name:
                ws.name = "MCP Validation"

                # Configure the layout
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
    """
    Configure all views for validation:
    - Set up 3D viewports (perspective + front ortho)
    - Frame all nodes in node editor
    - Set appropriate shading (matcap for visibility)

    Args:
        obj_name: Name of the object with geometry nodes
        modifier_name: Name of the geometry nodes modifier

    Returns:
        Tuple of (success: bool, message: str)
    """
    screen = bpy.context.screen
    obj = bpy.data.objects.get(obj_name)

    if not obj:
        return False, f"Object '{obj_name}' not found"

    mod = obj.modifiers.get(modifier_name)
    if not mod or not mod.node_group:
        return False, f"Modifier '{modifier_name}' not found or has no node group"

    ng = mod.node_group

    # Configure VIEW_3D areas
    view3d_areas = [a for a in screen.areas if a.type == 'VIEW_3D']

    for i, area in enumerate(view3d_areas[:2]):  # Only configure first 2
        space = area.spaces[0]
        r3d = space.region_3d

        # Common settings - matcap shows depth well
        space.shading.type = 'SOLID'
        space.shading.light = 'MATCAP'
        try:
            space.shading.studio_light = 'check_normal+y.exr'
        except:
            pass  # Matcap might not exist

        if i == 0:  # First viewport: Perspective
            r3d.view_perspective = 'PERSP'
            r3d.view_rotation = Euler((math.radians(70), 0, math.radians(30))).to_quaternion()
            r3d.view_distance = 35
            r3d.view_location = (0, 0, 4)
        elif i == 1:  # Second viewport: Front ortho (ground check)
            r3d.view_perspective = 'ORTHO'
            r3d.view_rotation = Euler((math.radians(90), 0, 0)).to_quaternion()
            r3d.view_distance = 25
            r3d.view_location = (0, 0, 5)

    # Configure NODE_EDITOR - frame all nodes
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


def capture_fullscreen_node_graph(obj_name, modifier_name):
    """
    Capture a fullscreen screenshot of just the node graph.
    Temporarily toggles fullscreen, frames all nodes, captures, then exits.

    Args:
        obj_name: Name of the object with geometry nodes
        modifier_name: Name of the geometry nodes modifier

    Returns:
        Path to screenshot file, or None on failure
    """
    import os
    import tempfile

    obj = bpy.data.objects.get(obj_name)
    if not obj:
        return None

    mod = obj.modifiers.get(modifier_name)
    if not mod or not mod.node_group:
        return None

    ng = mod.node_group
    screen = bpy.context.screen

    # Find a NODE_EDITOR area
    node_area = None
    for area in screen.areas:
        if area.type == 'NODE_EDITOR':
            node_area = area
            break

    if not node_area:
        # Try to convert another area
        for area in screen.areas:
            if area.type in ['SPREADSHEET', 'DOPESHEET_EDITOR', 'CONSOLE']:
                area.type = 'NODE_EDITOR'
                node_area = area
                break

    if not node_area:
        return None

    # Set up the node tree
    space = node_area.spaces[0]
    space.node_tree = ng
    space.pin = True

    # Find the WINDOW region
    window_region = None
    for region in node_area.regions:
        if region.type == 'WINDOW':
            window_region = region
            break

    # Go fullscreen
    with bpy.context.temp_override(area=node_area, region=window_region):
        bpy.ops.screen.screen_full_area(use_hide_panels=True)

    # Frame all nodes (re-find area after fullscreen)
    for area in bpy.context.screen.areas:
        if area.type == 'NODE_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    with bpy.context.temp_override(area=area, region=region):
                        bpy.ops.node.view_all()
                    break
            break

    # Screenshot
    path = os.path.join(tempfile.gettempdir(), f"node_graph_{ng.name}.png")
    bpy.ops.screen.screenshot(filepath=path)

    # Exit fullscreen
    for area in bpy.context.screen.areas:
        if area.type == 'NODE_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    with bpy.context.temp_override(area=area, region=region):
                        bpy.ops.screen.screen_full_area(use_hide_panels=True)
                    break
            break

    return path
