#!/usr/bin/env python3
"""Extract Geometry Nodes metadata from the Blender manual.

Parses a local Blender manual checkout (reStructuredText) for
``.. _bpy.types.GeometryNode*`` anchors and captures description, inputs,
outputs, and properties text for each node. Outputs JSON keyed by Blender node
identifier so the toolkit can fill in missing catalogue details.

Manual checkout (sparse clone) commands:

```
git lfs install --skip-smudge
git clone --depth 1 --filter=blob:none --sparse \
    https://projects.blender.org/blender/blender-manual.git blender-manual-gn
cd blender-manual-gn
git sparse-checkout set manual/modeling/geometry_nodes
```
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ANCHOR_PATTERN = re.compile(r"\.\. _bpy\.types\.([A-Za-z0-9_]+):")
HEADING_PATTERN = re.compile(r"(?m)^([A-Za-z0-9 ].+)\n([=*~`^\"'\-]{3,})\n")
SECTION_SKIP = {"GeometryNode", "GeometryNodeTree", "GeometryNodeGroup"}
ADMONITION_PATTERN = re.compile(r"(?ms)\.{2} (note|tip|warning|caution)::\n\s+(.+?)(?:\n\n|$)")
IDENT_PREFIXES = ("GeometryNode", "ShaderNode", "FunctionNode")
ROLE_WITH_LINK = re.compile(r":([A-Za-z0-9_-]+):`([^`<]+)(?: <([^`>]+)>)?`")
ROLE_SIMPLE = re.compile(r":([A-Za-z0-9_-]+):`([^`]*)`")


def extract_metadata(manual_root: Path) -> dict[str, dict[str, object]]:
    data: dict[str, dict[str, object]] = {}
    for path in manual_root.rglob("*.rst"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in ANCHOR_PATTERN.finditer(text):
            identifier = match.group(1)
            if not identifier.startswith(IDENT_PREFIXES):
                continue
            if identifier in SECTION_SKIP:
                continue
            block = _slice_block(text, match.end())
            if not block:
                continue
            sections = _split_sections(block)
            label = sections.get("__label__", identifier)
            label_key = label.lower() if label else ""
            desc_source = sections.get(label_key, sections.get(None, ""))
            entry: dict[str, object] = {
                "label": label,
                "description": _clean_text(desc_source),
                "source": str(path),
            }
            inputs = sections.get("inputs")
            outputs = sections.get("outputs")
            props = sections.get("properties")
            if inputs:
                entry["inputs"] = _parse_definition_list(inputs)
            if outputs:
                entry["outputs"] = _parse_definition_list(outputs)
            if props:
                cleaned_props, prop_params = _clean_text_and_params(props)
                entry["properties"] = cleaned_props
                if prop_params:
                    entry.setdefault("properties_parameters", prop_params)
            notes = _extract_admonitions(block)
            if notes:
                entry["notes"] = notes
            data[identifier] = entry
    return data


def _slice_block(text: str, start: int) -> str:
    tail = text[start:]
    next_anchor = ANCHOR_PATTERN.search(tail)
    return tail[: next_anchor.start()] if next_anchor else tail


def _split_sections(block: str) -> dict[str | None, str]:
    sections: dict[str | None, str] = {}
    matches = list(HEADING_PATTERN.finditer(block))
    if not matches:
        sections[None] = block.strip()
        return sections
    first = matches[0]
    intro = block[: first.start()].strip()
    if intro:
        sections[None] = intro
    sections["__label__"] = first.group(1).strip()
    for idx, match in enumerate(matches):
        title = match.group(1).strip().lower()
        content_start = match.end()
        content_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(block)
        content = block[content_start:content_end].strip()
        sections[title] = content
    return sections


def _clean_text(text: str) -> str:
    lines = text.splitlines()
    cleaned: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith(".. "):
            i += 1
            continue
        if line.startswith(":") and "`" not in line:
            if line.count(":") >= 2:
                i += 1
                continue
        if i + 1 < len(lines):
            underline = lines[i + 1].strip()
            if underline and all(ch in "*-=~_" for ch in underline):
                i += 2
                continue
        if all(ch in "*-=~_" for ch in line):
            i += 1
            continue
        cleaned.append(_replace_roles(line))
        i += 1
    paragraphs = [p.strip() for p in "\n".join(cleaned).split("\n\n") if p.strip()]
    return paragraphs[0] if paragraphs else ""


def _clean_text_and_params(text: str) -> tuple[str, list[dict[str, str]]]:
    params = _parse_bullet_parameters(text)
    cleaned = _clean_text(text)
    return cleaned, params


def _parse_definition_list(text: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    items: list[dict[str, str]] = []
    current_name = None
    current_desc: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        if not line.startswith(" ") and not line.startswith("\t"):
            if current_name:
                desc_text = "\n".join(current_desc)
                desc_clean, params = _clean_text_and_params(desc_text)
                item = {"name": _replace_roles(current_name), "description": desc_clean}
                if params:
                    item["parameters"] = params
                items.append(item)
            candidate_name = line.strip()
            if candidate_name.startswith(".. "):
                current_name = None
                current_desc = []
                continue
            current_name = candidate_name
            current_desc = []
        else:
            current_desc.append(line.strip())
    if current_name:
        desc_text = "\n".join(current_desc)
        desc_clean, params = _clean_text_and_params(desc_text)
        item = {"name": _replace_roles(current_name), "description": desc_clean}
        if params:
            item["parameters"] = params
        items.append(item)
    return items

def _parse_bullet_parameters(text: str) -> list[dict[str, str]]:
    params: list[dict[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        match = re.match(r"-\s+\*\*(.+?)\*\*\s+--\s+(.*)", stripped)
        if match:
            name = _replace_roles(match.group(1).strip())
            desc = _replace_roles(match.group(2).strip())
            params.append({"name": name, "description": desc})
    return params


def _replace_roles(text: str) -> str:
    def repl_link(match: re.Match) -> str:
        return match.group(2).strip()

    text = ROLE_WITH_LINK.sub(repl_link, text)
    text = ROLE_SIMPLE.sub(lambda m: m.group(2).strip(), text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r":([A-Za-z0-9 _-]+):", r"\1", text)
    return text


def _extract_admonitions(text: str) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    for match in ADMONITION_PATTERN.finditer(text):
        kind = match.group(1)
        body = _clean_text(match.group(2))
        if body:
            notes.append({"type": kind, "text": body})
    return notes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manual-root",
        type=Path,
        default=Path("_archive/blender-manual-gn/manual/modeling/geometry_nodes"),
        help="Path to the Blender manual geometry_nodes directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reference/node_metadata_extras.json"),
        help="Path to output JSON file",
    )
    args = parser.parse_args()
    data = extract_metadata(args.manual_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Wrote {len(data)} entries to {args.output}")


if __name__ == "__main__":
    main()
