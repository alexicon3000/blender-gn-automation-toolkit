"""MCP payload to validate field mismatch guarding.

Run via Blender MCP execute_blender_code.
This intentionally wires a field output into a non-field input and
expects the preflight/build to fail.
"""

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

OBJECT_NAME = "MCP_Field_Mismatch_Object"
MODIFIER_NAME = "MCP_Field_Mismatch_Mod"
TEST_COLLECTION = "MCP_Field_Mismatch_Test"

cleared = clear_collection(TEST_COLLECTION)
if cleared:
    print(f"Cleared {cleared} objects from {TEST_COLLECTION} collection")

# Intentional field mismatch:
# GeometryNodeMeshToPoints.Points (field) -> GeometryNodeMeshGrid.Size X (non-field input)
GRAPH_JSON = {
    "nodes": [
        {"id": "grid", "type": "GeometryNodeMeshGrid"},
        {"id": "to_points", "type": "GeometryNodeMeshToPoints"},
    ],
    "links": [
        {"from": "to_points", "from_socket": "Points", "to": "grid", "to_socket": "Size X"},
    ],
}

print("Running field mismatch test via MCP session...", flush=True)
build_result = build_graph_from_json(
    OBJECT_NAME,
    MODIFIER_NAME,
    GRAPH_JSON,
    collection=TEST_COLLECTION,
)

if build_result.get("success", False):
    print("\nFAILED: Field mismatch was not blocked!")
    raise SystemExit(2)

print("\nExpected failure detected.")
print("Errors:")
for err in build_result.get("errors", []):
    print(f"  - {err}")

print("\nField mismatch guard PASSED.", flush=True)
