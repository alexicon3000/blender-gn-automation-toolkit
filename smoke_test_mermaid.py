#!/usr/bin/env python3
"""Headless Blender MCP smoke test for the Geometry Nodes toolkit."""

import json
import textwrap
from pathlib import Path

import bpy  # type: ignore

REPO_ROOT = Path(__file__).resolve().parent
TOOLKIT_PATH = REPO_ROOT / "toolkit.py"

# Load the toolkit into Blender's Python environment (mirrors in-Blender exec).
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

print("Running Mermaid smoke test via toolkit.py...", flush=True)
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
