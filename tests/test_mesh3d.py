import numpy as np
import pytest

from swirengine import MeshData, cube_mesh, load_obj


def test_mesh_data_validates_triangle_shape():
    with pytest.raises(ValueError, match="multiple of 3"):
        MeshData(np.zeros((4, 3), dtype="f4"), np.zeros((4, 3), dtype="f4"))


def test_cube_mesh_has_expected_geometry():
    mesh = cube_mesh()
    assert mesh.vertex_count == 36
    assert mesh.triangle_count == 12
    assert mesh.interleaved().shape == (36, 6)


def test_obj_loader_triangulates_quads_and_generates_normals(tmp_path):
    path = tmp_path / "quad.obj"
    path.write_text(
        "v -1 0 0\n"
        "v 1 0 0\n"
        "v 1 1 0\n"
        "v -1 1 0\n"
        "f 1 2 3 4\n",
        encoding="utf-8",
    )
    mesh = load_obj(path)
    assert mesh.vertex_count == 6
    assert mesh.triangle_count == 2
    assert np.allclose(np.linalg.norm(mesh.normals, axis=1), 1.0)


def test_obj_loader_supports_negative_indices_and_normals(tmp_path):
    path = tmp_path / "triangle.obj"
    path.write_text(
        "v 0 0 0\n"
        "v 1 0 0\n"
        "v 0 1 0\n"
        "vn 0 0 1\n"
        "f -3//1 -2//1 -1//1\n",
        encoding="utf-8",
    )
    mesh = load_obj(path)
    assert np.allclose(mesh.normals, (0.0, 0.0, 1.0))


def test_obj_loader_reports_line_number(tmp_path):
    path = tmp_path / "bad.obj"
    path.write_text("v 0 0 0\nf 1 2 nope\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"bad\.obj:2"):
        load_obj(path)
