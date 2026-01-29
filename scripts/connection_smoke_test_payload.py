#!/usr/bin/env python3
"""Quick MCP payload to verify Blender connectivity and scene state."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALIAS = "blender"

def common_preamble() -> str:
    return textwrap.dedent(
        f"""
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
    )

def payload(include_preamble: bool = True) -> str:
    code = common_preamble() if include_preamble else ""
    code += textwrap.dedent(
        """
        import bpy, json
        info = {
            "blender_version": bpy.app.version_string,
            "scene": bpy.context.scene.name,
            "object_count": len(bpy.context.scene.objects),
            "modifiers": {
                obj.name: [mod.name for mod in obj.modifiers]
                for obj in bpy.context.scene.objects
                if obj.modifiers
            },
        }
        print("[connection-smoke] MCP bridge OK")
        print(json.dumps(info, indent=2))
        """
    )
    return code

def run_mcp(code: str, alias: str) -> None:
    params = json.dumps({"code": code, "user_prompt": "MCP connection smoke test"})
    cmd = ["uvx", "blender-mcp", "call", alias, "execute_blender_code", "--params", params]
    print(f"Running {' '.join(cmd[:-2])} ...", flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alias", default=DEFAULT_ALIAS, help="MCP alias to use (cli mode)")
    parser.add_argument(
        "--mode",
        choices=("emit", "cli"),
        default="emit",
        help="emit (default) prints payload for MCP sidebar; cli uses uvx blender-mcp",
    )
    args = parser.parse_args(argv)

    if args.mode == "cli":
        run_mcp(payload(include_preamble=True), args.alias)
        return 0

    instructions = textwrap.dedent(
        """
        ==================================================================================
        MCP Connection Smoke Test
        ----------------------------------------------------------------------------------
        Paste the payload below into your MCP sidebar's `execute_blender_code` tool and run
        it once. You should see a short scene summary (version, scene name, object count,
        modifiers). If nothing prints, the MCP bridge is down.
        ==================================================================================
        """
    ).strip("\n")
    print(instructions)
    print()
    print(payload(include_preamble=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
