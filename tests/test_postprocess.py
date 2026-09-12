import pytest

from swirengine import Game, PostProcessSettings


def test_postprocess_defaults_are_disabled_and_creator_safe():
    settings = PostProcessSettings()

    assert settings.enabled is False
    assert settings.tone_mapping == "aces"
    assert settings.tone_mapping_mode == 2
    assert settings.exposure == 1.0
    assert settings.gamma == 2.2
    assert settings.fxaa is True


def test_postprocess_tone_mapping_modes_are_stable():
    assert PostProcessSettings(tone_mapping="none").tone_mapping_mode == 0
    assert PostProcessSettings(tone_mapping="reinhard").tone_mapping_mode == 1
    assert PostProcessSettings(tone_mapping="aces").tone_mapping_mode == 2


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"tone_mapping": "invalid"}, "tone_mapping"),
        ({"exposure": 0.0}, "exposure"),
        ({"gamma": 0.0}, "gamma"),
        ({"contrast": -0.1}, "contrast"),
        ({"saturation": -0.1}, "saturation"),
        ({"vignette": -0.1}, "vignette"),
        ({"vignette": 1.1}, "vignette"),
    ],
)
def test_postprocess_rejects_invalid_settings(kwargs, message):
    with pytest.raises(ValueError, match=message):
        PostProcessSettings(**kwargs)


def test_postprocess_update_is_atomic_when_validation_fails():
    settings = PostProcessSettings(enabled=True, exposure=1.5)

    with pytest.raises(ValueError, match="gamma"):
        settings.update(exposure=3.0, gamma=0.0)

    assert settings.exposure == 1.5
    assert settings.gamma == 2.2


def test_postprocess_update_rejects_unknown_fields():
    settings = PostProcessSettings()

    with pytest.raises(TypeError, match="unknown post-process setting"):
        settings.update(bloom=True)


def test_game_exposes_shared_postprocess_settings():
    game = Game(mode="3d")

    returned = game.configure_postprocess(
        enabled=True,
        tone_mapping="reinhard",
        exposure=1.4,
        saturation=1.1,
        vignette=0.25,
        fxaa=False,
    )

    assert returned is game.postprocess
    assert game.postprocess.enabled is True
    assert game.postprocess.tone_mapping == "reinhard"
    assert game.postprocess.exposure == 1.4
    assert game.postprocess.saturation == 1.1
    assert game.postprocess.vignette == 0.25
    assert game.postprocess.fxaa is False
