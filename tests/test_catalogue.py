"""Tests for catalogue loading, node lookup, socket compat, and version inference."""


def test_catalogue_loads(toolkit):
    cat = toolkit["load_node_catalogue"]()
    assert isinstance(cat, list)
    assert len(cat) > 100, "Catalogue should have >100 node definitions"


def test_catalogue_has_identifiers(toolkit):
    cat = toolkit["load_node_catalogue"]()
    for node in cat:
        assert "identifier" in node, f"Node missing identifier: {node}"
        assert "label" in node, f"Node missing label: {node}"


def test_node_lookup_known_type(toolkit):
    spec = toolkit["get_node_spec"]("GeometryNodeMeshCone")
    assert spec is not None
    assert spec["identifier"] == "GeometryNodeMeshCone"
    assert spec["label"] == "Cone"


def test_node_lookup_unknown_type(toolkit):
    spec = toolkit["get_node_spec"]("GeometryNodeDoesNotExist")
    assert spec is None


def test_node_has_inputs_outputs(toolkit):
    spec = toolkit["get_node_spec"]("GeometryNodeMeshCone")
    assert "inputs" in spec
    assert "outputs" in spec
    assert len(spec["outputs"]) > 0
    output_names = [s["name"] for s in spec["outputs"]]
    assert "Mesh" in output_names


def test_socket_spec_output(toolkit):
    spec = toolkit["get_socket_spec"]("GeometryNodeMeshCone", "Mesh", is_output=True)
    assert spec is not None
    assert spec["name"] == "Mesh"


def test_socket_spec_input(toolkit):
    spec = toolkit["get_socket_spec"]("GeometryNodeMeshCone", "Vertices", is_output=False)
    assert spec is not None
    assert spec["name"] == "Vertices"


def test_socket_spec_nonexistent(toolkit):
    spec = toolkit["get_socket_spec"]("GeometryNodeMeshCone", "FakeName", is_output=True)
    assert spec is None


def test_socket_compat_loads(toolkit):
    compat = toolkit["load_socket_compatibility"]()
    assert isinstance(compat, set)
    assert len(compat) > 0, "Socket compat matrix should have entries"
    # Each entry is a (from_idname, to_idname) tuple
    sample = next(iter(compat))
    assert isinstance(sample, tuple) and len(sample) == 2


def test_socket_types_compatible(toolkit):
    toolkit["load_socket_compatibility"]()
    # Geometry→Geometry should be compatible
    assert toolkit["are_socket_types_compatible"](
        "NodeSocketGeometry", "NodeSocketGeometry"
    )


def test_socket_types_incompatible(toolkit):
    toolkit["load_socket_compatibility"]()
    # String→Geometry should not be compatible
    assert not toolkit["are_socket_types_compatible"](
        "NodeSocketString", "NodeSocketGeometry"
    )


def test_detect_catalogue_version(toolkit):
    version = toolkit["_detect_catalogue_version"]()
    # Our mock bpy.app.version is (5, 0, 1), so should detect "5.0"
    assert version == "5.0"


def test_catalogue_version_from_path(toolkit):
    fn = toolkit["_catalogue_version_from_path"]
    assert fn("reference/geometry_nodes_complete_5_0.json") == "5.0"
    assert fn("reference/geometry_nodes_complete_4_4.json") == "4.4"
    assert fn("reference/geometry_nodes_min_5_0.json") == "5.0"
    assert fn("reference/no_version.json") is None


def test_catalogue_source_is_set(toolkit):
    toolkit["load_node_catalogue"]()
    source = toolkit["get_catalogue_source"]()
    assert source is not None
    assert "geometry_nodes_complete" in source
