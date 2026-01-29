# MCP Run Instructions (updated)

## Goal:
Produce a validated frame graph via MCP (screenshot + log) and capture the current Blender workspace state.

## Steps:

1. If Blender isn’t already running with the MCP add-on, launch it via `./blender-launcher.sh` (reads `blender_mcp_path.txt`). Otherwise skip this step.
2. In Blender’s scripting console, run `exec(open("/Users/alexanderporter/Documents/_DEV/Geo Nodes MCP/toolkit.py").read())` to load the toolkit.
   - Resolve node identifiers/sockets via `python3 scripts/query_node_metadata.py --node "<label>"` (or `--search <term>`). This CLI + alias map is authoritative; **do not** scan `reference/geometry_nodes_complete_*.json` manually.
   - Sanity-check MCP is responsive: `uvx blender-mcp call blender get_scene_info` should return the active scene; if it fails, relaunch via `./blender-launcher.sh`.
   - In the VS Code MCP sidebar, you can run the same tools (e.g., `get_scene_info`, `execute_blender_code`). Prefer this UI when the CLI bridge is unstable, since it talks directly to the running MCP server.
3. Stay in the build loop while constructing the graph: use `add_node`, `auto_link`, and `describe_node_group` to add nodes incrementally and verify the state after each change. Only move to validation once `describe_node_group` reports no warnings.
4. Run the frame validation payload in incremental mode:
   ```bash
   python3 scripts/frame_validation_payload.py --alias <your-mcp-alias>
   ```
   - This handles build → node-settings → validation → frames → export as separate MCP calls.
   - The script now prints the `capture_node_graph` path and retries once if the PNG is missing. Treat “Screenshot capture failed” as an error.
5. Confirm a new PNG exists in `_archive/` (e.g., `_archive/frame_validation_nodes_<timestamp>.png`). If it’s missing, run the capture smoke test:
   ```bash
   uvx blender-mcp call <alias> execute_blender_code --params "$(python3 scripts/capture_smoke_test_payload.py)"
   ```
   and share the output (screen areas + capture path) before proceeding.
6. Log the run:
   - Append an entry to `mcp_run_log.md` (include timestamp, alias, script name, screenshot path, and any issues). This file is gitignored.
   - Add a bullet to `_archive/session_notes_YYYYMMDD.md` summarizing the MCP run (success/failure, screenshot, next steps).
7. If a crash occurs, follow the crash checklist in `GUIDE.md` (ask the user to relaunch Blender, rerun toolkit, resume at the last successful step).

## Deliverables:
- A confirmed PNG under `_archive/`.
- Entries in `mcp_run_log.md` and the current session note file.
- Any diagnostic output (especially if capture fails) pasted into the chat/log so we can review later.
