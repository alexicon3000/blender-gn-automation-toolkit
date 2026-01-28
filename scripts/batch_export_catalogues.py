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
COMPAT_PATTERN = "socket_compat"


def required_files_exist(version: str) -> bool:
    major, minor = version.split('.')[:2]
    complete = REFERENCE_DIR / f"geometry_nodes_complete_{major}_{minor}.json"
    compat = REFERENCE_DIR / f"socket_compat_{major}_{minor}.csv"
    return complete.exists() and compat.exists()


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
    candidates = []
    for ext in (".json", ".csv"):
        candidates.extend(
            p for p in DOWNLOADS.glob(f"{pattern}_*{ext}")
            if p.stat().st_mtime >= before
        )
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def run_export(blender_exec: Path, version: str | None = None):
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

    compat = newest_download(COMPAT_PATTERN, before)
    if compat:
        target = REFERENCE_DIR / compat.name
        shutil.move(str(compat), target)
        print(f"  → copied {compat.name} to reference/")
    else:
        print("  (no socket compat file detected)")


def main():
    parser = argparse.ArgumentParser(description="Export Geo Nodes catalogues from Blender builds")
    parser.add_argument(
        "--root",
        required=True,
        help="Path to Blender Launcher 'stable' folder (e.g., /Users/.../_Blender_Builds/stable)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-export even if catalogue/compat files already exist",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser()
    execs = sorted(set(find_blender_execs(root)))
    if not execs:
        raise SystemExit(f"No Blender executables found under {root}")

    for exec_path in execs:
        version = None
        try:
            proc = subprocess.run(
                [str(exec_path), "--version"],
                capture_output=True,
                text=True,
                check=True,
            )
            for line in proc.stdout.splitlines():
                if line.startswith("Blender"):
                    parts = line.split()
                    if len(parts) >= 2:
                        version = parts[1]
                        break
        except Exception as exc:
            print(f"Could not determine version for {exec_path}: {exc}")

        if not args.force and version and required_files_exist(version):
            print(f"Skipping {exec_path} (files for Blender {version} already exist)")
            continue

        run_export(exec_path, version=version)


if __name__ == "__main__":
    main()
