# Geo Nodes MCP Toolkit

Utilities and reference data for building Blender Geometry Nodes graphs through
LLM- or MCP-driven workflows. The repo packages a portable `toolkit.py` for
in-Blender use plus a `geo_nodes_mcp` module for agents or scripts that need to
load catalogues, validate socket compatibility, or snapshot node graphs.

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
- `_archive/` – Legacy assets kept for historical reference (ignored by git).

## Contributing / Next Steps
High-level roadmap items live near the end of `GUIDE.md`. Briefly:
1. Regenerate catalogues so `supports_field` flags are accurate for field-aware
   validation.
2. Add stricter node-setting validation using catalogue metadata.
3. Automate the LLM checklist in code so MCP workflows can fail fast before
   building.
