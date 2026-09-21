from __future__ import annotations

from pathlib import Path

import pytest

from swirengine.cli import new_project
from swirengine.editor_animation_frontend21 import TkAnimationEditorApp21
from swirengine.editor_app21 import EditorProjectSession
from swirengine.editor_physics_frontend21 import (
    EditorPhysicsPanelController21,
    TkPhysicsEditorApp21,
    parse_physics_size21,
)
from swirengine.editor_physics_tooling21 import EditorPhysicsTooling21
from swirengine.physics.dynamics3d import PhysicsBody3D
from swirengine.physics.rigidbody2d import RigidBody2D


def test_physics_panel_authors_and_previews_real_runtime_bodies(tmp_path: Path) -> None:
    controller = EditorPhysicsPanelController21(EditorPhysicsTooling21(tmp_path))

    frame = controller.create_body(
        "Player",
        dimension="2d",
        shape="box",
        size=(24.0, 40.0),
        mass=2.0,
        layer=2,
        mask=7,
    )
    assert frame.dirty is True
    assert frame.selected_name == "Player"
    assert frame.bodies[0].size == (24.0, 40.0)

    frame, player = controller.preview("Player", position=(10.0, 20.0))
    assert isinstance(player, RigidBody2D)
    assert frame.preview_type == "RigidBody2D"
    assert frame.preview_collider == "BoxCollider2D"

    controller.create_body(
        "Crate",
        dimension="3d",
        shape="box",
        size=(1.0, 2.0, 3.0),
        body_type="dynamic",
        friction=0.8,
    )
    frame, crate = controller.preview("Crate", position=(1.0, 2.0, 3.0))
    assert isinstance(crate, PhysicsBody3D)
    assert frame.preview_type == "PhysicsBody3D"
    assert frame.preview_collider == "BoxCollider3D"


def test_physics_panel_updates_renames_removes_and_round_trips(tmp_path: Path) -> None:
    controller = EditorPhysicsPanelController21(EditorPhysicsTooling21(tmp_path))
    controller.create_body("Player", dimension="2d", size=(16.0, 24.0))
    frame = controller.update_body("Player", restitution=0.5, gravity_scale=0.75)
    assert frame.selected_name == "Player"

    frame = controller.rename_body("Player", "Hero")
    assert frame.selected_name == "Hero"
    assert frame.bodies[0].name == "Hero"

    saved = controller.save()
    assert saved.dirty is False
    reopened = EditorPhysicsPanelController21(EditorPhysicsTooling21(tmp_path))
    assert reopened.frame().bodies[0].name == "Hero"

    frame = reopened.remove_body("Hero")
    assert frame.bodies == ()
    assert frame.dirty is True


def test_physics_size_parser_accepts_portable_numeric_dimensions() -> None:
    assert parse_physics_size21("32, 48") == (32.0, 48.0)
    assert parse_physics_size21("0.5") == (0.5,)

    with pytest.raises(ValueError, match="at least one"):
        parse_physics_size21(" , ")
    with pytest.raises(ValueError, match="comma-separated numbers"):
        parse_physics_size21("1, nope")


def test_project_session_tracks_and_saves_physics_authoring(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    root = new_project("PhysicsPanel", "2d")
    session = EditorProjectSession.open(root)

    session.physics.create_body(
        "Player",
        dimension="2d",
        size=(24.0, 40.0),
        restitution=0.2,
        tag="player",
    )
    assert session.summary().dirty is True

    session.save()
    assert session.summary().dirty is False
    target = root / "config" / "physics.json"
    assert target.is_file()

    reopened = EditorPhysicsTooling21(root)
    body = reopened.build_runtime("Player", position=(4.0, 8.0))
    assert isinstance(body, RigidBody2D)
    assert body.collider.tag == "player"


def test_physics_shell_preserves_animation_editor_capability() -> None:
    assert issubclass(TkPhysicsEditorApp21, TkAnimationEditorApp21)
