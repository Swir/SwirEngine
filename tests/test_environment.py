from pathlib import Path

import numpy as np
import pytest

from swirengine import Camera3D, Color, Environment3D, Scene, Skybox3D, Vec3
from swirengine.graphics.environment import skybox_mesh_data


def test_skybox_mesh_has_inward_normals_and_valid_panorama_uvs() -> None:
    mesh = skybox_mesh_data()

    assert mesh.vertex_count == 36
    assert mesh.uvs is not None
    assert np.all(mesh.uvs >= 0.0)
    assert np.all(mesh.uvs <= 1.0)

    dots = np.sum(mesh.vertices * mesh.normals, axis=1)
    assert np.all(dots < 0.0)


def test_skybox_validates_size_and_uses_unlit_material() -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        Skybox3D("sky.png", size=0)

    skybox = Skybox3D("sky.png", size=42.0)
    assert skybox.scale == Vec3(42.0, 42.0, 42.0)
    assert skybox.material is not None
    assert skybox.material.texture == Path("sky.png") or skybox.material.texture == "sky.png"
    assert skybox.material.ambient == 1.0
    assert skybox.material.diffuse == 0.0
    assert skybox.material.specular == 0.0
    assert {"environment", "skybox"} <= skybox.tags


def test_skybox_follows_camera_without_changing_scale() -> None:
    camera = Camera3D(position=Vec3(4.0, 5.0, -6.0))
    skybox = Skybox3D("sky.png", size=64.0)

    skybox.follow(camera)

    assert skybox.position == Vec3(4.0, 5.0, -6.0)
    assert skybox.scale == Vec3(64.0, 64.0, 64.0)


def test_environment_lights_leave_room_for_authored_directionals() -> None:
    environment = Environment3D(
        sky_color=Color(0.8, 0.6, 0.4, 1.0),
        ground_color=Color(0.2, 0.3, 0.4, 1.0),
        intensity=0.5,
        ground_intensity=0.25,
    )

    sky, ground = environment.lights()

    assert sky.direction == Vec3(0.0, -1.0, 0.0)
    assert ground.direction == Vec3(0.0, 1.0, 0.0)
    assert sky.color.r == pytest.approx(0.4)
    assert ground.color.b == pytest.approx(0.1)
    assert sky.name.endswith(":sky")
    assert ground.name.endswith(":ground")


def test_environment_install_and_remove_scene_objects() -> None:
    scene = Scene()
    installation = Environment3D(name="outdoor").install(
        scene,
        skybox_texture="assets/sky.jpg",
        skybox_size=50.0,
    )

    assert len(installation.lights) == 2
    assert installation.skybox is not None
    assert all(obj in scene for obj in installation.objects)
    assert installation.skybox.name == "outdoor:skybox"

    installation.remove()
    assert all(obj not in scene for obj in installation.objects)


def test_environment_installation_can_follow_camera() -> None:
    scene = Scene()
    installation = Environment3D().install(scene, skybox_texture="sky.png")
    camera = Camera3D(position=Vec3(8.0, -2.0, 3.5))

    installation.follow(camera)

    assert installation.skybox is not None
    assert installation.skybox.position == camera.position
