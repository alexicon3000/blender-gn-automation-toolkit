# Fractal Leaf Instances Stress Test

## Overview
- Built the "Fractal Leaf Instances" graph (grid → points → instanced leaves)
- Applied a merge update to switch leaf geometry to a curve-based twig
- Observed toolkit/catalogue limitations for future improvements

## Findings
1. Catalogue lists FunctionNode math helpers that fail to instantiate in Blender 5.0 GN
2. Field outputs (FunctionNodeRandomValue) can’t feed Set Position Offset without conversion
3. `graph_json` can’t describe Group Input sockets; manual wiring is required
4. Builder returns non-serializable Blender objects in the result
5. Shader vs Function node ambiguity (Blender hides FunctionNodeCombineXYZ, etc.)

## Proposed Fixes
- Mark/remove non-instantiable FunctionNodes from the catalogue or provide Shader fallbacks
- Document/automate a flow for converting field outputs before Set Position Offset
- Extend `graph_json` to define modifier interface sockets
- Sanitize builder results (store node_group.name instead of the object)
- Clarify which Shader nodes are allowed in GN context

## Status
- Merge/diff flow works (diff summaries, validation)
- Validation catches catalogue mismatches, but documentation and catalogue accuracy need improvement
- Next steps added to GUIDE.md
