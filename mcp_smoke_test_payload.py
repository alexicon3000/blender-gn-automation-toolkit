"""MCP-first smoke test payload for Blender Geometry Nodes toolkit.

Copy the contents of this file into your MCP `execute_blender_code` call.
It assumes Blender MCP is already connected to a running Blender session.
"""

import json
import os
import textwrap
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

MERMAID_PLAN = textwrap.dedent(
    """
    flowchart LR
      gi["GroupInput"] -->|Geometry| n1["MeshToPoints"]
      n2["MeshGrid"] -->|Mesh| n1
      n1 -->|Points| n3["InstanceOnPoints"]
      n4["MeshCone"] -->|Mesh| n3
      n3 -->|Geometry| go["GroupOutput"]
    """
).strip()

NODE_SETTINGS = {
    "n2": {"Vertices X": 10, "Vertices Y": 10, "Size X": 5.0, "Size Y": 5.0},
    "n4": {"Vertices": 32, "Radius Top": 0.0, "Radius Bottom": 0.5, "Depth": 1.5},
    "n3": {"Scale": 0.5},
}

OBJECT_NAME = "MCP_Smoke_Object"
MODIFIER_NAME = "MCP_Smoke_Mod"

print("Running Mermaid smoke test via MCP session...", flush=True)
build_result = mermaid_to_blender(
    OBJECT_NAME,
    MODIFIER_NAME,
    MERMAID_PLAN,
    node_settings=NODE_SETTINGS,
)

if not build_result.get("success", False):
    print("Build errors detected:")
    for err in build_result.get("errors", []):
        print(f"  - {err}")
    raise SystemExit(1)

print("Graph built successfully; running validation...", flush=True)
validation = full_geo_nodes_validation(OBJECT_NAME, MODIFIER_NAME, capture_screenshot=False)
print_validation_report(validation)

summary = {
    "build_success": build_result.get("success", False),
    "validation_status": validation.get("status"),
    "issues": validation.get("issues", []),
    "graph_nodes": validation.get("graph", {}).get("node_count"),
    "graph_links": validation.get("graph", {}).get("link_count"),
    "metrics": validation.get("metrics", {}),
}

print("SMOKE_TEST_SUMMARY")
print(json.dumps(summary, indent=2))

if validation.get("status") != "VALID":
    raise SystemExit(2)

print("Smoke test completed without issues.", flush=True)
