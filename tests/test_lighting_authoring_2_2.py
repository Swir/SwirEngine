from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from swirengine.core.game import Game
from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21
from swirengine.graphics.lights import DirectionalLight3D, PointLight3D, SpotLight3D, select_lights
from swirengine.graphics.renderer2 import Renderer2Settings
from swirengine.lighting_authoring22 import (
    MAX_LIGHTING_BYTES,
    EditorLightingError22,
    EditorLightingTooling22,
    EnvironmentSpec22,
    LightSpec22,
    PostFXSpec22,
    SceneLightingSpec22,
)
from swirengine.project_scaffold21 import new_project21


def profile(mode: str = "3d") -> SceneLightingSpec22:
    return SceneLightingSpec22(
        "scenes/main.swirscene", mode=mode,
        lights=() if mode == "2d" else (
            LightSpec22("sun"), LightSpec22("point", kind="point"),
            LightSpec22("spot", kind="spot"),
        ),
        environment=EnvironmentSpec22(enabled=mode == "3d"),
        postfx=PostFXSpec22(exposure=1.75, vignette=0.2),
        renderer=Renderer2Settings(shadow_resolution=128, shadow_cascades=2, ssao_samples=8),
    )


@pytest.mark.parametrize("mode", ("2d", "3d"))
def test_integrated_scene_profile_round_trip_and_shipping_runtime(tmp_path: Path, mode: str) -> None:
    root = new_project21("LightingGate", mode, parent=tmp_path)
    session = EditorIntegratedProjectSession21.open(root)
    assert not session.lighting.dirty
    session.lighting.set_profile(profile(mode))
    assert session.summary().dirty and session._all_dirty()
    session.save()
    raw = session.lighting.target.read_bytes()
    reopened = EditorIntegratedProjectSession21.open(root)
    assert not reopened.summary().dirty
    assert reopened.lighting.profiles() == session.lighting.profiles()
    runtime = reopened.lighting.build_runtime("scenes/main.swirscene")
    assert runtime.spec.fingerprint == profile(mode).fingerprint
    game = Game(mode=mode)
    unrelated = object()
    game.add(unrelated)
    mount = runtime.apply_to_game(game)
    assert game.postprocess.exposure == 1.75
    assert game.postprocess.vignette == 0.2
    assert game.renderer2_enabled is (mode == "3d")
    if mode == "3d":
        assert len(runtime.lights) == 5
        assert {type(light) for light in runtime.lights} == {
            DirectionalLight3D, PointLight3D, SpotLight3D,
        }
        assert all(light in game.scene for light in runtime.lights)
        assert select_lights(game.scene.objects).total == 5
        assert not select_lights(game.scene.objects).dropped
        with pytest.raises(EditorLightingError22):
            runtime.apply_to_game(game)
        assert game.renderer2_settings.shadow_cascades == 2
    mount.unmount()
    assert unrelated in game.scene
    assert mount.unmount() == (0, 0)
    reopened.lighting.save()
    assert reopened.lighting.target.read_bytes() == raw


@pytest.mark.parametrize("value", (True, "1.5", float("nan"), float("inf"), -1))
def test_rejects_invalid_exposure(value: object) -> None:
    with pytest.raises(EditorLightingError22):
        PostFXSpec22(exposure=value)


@pytest.mark.parametrize("kwargs", (
    {"kind": "area"}, {"direction": (0, 0, 0)}, {"range": 0}, {"intensity": True},
    {"color": (1, 1, float("nan"), 1)}, {"enabled": 1}, {"outer_angle": 10},
))
def test_rejects_malformed_light(kwargs: dict[str, object]) -> None:
    with pytest.raises(EditorLightingError22):
        LightSpec22("light", **kwargs)


@pytest.mark.parametrize("path", ("../sky.png", "/sky.png", r"C:\sky.png", r"C:sky.png", "a//b", "x\x00"))
def test_skybox_paths_are_project_relative(path: str) -> None:
    with pytest.raises(EditorLightingError22):
        EnvironmentSpec22(skybox_texture=path)


def test_profile_budgets_and_2d_limits() -> None:
    with pytest.raises(EditorLightingError22, match="including environment"):
        SceneLightingSpec22("scene", lights=tuple(LightSpec22(str(i)) for i in range(3)),
                            environment=EnvironmentSpec22(enabled=True))
    with pytest.raises(EditorLightingError22, match="duplicate"):
        SceneLightingSpec22("scene", lights=(LightSpec22("x"), LightSpec22(" x ")))
    with pytest.raises(EditorLightingError22, match="2D"):
        replace(profile(), mode="2d")
    with pytest.raises(EditorLightingError22, match="4096"):
        replace(profile(), renderer=Renderer2Settings(shadow_resolution=8192))
    with pytest.raises(EditorLightingError22, match="integer"):
        replace(profile(), renderer=Renderer2Settings(shadow_cascades=2.5))
    with pytest.raises(EditorLightingError22, match="requires post-FX"):
        replace(profile(), postfx=PostFXSpec22(enabled=False))


@pytest.mark.parametrize("invalid", ("duplicate", "version-bool", "non-finite", "oversize", "unknown", "duplicate-field"))
@pytest.mark.parametrize("dirty", (False, True))
def test_rejected_reload_preserves_all_authoring(tmp_path: Path, invalid: str, dirty: bool) -> None:
    tool = EditorLightingTooling22(tmp_path)
    tool.set_profile(profile())
    tool.save()
    canonical = tool.target.read_bytes()
    if dirty:
        tool.update("scenes/main.swirscene", postfx=PostFXSpec22(exposure=2.0))
    before = tool.profiles()
    data = json.loads(canonical)
    if invalid == "duplicate":
        data["profiles"].append(data["profiles"][0])
    elif invalid == "version-bool":
        data["version"] = True
    elif invalid == "non-finite":
        data["profiles"][0]["postfx"]["exposure"] = float("nan")
    elif invalid == "unknown":
        data["profiles"][0]["injected"] = "field"
    raw = json.dumps(data).encode()
    if invalid == "oversize":
        raw = b" " * (MAX_LIGHTING_BYTES + 1)
    elif invalid == "duplicate-field":
        raw = b'{"format": "swirengine.scene-lighting", "version":1, "version":1, "profiles":[]}'
    tool.target.write_bytes(raw)
    with pytest.raises(EditorLightingError22):
        tool.load()
    assert tool.profiles() == before
    assert tool.dirty is dirty
    assert tool.target.read_bytes() == raw
    tool.target.write_bytes(canonical)
    tool.load()
    assert not tool.dirty


def test_atomic_save_failure_keeps_saved_file_and_unsaved_state(tmp_path: Path, monkeypatch) -> None:
    tool = EditorLightingTooling22(tmp_path)
    tool.set_profile(profile())
    tool.save()
    before = tool.target.read_bytes()
    tool.update("scenes/main.swirscene", postfx=PostFXSpec22(exposure=2.0))
    def fail(*args):
        raise OSError("disk failure")
    monkeypatch.setattr("swirengine.lighting_authoring22.os.replace", fail)
    with pytest.raises(OSError, match="disk failure"):
        tool.save()
    assert tool.dirty and tool.target.read_bytes() == before
    assert sorted(p.name for p in tool.target.parent.iterdir()) == ["lighting.json"]


def test_skybox_runtime_confines_assets_and_revalidates_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "project"
    assets = root / "assets"
    assets.mkdir(parents=True)
    spec = replace(profile(), environment=EnvironmentSpec22(enabled=True, skybox_texture="sky.png"))
    tool = EditorLightingTooling22(root)
    tool.set_profile(spec)
    with pytest.raises(EditorLightingError22, match="missing skybox"):
        tool.build_runtime(spec.scene)
    (assets / "sky.png").write_bytes(b"asset-path-fixture-not-a-render-test")
    assert tool.build_runtime(spec.scene).skybox is not None
    (assets / "sky.png").unlink()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")
    try:
        (assets / "sky.png").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(EditorLightingError22, match="outside"):
        tool.build_runtime(spec.scene)
    (assets / "sky.png").unlink()
    assets.rmdir()
    assets.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(EditorLightingError22, match="outside"):
        tool.build_runtime(spec.scene)


def test_runtime_rejects_mode_running_and_existing_light_overflow_without_mutation(tmp_path: Path) -> None:
    tool = EditorLightingTooling22(tmp_path)
    tool.set_profile(profile())
    runtime = tool.build_runtime("scenes/main.swirscene")
    for mode, running, extra in (("2d", False, 0), ("3d", True, 0), ("3d", False, 2)):
        game = Game(mode=mode)
        game.running = running
        for i in range(extra):
            game.add(DirectionalLight3D(name=f"unrelated-{i}"))
        before = game.scene.objects
        settings = asdict(game.postprocess)
        with pytest.raises(EditorLightingError22):
            runtime.apply_to_game(game)
        assert game.scene.objects == before
        assert asdict(game.postprocess) == settings
        assert not game.renderer2_enabled


def test_canonical_light_order_and_scene_paths(tmp_path: Path) -> None:
    tool = EditorLightingTooling22(tmp_path)
    original = profile()
    reverse = replace(original, lights=tuple(reversed(original.lights)))
    assert reverse.fingerprint == original.fingerprint
    tool.set_profile(reverse)
    with pytest.raises(EditorLightingError22):
        replace(original, scene="../outside.json")
    with pytest.raises(EditorLightingError22):
        tool.update(original.scene, scene="other.json")
    tool.remove(original.scene)
    assert not tool.profiles()
