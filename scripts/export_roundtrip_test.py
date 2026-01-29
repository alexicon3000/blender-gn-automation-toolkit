"""
Export Round-Trip Smoke Test

Tests that a graph can be built, exported, and rebuilt with fidelity.
Run via MCP execute_blender_code after loading the toolkit.

Usage (MCP):
    1. First load toolkit: exec(open("/path/to/toolkit.py").read())
    2. Then run this test: exec(open("/path/to/export_roundtrip_test.py").read())
"""

import json

# Test configuration
TEST_OBJ = "ExportTest"
TEST_MOD = "GeometryNodes"
TEST_COLLECTION = "MCP_Export_Test"

# Clear previous test artifacts
clear_collection(TEST_COLLECTION)

# Original graph_json to build
original_graph = {
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
        "grid": {"Vertices X": 5, "Vertices Y": 5, "Size X": 2.0, "Size Y": 2.0},
        "cone": {"Vertices": 16, "Radius Bottom": 0.3, "Depth": 0.8},
    },
}

print("=" * 60)
print("EXPORT ROUND-TRIP TEST")
print("=" * 60)

# Step 1: Build the original graph
print("\n[1] Building original graph...")
build_result = build_graph_from_json(
    TEST_OBJ, TEST_MOD, original_graph,
    clear_existing=True,
    collection=TEST_COLLECTION,
)
assert build_result["success"], f"Build failed: {build_result['errors']}"
print(f"    Built: {build_result['node_group_name']}")
print(f"    Nodes created: {len(build_result['nodes'])}")

# Step 2: Export the graph back to JSON
print("\n[2] Exporting graph to JSON...")
export_result = export_modifier_to_json(TEST_OBJ, TEST_MOD)
assert export_result["success"], f"Export failed: {export_result['error']}"
exported_graph = export_result["graph_json"]
print(f"    Exported {len(exported_graph['nodes'])} nodes")
print(f"    Exported {len(exported_graph['links'])} links")
print(f"    Settings for: {list(exported_graph['node_settings'].keys())}")

# Step 3: Verify structure matches
print("\n[3] Verifying structure...")
original_node_ids = {n["id"] for n in original_graph["nodes"]}
exported_node_ids = {n["id"] for n in exported_graph["nodes"]}
assert original_node_ids == exported_node_ids, f"Node IDs mismatch: {original_node_ids} vs {exported_node_ids}"
print(f"    Node IDs match: {original_node_ids}")

original_link_count = len(original_graph["links"])
exported_link_count = len(exported_graph["links"])
assert original_link_count == exported_link_count, f"Link count mismatch: {original_link_count} vs {exported_link_count}"
print(f"    Link count matches: {exported_link_count}")

# Step 4: Verify settings were captured
print("\n[4] Verifying settings...")
for node_id, original_settings in original_graph["node_settings"].items():
    exported_settings = exported_graph["node_settings"].get(node_id, {})
    for key, original_value in original_settings.items():
        exported_value = exported_settings.get(key)
        # Allow some float tolerance
        if isinstance(original_value, float) and isinstance(exported_value, float):
            assert abs(original_value - exported_value) < 0.001, f"{node_id}.{key}: {original_value} vs {exported_value}"
        else:
            assert exported_value == original_value, f"{node_id}.{key}: {original_value} vs {exported_value}"
        print(f"    {node_id}.{key}: {original_value} == {exported_value}")

# Step 5: Rebuild from exported JSON (on a new object)
print("\n[5] Rebuilding from exported JSON...")
REBUILT_OBJ = "ExportTest_Rebuilt"
rebuild_result = build_graph_from_json(
    REBUILT_OBJ, TEST_MOD, exported_graph,
    clear_existing=True,
    collection=TEST_COLLECTION,
)
assert rebuild_result["success"], f"Rebuild failed: {rebuild_result['errors']}"
print(f"    Rebuilt: {rebuild_result['node_group_name']}")

# Step 6: Export rebuilt and compare
print("\n[6] Comparing rebuilt graph...")
rebuilt_export = export_modifier_to_json(REBUILT_OBJ, TEST_MOD)
assert rebuilt_export["success"], f"Rebuilt export failed: {rebuilt_export['error']}"
rebuilt_graph = rebuilt_export["graph_json"]

# Compare node counts and link counts
assert len(rebuilt_graph["nodes"]) == len(exported_graph["nodes"]), "Node count changed after rebuild"
assert len(rebuilt_graph["links"]) == len(exported_graph["links"]), "Link count changed after rebuild"
print(f"    Round-trip preserved {len(rebuilt_graph['nodes'])} nodes, {len(rebuilt_graph['links'])} links")

print("\n" + "=" * 60)
print("EXPORT ROUND-TRIP TEST: PASSED")
print("=" * 60)

# Print the exported JSON for inspection
print("\n[Exported graph_json]:")
print(json.dumps(exported_graph, indent=2))
