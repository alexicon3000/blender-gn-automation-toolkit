"""MCP-first smoke test payload for Blender Geometry Nodes toolkit.

Copy the contents of this file into your MCP `execute_blender_code` call.
It assumes Blender MCP is already connected to a running Blender session.

This test validates:
1. Toolkit loads correctly
2. graph_json builds nodes and links
3. Group Output is properly connected
4. Node names display naturally (Grid, Mesh to Points, etc.)
5. Validation pipeline works end-to-end
"""

import json
import os
from pathlib import Path

REPO_ROOT = Path(os.environ.get("GN_MCP_BASE_PATH", "/Users/alexanderporter/Documents/_DEV/Geo Nodes MCP"))
TOOLKIT_PATH = Path(os.environ.get("GN_MCP_TOOLKIT_PATH", REPO_ROOT / "toolkit.py"))

if "GN_MCP_SOCKET_COMPAT_PATH" not in os.environ:
    os.environ["GN_MCP_SOCKET_COMPAT_PATH"] = str(REPO_ROOT / "reference" / "socket_compat.csv")
if "GN_MCP_CATALOGUE_PATH" not in os.environ:
    os.environ["GN_MCP_CATALOGUE_PATH"] = str(REPO_ROOT / "reference" / "geometry_nodes_complete_4_4.json")

with open(TOOLKIT_PATH, "r", encoding="utf-8") as fh:
    code = compile(fh.read(), str(TOOLKIT_PATH), "exec")
exec(code, globals())

# Use graph_json directly for precise control over Group I/O connections
GRAPH_JSON = {
    "nodes": [
        {"id": "grid", "type": "GeometryNodeMeshGrid"},
        {"id": "to_points", "type": "GeometryNodeMeshToPoints"},
        {"id": "instance", "type": "GeometryNodeInstanceOnPoints"},
        {"id": "cone", "type": "GeometryNodeMeshCone"},
    ],
    "links": [
        {"from": "grid", "from_socket": "Mesh", "to": "to_points", "to_socket": "Mesh"},
        {"from": "to_points", "from_socket": "Points", "to": "instance", "to_socket": "Points"},
        {"from": "cone", "from_socket": "Mesh", "to": "instance", "to_socket": "Instance"},
        # CRITICAL: Connect to Group Output using special __GROUP_OUTPUT__ ID
        {"from": "instance", "from_socket": "Instances", "to": "__GROUP_OUTPUT__", "to_socket": "Geometry"},
    ],
    "node_settings": {
        "grid": {"Vertices X": 10, "Vertices Y": 10, "Size X": 5.0, "Size Y": 5.0},
        "cone": {"Vertices": 32, "Radius Top": 0.0, "Radius Bottom": 0.5, "Depth": 1.5},
        # Scale is a vector input, not a float
        "instance": {"Scale": [0.5, 0.5, 0.5]},
    },
}

OBJECT_NAME = "MCP_Smoke_Object"
MODIFIER_NAME = "MCP_Smoke_Mod"

print("Running graph_json smoke test via MCP session...", flush=True)
build_result = build_graph_from_json(
    OBJECT_NAME,
    MODIFIER_NAME,
    GRAPH_JSON,
)

if not build_result.get("success", False):
    print("Build errors detected:")
    for err in build_result.get("errors", []):
        print(f"  - {err}")
    raise SystemExit(1)

print("Graph built successfully; running validation...", flush=True)
validation = full_geo_nodes_validation(OBJECT_NAME, MODIFIER_NAME, capture_screenshot=False)
print_validation_report(validation)

# Additional checks
import bpy
obj = bpy.data.objects.get(OBJECT_NAME)
ng = obj.modifiers.get(MODIFIER_NAME).node_group
group_output = ng.nodes.get("Group Output")
go_connected = any(link.to_node == group_output for link in ng.links)

print(f"\nGroup Output connected: {go_connected}")

# Show node names (should be natural Blender names, no labels)
print("\nNode names (should be natural Blender names):")
for node in ng.nodes:
    label_info = f" [label: '{node.label}']" if node.label else ""
    print(f"  {node.name}{label_info}")

summary = {
    "build_success": build_result.get("success", False),
    "validation_status": validation.get("status"),
    "group_output_connected": go_connected,
    "issues": validation.get("issues", []),
    "graph_nodes": validation.get("graph", {}).get("node_count"),
    "graph_links": validation.get("graph", {}).get("link_count"),
}

print("\nSMOKE_TEST_SUMMARY")
print(json.dumps(summary, indent=2))

# Fail if Group Output not connected or validation issues
if not go_connected:
    print("\nFAILED: Group Output not connected!")
    raise SystemExit(2)

if validation.get("status") != "VALID":
    print("\nFAILED: Validation issues detected!")
    raise SystemExit(2)

print("\nSmoke test PASSED!", flush=True)
