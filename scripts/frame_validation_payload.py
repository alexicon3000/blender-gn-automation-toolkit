"""Frame-focused Blender MCP validation payload.

Run this via `execute_blender_code` to ensure frame metadata survives
the build/validation cycle and to capture a node-graph screenshot for
_archive diagnostics.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(os.environ.get("GN_MCP_BASE_PATH", "/Users/alexanderporter/Documents/_DEV/Geo Nodes MCP"))
TOOLKIT_PATH = Path(os.environ.get("GN_MCP_TOOLKIT_PATH", REPO_ROOT / "toolkit.py"))

if "GN_MCP_SOCKET_COMPAT_PATH" not in os.environ:
    os.environ["GN_MCP_SOCKET_COMPAT_PATH"] = str(REPO_ROOT / "reference" / "socket_compat.csv")
if "GN_MCP_CATALOGUE_PATH" not in os.environ:
    os.environ["GN_MCP_CATALOGUE_PATH"] = str(REPO_ROOT / "reference" / "geometry_nodes_complete_5_0.json")

with open(TOOLKIT_PATH, "r", encoding="utf-8") as fh:
    code = compile(fh.read(), str(TOOLKIT_PATH), "exec")
exec(code, globals())

COLLECTION = "MCP_Frame_Test"
OBJECT_NAME = "MCP_Frame_Object"
MODIFIER_NAME = "MCP_Frame_Mod"

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
SCREENSHOT_PATH = REPO_ROOT / "_archive" / f"frame_validation_nodes_{timestamp}.png"

# Clear any previous test objects
clear_collection(COLLECTION)

GRAPH_JSON = {
    "nodes": [
        {"id": "grid", "type": "GeometryNodeMeshGrid"},
        {"id": "distribute", "type": "GeometryNodeDistributePointsOnFaces"},
        {"id": "cube", "type": "GeometryNodeMeshCube"},
        {"id": "instance", "type": "GeometryNodeInstanceOnPoints"},
        {"id": "realize", "type": "GeometryNodeRealizeInstances"},
    ],
    "links": [
        {"from": "grid", "from_socket": "Mesh", "to": "distribute", "to_socket": "Mesh"},
        {"from": "distribute", "from_socket": "Points", "to": "instance", "to_socket": "Points"},
        {"from": "cube", "from_socket": "Mesh", "to": "instance", "to_socket": "Instance"},
        {"from": "instance", "from_socket": "Instances", "to": "realize", "to_socket": "Geometry"},
        {"from": "realize", "from_socket": "Geometry", "to": "__GROUP_OUTPUT__", "to_socket": "Geometry"},
    ],
    "node_settings": {
        "grid": {"Vertices X": 32, "Vertices Y": 32, "Size X": 4.0, "Size Y": 4.0},
        "distribute": {"Density Max": 5.0},
        "cube": {"Size": 0.3},
        "instance": {"Scale": [0.5, 0.5, 0.5]},
    },
    "frames": [
        {
            "id": "emit_points",
            "label": "Emit Points",
            "color": [0.2, 0.46, 0.84, 1.0],
            "nodes": ["grid", "distribute"],
            "text": "Controls surface sampling density",
        },
        {
            "id": "instance_block",
            "label": "Instance Shapes",
            "color": [0.88, 0.42, 0.25, 1.0],
            "nodes": ["cube", "instance", "realize"],
            "shrink": True,
            "text": "Instancing pipeline (cube → realize)",
        },
    ],
}

print("Building frame-focused graph via MCP session...", flush=True)
build_result = build_graph_from_json(
    OBJECT_NAME,
    MODIFIER_NAME,
    GRAPH_JSON,
    collection=COLLECTION,
)

if not build_result.get("success"):
    print("Build errors detected:")
    for err in build_result.get("errors", []):
        print(f"  - {err}")
    raise SystemExit(1)

print("Graph built; running validation...", flush=True)
validation = full_geo_nodes_validation(OBJECT_NAME, MODIFIER_NAME, capture_screenshot=False)
print_validation_report(validation)

if validation.get("status") != "VALID":
    print("Validation failed; aborting frame checks.")
    raise SystemExit(2)

import bpy  # noqa: E402  (requires Blender runtime)

obj = bpy.data.objects.get(OBJECT_NAME)
mod = obj.modifiers.get(MODIFIER_NAME) if obj else None
ng = mod.node_group if mod else None

if not ng:
    raise SystemExit("Node group not found after build")

frame_nodes = [node for node in ng.nodes if getattr(node, "bl_idname", "") == "NodeFrame"]
frame_specs = {spec["id"]: spec for spec in GRAPH_JSON.get("frames", [])}
id_to_name = {node_id: node.name for node_id, node in build_result.get("nodes", {}).items()}
frame_prop_key = globals().get("_FRAME_ID_PROP", "gn_mcp_frame_id")

def nodes_inside_frame(frame):
    parented = [node.name for node in ng.nodes if getattr(node, "parent", None) == frame]
    if parented:
        return parented

    contained = []
    for node in ng.nodes:
        if node == frame or getattr(node, "bl_idname", "") == "NodeFrame":
            continue
        width = getattr(node, "width", 140.0)
        height = getattr(node, "height", 100.0)
        center_x = node.location.x + width * 0.5
        center_y = node.location.y - height * 0.5
        if (frame.location.x <= center_x <= frame.location.x + frame.width and
                frame.location.y - frame.height <= center_y <= frame.location.y):
            contained.append(node.name)
    return contained

errors = []
print(f"Detected {len(frame_nodes)} frame nodes in Blender.")

for frame_id, spec in frame_specs.items():
    frame = next((node for node in frame_nodes if node.get(frame_prop_key, node.name) == frame_id), None)
    if not frame:
        errors.append(f"Frame '{frame_id}' was not created")
        continue

    expected_names = {id_to_name.get(nid, nid) for nid in spec.get("nodes", [])}
    actual_names = set(nodes_inside_frame(frame))
    missing = sorted(expected_names - actual_names)
    if missing:
        errors.append(f"Frame '{frame_id}' is missing nodes: {missing}")

    frame_info = {
        "id": frame_id,
        "label": frame.label,
        "color": tuple(getattr(frame, "color", (0, 0, 0))),
        "shrink": getattr(frame, "shrink", False),
        "description": frame.items().get("description") if hasattr(frame, "items") else None,
        "contained_nodes": sorted(actual_names),
    }
    print(json.dumps(frame_info, indent=2))

exported = export_modifier_to_json(OBJECT_NAME, MODIFIER_NAME)
frames_export = exported.get("frames", []) if isinstance(exported, dict) else []
print("\nExported frame specs:")
print(json.dumps(frames_export, indent=2))

switch_to_mcp_workspace()
frame_object_in_viewport(OBJECT_NAME, use_local_view=True)
capture_path = capture_node_graph(OBJECT_NAME, MODIFIER_NAME)

if capture_path and os.path.exists(capture_path):
    SCREENSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(capture_path, SCREENSHOT_PATH)
    print(f"Node graph screenshot saved to {SCREENSHOT_PATH}")
else:
    print("Node graph screenshot unavailable")

summary = {
    "validation_status": validation.get("status"),
    "frame_errors": errors,
    "frame_count": len(frame_nodes),
    "exported_frame_count": len(frames_export),
    "screenshot": str(SCREENSHOT_PATH if SCREENSHOT_PATH.exists() else ""),
}

print("\nFRAME_VALIDATION_SUMMARY")
print(json.dumps(summary, indent=2))

if errors:
    print("\nFrame validation detected issues.")
    raise SystemExit(3)

print("\nFrame validation PASSED!", flush=True)
