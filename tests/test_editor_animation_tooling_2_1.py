from __future__ import annotations

import json
from pathlib import Path

import pytest

from swirengine.animation15 import InterpolationMode
from swirengine.editor_animation_tooling21 import (
    ANIMATION_ASSET_FORMAT,
    ANIMATION_ASSET_VERSION,
    EditorAnimationTooling21,
    EditorAnimationToolingError,
)


def test_animation_authoring_round_trip_uses_runtime_sampling(tmp_path: Path) -> None:
    tooling = EditorAnimationTooling21(tmp_path)
    created = tooling.new_clip("Player Run", duration=1.0, loop=True)

    assert created.path == "assets/animations/player-run.swiranim.json"
    assert created.dirty is True
    assert created.clip is not None

    tooling.add_track("transform.position", initial_value=[0.0, 0.0])
    tooling.set_keyframe("transform.position", 1.0, [10.0, 4.0])
    tooling.add_track(
        "sprite.frame",
        initial_value=0,
        interpolation=InterpolationMode.STEP,
    )
    tooling.set_keyframe("sprite.frame", 0.5, 1)
    tooling.set_keyframe("sprite.frame", 1.0, 2)

    midpoint = tooling.sample(0.5)
    assert midpoint.values["transform.position"] == [5.0, 2.0]
    assert midpoint.values["sprite.frame"] == 1

    saved = tooling.save()
    assert saved.dirty is False

    reopened = EditorAnimationTooling21(tmp_path)
    loaded = reopened.load(saved.path or "")
    assert loaded.clip is not None
    assert loaded.clip.name == "Player Run"
    assert loaded.loop is True
    assert [track.binding for track in loaded.clip.tracks] == [
        "transform.position",
        "sprite.frame",
    ]
    assert reopened.sample(0.75).values["transform.position"] == [7.5, 3.0]
    assert reopened.sample(1.25).values["transform.position"] == [2.5, 1.0]


def test_animation_asset_is_deterministic_versioned_json(tmp_path: Path) -> None:
    tooling = EditorAnimationTooling21(tmp_path)
    tooling.new_clip("Idle", duration=2.0, loop=False)
    tooling.add_track("transform.rotation", initial_value=0.0)
    tooling.set_keyframe("transform.rotation", 2.0, 90.0)
    tooling.save()

    target = tmp_path / "assets" / "animations" / "idle.swiranim.json"
    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["format"] == ANIMATION_ASSET_FORMAT
    assert payload["version"] == ANIMATION_ASSET_VERSION
    assert payload["name"] == "Idle"
    assert payload["duration"] == 2.0
    assert payload["loop"] is False
    assert payload["tracks"][0]["binding"] == "transform.rotation"
    assert payload["tracks"][0]["interpolation"] == "linear"
    first_bytes = target.read_bytes()

    tooling.load("assets/animations/idle.swiranim.json")
    tooling.save()
    assert target.read_bytes() == first_bytes


def test_animation_authoring_replaces_keyframe_and_tracks_dirty_state(tmp_path: Path) -> None:
    tooling = EditorAnimationTooling21(tmp_path)
    tooling.new_clip("Door", duration=1.0)
    tooling.add_track("transform.position", initial_value=0.0)
    tooling.set_keyframe("transform.position", 1.0, 10.0)
    tooling.save()
    assert tooling.dirty is False

    tooling.set_keyframe("transform.position", 1.0, 20.0)
    assert tooling.dirty is True
    assert tooling.sample(0.5).values["transform.position"] == 10.0

    tooling.set_interpolation("transform.position", "step")
    assert tooling.sample(0.5).values["transform.position"] == 0.0

    tooling.remove_keyframe("transform.position", 1.0)
    assert tooling.snapshot().tracks[0].keyframe_count == 1

    with pytest.raises(EditorAnimationToolingError, match="retain at least one"):
        tooling.remove_keyframe("transform.position", 0.0)


def test_animation_duration_cannot_truncate_existing_keyframes(tmp_path: Path) -> None:
    tooling = EditorAnimationTooling21(tmp_path)
    tooling.new_clip("Attack", duration=2.0)
    tooling.add_track("weapon.angle", initial_value=0.0)
    tooling.set_keyframe("weapon.angle", 2.0, 45.0)

    with pytest.raises(ValueError, match="must not exceed clip duration"):
        tooling.set_duration(1.0)

    assert tooling.clip.duration == 2.0


def test_animation_authoring_rejects_duplicate_and_unknown_bindings(tmp_path: Path) -> None:
    tooling = EditorAnimationTooling21(tmp_path)
    tooling.new_clip("Idle")
    tooling.add_track("transform.scale", initial_value=[1.0, 1.0])

    with pytest.raises(EditorAnimationToolingError, match="already exists"):
        tooling.add_track("transform.scale")

    with pytest.raises(EditorAnimationToolingError, match="unknown animation binding"):
        tooling.set_keyframe("transform.position", 0.5, [1.0, 2.0])

    with pytest.raises(EditorAnimationToolingError, match="unknown animation binding"):
        tooling.remove_track("transform.position")


def test_animation_authoring_rejects_paths_outside_project(tmp_path: Path) -> None:
    tooling = EditorAnimationTooling21(tmp_path)

    with pytest.raises(EditorAnimationToolingError, match="project-relative"):
        tooling.new_clip("Bad", path="../bad.swiranim.json")
    with pytest.raises(EditorAnimationToolingError, match="project-relative"):
        tooling.load("C:\\bad.swiranim.json")
    with pytest.raises(EditorAnimationToolingError, match="must end with"):
        tooling.new_clip("Bad", path="assets/animations/bad.json")


def test_animation_authoring_revalidates_symlink_before_save(tmp_path: Path) -> None:
    tooling = EditorAnimationTooling21(tmp_path)
    tooling.new_clip("Escape")
    outside = tmp_path.parent / f"{tmp_path.name}-outside-animation"
    outside.mkdir()
    assets = tmp_path / "assets"
    assets.mkdir()
    animation_dir = assets / "animations"
    try:
        animation_dir.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this runner")

    with pytest.raises(EditorAnimationToolingError, match="escapes the project root"):
        tooling.save()

    assert not (outside / "escape.swiranim.json").exists()


def test_animation_asset_validation_rejects_invalid_envelopes(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "animations" / "broken.swiranim.json"
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(
            {
                "format": ANIMATION_ASSET_FORMAT,
                "version": ANIMATION_ASSET_VERSION,
                "name": "Broken",
                "duration": 1.0,
                "loop": True,
                "tracks": [
                    {
                        "binding": "transform.position",
                        "interpolation": "linear",
                        "keyframes": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    tooling = EditorAnimationTooling21(tmp_path)
    with pytest.raises(EditorAnimationToolingError, match="at least one keyframe"):
        tooling.load("assets/animations/broken.swiranim.json")


def test_animation_values_must_be_portable_and_finite(tmp_path: Path) -> None:
    tooling = EditorAnimationTooling21(tmp_path)
    tooling.new_clip("Portable")
    with pytest.raises(EditorAnimationToolingError, match="unsupported animation value type"):
        tooling.add_track("custom.value", initial_value={"x": 1})
    with pytest.raises(EditorAnimationToolingError, match="finite"):
        tooling.add_track("custom.value", initial_value=float("nan"))
