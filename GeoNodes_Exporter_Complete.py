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
def _infer_supports_field(sock):
    if hasattr(sock, "supports_field"):
        return bool(getattr(sock, "supports_field"))
    display_shape = getattr(sock, "display_shape", "")
    return display_shape in {"DIAMOND", "DIAMOND_DOT"}


def extract_socket_info(sock):
    """Extract minimal socket information from a socket instance."""
    return {
        "name": sock.name,
        "idname": getattr(sock, "bl_idname", sock.__class__.__name__),
        "type": sock.type,  # VECTOR, FLOAT, INT, etc.
        "is_output": sock.is_output,
        "supports_field": _infer_supports_field(sock),
    }


def extract_socket_info_from_node(node):
    """Extract socket info from a node instance."""
    return {
        "inputs": [extract_socket_info(s) for s in node.inputs],
        "outputs": [extract_socket_info(s) for s in node.outputs],
    }


def extract_node_properties(node):
    """Extract enum/dropdown properties from a node.

    Returns a dict mapping property name to property info including:
    - type: 'enum' for enum properties
    - options: list of valid option identifiers
    - default: the default value
    - description: property description if available
    """
    props = {}

    # Skip these internal/visual properties that aren't useful for graph building
    skip_props = {
        'bl_idname', 'bl_label', 'bl_description', 'bl_icon', 'bl_width_default',
        'bl_width_min', 'bl_width_max', 'bl_height_default', 'bl_height_min',
        'bl_height_max', 'bl_static_type', 'color', 'height', 'hide', 'label',
        'location', 'mute', 'name', 'parent', 'select', 'show_options',
        'show_preview', 'show_texture', 'type', 'use_custom_color', 'width',
        'width_hidden', 'dimensions', 'internal_links', 'inputs', 'outputs',
        'rna_type', 'is_active_output', 'target', 'is_registered_node_type',
    }

    if not hasattr(node, 'bl_rna'):
        return props

    for prop in node.bl_rna.properties:
        prop_name = prop.identifier

        # Skip internal/visual properties
        if prop_name in skip_props or prop_name.startswith('bl_'):
            continue

        # Only extract ENUM type properties (dropdowns)
        if prop.type == 'ENUM':
            try:
                enum_items = prop.enum_items
                options = [item.identifier for item in enum_items]

                if options:  # Only include if there are actual options
                    prop_info = {
                        "type": "enum",
                        "options": options,
                    }

                    # Add default if available
                    if hasattr(prop, 'default') and prop.default:
                        prop_info["default"] = prop.default

                    # Add description if available
                    if prop.description:
                        prop_info["description"] = prop.description

                    props[prop_name] = prop_info
            except Exception:
                # Some properties may not have accessible enum_items
                pass

    return props


def instantiate_node(cls_name):
    """Instantiate a node in a temporary GeometryNodeTree and return (node, tree)."""
    nt = bpy.data.node_groups.new("_GN_MCP_EXPORT_", "GeometryNodeTree")
    node = nt.nodes.new(cls_name)
    return node, nt


def remove_node_tree(node_tree):
    """Safely remove a temporary node tree."""
    if node_tree and node_tree.name in bpy.data.node_groups:
        bpy.data.node_groups.remove(node_tree, do_unlink=True)


def can_instantiate_in_geo_nodes(cls_name):
    """Test if a node type works in Geometry Nodes context."""
    node_tree = None
    try:
        _node, node_tree = instantiate_node(cls_name)
        return True
    except Exception:
        return False
    finally:
        remove_node_tree(node_tree)

# -------------------------------------------------------------
# Extract node specification
# -------------------------------------------------------------
def extract_node_spec(cls_name, skipped_nodes):
    """Extract full specification for a node type."""
    node_tree = None
    try:
        node, node_tree = instantiate_node(cls_name)
        socket_payload = extract_socket_info_from_node(node)

        spec = {
            "identifier": cls_name,
            "label": node.bl_label if hasattr(node, 'bl_label') else node.name,
            "category": CATEGORY_MAP.get(cls_name, "UNSORTED"),
            "inputs": socket_payload["inputs"],
            "outputs": socket_payload["outputs"],
        }

        # Add bl_description if available (tooltip)
        if hasattr(node, 'bl_description') and node.bl_description:
            spec["description"] = node.bl_description

        # Extract enum properties (dropdowns like data_type, operation, etc.)
        props = extract_node_properties(node)
        if props:
            spec["properties"] = props

        return spec
    except Exception as e:
        skipped_nodes.append({"identifier": cls_name, "error": str(e)})
        return None
    finally:
        remove_node_tree(node_tree)

# -------------------------------------------------------------
# Main collection
# -------------------------------------------------------------
nodes = []
stats = {"GeometryNode": 0, "FunctionNode": 0, "ShaderNode": 0}
skipped = []

print("Scanning node types...")

# 1. Collect GeometryNode* types
for name in dir(bpy.types):
    if not name.startswith("GeometryNode") or name == "GeometryNode":
        continue
    cls = getattr(bpy.types, name)
    if not (inspect.isclass(cls) and issubclass(cls, bpy.types.Node)):
        continue

    spec = extract_node_spec(name, skipped)
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

    spec = extract_node_spec(name, skipped)
    if spec:
        nodes.append(spec)
        stats["FunctionNode"] += 1

print(f"  FunctionNode: {stats['FunctionNode']}")

# 3. Collect valid ShaderNode* types
for name in SHADER_NODES_TO_TEST:
    if can_instantiate_in_geo_nodes(name):
        spec = extract_node_spec(name, skipped)
        if spec:
            nodes.append(spec)
            stats["ShaderNode"] += 1

print(f"  ShaderNode: {stats['ShaderNode']}")

# Sort by identifier
nodes.sort(key=lambda d: d["identifier"])

# -------------------------------------------------------------
# Write output
# -------------------------------------------------------------
build_hash = getattr(bpy.app, "build_hash", "")
build_date = getattr(bpy.app, "build_date", "")
if isinstance(build_hash, (bytes, bytearray)):
    build_hash = build_hash.decode("utf-8", errors="ignore")
if isinstance(build_date, (bytes, bytearray)):
    build_date = build_date.decode("utf-8", errors="ignore")

output = {
    "blender_version": f"{bpy.app.version[0]}.{bpy.app.version[1]}.{bpy.app.version[2]}",
    "blender_version_string": getattr(bpy.app, "version_string", ""),
    "blender_build_hash": build_hash,
    "blender_build_date": build_date,
    "total_nodes": len(nodes),
    "breakdown": stats,
    "skipped": skipped,
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
print(f"  Skipped:      {len(skipped)}")
print(f"{'='*50}")
