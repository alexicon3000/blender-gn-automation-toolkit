#!/usr/bin/env bash

# Launch Blender with the MCP add-on and the dedicated MCP test scene.
#
# The exact Blender build to use is stored in blender_mcp_path.txt.
# Update that file whenever you want to point at a different build.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
BLENDER_PATH_FILE="$REPO_ROOT/blender_mcp_path.txt"

if [[ ! -f "$BLENDER_PATH_FILE" ]]; then
  echo "Missing blender_mcp_path.txt — create it with the full path to your Blender binary." >&2
  exit 1
fi

BLENDER_BIN="$(<"$BLENDER_PATH_FILE")"

if [[ ! -x "$BLENDER_BIN" ]]; then
  echo "Blender binary not found or not executable: $BLENDER_BIN" >&2
  exit 1
fi

TEST_SCENE_DEFAULT="$REPO_ROOT/_archive/MCP_Testing_5.0.blend"
TEST_SCENE="${MCP_SCENE:-$TEST_SCENE_DEFAULT}"
if [[ -n "$TEST_SCENE" && ! -f "$TEST_SCENE" ]]; then
  echo "Warning: test scene not found at $TEST_SCENE; launching Blender with the default empty scene." >&2
  TEST_SCENE=""
fi

ADDON_LOADER="$REPO_ROOT/blender_mcp_loader.py"
if [[ ! -f "$ADDON_LOADER" ]]; then
  echo "Add-on loader script missing: $ADDON_LOADER" >&2
  exit 1
fi

LAUNCH_ARGS=("$BLENDER_BIN" --factory-startup --python "$ADDON_LOADER")
if [[ -n "$TEST_SCENE" ]]; then
  LAUNCH_ARGS+=("$TEST_SCENE")
fi

"${LAUNCH_ARGS[@]}"
