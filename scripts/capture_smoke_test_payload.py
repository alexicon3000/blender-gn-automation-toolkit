"""Minimal MCP payload to verify capture_node_graph from the node editor."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

COMMON = f"""
import json, os
from pathlib import Path
REPO_ROOT = Path({str(REPO_ROOT)!r})
TOOLKIT_PATH = REPO_ROOT / "toolkit.py"
os.environ.setdefault("GN_MCP_SOCKET_COMPAT_PATH", str(REPO_ROOT / "reference" / "socket_compat.csv"))
os.environ.setdefault("GN_MCP_CATALOGUE_PATH", str(REPO_ROOT / "reference" / "geometry_nodes_complete_5_0.json"))
with open(TOOLKIT_PATH, "r", encoding="utf-8") as fh:
    code = compile(fh.read(), str(TOOLKIT_PATH), "exec")
exec(code, globals())
"""

def payload() -> str:
    return COMMON + """
import bpy
print("[capture-smoke] Active screen:", getattr(bpy.context, "screen", None))
for area in bpy.context.screen.areas:
    print(f"  area type={area.type} width={area.width} height={area.height}")
    for space in area.spaces:
        print(f"    space type={space.type}")
switch_to_mcp_workspace()
frame_object_in_viewport("MCP_Frame_Object", use_local_view=True)
path = capture_node_graph("MCP_Frame_Object", "MCP_Frame_Mod")
print("[capture-smoke] capture_node_graph returned:", path)
"""

if __name__ == "__main__":
    print(payload())
