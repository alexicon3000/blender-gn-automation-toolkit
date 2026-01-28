"""Report how many sockets in the catalogue support fields.

Usage:
    python scripts/verify_supports_field.py reference/geometry_nodes_complete_4_4.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load_catalogue(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        return data.get("nodes", [])
    if isinstance(data, list):
        return data
    raise ValueError("Unsupported catalogue format")


def count_supports_field(nodes):
    total = 0
    supported = 0
    by_node = {}
    for node in nodes:
        for direction in ("inputs", "outputs"):
            for socket in node.get(direction, []):
                total += 1
                if socket.get("supports_field"):
                    supported += 1
                    by_node.setdefault(node.get("identifier", "<unknown>"), 0)
                    by_node[node.get("identifier", "<unknown>")] += 1
    return total, supported, by_node


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/verify_supports_field.py <catalogue.json>")
    path = Path(sys.argv[1]).expanduser()
    nodes = load_catalogue(path)
    total, supported, by_node = count_supports_field(nodes)
    percent = (supported / total * 100) if total else 0.0
    print(f"Catalogue: {path}")
    print(f"Sockets supporting fields: {supported}/{total} ({percent:.2f}%)")
    if supported:
        top = sorted(by_node.items(), key=lambda item: item[1], reverse=True)[:10]
        print("Top nodes with field-capable sockets:")
        for name, count in top:
            print(f"  {name}: {count}")


if __name__ == "__main__":
    main()