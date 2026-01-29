# MCP Payload Scripts

This directory contains scripts for automating Blender MCP operations. Each script generates Python code that runs inside Blender via the MCP `execute_blender_code` tool.

## Quick Reference

| Script | Purpose | When to Use |
|--------|---------|-------------|
| `frame_validation_payload.py` | Full pipeline: build → settings → validate → frames → export | Testing frame support end-to-end |
| `capture_smoke_test_payload.py` | Debug screenshot capture | When `capture_node_graph()` returns None |
| `merge_smoke_test_payload.py` | Test incremental merge mode | Validating `merge_existing=True` behavior |
| `field_mismatch_test_payload.py` | Verify field compatibility checks | Confirming field guards are active |
| `export_roundtrip_test.py` | Test build → export → rebuild | Verifying graph serialization |
| `batch_export_catalogues.py` | Export catalogues for multiple Blender versions | Updating reference data |
| `verify_supports_field.py` | Check field support flags in catalogue | After catalogue regeneration |
| `mcp_smoke_test_payload.py` | MCP-first smoke test | Quick validation of toolkit + MCP connection |
| `smoke_test_mermaid.py` | Headless Blender smoke test | CI/batch testing without MCP |

---

## Scripts

### frame_validation_payload.py

**Purpose:** Complete frame validation pipeline using incremental MCP steps.

**Why incremental?** Blender 5.0.1 crashes when large scripts set Distribute Points inputs during build. This script works around that by:
1. Building the graph (nodes + links only)
2. Applying node settings in a separate call
3. Validating the result
4. Applying frames
5. Exporting and capturing screenshots

**Usage:**
```bash
# Run with default alias
python scripts/frame_validation_payload.py

# Specify MCP alias
python scripts/frame_validation_payload.py --alias my-blender

# Skip session notes update
python scripts/frame_validation_payload.py --skip-log
```

**Environment Variables:**
- `MCP_SESSION_NOTES` — Override session notes path (default: `_archive/session_notes_YYYYMMDD.md`)

**Output:**
- Screenshot in `_archive/frame_validation_nodes_YYYYMMDD_HHMMSS.png`
- Log in `_archive/frame_validation_payload.log`
- Entry appended to session notes

---

### capture_smoke_test_payload.py

**Purpose:** Debug screenshot capture issues by inspecting Blender's screen state.

**When to use:**
- `capture_node_graph()` returns `None`
- Screenshots aren't being saved
- Need to verify workspace/area configuration

**Usage:**
```bash
# Print the payload (for inspection)
python scripts/capture_smoke_test_payload.py

# Execute via MCP
uvx blender-mcp call blender execute_blender_code \
  --params "$(python3 scripts/capture_smoke_test_payload.py)"
```

**Output:**
- Prints active screen areas and space types
- Attempts `capture_node_graph()`
- Falls back to `bpy.ops.screen.screenshot()` if primary fails
- Reports final capture path

---

### merge_smoke_test_payload.py

**Purpose:** Test incremental graph updates using merge mode.

**What it tests:**
- `build_graph_from_json(..., merge_existing=True)`
- Diff summary generation (nodes added/updated/removed)
- Link rewiring behavior

**Usage:**
```bash
# Print payload for MCP execution
python scripts/merge_smoke_test_payload.py
```

Copy the output into `execute_blender_code`.

---

### field_mismatch_test_payload.py

**Purpose:** Verify that field compatibility guards are active.

**Expected behavior:** Should fail with a field-compatibility error when connecting a field output to a non-field input.

**Usage:**
```bash
python scripts/field_mismatch_test_payload.py
```

Copy into `execute_blender_code`. Expect preflight to reject the graph.

---

### export_roundtrip_test.py

**Purpose:** Test graph serialization fidelity.

**What it tests:**
1. Build a graph from `graph_json`
2. Export the graph to JSON
3. Rebuild from the export
4. Verify the result matches

**Usage:**
```bash
# Run inside Blender (not via MCP)
blender --background --python scripts/export_roundtrip_test.py
```

---

### batch_export_catalogues.py

**Purpose:** Export node catalogues for multiple Blender versions.

**Usage:**
```bash
# Requires Blender to be running
python scripts/batch_export_catalogues.py
```

Outputs to `reference/geometry_nodes_complete_X_Y.json`.

---

### verify_supports_field.py

**Purpose:** Verify field support flags in a catalogue file.

**Usage:**
```bash
python scripts/verify_supports_field.py reference/geometry_nodes_complete_5_0.json
```

Reports count of nodes/sockets with `supports_field: true`.

---

### mcp_smoke_test_payload.py

**Purpose:** MCP-first smoke test for the toolkit.

**What it tests:**
- Toolkit loads correctly via MCP
- `graph_json` builds nodes and links
- Group Output is properly connected
- Validation pipeline works end-to-end

**Usage:**
```bash
# Copy contents into execute_blender_code MCP call
cat scripts/mcp_smoke_test_payload.py
```

Uses a dedicated `MCP_Smoke_Test` collection to isolate test objects.

---

### smoke_test_mermaid.py

**Purpose:** Headless Blender smoke test (no MCP required).

**What it tests:**
- Same as `mcp_smoke_test_payload.py` but runs directly in Blender
- Useful for CI/CD or batch testing

**Usage:**
```bash
blender --background --python scripts/smoke_test_mermaid.py
```

**Note:** Expects `toolkit.py` to be in the parent directory. Update `REPO_ROOT` if running from a different location.

---

## Writing New Payloads

### Template

```python
#!/usr/bin/env python3
"""Brief description of what this payload does."""

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
# Your Blender code here
import bpy
print("Hello from Blender!", bpy.app.version_string)
"""

if __name__ == "__main__":
    print(payload())
```

### Best Practices

1. **Keep payloads small** — Split into multiple steps if > 50 lines
2. **Always load toolkit first** — Use the `COMMON` preamble
3. **Print progress markers** — `print("[step-name] doing X...")` helps debugging
4. **Handle failures gracefully** — Use try/except, log errors
5. **Document workarounds** — If avoiding a crash, explain why in comments

---

## Debugging Tips

### Payload isn't running

1. Check MCP connection: `uvx blender-mcp list`
2. Verify Blender is running with addon enabled
3. Try a simple ping: `execute_blender_code` with `print("pong")`

### Script crashes Blender

1. Split into smaller chunks
2. Check for known problematic nodes (see docs/AGENT_GUIDE.md)
3. Apply node settings in a separate step from graph building

### Screenshot missing

1. Run `capture_smoke_test_payload.py` to inspect screen state
2. Call `switch_to_mcp_workspace()` before capture
3. Try the fallback: `bpy.ops.screen.screenshot(filepath=path, full=False)`
