"""Tests for frame support (creation, export, auto-framing)."""

import pytest
import types


def _make_mock_node(name, bl_idname="GeometryNodeMeshCone", gn_mcp_id=None, location=(0, 0), width=150):
    """Create a mock node object with location and size."""
    props = {}
    if gn_mcp_id:
        props["gn_mcp_id"] = gn_mcp_id

    node = types.SimpleNamespace(
        name=name,
        bl_idname=bl_idname,
        location=types.SimpleNamespace(x=location[0], y=location[1]),
        width=width,
    )
    node.get = lambda k, default=None: props.get(k, default)
    node.keys = lambda: list(props.keys())
    return node


def _make_mock_frame(name, gn_mcp_frame_id=None, location=(0, 0), width=300, height=200,
                     label="", use_custom_color=False, color=(0.5, 0.5, 0.5), shrink=False,
                     description=""):
    """Create a mock Frame node."""
    props = {}
    if gn_mcp_frame_id:
        props["gn_mcp_frame_id"] = gn_mcp_frame_id
    if description:
        props["description"] = description

    frame = types.SimpleNamespace(
        name=name,
        bl_idname="NodeFrame",
        location=types.SimpleNamespace(x=location[0], y=location[1]),
        width=width,
        height=height,
        label=label,
        use_custom_color=use_custom_color,
        color=color,
        shrink=shrink,
    )
    frame.get = lambda k, default=None: props.get(k, default)
    frame.keys = lambda: list(props.keys())
    return frame


def _make_mock_link(from_node, from_socket_name, to_node, to_socket_name):
    """Create a mock link object with actual node references."""
    return types.SimpleNamespace(
        from_node=from_node,
        from_socket=types.SimpleNamespace(name=from_socket_name),
        to_node=to_node,
        to_socket=types.SimpleNamespace(name=to_socket_name),
    )


def _make_mock_node_group(nodes, links):
    """Create a mock node group with nodes and links."""
    return types.SimpleNamespace(nodes=nodes, links=links)


# -- Frame bounds calculation tests ------------------------------------------

class TestCalculateFrameBounds:
    def test_empty_nodes_returns_default(self, toolkit):
        x, y, w, h = toolkit["_calculate_frame_bounds"]([])
        assert x == 0
        assert y == 0
        assert w == 200
        assert h == 100

    def test_single_node(self, toolkit):
        node = _make_mock_node("Test", location=(100, 200))
        x, y, w, h = toolkit["_calculate_frame_bounds"]([node])
        # Should have padding around the node
        assert x < 100  # Left of node
        assert y > 200  # Above node (y increases upward)
        assert w > 150  # Node width + padding
        assert h > 150  # Node height estimate + padding

    def test_multiple_nodes(self, toolkit):
        nodes = [
            _make_mock_node("A", location=(0, 0)),
            _make_mock_node("B", location=(200, 100)),
            _make_mock_node("C", location=(100, -50)),
        ]
        x, y, w, h = toolkit["_calculate_frame_bounds"](nodes)
        # Frame should encompass all nodes
        assert x < 0  # Left of leftmost node
        assert y > 100  # Above topmost node
        assert w > 350  # Span from 0 to 200+node_width + padding


# -- Frame export tests ------------------------------------------------------

class TestExportFrames:
    def test_no_frames_returns_empty(self, toolkit):
        nodes = [_make_mock_node("Test")]
        ng = _make_mock_node_group(nodes, [])
        result = toolkit["_export_frames"](ng, {"Test": [0, 0]})
        assert result == []

    def test_exports_basic_frame(self, toolkit):
        # Node at (50, 50)
        node = _make_mock_node("grid", gn_mcp_id="grid", location=(50, 50))
        # Frame covering node (location is top-left, extends down)
        frame = _make_mock_frame(
            "Frame",
            gn_mcp_frame_id="test_frame",
            location=(0, 100),  # Top at y=100
            width=200,
            height=100,  # Bottom at y=0
            label="Test Frame",
        )
        ng = _make_mock_node_group([node, frame], [])
        node_positions = {"grid": [50, 50]}

        result = toolkit["_export_frames"](ng, node_positions)
        assert len(result) == 1
        assert result[0]["id"] == "test_frame"
        assert result[0]["label"] == "Test Frame"
        assert "grid" in result[0]["nodes"]

    def test_exports_frame_without_positions_dict(self, toolkit):
        node = _make_mock_node("grid", gn_mcp_id="grid", location=(25, 25))
        frame = _make_mock_frame(
            "Frame",
            gn_mcp_frame_id="test_frame",
            location=(0, 60),
            width=100,
            height=80,
        )
        ng = _make_mock_node_group([node, frame], [])

        result = toolkit["_export_frames"](ng, {})
        assert len(result) == 1
        assert "grid" in result[0]["nodes"]

    def test_exports_frame_with_color(self, toolkit):
        frame = _make_mock_frame(
            "ColorFrame",
            gn_mcp_frame_id="colored",
            use_custom_color=True,
            color=(0.2, 0.4, 0.8),
        )
        ng = _make_mock_node_group([frame], [])

        result = toolkit["_export_frames"](ng, {})
        assert len(result) == 1
        assert "color" in result[0]
        assert result[0]["color"][0] == pytest.approx(0.2)
        assert result[0]["color"][1] == pytest.approx(0.4)
        assert result[0]["color"][2] == pytest.approx(0.8)

    def test_exports_frame_with_shrink(self, toolkit):
        frame = _make_mock_frame(
            "ShrunkFrame",
            gn_mcp_frame_id="shrunk",
            shrink=True,
        )
        ng = _make_mock_node_group([frame], [])

        result = toolkit["_export_frames"](ng, {})
        assert len(result) == 1
        assert result[0].get("shrink") is True

    def test_exports_frame_with_description(self, toolkit):
        frame = _make_mock_frame(
            "DescFrame",
            gn_mcp_frame_id="desc",
            description="This is a test description",
        )
        ng = _make_mock_node_group([frame], [])

        result = toolkit["_export_frames"](ng, {})
        assert len(result) == 1
        assert result[0].get("text") == "This is a test description"

    def test_excludes_frames_from_containment(self, toolkit):
        # Frame A at (0, 100), Frame B at (50, 80) - B is inside A's bounds
        frame_a = _make_mock_frame(
            "FrameA",
            gn_mcp_frame_id="frame_a",
            location=(0, 100),
            width=200,
            height=150,
        )
        frame_b = _make_mock_frame(
            "FrameB",
            gn_mcp_frame_id="frame_b",
            location=(50, 80),
            width=100,
            height=50,
        )
        ng = _make_mock_node_group([frame_a, frame_b], [])

        result = toolkit["_export_frames"](ng, {})
        # Neither frame should contain the other
        for frame_spec in result:
            assert "frame_a" not in frame_spec["nodes"]
            assert "frame_b" not in frame_spec["nodes"]


class TestClearManagedFrames:
    def test_removes_only_managed_frames(self, toolkit):
        managed = _make_mock_frame(
            "Managed",
            gn_mcp_frame_id="frame_managed",
        )
        manual = _make_mock_frame(
            "Manual",
            gn_mcp_frame_id=None,
        )
        manual.keys = lambda: []

        nodes = [managed, manual]
        node_group = types.SimpleNamespace(nodes=nodes)

        toolkit["_clear_managed_frames"](node_group)

        assert managed not in node_group.nodes
        assert manual in node_group.nodes


class _MockFrameNode:
    """Mock frame node that supports item assignment like Blender nodes."""
    def __init__(self, name):
        self.name = name
        self.bl_idname = "NodeFrame"
        self.location = types.SimpleNamespace(x=0, y=0)
        self.width = 200
        self.height = 100
        self.label = ""
        self.use_custom_color = False
        self.color = (0.5, 0.5, 0.5)
        self.shrink = False
        self._props = {}

    def __setitem__(self, key, value):
        self._props[key] = value

    def __getitem__(self, key):
        return self._props[key]

    def get(self, key, default=None):
        return self._props.get(key, default)

    def keys(self):
        return list(self._props.keys())


class TestApplyFramesDuplicateIds:
    def test_duplicate_frame_ids_reported_as_error(self, toolkit):
        """Duplicate frame IDs should be skipped and logged as errors."""
        node_a = _make_mock_node("a", gn_mcp_id="a")
        node_b = _make_mock_node("b", gn_mcp_id="b")

        # Mock node_group with a nodes list that supports iteration and .new()
        created_frames = []
        class MockNodeList(list):
            def new(self, node_type):
                frame = _MockFrameNode(f"Frame_{len(created_frames)}")
                created_frames.append(frame)
                return frame

        nodes = MockNodeList([node_a, node_b])
        node_group = types.SimpleNamespace(nodes=nodes)

        node_map = {"a": node_a, "b": node_b}
        frames_spec = [
            {"id": "same_id", "label": "First", "nodes": ["a"]},
            {"id": "same_id", "label": "Duplicate", "nodes": ["b"]},  # Duplicate!
            {"id": "unique_id", "label": "Unique", "nodes": ["a", "b"]},
        ]
        errors = []

        toolkit["_apply_frames"](node_group, node_map, frames_spec, errors)

        # Should have one error about duplicate ID
        assert len(errors) == 1
        assert "Duplicate frame ID" in errors[0]
        assert "same_id" in errors[0]

        # Should have created only 2 frames (not 3)
        assert len(created_frames) == 2


# -- Auto-framing by connectivity tests --------------------------------------

class TestAutoFrameByConnectivity:
    def test_empty_graph_returns_empty(self, toolkit):
        ng = _make_mock_node_group([], [])
        result = toolkit["_auto_frame_by_connectivity"](ng)
        assert result == []

    def test_single_node_no_frame(self, toolkit):
        """Single isolated nodes shouldn't get their own frame."""
        nodes = [_make_mock_node("lone", gn_mcp_id="lone")]
        ng = _make_mock_node_group(nodes, [])
        result = toolkit["_auto_frame_by_connectivity"](ng)
        assert result == []

    def test_connected_pair_gets_frame(self, toolkit):
        """Two connected nodes should get a frame."""
        node_a = _make_mock_node("a", "GeometryNodeMeshGrid", gn_mcp_id="a")
        node_b = _make_mock_node("b", "GeometryNodeMeshToPoints", gn_mcp_id="b")
        link = _make_mock_link(node_a, "Mesh", node_b, "Mesh")

        ng = _make_mock_node_group([node_a, node_b], [link])
        result = toolkit["_auto_frame_by_connectivity"](ng)

        assert len(result) == 1
        assert set(result[0]["nodes"]) == {"a", "b"}
        assert "color" in result[0]

    def test_two_separate_components(self, toolkit):
        """Two disconnected pairs should get two frames."""
        # Component 1: a -> b
        node_a = _make_mock_node("a", gn_mcp_id="a")
        node_b = _make_mock_node("b", gn_mcp_id="b")
        link_ab = _make_mock_link(node_a, "Out", node_b, "In")

        # Component 2: c -> d
        node_c = _make_mock_node("c", gn_mcp_id="c")
        node_d = _make_mock_node("d", gn_mcp_id="d")
        link_cd = _make_mock_link(node_c, "Out", node_d, "In")

        ng = _make_mock_node_group([node_a, node_b, node_c, node_d], [link_ab, link_cd])
        result = toolkit["_auto_frame_by_connectivity"](ng)

        assert len(result) == 2
        node_sets = [set(f["nodes"]) for f in result]
        assert {"a", "b"} in node_sets
        assert {"c", "d"} in node_sets

    def test_excludes_group_io_from_connectivity(self, toolkit):
        """Group Input/Output shouldn't be included in components."""
        node_a = _make_mock_node("a", gn_mcp_id="a")
        node_b = _make_mock_node("b", gn_mcp_id="b")
        group_input = _make_mock_node("Group Input", "NodeGroupInput")
        group_output = _make_mock_node("Group Output", "NodeGroupOutput")

        link_ab = _make_mock_link(node_a, "Out", node_b, "In")
        link_input = _make_mock_link(group_input, "Value", node_a, "In")
        link_output = _make_mock_link(node_b, "Out", group_output, "Geometry")

        ng = _make_mock_node_group(
            [node_a, node_b, group_input, group_output],
            [link_ab, link_input, link_output]
        )
        result = toolkit["_auto_frame_by_connectivity"](ng)

        # Should have one frame with a and b, not including group IO
        assert len(result) == 1
        assert set(result[0]["nodes"]) == {"a", "b"}


# -- Auto-framing by type tests ----------------------------------------------

class TestAutoFrameByType:
    def test_empty_graph_returns_empty(self, toolkit):
        ng = _make_mock_node_group([], [])
        result = toolkit["_auto_frame_by_type"](ng)
        assert result == []

    def test_single_node_no_frame(self, toolkit):
        """Single node of a type shouldn't get its own frame."""
        nodes = [_make_mock_node("cone", "GeometryNodeMeshCone", gn_mcp_id="cone")]
        ng = _make_mock_node_group(nodes, [])
        result = toolkit["_auto_frame_by_type"](ng)
        assert result == []

    def test_mesh_nodes_grouped(self, toolkit):
        """Multiple mesh nodes should be grouped together."""
        nodes = [
            _make_mock_node("grid", "GeometryNodeMeshGrid", gn_mcp_id="grid"),
            _make_mock_node("cone", "GeometryNodeMeshCone", gn_mcp_id="cone"),
            _make_mock_node("cube", "GeometryNodeMeshCube", gn_mcp_id="cube"),
        ]
        ng = _make_mock_node_group(nodes, [])
        result = toolkit["_auto_frame_by_type"](ng)

        assert len(result) == 1
        assert result[0]["id"] == "type_mesh"
        assert "Mesh" in result[0]["label"]
        assert set(result[0]["nodes"]) == {"grid", "cone", "cube"}

    def test_multiple_type_groups(self, toolkit):
        """Nodes of different types should be in different frames."""
        nodes = [
            _make_mock_node("grid", "GeometryNodeMeshGrid", gn_mcp_id="grid"),
            _make_mock_node("cone", "GeometryNodeMeshCone", gn_mcp_id="cone"),
            _make_mock_node("curve1", "GeometryNodeCurvePrimitiveLine", gn_mcp_id="curve1"),
            _make_mock_node("curve2", "GeometryNodeCurvePrimitiveCircle", gn_mcp_id="curve2"),
        ]
        ng = _make_mock_node_group(nodes, [])
        result = toolkit["_auto_frame_by_type"](ng)

        assert len(result) == 2
        ids = {f["id"] for f in result}
        assert "type_mesh" in ids
        assert "type_curve" in ids

    def test_excludes_group_io_and_frames(self, toolkit):
        """Group Input/Output and Frame nodes should be excluded."""
        nodes = [
            _make_mock_node("grid", "GeometryNodeMeshGrid", gn_mcp_id="grid"),
            _make_mock_node("cone", "GeometryNodeMeshCone", gn_mcp_id="cone"),
            _make_mock_node("Group Input", "NodeGroupInput"),
            _make_mock_node("Group Output", "NodeGroupOutput"),
            _make_mock_frame("Frame", gn_mcp_frame_id="frame"),
        ]
        ng = _make_mock_node_group(nodes, [])
        result = toolkit["_auto_frame_by_type"](ng)

        # Should only have mesh frame
        assert len(result) == 1
        for frame in result:
            assert "Group Input" not in frame["nodes"]
            assert "Group Output" not in frame["nodes"]
            assert "frame" not in frame["nodes"]


# -- auto_frame_graph wrapper tests ------------------------------------------

class TestAutoFrameGraph:
    def test_invalid_strategy_raises(self, toolkit):
        ng = _make_mock_node_group([], [])
        with pytest.raises(ValueError, match="Unknown auto-frame strategy"):
            toolkit["auto_frame_graph"](ng, strategy="invalid")

    def test_connectivity_strategy(self, toolkit):
        node_a = _make_mock_node("a", gn_mcp_id="a")
        node_b = _make_mock_node("b", gn_mcp_id="b")
        link = _make_mock_link(node_a, "Out", node_b, "In")
        ng = _make_mock_node_group([node_a, node_b], [link])

        result = toolkit["auto_frame_graph"](ng, strategy="connectivity")
        assert len(result) == 1
        assert set(result[0]["nodes"]) == {"a", "b"}

    def test_type_strategy(self, toolkit):
        nodes = [
            _make_mock_node("grid", "GeometryNodeMeshGrid", gn_mcp_id="grid"),
            _make_mock_node("cone", "GeometryNodeMeshCone", gn_mcp_id="cone"),
        ]
        ng = _make_mock_node_group(nodes, [])

        result = toolkit["auto_frame_graph"](ng, strategy="type")
        assert len(result) == 1
        assert result[0]["id"] == "type_mesh"
