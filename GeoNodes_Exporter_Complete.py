"""
Complete Geometry Nodes Exporter for Blender 4.4+

Exports ALL node types valid in Geometry Nodes context:
- GeometryNode* (geometry operations)
- FunctionNode* (math, random, rotation, string, etc.)
- Valid ShaderNode* (Math, VectorMath, Mix, ColorRamp, etc.)

Usage:
1. Open Blender (4.4 or later)
2. Go to Scripting workspace
3. Create new text block, paste this script
4. Run script
5. Find output in ~/Downloads/geometry_nodes_complete_X_X.json
"""

import bpy
import inspect
import pathlib
import json

# -------------------------------------------------------------
# Configuration
# -------------------------------------------------------------
VERSION = f"{bpy.app.version[0]}_{bpy.app.version[1]}"
OUTPUT_FILE = pathlib.Path.home() / "Downloads" / f"geometry_nodes_complete_{VERSION}.json"

# ShaderNodes known to work in Geometry Nodes context
# (We test each one, but this is a hint list)
SHADER_NODES_TO_TEST = [
    'ShaderNodeMath',
    'ShaderNodeVectorMath',
    'ShaderNodeMix',
    'ShaderNodeMixRGB',
    'ShaderNodeSeparateXYZ',
    'ShaderNodeCombineXYZ',
    'ShaderNodeSeparateRGB',
    'ShaderNodeCombineRGB',
    'ShaderNodeSeparateHSV',
    'ShaderNodeCombineHSV',
    'ShaderNodeMapRange',
    'ShaderNodeClamp',
    'ShaderNodeValToRGB',  # Color Ramp
    'ShaderNodeRGBCurve',
    'ShaderNodeFloatCurve',
    'ShaderNodeVectorCurve',
    'ShaderNodeInvert',
    'ShaderNodeGamma',
    'ShaderNodeBrightContrast',
    'ShaderNodeHueSaturation',
]

# -------------------------------------------------------------
# Build Add-menu category map
# -------------------------------------------------------------
import nodeitems_builtins as nib

CATEGORY_MAP = {}
cats = getattr(nib, "_node_categories", None) \
        or getattr(nib, "node_categories_iter", lambda c: [])(bpy.context)

for cat in cats or []:
    try:
        for it in cat.items(bpy.context):
            idname = it["idname"] if isinstance(it, dict) else it.nodetype
            CATEGORY_MAP[idname] = cat.identifier
    except:
        pass

# -------------------------------------------------------------
# Socket payload (essential info only)
# -------------------------------------------------------------
def extract_socket_info(sock):
    """Extract minimal socket information."""
    return {
        "name": sock.name,
        "idname": getattr(sock, "bl_idname", sock.__class__.__name__),
        "type": sock.type,  # VECTOR, FLOAT, INT, etc.
        "is_output": sock.is_output,
        "supports_field": getattr(sock, "supports_field", False),
    }

# -------------------------------------------------------------
# Test if a node type can be instantiated in GeometryNodeTree
# -------------------------------------------------------------
def can_instantiate_in_geo_nodes(cls_name):
    """Test if a node type works in Geometry Nodes context."""
    try:
        nt = bpy.data.node_groups.new("_TEST_", "GeometryNodeTree")
        node = nt.nodes.new(cls_name)
        bpy.data.node_groups.remove(nt, do_unlink=True)
        return True
    except:
        try:
            bpy.data.node_groups.remove(nt, do_unlink=True)
        except:
            pass
        return False

# -------------------------------------------------------------
# Extract node specification
# -------------------------------------------------------------
def extract_node_spec(cls_name):
    """Extract full specification for a node type."""
    try:
        nt = bpy.data.node_groups.new("_TEST_", "GeometryNodeTree")
        node = nt.nodes.new(cls_name)

        spec = {
            "identifier": cls_name,
            "label": node.bl_label if hasattr(node, 'bl_label') else node.name,
            "category": CATEGORY_MAP.get(cls_name, "UNSORTED"),
            "inputs": [extract_socket_info(s) for s in node.inputs],
            "outputs": [extract_socket_info(s) for s in node.outputs],
        }

        # Add bl_description if available (tooltip)
        if hasattr(node, 'bl_description') and node.bl_description:
            spec["description"] = node.bl_description

        bpy.data.node_groups.remove(nt, do_unlink=True)
        return spec
    except Exception as e:
        try:
            bpy.data.node_groups.remove(nt, do_unlink=True)
        except:
            pass
        return None

# -------------------------------------------------------------
# Main collection
# -------------------------------------------------------------
nodes = []
stats = {"GeometryNode": 0, "FunctionNode": 0, "ShaderNode": 0}

print("Scanning node types...")

# 1. Collect GeometryNode* types
for name in dir(bpy.types):
    if not name.startswith("GeometryNode") or name == "GeometryNode":
        continue
    cls = getattr(bpy.types, name)
    if not (inspect.isclass(cls) and issubclass(cls, bpy.types.Node)):
        continue

    spec = extract_node_spec(name)
    if spec:
        nodes.append(spec)
        stats["GeometryNode"] += 1

print(f"  GeometryNode: {stats['GeometryNode']}")

# 2. Collect FunctionNode* types
for name in dir(bpy.types):
    if not name.startswith("FunctionNode") or name == "FunctionNode":
        continue
    cls = getattr(bpy.types, name)
    if not (inspect.isclass(cls) and issubclass(cls, bpy.types.Node)):
        continue

    spec = extract_node_spec(name)
    if spec:
        nodes.append(spec)
        stats["FunctionNode"] += 1

print(f"  FunctionNode: {stats['FunctionNode']}")

# 3. Collect valid ShaderNode* types
for name in SHADER_NODES_TO_TEST:
    if can_instantiate_in_geo_nodes(name):
        spec = extract_node_spec(name)
        if spec:
            nodes.append(spec)
            stats["ShaderNode"] += 1

print(f"  ShaderNode: {stats['ShaderNode']}")

# Sort by identifier
nodes.sort(key=lambda d: d["identifier"])

# -------------------------------------------------------------
# Write output
# -------------------------------------------------------------
output = {
    "blender_version": f"{bpy.app.version[0]}.{bpy.app.version[1]}.{bpy.app.version[2]}",
    "total_nodes": len(nodes),
    "breakdown": stats,
    "nodes": nodes
}

OUTPUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))

print(f"\n{'='*50}")
print(f"Exported {len(nodes)} nodes to:")
print(f"  {OUTPUT_FILE}")
print(f"\nBreakdown:")
print(f"  GeometryNode: {stats['GeometryNode']}")
print(f"  FunctionNode: {stats['FunctionNode']}")
print(f"  ShaderNode:   {stats['ShaderNode']}")
print(f"{'='*50}")
