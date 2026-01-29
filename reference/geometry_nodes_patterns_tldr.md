Geometry Nodes Pattern Library – TL;DR
======================================

## 1. Surface Scattering
- Use `Distribute Points on Faces` (Poisson Disk for non-overlap) + `Instance on Points`.
- Drive rotation/scale via `Random Value` (vector) and noise textures through `Color Ramp` for art-directed patterns.
- Feed density sockets with vertex groups/textures; weight painting gives manual control.
- Scatter collections via `Collection Info` (enable Separate Children, Reset Children, Pick Instance).
- Keep instances unrealized for performance; large scenes may lag beyond ~150k view-dependent instances.

**References:** Blender manual nodes docs; Artisticrender scatter tutorial; Poliigon environment scattering guide.

## 2. Modular City / Buildings
- Base plane/grid → `Distribute Points on Faces` for footprints.
- Instance building modules via `Instance on Points` + `Object Info` or Collection Info; randomize heights with `Random Value` + `Noise`.
- Use Repeat Zones to extrude floors iteratively; For Each zones when mixing fields/constants.
- Organize geography (roads, green spaces) by excluding points, instancing vegetation separately.

**References:** Morphic Studio city generator; CG Cookie BCITY course.

## 3. Rock Generator
- Start from mesh primitives or `Voronoi Fracture` + `Boolean` for silhouettes.
- `Noise/Musgrave Texture → Set Position` for macro detail; `Voronoi Distance` knocks out faces.
- For micro-detail, scatter points on the surface and instance tiny spikes or use `GeometryNodeMusgraveTexture` to perturb normals.
- Use Group Inputs for random orientation, scale, color variation.

**References:** Blender 3D Architect “procedural rocks” tutorial.

## 4. Trees & Bushes
- Use curves (“branch skeleton”) → `Curve to Mesh` with `Curve Circle` profile.
- Arms/branches: duplicate and rotate child curves; randomize via `Rotate Euler` + `Translate Instances`.
- Leaves: `Distribute Points on Faces` of the branch mesh; `Instance on Points` with leaf meshes; align to normals.
- For bushy growth, use `Simulation Zone` to grow branch curves iteratively.

**References:** AskNK tutorial; Blender Guru’s tree/bush walkthroughs.

## 5. Repeat Zone (Loops)
- Enclose iterative logic between Repeat Input/Output (orange zone). Inputs evaluated first iteration, passed to subsequent iterations.
- Use the Iteration socket (starts at 0) to vary per-step offsets. Common for staircases, pyramids, modular floors.

**References:** Blender 5.0 Repeat Zone manual.

## 6. For Each Zone
- Converts fields to constants for nodes that only accept circle inputs.
- Use when you need to evaluate a field once per instance and reuse the value across multiple operations.

**References:** Cristóbal Vila’s For Each tips.

## 7. Simulation Zones
- Each frame depends on the previous state; only Simulation Output exposes results.
- Anonymous attributes aren’t propagated—store needed data explicitly.
- Bake simulations to keep playback deterministic.

**References:** Blender manual – Simulation Zone.

## 8. Motion Graphics / Instances
- Fields + instancing for generating animated patterns (e.g., oscillating columns, waveforms).
- `Scene Time` + Math nodes drive transformations; `Instance on Points` replicates base geometry.

**References:** Blender Motion Design community tutorials.

---

Source files (`geometry_nodes_patterns*.md`) have been condensed here. Update this TL;DR as patterns evolve.
