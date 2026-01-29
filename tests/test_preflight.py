"""Tests for validate_graph_json_preflight() and helpers."""

import pytest


# -- Valid graph fixture ---------------------------------------------------

VALID_GRAPH = {
    "nodes": [
        {"id": "grid", "type": "GeometryNodeMeshGrid"},
        {"id": "to_points", "type": "GeometryNodeMeshToPoints"},
        {"id": "instance", "type": "GeometryNodeInstanceOnPoints"},
        {"id": "cone", "type": "GeometryNodeMeshCone"},
    ],
    "links": [
        {"from": "grid", "from_socket": "Mesh", "to": "to_points", "to_socket": "Mesh"},
        {"from": "to_points", "from_socket": "Points", "to": "instance", "to_socket": "Points"},
        {"from": "cone", "from_socket": "Mesh", "to": "instance", "to_socket": "Instance"},
        {"from": "instance", "from_socket": "Instances", "to": "__GROUP_OUTPUT__", "to_socket": "Geometry"},
    ],
    "node_settings": {
        "grid": {"Vertices X": 10, "Vertices Y": 10, "Size X": 5.0, "Size Y": 5.0},
        "cone": {"Vertices": 32, "Radius Top": 0.0, "Radius Bottom": 0.5, "Depth": 1.5},
        "instance": {"Scale": [0.5, 0.5, 0.5]},
    },
}


def test_valid_graph_passes(toolkit):
    result = toolkit["validate_graph_json_preflight"](VALID_GRAPH)
    assert result["status"] == "OK", f"Issues: {result['issues']}"
    assert len(result["issues"]) == 0


def test_empty_graph_fails(toolkit):
    result = toolkit["validate_graph_json_preflight"]({"nodes": [], "links": []})
    assert result["status"] == "ERROR"
    assert any("no nodes" in issue for issue in result["issues"])


def test_missing_node_type_fails(toolkit):
    graph = {
        "nodes": [
            {"id": "n1", "type": "GeometryNodeDoesNotExist"},
        ],
        "links": [],
    }
    result = toolkit["validate_graph_json_preflight"](graph)
    assert result["status"] == "ERROR"
    assert any("Unknown node types" in issue for issue in result["issues"])


def test_duplicate_node_ids_fail(toolkit):
    graph = {
        "nodes": [
            {"id": "n1", "type": "GeometryNodeMeshCone"},
            {"id": "n1", "type": "GeometryNodeMeshCube"},
        ],
        "links": [],
    }
    result = toolkit["validate_graph_json_preflight"](graph)
    assert result["status"] == "ERROR"
    assert any("Duplicate node IDs" in issue for issue in result["issues"])


def test_bad_socket_name_fails(toolkit):
    graph = {
        "nodes": [
            {"id": "cone", "type": "GeometryNodeMeshCone"},
        ],
        "links": [
            {"from": "cone", "from_socket": "FakeSocket", "to": "__GROUP_OUTPUT__", "to_socket": "Geometry"},
        ],
    }
    result = toolkit["validate_graph_json_preflight"](graph)
    assert result["status"] == "ERROR"
    assert any("Unknown output socket" in issue for issue in result["issues"])


def test_link_to_unknown_node_fails(toolkit):
    graph = {
        "nodes": [
            {"id": "cone", "type": "GeometryNodeMeshCone"},
        ],
        "links": [
            {"from": "cone", "from_socket": "Mesh", "to": "missing_node", "to_socket": "Geometry"},
        ],
    }
    result = toolkit["validate_graph_json_preflight"](graph)
    assert result["status"] == "ERROR"
    assert any("unknown node" in issue.lower() for issue in result["issues"])


def test_settings_for_unknown_node_fails(toolkit):
    graph = {
        "nodes": [
            {"id": "cone", "type": "GeometryNodeMeshCone"},
        ],
        "links": [],
        "node_settings": {
            "nonexistent": {"Vertices": 10},
        },
    }
    result = toolkit["validate_graph_json_preflight"](graph)
    assert result["status"] == "ERROR"
    assert any("unknown node" in issue.lower() for issue in result["issues"])


def test_settings_with_bad_input_name_fails(toolkit):
    graph = {
        "nodes": [
            {"id": "cone", "type": "GeometryNodeMeshCone"},
        ],
        "links": [],
        "node_settings": {
            "cone": {"FakeInput": 10},
        },
    }
    result = toolkit["validate_graph_json_preflight"](graph)
    assert result["status"] == "ERROR"
    assert any("Unknown input socket" in issue for issue in result["issues"])


def test_settings_wrong_value_type_fails(toolkit):
    graph = {
        "nodes": [
            {"id": "cone", "type": "GeometryNodeMeshCone"},
        ],
        "links": [],
        "node_settings": {
            "cone": {"Vertices": "not_a_number"},
        },
    }
    result = toolkit["validate_graph_json_preflight"](graph)
    assert result["status"] == "ERROR"
    assert any("Invalid value" in issue for issue in result["issues"])


def test_group_output_link_passes(toolkit):
    """Links to __GROUP_OUTPUT__ should not produce 'unknown node' errors."""
    graph = {
        "nodes": [
            {"id": "cone", "type": "GeometryNodeMeshCone"},
        ],
        "links": [
            {"from": "cone", "from_socket": "Mesh", "to": "__GROUP_OUTPUT__", "to_socket": "Geometry"},
        ],
    }
    result = toolkit["validate_graph_json_preflight"](graph)
    # Should not have "unknown node" errors
    assert not any("unknown node" in issue.lower() for issue in result["issues"])


# -- _validate_value tests ------------------------------------------------

class TestValidateValue:
    def test_vector_valid(self, toolkit):
        ok, err = toolkit["_validate_value"]("VECTOR", [1.0, 2.0, 3.0])
        assert ok

    def test_vector_wrong_length(self, toolkit):
        ok, err = toolkit["_validate_value"]("VECTOR", [1.0, 2.0])
        assert not ok

    def test_vector_not_list(self, toolkit):
        ok, err = toolkit["_validate_value"]("VECTOR", 3.0)
        assert not ok

    def test_color_valid(self, toolkit):
        ok, err = toolkit["_validate_value"]("RGBA", [1.0, 0.0, 0.0, 1.0])
        assert ok

    def test_color_wrong_length(self, toolkit):
        ok, err = toolkit["_validate_value"]("RGBA", [1.0, 0.0, 0.0])
        assert not ok

    def test_bool_valid(self, toolkit):
        ok, err = toolkit["_validate_value"]("BOOLEAN", True)
        assert ok

    def test_bool_wrong_type(self, toolkit):
        ok, err = toolkit["_validate_value"]("BOOLEAN", 1)
        assert not ok

    def test_int_valid(self, toolkit):
        ok, err = toolkit["_validate_value"]("INT", 42)
        assert ok

    def test_int_wrong_type(self, toolkit):
        ok, err = toolkit["_validate_value"]("INT", 42.5)
        assert not ok

    def test_float_valid(self, toolkit):
        ok, err = toolkit["_validate_value"]("VALUE", 3.14)
        assert ok

    def test_float_accepts_int(self, toolkit):
        ok, err = toolkit["_validate_value"]("VALUE", 3)
        assert ok

    def test_string_valid(self, toolkit):
        ok, err = toolkit["_validate_value"]("STRING", "hello")
        assert ok

    def test_geometry_always_fails(self, toolkit):
        ok, err = toolkit["_validate_value"]("GEOMETRY", None)
        assert not ok

    def test_unknown_type_passes(self, toolkit):
        ok, err = toolkit["_validate_value"]("UNKNOWN_TYPE", "anything")
        assert ok
