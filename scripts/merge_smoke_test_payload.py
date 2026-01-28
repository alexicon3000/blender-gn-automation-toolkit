"""MCP-first merge-mode smoke test payload for Blender Geometry Nodes toolkit.

Copy the contents of this file into your MCP `execute_blender_code` call.
It assumes Blender MCP is already connected to a running Blender session.

This test validates:
1. Baseline graph_json builds nodes and links
2. merge_existing diff updates apply without clearing
3. remove_extras removes nodes/links not in the updated JSON
4. diff_summary reports created/updated/removed nodes and links
"""

import json
import os
from pathlib import Path

REPO_ROOT = Path(os.environ.get("GN_MCP_BASE_PATH", "/Users/alexanderporter/Documents/_DEV/Geo Nodes MCP"))
TOOLKIT_PATH = Path(os.environ.get("GN_MCP_TOOLKIT_PATH", REPO_ROOT / "toolkit.py"))

try:
    import bpy  # type: ignore
    blender_version = f"{bpy.app.version[0]}.{bpy.app.version[1]}"
except Exception:
    blender_version = "5.0"

catalogue_filename = f"geometry_nodes_complete_{blender_version.replace('.', '_')}.json"
socket_compat_filename = f"socket_compat_{blender_version.replace('.', '_')}.csv"

if "GN_MCP_SOCKET_COMPAT_PATH" not in os.environ:
    os.environ["GN_MCP_SOCKET_COMPAT_PATH"] = str(REPO_ROOT / "reference" / socket_compat_filename)
if "GN_MCP_CATALOGUE_PATH" not in os.environ:
    os.environ["GN_MCP_CATALOGUE_PATH"] = str(REPO_ROOT / "reference" / catalogue_filename)

with open(TOOLKIT_PATH, "r", encoding="utf-8") as fh:
    code = compile(fh.read(), str(TOOLKIT_PATH), "exec")
exec(code, globals())

# Use a dedicated collection for smoke tests (safe - doesn't destroy user's scene)
SMOKE_TEST_COLLECTION = "MCP_Merge_Smoke_Test"
OBJECT_NAME = "MCP_Merge_Object"
MODIFIER_NAME = "MCP_Merge_Mod"

# Clear any previous smoke test objects
cleared = clear_collection(SMOKE_TEST_COLLECTION)
if cleared:
    print(f"Cleared {cleared} objects from {SMOKE_TEST_COLLECTION} collection")

BASE_GRAPH_JSON = {
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
        {"from": "instance", "from_socket": "Instances", "to": "__GROUP_OUTPUT__", "to_socket": "Geometry"},
    ],
    "node_settings": {
        "grid": {"Vertices X": 10, "Vertices Y": 10, "Size X": 5.0, "Size Y": 5.0},
        "cone": {"Vertices": 16, "Radius Top": 0.0, "Radius Bottom": 0.3, "Depth": 1.2},
        "instance": {"Scale": [0.5, 0.5, 0.5]},
    },
}

MERGE_GRAPH_JSON = {
    "nodes": [
        {"id": "grid", "type": "GeometryNodeMeshGrid"},
        {"id": "to_points", "type": "GeometryNodeMeshToPoints"},
        {"id": "instance", "type": "GeometryNodeInstanceOnPoints"},
        {"id": "cube", "type": "GeometryNodeMeshCube"},
    ],
    "links": [
        {"from": "grid", "from_socket": "Mesh", "to": "to_points", "to_socket": "Mesh"},
        {"from": "to_points", "from_socket": "Points", "to": "instance", "to_socket": "Points"},
        {"from": "cube", "from_socket": "Mesh", "to": "instance", "to_socket": "Instance"},
        {"from": "instance", "from_socket": "Instances", "to": "__GROUP_OUTPUT__", "to_socket": "Geometry"},
    ],
    "node_settings": {
        "grid": {"Vertices X": 6, "Vertices Y": 6, "Size X": 3.0, "Size Y": 3.0},
        "cube": {"Size": [0.4, 0.4, 0.4]},
        "instance": {"Scale": [0.25, 0.25, 0.25]},
    },
}

print("Running base graph_json build...", flush=True)
base_result = build_graph_from_json(
    OBJECT_NAME,
    MODIFIER_NAME,
    BASE_GRAPH_JSON,
    collection=SMOKE_TEST_COLLECTION,
)

if not base_result.get("success", False):
    print("Base build errors detected:")
    for err in base_result.get("errors", []):
        print(f"  - {err}")
    raise SystemExit(1)

print("Running merge graph_json update...", flush=True)
merge_result = build_graph_from_json(
    OBJECT_NAME,
    MODIFIER_NAME,
    MERGE_GRAPH_JSON,
    collection=SMOKE_TEST_COLLECTION,
    merge_existing=True,
    remove_extras=True,
)

if not merge_result.get("success", False):
    print("Merge build errors detected:")
    for err in merge_result.get("errors", []):
        print(f"  - {err}")
    raise SystemExit(2)

summary = {
    "base_success": base_result.get("success", False),
    "merge_success": merge_result.get("success", False),
    "diff_summary": merge_result.get("diff_summary"),
}

diff_summary = merge_result.get("diff_summary") or {}
expected_removed_nodes = {"cone"}
expected_removed_links = {
    ("cone", "Mesh", "instance", "Instance"),
}

removed_nodes = set(diff_summary.get("nodes_to_remove", []))
removed_links = set(tuple(link) for link in diff_summary.get("links_to_remove", []))

if not expected_removed_nodes.issubset(removed_nodes):
    print("\nFAILED: remove_extras did not remove expected nodes")
    print("Expected:", expected_removed_nodes)
    print("Actual:", removed_nodes)
    raise SystemExit(3)

if not expected_removed_links.issubset(removed_links):
    print("\nFAILED: remove_extras did not remove expected links")
    print("Expected:", expected_removed_links)
    print("Actual:", removed_links)
    raise SystemExit(3)

print("\nMERGE_SMOKE_TEST_SUMMARY")
print(json.dumps(summary, indent=2))

if not merge_result.get("diff_summary"):
    print("\nFAILED: diff_summary missing from merge result")
    raise SystemExit(3)

print("\nMerge smoke test PASSED!", flush=True)
