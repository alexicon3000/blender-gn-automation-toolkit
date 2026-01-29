"""Tests for diff/merge logic (_diff_graph, _normalize_link_spec, _link_key)."""

import pytest
import types


def _make_mock_node(name, bl_idname="GeometryNodeMeshCone", gn_mcp_id=None):
    """Create a mock node object."""
    node = types.SimpleNamespace(
        name=name,
        bl_idname=bl_idname,
    )
    # Simulate node[prop] access via get()
    props = {}
    if gn_mcp_id:
        props["gn_mcp_id"] = gn_mcp_id
    node.get = lambda k, default=None: props.get(k, default)
    return node


def _make_mock_link(from_node_name, from_socket_name, to_node_name, to_socket_name):
    """Create a mock link object."""
    return types.SimpleNamespace(
        from_node=types.SimpleNamespace(name=from_node_name),
        from_socket=types.SimpleNamespace(name=from_socket_name),
        to_node=types.SimpleNamespace(name=to_node_name),
        to_socket=types.SimpleNamespace(name=to_socket_name),
    )


def _make_mock_node_group(nodes, links):
    """Create a mock node group with nodes and links."""
    return types.SimpleNamespace(nodes=nodes, links=links)


# -- _normalize_link_spec tests ------------------------------------------

class TestNormalizeLinkSpec:
    def test_full_spec(self, toolkit):
        spec = {
            "from": "a",
            "from_socket": "Out",
            "to": "b",
            "to_socket": "In",
        }
        result = toolkit["_normalize_link_spec"](spec)
        assert result == ("a", "Out", "b", "In")

    def test_shared_socket_name(self, toolkit):
        """When only 'socket' is provided, it's used for both."""
        spec = {"from": "a", "to": "b", "socket": "Geometry"}
        result = toolkit["_normalize_link_spec"](spec)
        assert result == ("a", "Geometry", "b", "Geometry")

    def test_to_socket_overrides_socket(self, toolkit):
        """Explicit to_socket takes precedence over shared socket."""
        spec = {
            "from": "a",
            "to": "b",
            "socket": "Geometry",
            "to_socket": "Mesh",
        }
        result = toolkit["_normalize_link_spec"](spec)
        assert result == ("a", "Geometry", "b", "Mesh")


# -- _link_key tests -----------------------------------------------------

class TestLinkKey:
    def test_basic(self, toolkit):
        key = toolkit["_link_key"]("a", "Out", "b", "In")
        assert key == ("a", "Out", "b", "In")

    def test_tuple_hashable(self, toolkit):
        key = toolkit["_link_key"]("a", "Out", "b", "In")
        d = {key: "value"}
        assert d[key] == "value"


# -- _gather_existing_nodes tests ----------------------------------------

class TestGatherExistingNodes:
    def test_excludes_group_io(self, toolkit):
        nodes = [
            _make_mock_node("Grid", "GeometryNodeMeshGrid"),
            _make_mock_node("Group Input", "NodeGroupInput"),
            _make_mock_node("Group Output", "NodeGroupOutput"),
        ]
        ng = _make_mock_node_group(nodes, [])
        result = toolkit["_gather_existing_nodes"](ng)
        assert "Grid" in result
        assert "Group Input" not in result
        assert "Group Output" not in result

    def test_uses_gn_mcp_id_if_present(self, toolkit):
        nodes = [
            _make_mock_node("Grid.001", "GeometryNodeMeshGrid", gn_mcp_id="my_grid"),
        ]
        ng = _make_mock_node_group(nodes, [])
        result = toolkit["_gather_existing_nodes"](ng)
        assert "my_grid" in result
        assert "Grid.001" not in result


# -- _gather_existing_links tests ----------------------------------------

class TestGatherExistingLinks:
    def test_basic(self, toolkit):
        links = [
            _make_mock_link("Grid", "Mesh", "ToPoints", "Mesh"),
        ]
        ng = _make_mock_node_group([], links)
        result = toolkit["_gather_existing_links"](ng)
        assert ("Grid", "Mesh", "ToPoints", "Mesh") in result

    def test_skips_broken_links(self, toolkit):
        broken = types.SimpleNamespace(from_node=None, to_node=None, from_socket=None, to_socket=None)
        ng = _make_mock_node_group([], [broken])
        result = toolkit["_gather_existing_links"](ng)
        assert len(result) == 0


# -- _diff_graph tests ---------------------------------------------------

class TestDiffGraph:
    def test_empty_existing_all_nodes_added(self, toolkit):
        ng = _make_mock_node_group([], [])
        graph_json = {
            "nodes": [
                {"id": "cone", "type": "GeometryNodeMeshCone"},
                {"id": "cube", "type": "GeometryNodeMeshCube"},
            ],
            "links": [],
        }
        diff = toolkit["_diff_graph"](ng, graph_json)
        assert set(diff["nodes_to_add"]) == {"cone", "cube"}
        assert diff["nodes_to_update"] == []
        assert diff["nodes_to_remove"] == []

    def test_existing_node_marked_for_update(self, toolkit):
        nodes = [_make_mock_node("cone", "GeometryNodeMeshCone")]
        ng = _make_mock_node_group(nodes, [])
        graph_json = {
            "nodes": [{"id": "cone", "type": "GeometryNodeMeshCone"}],
            "links": [],
        }
        diff = toolkit["_diff_graph"](ng, graph_json)
        assert diff["nodes_to_add"] == []
        assert diff["nodes_to_update"] == ["cone"]
        assert diff["nodes_to_remove"] == []

    def test_extra_existing_node_removed(self, toolkit):
        nodes = [
            _make_mock_node("cone", "GeometryNodeMeshCone"),
            _make_mock_node("cube", "GeometryNodeMeshCube"),
        ]
        ng = _make_mock_node_group(nodes, [])
        graph_json = {
            "nodes": [{"id": "cone", "type": "GeometryNodeMeshCone"}],
            "links": [],
        }
        diff = toolkit["_diff_graph"](ng, graph_json)
        assert diff["nodes_to_remove"] == ["cube"]

    def test_link_added(self, toolkit):
        ng = _make_mock_node_group([], [])
        graph_json = {
            "nodes": [],
            "links": [
                {"from": "a", "from_socket": "Out", "to": "b", "to_socket": "In"},
            ],
        }
        diff = toolkit["_diff_graph"](ng, graph_json)
        assert ("a", "Out", "b", "In") in diff["links_to_add"]

    def test_link_kept(self, toolkit):
        links = [_make_mock_link("a", "Out", "b", "In")]
        ng = _make_mock_node_group([], links)
        graph_json = {
            "nodes": [],
            "links": [
                {"from": "a", "from_socket": "Out", "to": "b", "to_socket": "In"},
            ],
        }
        diff = toolkit["_diff_graph"](ng, graph_json)
        assert ("a", "Out", "b", "In") in diff["links_to_keep"]
        assert diff["links_to_add"] == []

    def test_link_removed(self, toolkit):
        links = [_make_mock_link("a", "Out", "b", "In")]
        ng = _make_mock_node_group([], links)
        graph_json = {"nodes": [], "links": []}
        diff = toolkit["_diff_graph"](ng, graph_json)
        assert ("a", "Out", "b", "In") in diff["links_to_remove"]

    def test_full_diff_scenario(self, toolkit):
        """Comprehensive diff: some nodes/links added, updated, removed."""
        nodes = [
            _make_mock_node("keep", "GeometryNodeMeshCone"),
            _make_mock_node("remove_me", "GeometryNodeMeshCube"),
        ]
        links = [
            _make_mock_link("keep", "Mesh", "remove_me", "Mesh"),
            _make_mock_link("keep", "Mesh", "other", "In"),
        ]
        ng = _make_mock_node_group(nodes, links)

        graph_json = {
            "nodes": [
                {"id": "keep", "type": "GeometryNodeMeshCone"},
                {"id": "add_me", "type": "GeometryNodeMeshGrid"},
            ],
            "links": [
                {"from": "keep", "from_socket": "Mesh", "to": "add_me", "to_socket": "Geometry"},
            ],
        }
        diff = toolkit["_diff_graph"](ng, graph_json)

        assert "add_me" in diff["nodes_to_add"]
        assert "keep" in diff["nodes_to_update"]
        assert "remove_me" in diff["nodes_to_remove"]
        assert ("keep", "Mesh", "add_me", "Geometry") in diff["links_to_add"]
        assert ("keep", "Mesh", "remove_me", "Mesh") in diff["links_to_remove"]
        assert ("keep", "Mesh", "other", "In") in diff["links_to_remove"]
