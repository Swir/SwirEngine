import pytest

from swirengine import (
    MAX_DIRECTIONAL_LIGHTS,
    MAX_POINT_LIGHTS,
    MAX_SPOT_LIGHTS,
    DirectionalLight3D,
    Game,
    Material3D,
    PointLight3D,
    SpotLight3D,
    Vec3,
    select_lights,
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


def test_select_lights_preserves_scene_order_and_supports_multiple_per_type():
    point_a = PointLight3D(position=Vec3(1.0, 0.0, 0.0))
    point_b = PointLight3D(position=Vec3(2.0, 0.0, 0.0))
    sun_a = DirectionalLight3D(direction=Vec3(-1.0, -1.0, 0.0))
    sun_b = DirectionalLight3D(direction=Vec3(1.0, -1.0, 0.0))
    spot = SpotLight3D(position=Vec3(0.0, 3.0, 0.0))

    selected = select_lights([point_a, sun_a, point_b, spot, sun_b])

    assert selected.directional == (sun_a, sun_b)
    assert selected.point == (point_a, point_b)
    assert selected.spot == (spot,)
    assert selected.total == 5
    assert selected.dropped == 0


def test_select_lights_ignores_disabled_and_hidden_lights():
    disabled = PointLight3D(enabled=False)
    hidden = SpotLight3D(visible=False)
    active = DirectionalLight3D()

    selected = select_lights([disabled, hidden, active])

    assert selected.directional == (active,)
    assert selected.point == ()
    assert selected.spot == ()


def test_select_lights_reports_gpu_budget_overflow():
    points = [PointLight3D(position=Vec3(float(index), 0.0, 0.0)) for index in range(7)]
    spots = [SpotLight3D(position=Vec3(float(index), 2.0, 0.0)) for index in range(6)]
    suns = [DirectionalLight3D() for _ in range(5)]

    selected = select_lights([*points, *spots, *suns])

    assert len(selected.point) == MAX_POINT_LIGHTS
    assert len(selected.spot) == MAX_SPOT_LIGHTS
    assert len(selected.directional) == MAX_DIRECTIONAL_LIGHTS
    assert selected.dropped_point == 3
    assert selected.dropped_spot == 2
    assert selected.dropped_directional == 1
    assert selected.dropped == 6


def test_select_lights_keeps_legacy_default_sun_only_when_scene_has_no_active_lights():
    fallback = select_lights([])
    no_fallback_when_user_light_exists = select_lights([PointLight3D()])

    assert len(fallback.directional) == 1
    assert fallback.point == ()
    assert no_fallback_when_user_light_exists.directional == ()
    assert len(no_fallback_when_user_light_exists.point) == 1


def test_select_lights_rejects_negative_limits():
    with pytest.raises(ValueError, match="light limits"):
        select_lights([], max_point=-1)
