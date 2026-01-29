#!/usr/bin/env python3
"""Automate frame validation via incremental Blender MCP calls."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Iterable, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
COLLECTION = "MCP_Frame_Test"
OBJECT_NAME = "MCP_Frame_Object"
MODIFIER_NAME = "MCP_Frame_Mod"
OBJECT_Z_OFFSET = 0.5

GRAPH_JSON = {
    "nodes": [
        {"id": "grid", "type": "GeometryNodeMeshGrid"},
        {"id": "distribute", "type": "GeometryNodeDistributePointsOnFaces"},
        {"id": "cube", "type": "GeometryNodeMeshCube"},
        {"id": "instance", "type": "GeometryNodeInstanceOnPoints"},
        {"id": "realize", "type": "GeometryNodeRealizeInstances"},
    ],
    "links": [
        {"from": "grid", "from_socket": "Mesh", "to": "distribute", "to_socket": "Mesh"},
        {"from": "distribute", "from_socket": "Points", "to": "instance", "to_socket": "Points"},
        {"from": "cube", "from_socket": "Mesh", "to": "instance", "to_socket": "Instance"},
        {"from": "instance", "from_socket": "Instances", "to": "realize", "to_socket": "Geometry"},
        {"from": "realize", "from_socket": "Geometry", "to": "__GROUP_OUTPUT__", "to_socket": "Geometry"},
    ],
}

FRAME_SPECS = [
    {
        "id": "emit_points",
        "label": "Emit Points",
        "color": [0.2, 0.46, 0.84, 1.0],
        "nodes": ["grid", "distribute"],
        "text": "Controls surface sampling density",
    },
    {
        "id": "instance_block",
        "label": "Instance Shapes",
        "color": [0.88, 0.42, 0.25, 1.0],
        "nodes": ["cube", "instance", "realize"],
        "shrink": True,
        "text": "Instancing pipeline (cube -> realize)",
    },
]

# Apply node inputs after the initial build. Setting GeometryNodeDistributePointsOnFaces
# values inside graph_json was crashing Blender 5.0.1, so we tweak inputs in a separate
# MCP call instead.
NODE_SETTINGS = {
    "grid": {"Vertices X": 32, "Vertices Y": 32, "Size X": 4.0, "Size Y": 4.0},
    "distribute": {"Density Max": 5.0},
    "cube": {"Size": 0.3},
    "instance": {"Scale": [0.5, 0.5, 0.5]},
}

SESSION_NOTES = REPO_ROOT / "_archive" / "session_notes_20260129.md"
DEFAULT_ALIAS = "blender"


def run_mcp(code: str, label: str, alias: str) -> None:
    params = json.dumps({"code": code, "user_prompt": f"Frame validation step: {label}"})
    cmd = ["uvx", "blender-mcp", "call", alias, "execute_blender_code", "--params", params]
    print(f"\n[step:{label}] running {' '.join(cmd[:-2])} ...", flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise SystemExit(f"Step '{label}' failed with exit code {proc.returncode}")


def common_preamble() -> str:
    return textwrap.dedent(
        f"""
        import json, os, shutil
        from datetime import datetime
        from pathlib import Path

        REPO_ROOT = Path({str(REPO_ROOT)!r})
        TOOLKIT_PATH = Path(os.environ.get("GN_MCP_TOOLKIT_PATH", REPO_ROOT / "toolkit.py"))
        os.environ.setdefault("GN_MCP_SOCKET_COMPAT_PATH", str(REPO_ROOT / "reference" / "socket_compat.csv"))
        os.environ.setdefault("GN_MCP_CATALOGUE_PATH", str(REPO_ROOT / "reference" / "geometry_nodes_complete_5_0.json"))

        with open(TOOLKIT_PATH, "r", encoding="utf-8") as fh:
            code = compile(fh.read(), str(TOOLKIT_PATH), "exec")
        exec(code, globals())
        """
    )


def dedent_template(template: str, **subs: str) -> str:
    dedented = textwrap.dedent(template)
    return textwrap.dedent(Template(dedented).substitute(**subs))


def build_code() -> str:
    code = common_preamble()
    code += f"\nGRAPH_JSON = {repr(GRAPH_JSON)}\n"
    code += dedent_template(
        """
        print("[build] Clearing collection and building graph...", flush=True)
        clear_collection($collection)
        build_result = build_graph_from_json(
            $object_name,
            $modifier_name,
            GRAPH_JSON,
            collection=$collection,
        )
        print(json.dumps(build_result, indent=2))
        if not build_result.get("success"):
            raise SystemExit("build failed")
        """,
        collection=repr(COLLECTION),
        object_name=repr(OBJECT_NAME),
        modifier_name=repr(MODIFIER_NAME),
    )
    return code


def node_settings_code() -> str:
    code = common_preamble()
    code += f"\nNODE_SETTINGS = {repr(NODE_SETTINGS)}\n"
    code += dedent_template(
        """
        import bpy
        print("[node-settings] Applying post-build node parameters...", flush=True)
        obj = bpy.data.objects.get($object_name)
        mod = obj.modifiers.get($modifier_name) if obj else None
        if not (obj and mod and mod.node_group):
            raise SystemExit("Missing object or node group for node-settings step")
        node_map = {}
        for node in mod.node_group.nodes:
            node_id = node.get(_NODE_ID_PROP) if hasattr(node, "get") else None
            if node_id:
                node_map[node_id] = node
        for node_id, inputs in NODE_SETTINGS.items():
            node = node_map.get(node_id)
            if not node:
                print(f"[node-settings] Skipping unknown node {node_id}")
                continue
            for socket_name, value in inputs.items():
                set_node_input(node, socket_name, value)
        print("[node-settings] Done", flush=True)
        """,
        object_name=repr(OBJECT_NAME),
        modifier_name=repr(MODIFIER_NAME),
    )
    return code


def validation_code() -> str:
    code = common_preamble()
    code += dedent_template(
        """
        import bpy
        print("[validation] Running full_geo_nodes_validation...", flush=True)
        obj = bpy.data.objects.get($object_name)
        if obj:
            obj.location.z = $z_offset
        validation = full_geo_nodes_validation($object_name, $modifier_name, capture_screenshot=False)
        print_validation_report(validation)
        if validation.get("status") != "VALID":
            raise SystemExit("Validation failed; adjust node settings or offsets")
        """,
        object_name=repr(OBJECT_NAME),
        modifier_name=repr(MODIFIER_NAME),
        z_offset=OBJECT_Z_OFFSET,
    )
    return code


def frames_code() -> str:
    code = common_preamble()
    code += f"\nFRAME_SPECS = {repr(FRAME_SPECS)}\n"
    code += dedent_template(
        """
        import bpy
        print("[frames] Applying frame specs...", flush=True)
        obj = bpy.data.objects.get($object_name)
        mod = obj.modifiers.get($modifier_name) if obj else None
        if not (obj and mod and mod.node_group):
            raise SystemExit("Missing object/modifier for frames step")
        node_map = {}
        for node in mod.node_group.nodes:
            node_id = node.get(_NODE_ID_PROP) if hasattr(node, "get") else None
            if node_id:
                node_map[node_id] = node
        errors = []
        _apply_frames(mod.node_group, node_map, FRAME_SPECS, errors)
        if errors:
            raise SystemExit("Frame errors: " + "; ".join(errors))
        print("[frames] Applied", len(FRAME_SPECS), "frames", flush=True)
        """,
        object_name=repr(OBJECT_NAME),
        modifier_name=repr(MODIFIER_NAME),
    )
    return code


def export_code(screenshot_rel: str) -> str:
    screenshot_abs = (REPO_ROOT / "_archive" / screenshot_rel).as_posix()
    code = common_preamble()
    template = Template(
        """
import bpy
print("[export] Dumping frames and capturing screenshot...", flush=True)
export_data = export_modifier_to_json($object_name, $modifier_name)
frames = export_data.get("graph_json", {}).get("frames", [])
print(json.dumps(frames, indent=2))
switch_to_mcp_workspace()
frame_object_in_viewport($object_name, use_local_view=True)

def _payload_log(message: str):
    log_path = REPO_ROOT / "_archive" / "frame_validation_payload.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as log_fh:
        log_fh.write(f"{datetime.now().isoformat()} {message}\\n")

# Screenshot capture is flaky when Blender is left in fullscreen; capturing twice is safer
capture_path = capture_node_graph($object_name, $modifier_name)
_payload_log(f"[export] capture_node_graph returned: {capture_path}")
print(f"[export] capture_node_graph returned: {capture_path}")
target = Path($screenshot_abs)

def _copy_candidate(candidate_path, label):
    candidate = Path(candidate_path) if candidate_path else None
    if candidate and candidate.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(candidate, target)
        msg = f"[export] Screenshot saved to {target} via {label}"
        print(msg)
        _payload_log(msg)
        return True
    return False

if not _copy_candidate(capture_path, "primary"):
    warn = "[export] Screenshot missing; retrying once..."
    print(warn)
    _payload_log(warn)
    capture_path = capture_node_graph($object_name, $modifier_name)
    print(f"[export] retry capture returned: {capture_path}")
    _payload_log(f"[export] retry capture returned: {capture_path}")
    if not _copy_candidate(capture_path, "retry"):
        raise SystemExit("Screenshot capture failed")

if not target.exists():
    _payload_log(f"[export] ERROR target missing after copy: {target}")
    raise SystemExit(f"Screenshot missing on disk: {target}")
else:
    _payload_log(f"[export] verified screenshot exists at {target}")
summary = {"frames": len(frames), "screenshot": str(target)}
print("[export] SUMMARY\\n" + json.dumps(summary, indent=2))
_payload_log(f"[export] SUMMARY -> {summary}")
        """,
    )
    body = template.substitute(
        object_name=repr(OBJECT_NAME),
        modifier_name=repr(MODIFIER_NAME),
        screenshot_abs=repr(screenshot_abs),
    ).strip("\n")
    code += "\n" + body + "\n"
    return code


def update_session_notes(screenshot_rel: str) -> None:
    entry = f"- Automated MCP frame validation via script ({screenshot_rel})."
    lines = SESSION_NOTES.read_text().splitlines()
    for idx, line in enumerate(lines):
        if line.strip().startswith("## Pending"):
            lines.insert(idx, entry)
            break
    else:
        lines.append(entry)
    SESSION_NOTES.write_text("\n".join(lines) + "\n")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alias", default=DEFAULT_ALIAS, help="MCP alias to use")
    parser.add_argument("--skip-log", action="store_true", help="Skip session note update")
    args = parser.parse_args(argv)

    screenshot_rel = f"frame_validation_nodes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    steps: Iterable[Tuple[str, str]] = [("build", build_code())]
    if NODE_SETTINGS:
        steps = [
            *steps,
            # Do not push node settings into graph_json; adjusting Distribute Points inputs
            # during the initial build caused Blender 5.0.1 to crash. Instead, tweak inputs
            # via a dedicated MCP call after the nodes exist.
            ("node-settings", node_settings_code()),
        ]
    steps = [
        *steps,
        ("validation", validation_code()),
        ("frames", frames_code()),
        ("export", export_code(screenshot_rel)),
    ]

    for label, code in steps:
        run_mcp(code, label, args.alias)

    screenshot_path = REPO_ROOT / "_archive" / screenshot_rel
    if not screenshot_path.exists():
        raise SystemExit(
            f"Expected screenshot {screenshot_rel} not found; check _archive/frame_validation_payload.log"
        )

    if not args.skip_log:
        update_session_notes(screenshot_rel)
        print(f"[log] Session notes updated with screenshot {screenshot_rel}")

    print("All steps completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
