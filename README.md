# Blender Geometry Nodes Automation Toolkit

Utilities and reference data for building Blender Geometry Nodes graphs through
LLM- or MCP-driven workflows. The repo packages a portable `toolkit.py` for
in-Blender use plus a `geo_nodes_mcp` module for agents or scripts that need to
load catalogues, validate socket compatibility, or snapshot node graphs.

You can drive it entirely via Mermaid + `graph_json`: sketch a flowchart, feed
it to `mermaid_to_blender()`, and the toolkit/builders do the rest—even if
you’re not using MCP. This makes it easy to pair any LLM (or your own scripts)
with Geometry Nodes automation.

**Key ideas**
- Plan visually: sketch Mermaid flow charts (with GroupInput/GroupOutput) so
  humans can sanity-check topology before executing anything.
- Catalog-driven safety: builders load Blender 5.0 node definitions and the
  socket compatibility matrix before linking, catching wrong directions or
  types early.
- Pre-flight validation: `build_graph_from_json()` now runs a fail-fast
  preflight checklist (node types, sockets, Group Output linkage, setting
  types) before touching Blender.
- Incremental merge support: set `merge_existing=True` to diff against existing
  graphs by JSON node ID, update settings, and rewire links without a full
  rebuild. Optional `remove_extras=True` removes nodes/links not in the JSON;
  the build result includes a `diff_summary` of changes.
- Full graph reporting: optional “full report” dumps nodes, sockets, defaults,
  and links to aid manual reconstruction when automation fails. You can pass
  `last_graph_json` and `last_diff_summary` to include recent merge context.

## Getting Started
1. Open Blender 5.0+ and run:
   ```python
   exec(open("/Users/alexanderporter/Documents/_DEV/Geo Nodes MCP/toolkit.py").read())
   ```
   This loads all helpers (Mermaid parsing, graph builders, validators) into the
   current Python session.
2. Plan graphs in Mermaid or `graph_json`, then call
   `mermaid_to_blender()` or `build_graph_from_json()` to instantiate the node
group. For incremental updates, call `build_graph_from_json(...,
merge_existing=True, remove_extras=True)` to diff and merge by node ID.
3. Run `full_geo_nodes_validation()` to capture screenshots and structural/
   metric reports. Pass `include_report=True` to include a full graph report.

## Catalogue Snapshot (Blender 5.0)
- **version_string:** 5.0.1
- **build_hash:** a3db93c5b259
- **build_date:** 2025-12-16
- **Complete catalogue:** `reference/geometry_nodes_complete_5_0.json`
- **Minimal catalogue:** `reference/geometry_nodes_min_5_0.json`
- **Socket compatibility:** `reference/socket_compat_5_0.csv`

**Field/random note:** In Blender 5.0 the default `FunctionNodeRandomValue` emits
fields (vectors). `Set Position.Offset` expects plain vectors, so set the node’s
data type to `FLOAT` (or capture the field) before wiring it.

## Documentation
- `GUIDE.md` – Hands-on quick start, helper catalog, project notes, and common
  pitfalls.
- `WORKFLOW.md` – MCP-centric process covering Mermaid rules, response format,
  and the 22-step checklist the LLM must satisfy before building.
- `reference/` – Blender 5.0 catalogue JSON and socket compatibility CSV (the
  files loader utilities rely on).

## Repository Layout
- `toolkit.py` – Single-file toolkit intended to be exec'd inside Blender.
- `geo_nodes_mcp/` – Installable module mirroring toolkit functionality for
  agents/servers.
- `reference/` – Source-of-truth catalogues generated from Blender exporters.
- `_archive/` – Legacy or other assets for internal reference (ignored by git).

## Contributing / Next Steps
High-level roadmap items live near the end of `GUIDE.md`. Briefly:
1. Regenerate catalogues so `supports_field` flags are accurate for field-aware
   validation (exporter now captures runtime values; refresh the catalogue to
   apply).
2. Expand node-setting validation using catalogue metadata (enum/mode rules).
3. Automate the LLM checklist in code so MCP workflows can fail fast before
   building.

## Status at a Glance
**Works today**
- Catalogue/socket loaders, Mermaid→graph_json parsing, graph builders, and
  validation helpers (`toolkit.py`, `geo_nodes_mcp/`).
- Pre-link safety checks (direction/type) using Blender 5.0 metadata.
- ✅ **MCP smoke tests pass (Blender 5.0)** (2026-01-29): graph_json workflow
  builds nodes, connects to Group Output, and validates under the 5.0 catalogue.

**Still to build/validate**
- Field-aware validation is now active using refreshed catalogue data (check
  graph_json links for field compatibility).
- Catalogue-driven node-setting validation (enum/mode properties).
- Automated enforcement of the 22-step LLM checklist.
- Extend the full graph report with per-link data payloads once the exporter
  captures them.

## Smoke Tests

**MCP-first (recommended)**: Copy contents of `mcp_smoke_test_payload.py` into
your MCP `execute_blender_code` call. This validates the full chain:
`graph_json → build → validation`.

**Targeted field-mismatch test (MCP)**: Copy
`scripts/field_mismatch_test_payload.py` into `execute_blender_code`. It should
fail with a field-compatibility error, confirming the guard is active.

**Merge-mode smoke test (MCP)**: Copy
`scripts/merge_smoke_test_payload.py` into `execute_blender_code` to verify
incremental merge/diff behavior and diff summaries.

**Standalone Blender**: `blender --background --python smoke_test_mermaid.py`

Both tests verify:
1. Toolkit loads correctly
2. Nodes and links build without errors
3. Group Output is properly connected (critical!)
4. Validation pipeline returns `"status": "VALID"`

### Using `__GROUP_OUTPUT__` in Mermaid

To connect your graph to the modifier's output, use the special ID
`__GROUP_OUTPUT__` (with underscores) in your Mermaid plan:

```mermaid
flowchart LR
  n1["MeshGrid"] -->|Mesh| n2["MeshToPoints"]
  n2 -->|Points| n3["InstanceOnPoints"]
  n4["MeshCone"] -->|Mesh| n3
  n3 -->|Instances| __GROUP_OUTPUT__
```

The parser automatically maps socket names (e.g., `Instances` → `Geometry`).
