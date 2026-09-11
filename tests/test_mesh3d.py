import numpy as np
import pytest

from swirengine import Material3D, Mesh3D, MeshData, cube_mesh, load_obj


def test_mesh_data_validates_triangle_shape():
    with pytest.raises(ValueError, match="multiple of 3"):
        MeshData(np.zeros((4, 3), dtype="f4"), np.zeros((4, 3), dtype="f4"))


def test_mesh_data_validates_uv_shape():
    with pytest.raises(ValueError, match="uvs must have shape"):
        MeshData(
            np.zeros((3, 3), dtype="f4"),
            np.zeros((3, 3), dtype="f4"),
            np.zeros((2, 2), dtype="f4"),
        )


def test_interleaved_default_remains_compatible():
    mesh = cube_mesh()
    assert mesh.interleaved().shape == (36, 6)
    assert mesh.interleaved(include_uvs=True).shape == (36, 8)


def test_cube_mesh_has_expected_geometry_and_uvs():
    mesh = cube_mesh()
    assert mesh.vertex_count == 36
    assert mesh.triangle_count == 12
    assert mesh.has_uvs
    assert mesh.uvs is not None
    assert np.all((mesh.uvs >= 0.0) & (mesh.uvs <= 1.0))


def test_mesh3d_accepts_material_without_breaking_instance_color():
    material = Material3D(texture="albedo.png", ambient=0.2, diffuse=0.8)
    mesh = Mesh3D(cube_mesh(), material=material)
    assert mesh.material is material
    assert mesh.color.r == 1.0
    assert material.textured


def test_material_clamps_negative_light_strengths():
    material = Material3D(ambient=-2, diffuse=-1)
    assert material.ambient == 0.0
    assert material.diffuse == 0.0


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
    assert not mesh.has_uvs
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


def test_obj_loader_imports_texture_coordinates(tmp_path):
    path = tmp_path / "textured.obj"
    path.write_text(
        "v 0 0 0\n"
        "v 1 0 0\n"
        "v 0 1 0\n"
        "vt 0.1 0.2\n"
        "vt 0.9 0.2\n"
        "vt 0.1 0.8\n"
        "f 1/1 2/2 3/3\n",
        encoding="utf-8",
    )
    mesh = load_obj(path)
    assert mesh.has_uvs
    assert mesh.uvs is not None
    assert np.allclose(mesh.uvs, ((0.1, 0.2), (0.9, 0.2), (0.1, 0.8)))


def test_obj_loader_supports_negative_texture_indices(tmp_path):
    path = tmp_path / "negative_uv.obj"
    path.write_text(
        "v 0 0 0\n"
        "v 1 0 0\n"
        "v 0 1 0\n"
        "vt 0 0\n"
        "vt 1 0\n"
        "vt 0 1\n"
        "f 1/-3 2/-2 3/-1\n",
        encoding="utf-8",
    )
    mesh = load_obj(path)
    assert mesh.uvs is not None
    assert np.allclose(mesh.uvs, ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)))


def test_obj_loader_reports_line_number(tmp_path):
    path = tmp_path / "bad.obj"
    path.write_text("v 0 0 0\nf 1 2 nope\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"bad\.obj:2"):
        load_obj(path)
