from dataclasses import dataclass

import pytest

from swirengine import Scene
from swirengine.editor import HierarchyEdit, PropertyEdit, SceneInspector


@dataclass
class Actor:
    name: str
    enabled: bool = True
    tags: set[str] | None = None
    health: int = 100

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = set()


@dataclass
class Velocity:
    x: float
    y: float


def test_hierarchy_combines_scene_objects_and_entities_with_filters():
    scene = Scene()
    player = scene.add(Actor("Player", tags={"hero", "playable"}))
    scene.add(Actor("Hidden", enabled=False, tags={"debug"}))
    enemy = scene.create_entity(name="Enemy", tags={"enemy"})

    inspector = SceneInspector(scene)
    rows = inspector.hierarchy()

    assert [row.label for row in rows] == ["Player", "Hidden", "Enemy"]
    assert rows[0].key == inspector.key_for(player)
    assert rows[2].key == f"entity:{enemy.id}"
    assert [row.label for row in inspector.hierarchy(tag="hero")] == ["Player"]
    assert [row.label for row in inspector.hierarchy(query="enemy")] == ["Enemy"]
    assert [row.label for row in inspector.hierarchy(include_disabled=False)] == ["Player", "Enemy"]


def test_hierarchy_parenting_builds_depth_first_tree_across_objects_and_entities():
    scene = Scene()
    root = scene.add(Actor("Root"))
    child = scene.add(Actor("Child"))
    entity = scene.create_entity(name="EntityChild")
    inspector = SceneInspector(scene)

    inspector.set_parent(child, root)
    inspector.set_parent(entity, child)

    rows = inspector.hierarchy()
    assert [row.label for row in rows] == ["Root", "Child", "EntityChild"]
    assert [row.depth for row in rows] == [0, 1, 2]
    assert rows[1].parent_key == inspector.key_for(root)
    assert rows[2].parent_key == inspector.key_for(child)
    assert inspector.parent(child) is root
    assert inspector.parent(entity) is child
    assert inspector.children(root) == (child,)
    assert inspector.children(child) == (entity,)


def test_hierarchy_reordering_and_reparent_index_are_deterministic():
    scene = Scene()
    root = scene.add(Actor("Root"))
    first = scene.add(Actor("First"))
    second = scene.add(Actor("Second"))
    third = scene.add(Actor("Third"))
    inspector = SceneInspector(scene)

    inspector.set_parent(first, root)
    inspector.set_parent(second, root)
    inspector.set_parent(third, root, index=1)
    assert inspector.children(root) == (first, third, second)

    inspector.move(second, 0)
    assert inspector.children(root) == (second, first, third)
    child_rows = [row for row in inspector.hierarchy() if row.parent_key == inspector.key_for(root)]
    assert [row.label for row in child_rows] == ["Second", "First", "Third"]
    assert [row.order for row in child_rows] == [0, 1, 2]

    with pytest.raises(IndexError):
        inspector.move(first, 5)
    with pytest.raises(IndexError):
        inspector.set_parent(first, None, index=99)


def test_structural_reparent_and_move_share_unified_undo_redo_history():
    scene = Scene()
    root = scene.add(Actor("Root"))
    first = scene.add(Actor("First"))
    second = scene.add(Actor("Second"))
    inspector = SceneInspector(scene)

    reparent = inspector.set_parent(first, root)
    assert isinstance(reparent, HierarchyEdit)
    assert inspector.parent(first) is root

    move_root = inspector.move(second, 0)
    assert isinstance(move_root, HierarchyEdit)
    assert inspector.children() == (second, root)

    inspector.undo()
    assert inspector.children() == (root, second)
    inspector.undo()
    assert inspector.parent(first) is None
    assert inspector.children() == (root, first, second)

    inspector.redo()
    assert inspector.parent(first) is root
    inspector.redo()
    assert inspector.children() == (second, root)


def test_property_and_hierarchy_edits_preserve_global_chronological_history():
    scene = Scene()
    root = scene.add(Actor("Root"))
    child = scene.add(Actor("Child", health=100))
    inspector = SceneInspector(scene)

    inspector.set_parent(child, root)
    inspector.set_property("health", 50, target=child)

    assert isinstance(inspector.undo_history[0], HierarchyEdit)
    assert isinstance(inspector.undo_history[1], PropertyEdit)

    inspector.undo()
    assert child.health == 100
    assert inspector.parent(child) is root
    inspector.undo()
    assert inspector.parent(child) is None

    inspector.redo()
    assert inspector.parent(child) is root
    inspector.redo()
    assert child.health == 50


def test_new_structural_edit_clears_redo_and_respects_shared_history_limit():
    scene = Scene()
    root = scene.add(Actor("Root"))
    first = scene.add(Actor("First"))
    second = scene.add(Actor("Second"))
    inspector = SceneInspector(scene, history_limit=2)

    inspector.set_parent(first, root)
    inspector.set_parent(second, root)
    inspector.move(second, 0)
    assert len(inspector.undo_history) == 2

    inspector.undo()
    assert inspector.can_redo
    inspector.set_parent(second, None)
    assert not inspector.can_redo


def test_structural_history_detects_destroyed_targets_without_corruption():
    scene = Scene()
    root = scene.add(Actor("Root"))
    entity = scene.create_entity(name="Temporary")
    inspector = SceneInspector(scene)
    inspector.set_parent(entity, root)
    scene.ecs.destroy(entity)

    with pytest.raises(LookupError):
        inspector.undo()

    assert inspector.can_undo
    assert not inspector.can_redo


def test_structural_history_detects_destroyed_parent_without_corruption():
    scene = Scene()
    root = scene.add(Actor("Root"))
    child = scene.add(Actor("Child"))
    inspector = SceneInspector(scene)
    inspector.set_parent(child, root)
    inspector.undo()
    scene.remove(root)

    with pytest.raises(LookupError):
        inspector.redo()

    assert inspector.can_redo


def test_hierarchy_cycle_prevention_and_stale_parent_cleanup():
    scene = Scene()
    parent = scene.add(Actor("Parent"))
    child = scene.add(Actor("Child"))
    grandchild = scene.add(Actor("Grandchild"))
    inspector = SceneInspector(scene)

    inspector.set_parent(child, parent)
    inspector.set_parent(grandchild, child)

    with pytest.raises(ValueError):
        inspector.set_parent(parent, grandchild)
    with pytest.raises(ValueError):
        inspector.set_parent(parent, parent)

    scene.remove(parent)
    rows = inspector.hierarchy()
    assert [row.label for row in rows] == ["Child", "Grandchild"]
    assert rows[0].depth == 0
    assert inspector.parent(child) is None
    assert inspector.children() == (child,)


def test_runtime_object_key_and_selection_survive_scene_reordering():
    scene = Scene()
    first = scene.add(Actor("First"))
    second = scene.add(Actor("Second"))
    inspector = SceneInspector(scene)

    key = inspector.key_for(second)
    assert inspector.select(key) is second

    scene.remove(first)
    scene.add(Actor("Third"))

    assert inspector.selected_key == key
    assert inspector.selected_target is second
    assert inspector.resolve(key) is second


def test_entity_snapshot_exposes_public_state_and_component_names():
    scene = Scene()
    entity = scene.create_entity(name="Mover", tags={"active"})
    entity.add(Velocity(3.0, 4.0))
    inspector = SceneInspector(scene)

    snapshot = inspector.inspect(entity)

    assert snapshot is not None
    assert snapshot.key == f"entity:{entity.id}"
    assert snapshot.components == ("Velocity",)
    fields = {field.name: field for field in snapshot.fields}
    assert fields["name"].value == "Mover"
    assert fields["enabled"].editable
    assert "_components" not in fields


def test_component_snapshot_and_property_editing_share_entity_selection():
    scene = Scene()
    entity = scene.create_entity(name="Mover")
    velocity = entity.add(Velocity(3.0, 4.0))
    inspector = SceneInspector(scene)
    inspector.select(entity)

    snapshot = inspector.inspect_component(Velocity)
    assert snapshot is not None
    assert snapshot.key == f"entity:{entity.id}"
    assert snapshot.type_name == "Velocity"
    assert {field.name: field.value for field in snapshot.fields} == {"x": 3.0, "y": 4.0}

    edit = inspector.set_component_property(Velocity, "x", 9.5)
    assert edit.component_type is Velocity
    assert velocity.x == 9.5
    inspector.undo()
    assert velocity.x == 3.0
    inspector.redo()
    assert velocity.x == 9.5


def test_component_edit_history_detects_removed_component():
    scene = Scene()
    entity = scene.create_entity(name="Mover")
    entity.add(Velocity(1.0, 2.0))
    inspector = SceneInspector(scene)
    inspector.set_component_property(Velocity, "y", 8.0, target=entity)
    entity.remove(Velocity)

    with pytest.raises(LookupError):
        inspector.undo()

    assert inspector.can_undo


def test_component_inspection_rejects_non_entities_and_missing_components():
    scene = Scene()
    actor = scene.add(Actor("Player"))
    entity = scene.create_entity(name="Empty")
    inspector = SceneInspector(scene)

    with pytest.raises(TypeError):
        inspector.inspect_component(Velocity, target=actor)
    with pytest.raises(KeyError):
        inspector.inspect_component(Velocity, target=entity)


def test_property_edits_support_undo_redo_and_clear_redo_on_new_change():
    scene = Scene()
    actor = scene.add(Actor("Player", health=100))
    inspector = SceneInspector(scene)
    inspector.select(actor)

    edit = inspector.set_property("health", 75)
    assert (edit.before, edit.after) == (100, 75)
    assert actor.health == 75
    assert inspector.can_undo
    assert not inspector.can_redo

    inspector.undo()
    assert actor.health == 100
    assert inspector.can_redo

    inspector.redo()
    assert actor.health == 75

    inspector.undo()
    inspector.set_property("health", 50)
    assert actor.health == 50
    assert not inspector.can_redo


def test_history_limit_and_foreign_targets_are_validated():
    scene = Scene()
    actor = scene.add(Actor("Player", health=3))
    inspector = SceneInspector(scene, history_limit=2)

    inspector.set_property("health", 2, target=actor)
    inspector.set_property("health", 1, target=actor)
    inspector.set_property("health", 0, target=actor)
    assert len(inspector.undo_history) == 2

    with pytest.raises(ValueError):
        inspector.inspect(Actor("Foreign"))

    with pytest.raises(AttributeError):
        inspector.set_property("_private", 1, target=actor)


def test_destroyed_edit_target_does_not_corrupt_history():
    scene = Scene()
    entity = scene.create_entity(name="Temporary")
    inspector = SceneInspector(scene)
    inspector.set_property("name", "Changed", target=entity)
    scene.ecs.destroy(entity)

    with pytest.raises(LookupError):
        inspector.undo()

    assert inspector.can_undo
