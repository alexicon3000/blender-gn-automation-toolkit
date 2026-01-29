# Geometry Nodes Pattern Library

Curated guidance drawn from the Blender manual + in-house experience. Use these patterns and rules to translate natural-language briefs into node graphs with minimal guesswork.

## 1. Field & Attribute Fundamentals
- *Fields are functions:* treat every field input as a lazy function evaluated per element (vertex, edge, face). Convert values to attributes only when you need persistent state (e.g., simulation or spreadsheet inspection).
- *Context matters:* check whether a socket supports fields (see catalogue `supports_field`). Feed values (not fields) only to sockets that explicitly refuse fields.
- *Capture Attribute when in doubt:* use `CaptureAttribute` to freeze field data for later use or for non-field consumers.

## 2. Surface Scatter (Landscape + Instances)
### Best Practices
- Displace the base mesh (Set Position + Noise/Musgrave) before scattering so point density follows the terrain.
- `DistributePointsOnFaces` defaults to random density; expose density as a Group Input to control instance count.
- Randomize instance transform via `RandomValue` (Scale/Rotation) before `InstanceOnPoints`.
- `RealizeInstances` only when necessary (Set Material, Set Shade Smooth, boolean ops). Keeping instances virtual improves performance.
- Frame sections: “Landscape”, “Scatter”, “Instance”, “Finalize”.

### Core Node Chain
`GroupInput → MeshGrid → SetPosition → DistributePointsOnFaces → InstanceOnPoints → RealizeInstances → GroupOutput`

## 3. Procedural Asset Generator (Modular)
Think of assets (rocks, trees, cacti) as subgraphs with reusable inputs.
- Build body geometry via `CurveLine`/`CurveCircle`/`CurveToMesh` or Mesh primitives.
- Branching/arms: duplicate geometry, `RotateEuler` + `TranslateInstances`, merge with `JoinGeometry`.
- Surface Detail (spikes, leaves): `DistributePointsOnFaces` on the asset surface → instance detail meshes aligned with normals.
- Promote controls (branch count, curvature, detail density) via Group Inputs; frame each subsystem (“Body”, “Branches”, “Surface Detail”).
- When combining with scatter pattern, treat the asset subgraph as a reusable node group.

## 4. Modular City / Building Generator
Patterns from Morphic Studio, CG Cookie, Blender Motion Design community.
- Grid/Plane → `DistributePointsOnFaces` for building footprints (apply scale).
- Instance buildings via Collection Info, randomize height/rotation/scale with Random Value + Noise + Color Ramp.
- Repeat Zones extrude floors iteratively; For Each Zones mix fields/instances.
- Plan for roads/green space by excluding scatter regions; add street furniture via additional instancers.
- Frame sections: “Footprints”, “Buildings”, “Streets”.

## 5. Repeat Zones (Iterative Logic)
### Rules of Thumb
- Use `RepeatInput`/`RepeatOutput` when you need a fixed iteration count (e.g., multi-step displacement, smoothing passes).
- Always expose `Iterations` via Group Input and clamp the range to avoid runaway loops.
- Cache intermediate attributes with `CaptureAttribute` if later steps need access to earlier field data.
- Keep the body of the repeat loop minimal—avoid expensive operations unless necessary.

## 6. Simulation Zones (State Across Frames)
- Simulation Input/Output nodes create a zone where geometry from frame N influences frame N+1.
- Only Simulation Output exposes the results; link nothing out of the zone except through that node.
- Remember: anonymous attributes are not persisted—store needed values explicitly inside the simulation state.
- Bake simulations for deterministic playback; note that baking one modifier bakes all simulations on that object.

## 7. Manual Metadata Sidecar
Additional per-node descriptions, socket details, properties, and manual notes are stored at `reference/node_metadata_extras.json` (generated via `python scripts/extract_manual_metadata.py`). Use it to inform planning decisions (e.g., property enums, socket behavior) until the toolkit consumes it automatically.

## Usage Workflow
1. Start with the relevant pattern(s) above; sketch a Mermaid flowchart using the referenced nodes.
2. Translate the flowchart to `graph_json`, exposing Group Inputs/Outputs per the tips.
3. Execute via MCP (`python3 scripts/frame_validation_payload.py --alias <alias>`) to build, validate, frame, and capture the node graph.
4. Log the run in `mcp_run_log.md` + `_archive/session_notes_YYYYMMDD.md`.

Extend this document with additional patterns (hair grooming, curve lofting, attribute mixing) as the project evolves.
