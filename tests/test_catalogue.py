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


def test_get_node_metadata(toolkit):
    meta = toolkit["get_node_metadata"]("GeometryNodeMeshCone")
    assert meta["identifier"] == "GeometryNodeMeshCone"
    assert meta["label"] == "Cone"
    assert isinstance(meta.get("description"), str)


def test_find_nodes_by_keyword(toolkit):
    matches = toolkit["find_nodes_by_keyword"]("switch between")
    assert any("Switch" in (m.get("label") or "") for m in matches)


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


def test_mermaid_type_map_invalidated_on_catalogue_reload(toolkit):
    """Verify _MERMAID_TYPE_MAP is cleared when catalogue is reloaded."""
    from pathlib import Path

    # Build the type map with 5.0 catalogue
    toolkit["_build_mermaid_type_map"]()
    assert toolkit["_MERMAID_TYPE_MAP"] is not None

    # Reload with 4.4 catalogue
    cat_44 = Path(__file__).parent.parent / "reference" / "geometry_nodes_complete_4_4.json"
    if cat_44.exists():
        toolkit["load_node_catalogue"](path=str(cat_44), force_reload=True)
        # Cache should be invalidated
        assert toolkit["_MERMAID_TYPE_MAP"] is None

        # Rebuild and verify it uses 4.4 data
        new_map = toolkit["_build_mermaid_type_map"]()
        assert new_map is not None
        # 4.4 catalogue has fewer nodes than 5.0
        assert len(new_map) < 742  # 5.0 has 742 entries
