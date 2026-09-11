import pytest

from swirengine import (
    DirectionalLight3D,
    Game,
    Material3D,
    PointLight3D,
    SpotLight3D,
    Vec3,
)


def test_directional_light_normalizes_direction():
    light = DirectionalLight3D(direction=Vec3(0.0, -2.0, 0.0), intensity=-4.0)
    assert light.direction == Vec3(0.0, -1.0, 0.0)
    assert light.intensity == 0.0


def test_light_validation_rejects_invalid_ranges_and_angles():
    with pytest.raises(ValueError, match="range"):
        PointLight3D(range=0.0)
    with pytest.raises(ValueError, match="spot angles"):
        SpotLight3D(inner_angle=30.0, outer_angle=20.0)
    with pytest.raises(ValueError, match="direction"):
        DirectionalLight3D(direction=Vec3())


def test_spot_light_normalizes_direction_and_clamps_intensity():
    light = SpotLight3D(direction=Vec3(0.0, 0.0, -5.0), intensity=-1.0)
    assert light.direction == Vec3(0.0, 0.0, -1.0)
    assert light.intensity == 0.0


def test_material_specular_controls_are_sanitized():
    material = Material3D(specular=-1.0, shininess=0.0)
    assert material.specular == 0.0
    assert material.shininess == 1.0


def test_game_light_factories_register_scene_objects():
    game = Game(mode="3d")
    sun = game.directional_light(direction=Vec3(1.0, -1.0, 0.0))
    bulb = game.point_light(position=Vec3(2.0, 3.0, 4.0), range=8.0)
    torch = game.spot_light(position=Vec3(0.0, 2.0, 0.0))

    assert sun in game.scene.objects
    assert bulb in game.scene.objects
    assert torch in game.scene.objects


def test_light_factories_require_3d_mode():
    game = Game(mode="2d")
    with pytest.raises(RuntimeError, match="mode='3d'"):
        game.directional_light()
    with pytest.raises(RuntimeError, match="mode='3d'"):
        game.point_light()
    with pytest.raises(RuntimeError, match="mode='3d'"):
        game.spot_light()
