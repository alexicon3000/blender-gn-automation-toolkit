#!/usr/bin/env python3
"""Batch-export Geometry Nodes catalogues from Blender Launcher builds."""

import argparse
import os
import shutil
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORTER = PROJECT_ROOT / "GeoNodes_Exporter_Complete.py"
REFERENCE_DIR = PROJECT_ROOT / "reference"
DOWNLOADS = Path.home() / "Downloads"

CAT_PATTERN = "geometry_nodes_complete"
MIN_PATTERN = "geometry_nodes_min"


def find_blender_execs(root: Path):
    """Yield Blender executables under the given root."""
    for app in root.rglob("Blender.app"):
        exec_path = app / "Contents/MacOS/Blender"
        if exec_path.exists():
            yield exec_path

    for exe in root.rglob("blender"):
        if exe.is_file() and os.access(exe, os.X_OK):
            yield exe


def newest_download(pattern: str, before: float) -> Path | None:
    candidates = [
        p for p in DOWNLOADS.glob(f"{pattern}_*.json")
        if p.stat().st_mtime >= before
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def run_export(blender_exec: Path):
    print(f"\n=== Exporting with {blender_exec} ===")
    before = time.time()
    env = os.environ.copy()

    subprocess.run(
        [str(blender_exec), "--background", "--python", str(EXPORTER)],
        env=env,
        check=True,
    )

    complete = newest_download(CAT_PATTERN, before)
    if complete:
        target = REFERENCE_DIR / complete.name
        shutil.move(str(complete), target)
        print(f"  → copied {complete.name} to reference/")
    else:
        print("  ! no geometry_nodes_complete_*.json created")

    minimal = newest_download(MIN_PATTERN, before)
    if minimal:
        target = REFERENCE_DIR / minimal.name
        shutil.move(str(minimal), target)
        print(f"  → copied {minimal.name} to reference/")
    else:
        print("  (no minimal file detected)")


def main():
    parser = argparse.ArgumentParser(description="Export Geo Nodes catalogues from Blender builds")
    parser.add_argument(
        "--root",
        required=True,
        help="Path to Blender Launcher 'stable' folder (e.g., /Users/.../_Blender_Builds/stable)",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser()
    execs = sorted(set(find_blender_execs(root)))
    if not execs:
        raise SystemExit(f"No Blender executables found under {root}")

    for exec_path in execs:
        run_export(exec_path)


if __name__ == "__main__":
    main()
