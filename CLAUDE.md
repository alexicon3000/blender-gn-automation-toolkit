# Geometry Nodes MCP Workflow

This project provides tools for creating and validating Blender Geometry Nodes via Claude Code and the Blender MCP.

## Quick Start

At the start of any geometry nodes session, load the validation toolkit:

```python
# Read and execute the loader
exec(open("/Users/alexanderporter/Documents/_DEV/Geo Nodes MCP/geo_nodes_mcp/loader.py").read().split("LOADER_CODE = '''")[1].split("'''")[0])
```

Or use the Blender MCP to read and execute the loader code.

## Reference Data

### Node Catalogue
- **File:** `geometry_nodes_min_4_4.json`
- **Version:** Blender 4.4
- **Contains:** 202 geometry node definitions with inputs/outputs and socket types

### Socket Compatibility
- **File:** `socket_compat.csv`
- **Contains:** 58 allowed socket type pairs for link validation

**Important:** If using a different Blender version, socket names may differ. Run `check_catalogue_version("4.4")` to verify compatibility.

## Workflow

### 1. Build Geometry Nodes

When creating nodes, use safe helpers:

```python
# Get output by TYPE not index (avoids wrong socket errors)
vector_out = get_output_by_type(random_node, 'VECTOR')

# Validate links immediately
safe_link(node_group, from_socket, to_socket)  # Raises if invalid
```

### 2. Validate

After building, always validate:

```python
result = full_geo_nodes_validation("ObjectName", "ModifierName")

# result contains:
# - status: "VALID" or "ISSUES_FOUND" or "ERROR"
# - graph: {node_count, link_count, invalid_links, issues}
# - metrics: {vertex_count, min_z, max_z, ground_contact}
# - issues: [list of all problems]
# - screenshot_path: path to workspace screenshot
```

### 3. Visual Inspection

The validation automatically:
- Switches to "MCP Validation" workspace
- Configures 2 viewports (perspective + front ortho)
- Frames all nodes in node editor
- Takes a full screenshot

For detailed node graph inspection:
```python
path = capture_node_graph("ObjectName", "ModifierName")
# Returns path to fullscreen node graph screenshot
```

## Available Functions

| Function | Purpose |
|----------|---------|
| `full_geo_nodes_validation(obj, mod)` | Complete validation with screenshot |
| `capture_node_graph(obj, mod)` | Fullscreen node graph screenshot |
| `validate_graph_structure(node_group)` | Check for invalid links |
| `validate_geometry_metrics(obj)` | Check ground contact, bounds |
| `safe_link(ng, from_sock, to_sock)` | Create link with validation |
| `get_output_by_type(node, type)` | Find socket by type not index |
| `switch_to_mcp_workspace()` | Switch to validation workspace |
| `check_catalogue_version(ver)` | Verify Blender version match |

## Common Mistakes to Avoid

1. **Wrong socket index:** Use `get_output_by_type()` instead of `outputs[2]`
2. **Invalid links:** Always use `safe_link()` or check `link.is_valid`
3. **Local Space on transforms:** Explicitly set `Local Space = False` for world-space translation
4. **Visual-only validation:** Always run numerical checks, don't trust screenshots alone
5. **Unchecked defaults:** Audit node parameters after creation

## Regenerating the Catalogue

If using a new Blender version, regenerate the catalogue:

1. Open Blender with the target version
2. Run `GeoNodes_Exporter_BlenderScript.txt` in Blender's scripting workspace
3. Update `geometry_nodes_min_4_4.json` with the output
4. Rename file to match version (e.g., `geometry_nodes_min_4_5.json`)

## Files

```
geo_nodes_mcp/
├── __init__.py      # Package marker
├── loader.py        # Code to inject into Blender
├── validator.py     # Validation functions (standalone)
└── workspace.py     # Workspace management (standalone)

geometry_nodes_min_4_4.json  # Node catalogue
socket_compat.csv            # Socket compatibility matrix
```
