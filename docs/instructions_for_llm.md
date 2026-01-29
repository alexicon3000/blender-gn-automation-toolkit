# MCP Capture Debug Instructions

1. Ensure Blender MCP is running via `./blender-launcher.sh` (sandbox scene + add-on) and the `blender-mcp` CLI can connect (e.g., `uvx blender-mcp list`).
2. Run the auto frame payload to the point of failure if needed: `python3 scripts/frame_validation_payload.py --alias <alias>`

   - Expect the export step to fail with “Screenshot capture failed" if `capture_node_graph` is still returning None.

3. Execute the capture smoke test to inspect the active workspace and capture path:

   ```bash
   uvx blender-mcp call <alias> execute_blender_code --params "$(python3 scripts/capture_smoke_test_payload.py)"
   ```

   - This prints the current screen/area layout, runs `switch_to_mcp_workspace()`, and then prints the exact path returned by `capture_node_graph`.

4. Share the output (screen areas + capture path). If the capture returns `None` or the areas lack a NODE editor, we’ll tweak `switch_to_mcp_workspace()` or add a fallback (`get_viewport_screenshot`).
5. Once capture is confirmed working, rerun `scripts/frame_validation_payload.py --alias <alias>` to produce a real `_archive/frame_validation_nodes_YYYYMMDD_HHMMSS.png` and log the run in `mcp_run_log.md`.
