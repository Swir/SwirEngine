from __future__ import annotations

from dataclasses import dataclass

import pytest

from swirengine import (
    BoxCollider2D,
    Material3D,
    Mesh3D,
    RigidBody2D,
    Scene,
    cube_mesh,
)
from swirengine.editor import SceneInspector
from swirengine.editor_authoring import EditorAuthoringSession, EditorAuthoringTransaction
from swirengine.editor_specialized import EditorSpecializedInspectors
from swirengine.navigation import NavigationAgent2D, NavigationGrid2D


@dataclass
class BodyTarget:
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0


def _physics_entity(scene: Scene, name: str, mass: float):
    target = BodyTarget()
    body = RigidBody2D(target, BoxCollider2D(target), mass=mass)
    entity = scene.create_entity(name=name)
    entity.add(body)
    return entity, body


def _navigation_entity(scene: Scene, name: str, speed: float):
    target = BodyTarget()
    agent = NavigationAgent2D(target, NavigationGrid2D(4, 4), speed=speed)
    entity = scene.create_entity(name=name)
    entity.add(agent)
    return entity, agent


def test_material_adapter_reports_mixed_values_and_groups_undo() -> None:
    scene = Scene()
    first = scene.add(
        Mesh3D(cube_mesh(), material=Material3D(metallic=0.2, roughness=0.3), name="First")
    )
    second = scene.add(Mesh3D(cube_mesh(), material=None, name="Second"))
    inspector = SceneInspector(scene)
    authoring = EditorAuthoringSession(inspector)
    authoring.select(first)
    authoring.select(second, mode="add")
    specialized = EditorSpecializedInspectors(authoring)

    snapshot = specialized.inspect("material")

    assert snapshot.label == "Material"
    assert snapshot.field("roughness").mixed is True
    assert snapshot.field("roughness").value is None

    result = specialized.set_property("material", "roughness", 0.65)

    assert result.transaction.edit_count == 2
    assert first.material is not None and first.material.roughness == pytest.approx(0.65)
    assert second.material is not None and second.material.roughness == pytest.approx(0.65)

    undone = authoring.undo()
    assert isinstance(undone, EditorAuthoringTransaction)
    assert first.material is not None and first.material.roughness == pytest.approx(0.3)
    assert second.material is None

    redone = authoring.redo()
    assert isinstance(redone, EditorAuthoringTransaction)
    assert first.material is not None and first.material.roughness == pytest.approx(0.65)
    assert second.material is not None and second.material.roughness == pytest.approx(0.65)


def test_material_adapter_validates_before_any_mutation() -> None:
    scene = Scene()
    first = scene.add(Mesh3D(cube_mesh(), material=Material3D(occlusion_strength=0.4)))
    second = scene.add(Mesh3D(cube_mesh(), material=Material3D(occlusion_strength=0.8)))
    inspector = SceneInspector(scene)
    authoring = EditorAuthoringSession(inspector)
    authoring.select(first)
    authoring.select(second, mode="add")
    specialized = EditorSpecializedInspectors(authoring)

    with pytest.raises(ValueError, match="occlusion_strength"):
        specialized.set_property("material", "occlusion_strength", 1.5)

    assert first.material is not None and first.material.occlusion_strength == pytest.approx(0.4)
    assert second.material is not None and second.material.occlusion_strength == pytest.approx(0.8)
    assert not inspector.can_undo


def test_physics_adapter_handles_multi_entity_component_edits_as_one_transaction() -> None:
    scene = Scene()
    first, first_body = _physics_entity(scene, "First", 1.0)
    second, second_body = _physics_entity(scene, "Second", 3.0)
    inspector = SceneInspector(scene)
    authoring = EditorAuthoringSession(inspector)
    authoring.select(first)
    authoring.select(second, mode="add")
    specialized = EditorSpecializedInspectors(authoring)

    snapshot = specialized.inspect("physics")
    assert snapshot.field("mass").mixed is True

    result = specialized.set_property("physics", "mass", 2.5)

    assert result.transaction.edit_count == 2
    assert first_body.mass == pytest.approx(2.5)
    assert second_body.mass == pytest.approx(2.5)
    assert isinstance(authoring.undo(), EditorAuthoringTransaction)
    assert first_body.mass == pytest.approx(1.0)
    assert second_body.mass == pytest.approx(3.0)


def test_physics_adapter_rejects_invalid_values_before_mutation() -> None:
    scene = Scene()
    first, first_body = _physics_entity(scene, "First", 1.0)
    second, second_body = _physics_entity(scene, "Second", 2.0)
    inspector = SceneInspector(scene)
    authoring = EditorAuthoringSession(inspector)
    authoring.select(first)
    authoring.select(second, mode="add")
    specialized = EditorSpecializedInspectors(authoring)

    with pytest.raises(ValueError, match="mass"):
        specialized.set_property("physics", "mass", 0)

    assert first_body.mass == pytest.approx(1.0)
    assert second_body.mass == pytest.approx(2.0)
    assert not inspector.can_undo


def test_navigation_adapter_edits_safe_configuration_and_undoes_group() -> None:
    scene = Scene()
    first, first_agent = _navigation_entity(scene, "First", 2.0)
    second, second_agent = _navigation_entity(scene, "Second", 5.0)
    inspector = SceneInspector(scene)
    authoring = EditorAuthoringSession(inspector)
    authoring.select(first)
    authoring.select(second, mode="add")
    specialized = EditorSpecializedInspectors(authoring)

    snapshot = specialized.inspect("navigation")
    assert {field.name for field in snapshot.fields} == {
        "speed",
        "stopping_distance",
        "auto_repath",
    }
    assert snapshot.field("speed").mixed is True

    result = specialized.set_property("navigation", "speed", 7.5)

    assert result.transaction.edit_count == 2
    assert first_agent.speed == pytest.approx(7.5)
    assert second_agent.speed == pytest.approx(7.5)
    authoring.undo()
    assert first_agent.speed == pytest.approx(2.0)
    assert second_agent.speed == pytest.approx(5.0)


def test_specialized_adapter_preflights_incompatible_mixed_selection() -> None:
    scene = Scene()
    physics_entity, body = _physics_entity(scene, "Physics", 1.0)
    navigation_entity, _agent = _navigation_entity(scene, "Navigation", 2.0)
    inspector = SceneInspector(scene)
    authoring = EditorAuthoringSession(inspector)
    authoring.select(physics_entity)
    authoring.select(navigation_entity, mode="add")
    specialized = EditorSpecializedInspectors(authoring)

    with pytest.raises(TypeError, match="needs RigidBody2D or RigidBody3D"):
        specialized.set_property("physics", "mass", 4.0)

    assert body.mass == pytest.approx(1.0)
    assert not inspector.can_undo
