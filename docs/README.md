# Documentation Index

This directory contains documentation for the Geometry Nodes MCP Toolkit.

## For LLM Agents

Start here when beginning a new session:

| Document | Purpose |
|----------|---------|
| **[AGENT_GUIDE.md](AGENT_GUIDE.md)** | How to operate the toolkit, run MCP payloads, avoid crashes, and hand off sessions |
| **[NODE_PATTERNS.md](NODE_PATTERNS.md)** | Common node patterns with sample code, plus nodes requiring special handling |

## Toolkit Reference

| Document | Purpose |
|----------|---------|
| **[../GUIDE.md](../GUIDE.md)** | Complete API reference: all functions, workflows, and validation |
| **[../WORKFLOW.md](../WORKFLOW.md)** | LLM checklist (22 rules), Mermaid conventions, graph_json spec |

## Scripts

| Document | Purpose |
|----------|---------|
| **[../scripts/README.md](../scripts/README.md)** | MCP payload scripts: purpose, usage, and debugging tips |

## Session Archives

Daily session notes live in `_archive/session_notes_YYYYMMDD.md`. Check the most recent one for:
- What was tried in previous sessions
- Known issues and workarounds
- Pending tasks

## Quick Links

- **Load toolkit:** `exec(open("toolkit.py").read())`
- **Run tests:** `python3 -m pytest tests/ -v`
- **Launch Blender:** `./blender-launcher.sh`
- **Frame validation:** `python scripts/frame_validation_payload.py`

## Document Hierarchy

```
docs/
├── README.md          ← You are here (index)
├── AGENT_GUIDE.md     ← Start here for new sessions
├── NODE_PATTERNS.md   ← Common patterns and quirks
└── fractal_leaf_instances.md  ← Example project notes

GUIDE.md               ← Toolkit API reference (root level)
WORKFLOW.md            ← LLM rules and Mermaid conventions (root level)
scripts/README.md      ← MCP payload documentation
```
