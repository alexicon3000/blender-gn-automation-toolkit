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
   - As you build, tag nodes with their functional section (e.g., Terrain, Cactus Asset, Scatter). Keep a dict like `{section: [node_ids...]}` so you can generate frame specs that match the design before running validation (see GUIDE.md “Frame Planning”). Leave nodes untagged if you don’t want them framed yet.
4. Generate the frame validation payload (default mode prints a single script to paste into VS Code MCP):
   ```bash
   python3 scripts/frame_validation_payload.py
   ```
   - Copy the emitted code block into the MCP sidebar’s `execute_blender_code` tool and run it once. It performs build → node-settings → validation → frames → export sequentially and writes the screenshot to `_archive/`.
   - If you specifically need the old CLI behavior (when the STDIO bridge is healthy), run `python3 scripts/frame_validation_payload.py --mode cli --alias <alias>`.
   - Optional connection ping (before running payload): paste the MCP snippet from GUIDE.md (“Quick Smoke Tests”) into `execute_blender_code` to confirm Blender responds, or run `python3 -m pytest tests/test_incremental_api.py tests/test_frames.py -q` for a fast local sanity check.
   - Shortcut: `python3 scripts/connection_smoke_test_payload.py` prints a payload you can paste into MCP; `--mode cli` attempts the check via `uvx` when that bridge is healthy.
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
