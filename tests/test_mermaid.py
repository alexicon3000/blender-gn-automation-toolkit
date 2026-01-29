"""Tests for Mermaid parsing and catalogue-derived type map."""

import pytest


BASIC_MERMAID = """flowchart LR
  n1["MeshGrid"] -->|Mesh| n2["MeshToPoints"]
  n2 -->|Points| n3["InstanceOnPoints"]
  n4["MeshCone"] -->|Mesh| n3
  n3 -->|Instances| __GROUP_OUTPUT__
"""


def test_basic_parse(toolkit):
    result = toolkit["parse_mermaid_to_graph_json"](BASIC_MERMAID)
    assert len(result["nodes"]) == 4
    assert len(result["links"]) == 4
    assert result["parse_warnings"] == []


def test_node_types_resolved(toolkit):
    result = toolkit["parse_mermaid_to_graph_json"](BASIC_MERMAID)
    type_by_id = {n["id"]: n["type"] for n in result["nodes"]}
    assert type_by_id["n1"] == "GeometryNodeMeshGrid"
    assert type_by_id["n2"] == "GeometryNodeMeshToPoints"
    assert type_by_id["n3"] == "GeometryNodeInstanceOnPoints"
    assert type_by_id["n4"] == "GeometryNodeMeshCone"


def test_group_output_handled(toolkit):
    result = toolkit["parse_mermaid_to_graph_json"](BASIC_MERMAID)
    # __GROUP_OUTPUT__ should appear in links but not as a regular node
    output_links = [l for l in result["links"] if l["to"] == "__GROUP_OUTPUT__"]
    assert len(output_links) == 1
    assert output_links[0]["to_socket"] == "Geometry"


def test_socket_names_preserved(toolkit):
    result = toolkit["parse_mermaid_to_graph_json"](BASIC_MERMAID)
    # First link: n1 --Mesh--> n2
    first_link = result["links"][0]
    assert first_link["from_socket"] == "Mesh"
    assert first_link["to_socket"] == "Mesh"


def test_unknown_type_warns(toolkit):
    mermaid = """flowchart LR
  n1["CompletelyFakeNode"] -->|Out| __GROUP_OUTPUT__
"""
    result = toolkit["parse_mermaid_to_graph_json"](mermaid)
    assert len(result["parse_warnings"]) > 0
    assert any("CompletelyFakeNode" in w for w in result["parse_warnings"])


def test_full_identifier_accepted(toolkit):
    """Full Blender identifiers should pass through as-is."""
    mermaid = """flowchart LR
  n1["GeometryNodeMeshCone"] -->|Mesh| __GROUP_OUTPUT__
"""
    result = toolkit["parse_mermaid_to_graph_json"](mermaid)
    type_by_id = {n["id"]: n["type"] for n in result["nodes"]}
    assert type_by_id["n1"] == "GeometryNodeMeshCone"
    assert result["parse_warnings"] == []


def test_custom_type_map_overrides(toolkit):
    """User-provided node_type_map should override catalogue entries."""
    mermaid = """flowchart LR
  n1["MyCustom"] -->|Out| __GROUP_OUTPUT__
"""
    result = toolkit["parse_mermaid_to_graph_json"](
        mermaid,
        node_type_map={"MyCustom": "GeometryNodeMeshCube"},
    )
    type_by_id = {n["id"]: n["type"] for n in result["nodes"]}
    assert type_by_id["n1"] == "GeometryNodeMeshCube"
    assert result["parse_warnings"] == []


# -- _build_mermaid_type_map tests ----------------------------------------

def test_type_map_has_many_entries(toolkit):
    type_map = toolkit["_build_mermaid_type_map"]()
    assert len(type_map) > 500, "Map should cover catalogue + label + prefix variants"


def test_type_map_label_based_key(toolkit):
    """Labels with spaces removed should be valid keys."""
    type_map = toolkit["_build_mermaid_type_map"]()
    # "Random Value" → "RandomValue" → FunctionNodeRandomValue
    assert type_map.get("RandomValue") == "FunctionNodeRandomValue"


def test_type_map_identifier_stripped_key(toolkit):
    """Identifiers with prefix stripped should be valid keys."""
    type_map = toolkit["_build_mermaid_type_map"]()
    # GeometryNodeMeshCone → strip "GeometryNode" → MeshCone
    assert type_map.get("MeshCone") == "GeometryNodeMeshCone"


def test_type_map_full_identifier_key(toolkit):
    """Full identifiers should map to themselves."""
    type_map = toolkit["_build_mermaid_type_map"]()
    assert type_map.get("GeometryNodeMeshCone") == "GeometryNodeMeshCone"


def test_type_map_manual_overrides(toolkit):
    """GroupInput/GroupOutput should be present from manual overrides."""
    type_map = toolkit["_build_mermaid_type_map"]()
    assert type_map.get("GroupInput") == "NodeGroupInput"
    assert type_map.get("GroupOutput") == "NodeGroupOutput"


def test_type_map_shader_node_correct(toolkit):
    """Math, CombineXYZ etc. should map to ShaderNode* (not FunctionNode*)."""
    type_map = toolkit["_build_mermaid_type_map"]()
    assert type_map.get("Math") == "ShaderNodeMath"
    assert type_map.get("CombineXYZ") == "ShaderNodeCombineXYZ"
    assert type_map.get("VectorMath") == "ShaderNodeVectorMath"


def test_multiline_mermaid(toolkit):
    """Multi-line Mermaid with separate node definitions."""
    mermaid = """flowchart LR
  n1["MeshCone"]
  n2["SetPosition"]
  n1 -->|Mesh| n2
  n2 -->|Geometry| __GROUP_OUTPUT__
"""
    result = toolkit["parse_mermaid_to_graph_json"](mermaid)
    assert len(result["nodes"]) == 2
    assert len(result["links"]) == 2
    type_by_id = {n["id"]: n["type"] for n in result["nodes"]}
    assert type_by_id["n1"] == "GeometryNodeMeshCone"
    assert type_by_id["n2"] == "GeometryNodeSetPosition"
