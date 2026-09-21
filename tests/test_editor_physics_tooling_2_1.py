from __future__ import annotations

import json
from pathlib import Path

import pytest

from swirengine.physics.collision2d import BoxCollider2D
from swirengine.physics.collision3d import BoxCollider3D, SphereCollider3D
from swirengine.physics.dynamics3d import PhysicsBody3D
from swirengine.physics.rigidbody2d import RigidBody2D
from swirengine.editor_physics_tooling21 import (
    PHYSICS_ASSET_FORMAT,
    PHYSICS_ASSET_VERSION,
    EditorPhysicsTooling21,
    EditorPhysicsToolingError,
    PhysicsBodySpec21,
)


def test_physics_authoring_round_trip_builds_real_2d_and_3d_runtime_bodies(
    tmp_path: Path,
) -> None:
    tooling = EditorPhysicsTooling21(tmp_path)
    tooling.create_body(
        "Player",
        dimension="2d",
        shape="box",
        size=(32.0, 48.0),
        offset=(0.0, 4.0),
        mass=2.0,
        restitution=0.25,
        layer=2,
        mask=7,
        tag="player",
    )
    tooling.create_body(
        "Crate3D",
        dimension="3d",
        shape="box",
        size=(1.0, 2.0, 3.0),
        offset=(0.0, 1.0, 0.0),
        friction=0.8,
        restitution=0.1,
        continuous=True,
    )
    tooling.create_body(
        "Pickup",
        dimension="3d",
        shape="sphere",
        size=(0.75,),
        body_type="kinematic",
    )

    player = tooling.build_runtime("Player", position=(10.0, 20.0))
    crate = tooling.build_runtime("Crate3D", position=(1.0, 2.0, 3.0))
    pickup = tooling.build_runtime("Pickup", position=(4.0, 5.0, 6.0))

    assert isinstance(player, RigidBody2D)
    assert isinstance(player.collider, BoxCollider2D)
    assert player.collider.bounds.width == pytest.approx(32.0)
    assert player.collider.bounds.y == pytest.approx(24.0)
    assert player.mass == pytest.approx(2.0)

    assert isinstance(crate, PhysicsBody3D)
    assert isinstance(crate.collider, BoxCollider3D)
    assert crate.collider.bounds.height == pytest.approx(2.0)
    assert crate.collider.bounds.y == pytest.approx(3.0)
    assert crate.material.friction == pytest.approx(0.8)
    assert crate.continuous is True

    assert isinstance(pickup, PhysicsBody3D)
    assert isinstance(pickup.collider, SphereCollider3D)
    assert pickup.collider.bounds.radius == pytest.approx(0.75)
    assert pickup.body_type == "kinematic"

    saved = tooling.save()
    assert saved.dirty is False
    assert saved.body_count == 3
    assert saved.two_d_count == 1
    assert saved.three_d_count == 2

    reopened = EditorPhysicsTooling21(tmp_path)
    assert reopened.snapshot() == saved
    assert isinstance(reopened.build_runtime("Crate3D"), PhysicsBody3D)


def test_physics_asset_is_deterministic_versioned_json(tmp_path: Path) -> None:
    tooling = EditorPhysicsTooling21(tmp_path)
    tooling.create_body(
        "World",
        dimension="3d",
        shape="box",
        size=(100.0, 1.0, 100.0),
        body_type="static",
        friction=1.0,
    )
    tooling.create_body(
        "Ball",
        dimension="3d",
        shape="sphere",
        size=(0.5,),
        restitution=0.9,
    )
    tooling.save()

    target = tmp_path / "config" / "physics.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["format"] == PHYSICS_ASSET_FORMAT
    assert payload["version"] == PHYSICS_ASSET_VERSION
    assert [body["name"] for body in payload["bodies"]] == ["Ball", "World"]
    first_bytes = target.read_bytes()

    tooling.load()
    tooling.save()
    assert target.read_bytes() == first_bytes


def test_physics_authoring_tracks_dirty_update_rename_and_remove(tmp_path: Path) -> None:
    tooling = EditorPhysicsTooling21(tmp_path)
    tooling.create_body("Player", dimension="2d", size=(16.0, 24.0))
    tooling.save()
    assert tooling.dirty is False

    tooling.update_body("Player", restitution=0.5, gravity_scale=0.75)
    assert tooling.dirty is True
    body = tooling.snapshot().bodies[0]
    assert body.restitution == pytest.approx(0.5)
    assert body.gravity_scale == pytest.approx(0.75)

    tooling.rename_body("Player", "Hero")
    assert tooling.snapshot().bodies[0].name == "Hero"
    with pytest.raises(EditorPhysicsToolingError, match="unknown physics body"):
        tooling.build_runtime("Player")

    tooling.remove_body("Hero")
    assert tooling.snapshot().body_count == 0


def test_physics_authoring_rejects_invalid_or_runtime_incompatible_profiles(
    tmp_path: Path,
) -> None:
    tooling = EditorPhysicsTooling21(tmp_path)

    with pytest.raises(EditorPhysicsToolingError, match="2D creator physics"):
        tooling.create_body("Bad", dimension="2d", shape="sphere", size=(1.0,))
    with pytest.raises(EditorPhysicsToolingError, match="greater than zero"):
        tooling.create_body("Bad", dimension="3d", size=(1.0, 0.0, 1.0))
    with pytest.raises(EditorPhysicsToolingError, match="between 0 and 1"):
        tooling.create_body(
            "Bad",
            dimension="3d",
            shape="sphere",
            size=(1.0,),
            restitution=1.5,
        )
    with pytest.raises(EditorPhysicsToolingError, match="finite"):
        tooling.create_body("Bad", dimension="2d", mass=float("nan"))


def test_physics_runtime_preview_uses_real_engine_validation(tmp_path: Path) -> None:
    tooling = EditorPhysicsTooling21(tmp_path)
    tooling.add_body(
        PhysicsBodySpec21(
            name="Bullet",
            dimension="3d",
            shape="sphere",
            size=(0.1,),
            mass=0.25,
            continuous=True,
            linear_damping=0.05,
            friction=0.2,
        )
    )

    body = tooling.build_runtime("Bullet", position=(1.0, 2.0, 3.0))
    assert isinstance(body, PhysicsBody3D)
    body.apply_impulse(1.0, 0.0, 0.0)
    assert body.velocity.x == pytest.approx(4.0)
    assert body.position.x == pytest.approx(1.0)


def test_physics_asset_validation_rejects_unknown_fields_and_duplicate_names(
    tmp_path: Path,
) -> None:
    target = tmp_path / "config" / "physics.json"
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(
            {
                "format": PHYSICS_ASSET_FORMAT,
                "version": PHYSICS_ASSET_VERSION,
                "bodies": [
                    {
                        "name": "Player",
                        "dimension": "2d",
                        "shape": "box",
                        "size": [1.0, 1.0],
                        "offset": [0.0, 0.0],
                        "unknown": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EditorPhysicsToolingError, match="unknown fields"):
        EditorPhysicsTooling21(tmp_path)

    target.write_text(
        json.dumps(
            {
                "format": PHYSICS_ASSET_FORMAT,
                "version": PHYSICS_ASSET_VERSION,
                "bodies": [
                    {
                        "name": "Player",
                        "dimension": "2d",
                        "shape": "box",
                        "size": [1.0, 1.0],
                        "offset": [0.0, 0.0],
                    },
                    {
                        "name": "Player",
                        "dimension": "2d",
                        "shape": "box",
                        "size": [2.0, 2.0],
                        "offset": [0.0, 0.0],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EditorPhysicsToolingError, match="duplicate physics body"):
        EditorPhysicsTooling21(tmp_path)


def test_physics_authoring_rejects_paths_outside_project(tmp_path: Path) -> None:
    with pytest.raises(EditorPhysicsToolingError, match="project-relative"):
        EditorPhysicsTooling21(tmp_path, path="../physics.json")
    with pytest.raises(EditorPhysicsToolingError, match="project-relative"):
        EditorPhysicsTooling21(tmp_path, path="C:\\physics.json")


def test_physics_authoring_revalidates_symlink_before_save(tmp_path: Path) -> None:
    tooling = EditorPhysicsTooling21(tmp_path)
    tooling.create_body("Player", dimension="2d")
    outside = tmp_path.parent / f"{tmp_path.name}-outside-physics"
    outside.mkdir()
    config = tmp_path / "config"
    try:
        config.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this runner")

    with pytest.raises(EditorPhysicsToolingError, match="escapes the project root"):
        tooling.save()

    assert not (outside / "physics.json").exists()