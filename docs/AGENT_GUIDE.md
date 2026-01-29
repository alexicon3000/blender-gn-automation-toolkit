# Agent Guide — Geometry Nodes MCP Toolkit

> **Purpose:** This document tells any LLM agent how to operate the toolkit, run MCP payloads, and avoid known pitfalls. Read this first when starting a new session.

## Quick Start Checklist

Before doing any work:

1. **Verify Blender is running** with MCP addon enabled
2. **Load the toolkit** via `exec(open("toolkit.py").read())`
3. **Health-check MCP**: `uvx blender-mcp call blender get_scene_info` should return the scene name; if it fails, relaunch Blender via `./blender-launcher.sh`.
3. **Check the handoff notes** in `_archive/session_notes_YYYYMMDD.md` for recent context
4. **Run tests** if you've made code changes: `python3 -m pytest tests/ -q`

---

## Session Workflow

### 1. Launch Blender

Use the repo's launcher script:

```bash
./blender-launcher.sh
```

This:
- Reads the Blender path from `blender_mcp_path.txt`
- Starts with `--factory-startup` for a clean environment
- Enables the `blender_mcp` addon automatically
- Optionally loads `_archive/MCP_Testing_5.0.blend` (override with `MCP_SCENE=/path/to/file.blend`)

**First-time setup:** If you see cache permission errors, run `uvx blender-mcp` once *outside* the sandbox to download dependencies:
```bash
rm -f ~/.cache/uv/sdists-v9/.git  # Clear stale cache if needed
uvx blender-mcp  # Downloads and caches the package
```

### 2. Load the Toolkit

Every MCP payload should start with:

```python
import os
from pathlib import Path

REPO_ROOT = Path("/Users/alexanderporter/Documents/_DEV/Geo Nodes MCP")
TOOLKIT_PATH = REPO_ROOT / "toolkit.py"

# Set environment for catalogue/socket compat loading
os.environ.setdefault("GN_MCP_SOCKET_COMPAT_PATH", str(REPO_ROOT / "reference" / "socket_compat.csv"))
os.environ.setdefault("GN_MCP_CATALOGUE_PATH", str(REPO_ROOT / "reference" / "geometry_nodes_complete_5_0.json"))

with open(TOOLKIT_PATH, "r", encoding="utf-8") as fh:
    code = compile(fh.read(), str(TOOLKIT_PATH), "exec")
exec(code, globals())
```

The toolkit prints available functions on load. Verify you see the banner.

### 3. Build Graphs Incrementally

**Critical:** Split work into multiple small MCP calls. Large monolithic scripts crash Blender 5.0.1.

Stay in the **build loop** (add_node → auto_link → describe_node_group) while constructing the graph. Only when describe_node_group reports no warnings should you enter the **evaluation loop** (run MCP validation, capture screenshots, log results).

**Good pattern:**
```
Step 1: build_graph_from_json()  → creates nodes and links
Step 2: set_node_input()         → applies input values
Step 3: _apply_frames()          → adds visual organization
Step 4: full_geo_nodes_validation() → validates result
Step 5: capture_node_graph()     → screenshots
```

**Bad pattern:**
```
# DON'T: One giant script that does everything
build_graph_from_json(..., node_settings={...})  # May crash!
```

See `scripts/frame_validation_payload.py` for the reference implementation. Run `python3 scripts/frame_validation_payload.py` to emit a single payload you can paste into the MCP sidebar’s `execute_blender_code` tool; pass `--mode cli` only if the `uvx blender-mcp` wrapper is working.

### 4. Validate Connectivity

Before running heavy operations, ping Blender:

```python
# Quick health check
import bpy
print("Blender version:", bpy.app.version_string)
```

If this fails, Blender needs a restart.

### 5. Log Results

After successful runs, update session notes:

```bash
# Automatic (for frame validation)
python3 scripts/frame_validation_payload.py  # copy emitted payload into MCP and run once

# Manual entry in _archive/session_notes_YYYYMMDD.md
```

---

## Crash Recovery

If Blender crashes mid-session:

1. **Ask user to restart Blender** via `./blender-launcher.sh`
2. **Wait for confirmation** that Blender is back online
3. **Reload toolkit:** `exec(open("toolkit.py").read())`
4. **Resume from last confirmed step** — don't repeat completed work
5. **Log the incident** in session notes with error context

If crashes persist after restart:
- Try `blender --factory-startup` for a completely clean state
- Check if the crash correlates with specific node types or settings
- Consider splitting the payload into even smaller chunks

---

## Known Quirks & Workarounds

### Node Settings That Crash Blender

| Node | Problematic Input | Workaround |
|------|-------------------|------------|
| `GeometryNodeDistributePointsOnFaces` | Any input during build | Apply settings in a separate MCP call *after* `build_graph_from_json()` |

### Frame Nodes

- **`frame.text` requires a Text datablock**, not a string. The toolkit stores text in a custom property `frame["description"]` instead.
- **Node dimensions aren't available** until the UI updates. The toolkit uses estimates (150x150px).
- **Re-applying frames** clears previously managed frames first (via `_FRAME_ID_PROP` marker).

### Screenshot Capture

- `capture_node_graph()` may return `None` if Blender is in fullscreen or the node editor isn't visible
- The toolkit includes retry logic, but if capture fails:
  1. Call `switch_to_mcp_workspace()` first
  2. Call `frame_object_in_viewport(obj_name)` to set up the view
  3. Retry the capture
  4. Fallback: `bpy.ops.screen.screenshot(filepath=path, full=False)`

### Socket Names & Node IDs

- **Always use names, not indices:** `node.inputs["Geometry"]` not `node.inputs[0]`.
- Socket names vary by Blender version — resolve them with `scripts/query_node_metadata.py` instead of grepping the catalogue.
- Blender 5.x exposes many math/utility helpers as **`ShaderNode*`** even inside Geometry Nodes (Combine/Separate/Math, Noise Texture, etc.). Trust the metadata CLI/alias map when it tells you the identifier; do **not** try to force a `FunctionNode*` name that doesn’t exist.

---

## File Reference

| File | Purpose |
|------|---------|
| `toolkit.py` | Single source of truth for all functions |
| `GUIDE.md` | Toolkit API reference and workflow options |
| `WORKFLOW.md` | LLM checklist (22 rules) and Mermaid conventions |
| `reference/geometry_nodes_complete_5_0.json` | Node catalogue (297 nodes) |
| `reference/socket_compat.csv` | Allowed socket type pairs |
| `_archive/session_notes_YYYYMMDD.md` | Daily session logs |
| `scripts/` | MCP payload scripts (see scripts/README.md) |
| `tests/` | pytest test suite |

---

## MCP Payload Execution

### Via CLI

```bash
# Frame validation (emit payload for VS Code)
python3 scripts/frame_validation_payload.py

# Optional legacy CLI mode (only if the STDIO bridge is healthy)
python3 scripts/frame_validation_payload.py --mode cli --alias blender

# Capture debugging
uvx blender-mcp call blender execute_blender_code --params "$(python3 scripts/capture_smoke_test_payload.py)"
```

### Via Direct MCP Call

```python
# In your MCP client
result = await client.call_tool(
    "execute_blender_code",
    {"code": payload_code, "user_prompt": "Build node graph"}
)
```

---

## Testing

Run all tests (no Blender required):

```bash
cd /Users/alexanderporter/Documents/_DEV/Geo Nodes MCP
python3 -m pytest tests/ -v
```

Current coverage:
- `test_catalogue.py` — catalogue loading, cache invalidation
- `test_preflight.py` — graph validation
- `test_mermaid.py` — Mermaid parsing and type resolution
- `test_diff.py` — incremental merge logic
- `test_frames.py` — frame creation, export, auto-framing

---

## Session Handoff

At the end of a session, update `_archive/session_notes_YYYYMMDD.md` with:

1. **What worked** — successful builds, payloads, screenshots
2. **What failed** — crashes, bugs, workarounds discovered
3. **What's next** — pending tasks for the next session

This ensures the next agent (or human) knows exactly where to pick up.

---

## Common Tasks

### Build a Node Graph from Mermaid

```python
mermaid_graph = '''
flowchart LR
  n1["MeshGrid"] -->|Mesh| n2["MeshToPoints"]
  n2 -->|Points| n3["InstanceOnPoints"]
  n4["MeshCone"] -->|Mesh| n3
  n3 -->|Instances| go["GroupOutput"]
'''
result = mermaid_to_blender("MyObject", "MyModifier", mermaid_graph)
print_validation_report(result)
```

### Read Back an Existing Graph

```python
export = export_modifier_to_json("MyObject", "MyModifier")
print(json.dumps(export["graph_json"], indent=2))
```

### Add Frames for Visual Organization

```python
# Manual frames
frames = [
    {"id": "inputs", "label": "Mesh Inputs", "nodes": ["grid", "cone"], "color": [0.2, 0.4, 0.8, 1.0]}
]
errors = []
_apply_frames(node_group, node_map, frames, errors)

# Or auto-generate
frames = auto_frame_graph(node_group, strategy="connectivity")
```

### Validate a Build

```python
result = full_geo_nodes_validation("MyObject", "MyModifier", capture_screenshot=True)
print_validation_report(result)
# result["screenshot_path"] has the image location
```
