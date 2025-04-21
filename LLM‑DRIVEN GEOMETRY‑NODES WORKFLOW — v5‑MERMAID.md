# LLM‑DRIVEN GEOMETRY‑NODES WORKFLOW — v3‑MERMAID

## ASSETS YOU LOAD IN MEMORY
- **geometry_nodes_min_4_4.json**  
  Lean catalogue: `identifier`, sockets (name, idname, is_output, supports_field), category.  
- **socket_compat.csv**  
  Allowed socket‑type pairs (generated once).

---

## PIPELINE (MCP‑centric)

1. **User brief** → e.g. “Scatter cones on a grid and randomise scale.”  
2. **Mermaid flowchart** (left→right) drafted by the LLM to sketch logic.  
3. **graph_json** generated from the diagram (nodes, links, node_settings).  
4. **LLM checklist self‑validation** using the catalogue + CSV.  
5. When `status = GRAPH_OK`, MCP builds the node tree inside Blender  
   (no `.blend` file required unless another tool needs one).

---

## MERMAID SKETCH RULES (keep syntax simple)

| Rule | Rationale |
|------|-----------|
| `flowchart LR` only | left→right means output→input direction |
| Node syntax | Prefer `n1["MeshCone"]` or `n1(MeshCone)` — avoid parentheses/brackets *inside* labels to prevent Mermaid routing bugs; full Blender type can be preserved in a `%% comment` or later JSON. |
| Edge label = socket name | e.g. `n1 --> |Mesh| n2` |
| Unique IDs (`n1`, `n2` …) | ensures clean mapping to JSON |

**Example sketch**

```mermaid
flowchart LR
  n1["MeshCone"] --> |Mesh| n2["SetPosition"]
  n2 --> |Geometry| n3["Viewer"]
```

## Corresponding graph_json

```json
{
  "nodes":[
    {"id":"n1","type":"GeometryNodeMeshCone"},
    {"id":"n2","type":"GeometryNodeSetPosition"},
    {"id":"n3","type":"GeometryNodeViewer"}
  ],
  "links":[
    {"from":"n1","socket":"Mesh","to":"n2","socket":"Geometry"},
    {"from":"n2","socket":"Geometry","to":"n3","socket":"Geometry"}
  ],
  "node_settings":{
    "n1":{"Vertices":32},
    "n2":{"Offset":[0,0,1]}
  }
}
```

## PROMPT STRUCTURE FOR THE LLM
  1.  CATALOGUE → insert only relevant node rows for this task.
  2.  COMPAT_RULE → identical idnames OK; Float ↔ Int ↔ Bool;
Geometry ↔ Geometry; Vector ↔ Vector; otherwise use socket_compat.csv.

### Instructions
A. Sketch the solution in Mermaid (flowchart LR).
B. Convert the diagram to graph_json.
C. Run the checklist; fix JSON until it passes.
D. Reply exactly in YAML‑ish form:

```yaml
mermaid_code: |
  (flowchart here)
graph_json: |
  { … }
status: GRAPH_OK | ERRORS_FOUND
errors: [ list ]      # empty if GRAPH_OK
```

## CHECKLIST (LLM MUST PASS BEFORE status = GRAPH_OK)
  1.  Every node.type exists in CATALOGUE.
  2.  For each link:
  • source & target IDs exist.
  • source socket → node.outputs && is_output = true.
  • target socket → node.inputs  && is_output = false.
  • (src.idname, dst.idname) appears in socket_compat.csv.
  3.  No duplicate node IDs or links.
  4.  Required inputs without defaults get a link or an explicit value.
  5. **Node‑ID correctness**  
   - When a node lives in the **Geometry** domain, use the *Geometry/Function‑node* idname, **never** the Shader tree equivalent.  
     •`FunctionNodeFloatMath` instead of `ShaderNodeMath`  
     •`FunctionNodeVectorMath` instead of `ShaderNodeVectorMath`  
     •(General rule → prefix `FunctionNode` for math/utility nodes inside Geo‑trees.)

  6. **Group Input / Output sockets**  
     - Before linking, add required IO sockets explicitly:  
       ```python
       node_group.inputs.new('NodeSocketGeometry', 'Geometry')
       node_group.outputs.new('NodeSocketGeometry', 'Geometry')
       ```  
     - Reference them by **name**, *not* by numeric index.

  7. **Always address sockets by name**  
     - `node.inputs['Geometry']`, `node.outputs['Instances']` — never `inputs[0]` or `outputs[1]`, which are unstable across Blender versions.

  8. **Direction guard in code as well**  
     - The builder must raise if `src.is_output == False` *or* `dst.is_output == True` before calling `links.new()`.

  9. **Type‑mismatch remediation**  
     - If the planned link fails the compat check **but base types differ only in dimensionality** (e.g. Float→Vector), auto‑insert a helper node:  
       •`Combine XYZ` for Float→Vector.  
       •`Separate XYZ` for Vector→Float.  
       •`Euler to Rotation` or `Align Euler to Vector` for Float/Vector→Rotation.

  10. **Scalar rotation & scale guidelines**  
      - *Scale* socket accepts **Float** (uniform) or **Vector** (XYZ).  
      - *Rotation* socket accepts **Vector (Euler)** or **Quaternion** — never plain Float.  
      - If only a scalar driver is available, convert via `Combine XYZ` into an Euler vector.

  11. **Material nodes belong in `mat.node_tree`, not the Geometry node group**  
      - Keep shader construction separate; MCP should attach materials after the Geo‑node graph is complete.

  12. **Optional self‑review step**  
      - After building the node tree, iterate over `group.links` and print `from_node.name → to_node.name` as a final sanity echo before returning success to MCP.
  13. *Never* rely on Blender’s modifier to create a fresh node tree you will discard.
    - Get the auto‑tree via `geomod.node_group`; if you need a clean slate,
      call `node_group.nodes.clear()` instead of `bpy.data.node_groups.new()`.

  14. Socket names are version‑specific.  For Blender 4.4:
        - GeometryNodeSubdivideMesh → output **Geometry**
        - GeometryNodeMeshToPoints  → input **Geometry**, output **Points**
        - InstanceOnPoints          → input **Points**, **Instance**, *Scale* (Float), *Rotation* (Vector)

  15. No Shader‑tree nodes inside Geometry‑node graphs.  
      Remove any fallback to `ShaderNode*`; raise an error if the intended
      `FunctionNode*` idname is missing.

  16. Always clear unused modifier‑generated groups to avoid “empty tree”
      warnings.

  17. Target *Rotation* with a **Vector (Euler)**; build it with
      `FunctionNodeCombineXYZ` (idname) and link by name.

  18. **Refresh group reference after destructive ops**  
    If you call any function that can delete or replace the node tree  
    (`node_group.nodes.clear()`, `bpy.data.node_groups.remove(…)`, etc.)  
    reacquire a fresh pointer before continuing:  
    ```python
    node_group = geomod.node_group
    ```

  19. **Step‑by‑step linking & validation**  
      Add one node and one link at a time; immediately verify:  
      ```python
      link = node_group.links.new(out_sock, in_sock)
      assert link.is_valid, "Invalid link created"
      ```  
      This surfaces socket‑name typos or direction errors early.

  20. **Runtime socket‑name checks during development**  
      ```python
      if "Geometry" not in n2.outputs:
          raise KeyError("SubdivideMesh output 'Geometry' not found")
      if "Scale" not in n4.inputs:
          raise KeyError("InstanceOnPoints missing 'Scale' input")
      ```  
      Explicit guards prevent silent failures when Blender renames sockets in future versions.

  21. **Socket‑compatibility test is mandatory, not optional**  
    - For every link, look up `(src.idname, dst.idname)` in `socket_compat.csv`.  
    - If the pair is missing, insert the required conversion node *or* raise an error; never skip the check.

  22. **Iterative checklist loop**  
    1. Build / update the graph.  
    2. Run the **entire** checklist (Rules 1‑21).  
    3. If any item fails → log the issues, fix them, **then restart from Step 1**.  
       Do **not** exit early or assume prior items remain valid after fixes.  
    4. Only when all rules pass in a single run may you emit `status: GRAPH_OK`.  

If any rule fails → status: ERRORS_FOUND + list issues; else GRAPH_OK.

## MCP ACTION AFTER GRAPH_OK
Feed graph_json to your MCP builder to instantiate the node tree.
Optionally run a headless‑Blender validator for extra certainty.

