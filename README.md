# Blender Geometry Nodes Automation Toolkit

Utilities and reference data for building Blender Geometry Nodes graphs through
LLM- or MCP-driven workflows. The repo packages a portable `toolkit.py` for
in-Blender use plus a `geo_nodes_mcp` module for agents or scripts that need to
load catalogues, validate socket compatibility, or snapshot node graphs.

**Key ideas**
- Plan visually: sketch Mermaid flow charts (with GroupInput/GroupOutput) so
  humans can sanity-check topology before executing anything.
- Catalog-driven safety: builders load Blender 4.4 node definitions and the
  socket compatibility matrix before linking, catching wrong directions or
  types early.
- Pre-flight validation: `safe_link()` checks direction + types before
  `links.new()`, and the validation suite captures both structural metrics and
  screenshots so MCP runs surface issues immediately.

## Getting Started
1. Open Blender 4.4+ and run:
   ```python
   exec(open("/Users/alexanderporter/Documents/_DEV/Geo Nodes MCP/toolkit.py").read())
   ```
   This loads all helpers (Mermaid parsing, graph builders, validators) into the
   current Python session.
2. Plan graphs in Mermaid or `graph_json`, then call
   `mermaid_to_blender()` or `build_graph_from_json()` to instantiate the node
group.
3. Run `full_geo_nodes_validation()` to capture screenshots and structural/
   metric reports.

## Documentation
- `GUIDE.md` – Hands-on quick start, helper catalog, project notes, and common
  pitfalls.
- `WORKFLOW.md` – MCP-centric process covering Mermaid rules, response format,
  and the 22-step checklist the LLM must satisfy before building.
- `reference/` – Blender 4.4 catalogue JSON and socket compatibility CSV (the
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
   validation.
2. Add stricter node-setting validation using catalogue metadata.
3. Automate the LLM checklist in code so MCP workflows can fail fast before
   building.

## Status at a Glance
**Works today**
- Catalogue/socket loaders, Mermaid→graph_json parsing, graph builders, and
  validation helpers (`toolkit.py`, `geo_nodes_mcp/`).
- Pre-link safety checks (direction/type) using Blender 4.4 metadata.
- Post-build validation with metrics + screenshots.

**Still to build/validate**
- Refresh catalogues with accurate `supports_field` data to enable the new
  field-awareness guard.
- Catalogue-driven node-setting validation (enum/mode properties).
- Automated enforcement of the 22-step LLM checklist.
- "Full fat" graph reporting (nodes, sockets, settings, wire payloads) for
  manual reconstruction when automation fails.
- Run Blender MCP smoke tests (Mermaid → graph_json → build → validation) to
  confirm the new safety checks behave as expected end-to-end.

## MCP-First Smoke Test (Recommended)
If a Blender MCP session is already running, use the MCP-first smoke payload
instead of launching a new Blender process. Copy the contents of
`mcp_smoke_test_payload.py` into your MCP `execute_blender_code` call.

This validates the full chain in the active MCP session:
Mermaid → graph_json → build → `full_geo_nodes_validation`.

Fallback (standalone Blender):
`blender --background --python smoke_test_mermaid.py`
