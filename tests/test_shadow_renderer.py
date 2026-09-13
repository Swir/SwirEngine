import pytest

from swirengine.core.game import Game
from swirengine.graphics.lights import DirectionalLight3D, PointLight3D
from swirengine.graphics.shadow_renderer import ShadowedImageBasedPostProcessRenderer


def test_game_shadows_are_opt_in_and_configurable():
    game = Game(mode="3d")

    assert game.shadows_enabled is False
    settings = game.configure_shadows(resolution=1024, extent=18.0, bias=0.002)

    assert game.shadows_enabled is True
    assert settings.resolution == 1024
    assert settings.extent == 18.0
    assert settings.bias == 0.002
    assert game.shadow_settings is settings


def test_shadow_configuration_is_atomic_on_invalid_change():
    game = Game(mode="3d")
    previous = game.shadow_settings

    with pytest.raises(ValueError):
        game.configure_shadows(resolution=32)

    assert game.shadow_settings is previous
    assert game.shadows_enabled is False


def test_shadow_configuration_rejects_unknown_settings():
    game = Game(mode="3d")

    with pytest.raises(TypeError, match="unknown shadow setting"):
        game.configure_shadows(quality="ultra")


def test_shadow_configuration_requires_3d_mode():
    game = Game(mode="2d")

    with pytest.raises(RuntimeError, match="requires mode='3d'"):
        game.configure_shadows()


def test_shadow_renderer_selects_first_budgeted_directional_light():
    point = PointLight3D()
    first = DirectionalLight3D(intensity=3.0)
    second = DirectionalLight3D(intensity=1.0)
    scene = type("SceneStub", (), {"objects": [point, first, second]})()

    selected = ShadowedImageBasedPostProcessRenderer._shadow_light(scene)

    assert selected is first


def test_shadow_renderer_handles_scene_without_directional_light():
    scene = type("SceneStub", (), {"objects": [PointLight3D()]})()

    assert ShadowedImageBasedPostProcessRenderer._shadow_light(scene) is None
