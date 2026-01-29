#!/usr/bin/env python3
"""Quickly look up Geometry Nodes metadata (identifier, sockets, manual notes).

Example:
    python scripts/query_node_metadata.py --node "Distribute Points on Faces"

The script searches the catalogue (reference/geometry_nodes_complete_5_0.json),
manual extras (reference/node_metadata_extras.json), and alias mappings
(reference/node_aliases.json) so you don't have to grep JSON manually.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = REPO_ROOT / "reference" / "geometry_nodes_complete_5_0.json"
NODE_EXTRAS = REPO_ROOT / "reference" / "node_metadata_extras.json"
ALIAS_FILE = REPO_ROOT / "reference" / "node_aliases.json"
PATTERN_MAP_FILE = REPO_ROOT / "reference" / "node_patterns_map.json"


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_indices(nodes: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    identifier_index = {}
    label_index = {}
    for entry in nodes:
        identifier = entry.get("identifier")
        label = entry.get("label", "")
        if not identifier:
            continue
        identifier_index[identifier.lower()] = entry
        if label:
            label_index[label.lower()] = identifier
    return identifier_index, label_index


def resolve_query(query: str, identifier_index: dict[str, dict[str, Any]], label_index: dict[str, str], aliases: dict[str, list[str]]) -> dict[str, Any] | None:
    q_lower = query.lower()
    if q_lower in identifier_index:
        return identifier_index[q_lower]
    if q_lower in label_index:
        ident = label_index[q_lower]
        return identifier_index.get(ident.lower())
    for ident, alias_list in aliases.items():
        if any(q_lower == alias.lower() for alias in alias_list):
            return identifier_index.get(ident.lower())
    # Fuzzy suggestions
    choices = list(label_index.keys()) + list(identifier_index.keys())
    matches = difflib.get_close_matches(q_lower, choices, n=1, cutoff=0.6)
    if matches:
        match = matches[0]
        if match in label_index:
            ident = label_index[match]
            return identifier_index.get(ident.lower())
        return identifier_index.get(match)
    return None


def print_metadata(entry: dict[str, Any], extras: dict[str, Any] | None, pattern_map: dict[str, list[str]]) -> None:
    identifier = entry.get("identifier")
    label = entry.get("label")
    category = entry.get("category")
    print(f"Identifier: {identifier}")
    if label:
        print(f"Label     : {label}")
    if category:
        print(f"Category  : {category}")
    print("Inputs    :")
    for inp in entry.get("inputs", []):
        print(f"  - {inp.get('name')} ({inp.get('type')})")
    print("Outputs   :")
    for out in entry.get("outputs", []):
        print(f"  - {out.get('name')} ({out.get('type')})")

    extra = extras.get(identifier, {}) if extras else {}
    description = extra.get("description")
    if description:
        print("Description:")
        print(f"  {description}")
    if extra.get("inputs"):
        print("Manual inputs:")
        for item in extra["inputs"]:
            print(f"  - {item['name']}: {item['description']}")
    if extra.get("outputs"):
        print("Manual outputs:")
        for item in extra["outputs"]:
            print(f"  - {item['name']}: {item['description']}")
    if extra.get("properties"):
        print("Properties:")
        print(f"  {extra['properties']}")
        if extra.get("properties_parameters"):
            for param in extra["properties_parameters"]:
                print(f"    * {param['name']}: {param['description']}")
    if extra.get("notes"):
        print("Notes:")
        for note in extra["notes"]:
            print(f"  - ({note['type']}) {note['text']}")
    patterns = pattern_map.get(identifier, [])
    if patterns:
        print(f"Patterns : {', '.join(patterns)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", required=True, help="Node label, identifier, or alias")
    args = parser.parse_args()

    catalogue = load_json(CATALOGUE)
    if not catalogue:
        sys.exit(f"Missing catalogue: {CATALOGUE}")
    nodes = catalogue.get("nodes", catalogue)
    identifier_index, label_index = build_indices(nodes)

    extras = load_json(NODE_EXTRAS) or {}
    aliases = load_json(ALIAS_FILE) or {}
    pattern_map = load_json(PATTERN_MAP_FILE) or {}

    entry = resolve_query(args.node, identifier_index, label_index, aliases)
    if not entry:
        sys.exit(f"Node '{args.node}' not found. Try a different name or alias.")

    print_metadata(entry, extras, pattern_map)


if __name__ == "__main__":
    main()
