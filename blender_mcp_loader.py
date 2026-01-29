"""Enable the Blender MCP add-on and print diagnostic info.

This script is invoked by blender-launcher.sh via ``--python`` so that every
MCP session starts with the add-on enabled and the toolkit path on sys.path.
"""

import bpy
import addon_utils
import sys
from pathlib import Path

ADDON_MODULE = "blender_mcp"
REPO_ROOT = Path(__file__).resolve().parent
TOOLKIT_PATH = REPO_ROOT / "toolkit.py"

print("============================================================")
print(f"Blender version: {bpy.app.version_string} (build {bpy.app.build_hash})")
print("Launching Geometry Nodes MCP session...")
print("============================================================")

try:
    addon_utils.enable(ADDON_MODULE, default_set=True)
except Exception as exc:  # noqa: BLE001
    print(f"[WARN] Could not enable add-on '{ADDON_MODULE}': {exc}")

if ADDON_MODULE not in bpy.context.preferences.addons:
    raise RuntimeError(
        f"Add-on '{ADDON_MODULE}' not found. Install blender-mcp before using this launcher."
    )

# Make sure the toolkit is easy to load from the Text Editor / scripting console.
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

print("Setup complete. You can now exec toolkit.py inside Blender to start the MCP toolkit.")
