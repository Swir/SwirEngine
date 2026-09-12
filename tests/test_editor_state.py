from dataclasses import dataclass

import pytest

from swirengine import Scene
from swirengine.editor import SceneInspector
from swirengine.editor_state import (
    EDITOR_HIERARCHY_FORMAT,
    EditorHierarchyNode,
    EditorHierarchyState,
    EditorTargetRef,
    capture_editor_hierarchy,
    restore_editor_hierarchy,
)
from swirengine.serialization import SceneCodecRegistry, SceneSerializer


@dataclass
class Actor:
    name: str
    enabled: bool = True
    tags: set[str] | None = None

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = set()


def make_serializer() -> SceneSerializer:
    registry = SceneCodecRegistry.default()
    registry.register(Actor)
    return SceneSerializer(registry)


def test_editor_hierarchy_state_round_trips_as_plain_data():
    scene = Scene()
    root = scene.add(Actor("Root"))
    child = scene.add(Actor("Child"))
    entity = scene.create_entity(entity_id=42, name="Entity")
    inspector = SceneInspector(scene)
    inspector.set_parent(child, root)
    inspector.set_parent(entity, child)
    inspector.select(entity)

    state = capture_editor_hierarchy(inspector)
    payload = state.to_dict()
    restored = EditorHierarchyState.from_dict(payload)

    assert payload["format"] == EDITOR_HIERARCHY_FORMAT
    assert restored == state
    assert restored.selection == EditorTargetRef("entity", 42)
    assert [node.target for node in restored.nodes] == [
        EditorTargetRef("object", 0),
        EditorTargetRef("object", 1),
        EditorTargetRef("entity", 42),
    ]


def test_editor_hierarchy_survives_scene_serialization_and_runtime_identity_changes():
    scene = Scene()
    root = scene.add(Actor("Root"))
    first = scene.add(Actor("First"))
    second = scene.add(Actor("Second"))
    entity = scene.create_entity(entity_id=7, name="Entity")
    inspector = SceneInspector(scene)
    inspector.set_parent(first, root)
    inspector.set_parent(entity, root, index=0)
    inspector.set_parent(second, first)
    inspector.select(second)
    state = capture_editor_hierarchy(inspector)

    serializer = make_serializer()
    reloaded_scene = serializer.loads_scene(serializer.dumps_scene(scene))
    reloaded = SceneInspector(reloaded_scene)
    restore_editor_hierarchy(reloaded, state)

    rows = reloaded.hierarchy()
    assert [row.label for row in rows] == ["Root", "Entity", "First", "Second"]
    assert [row.depth for row in rows] == [0, 1, 1, 2]
    assert reloaded.selected_target is reloaded_scene.objects[2]
    assert not reloaded.can_undo
    assert not reloaded.can_redo


def test_restore_can_preserve_generated_history_when_requested():
    scene = Scene()
    root = scene.add(Actor("Root"))
    child = scene.add(Actor("Child"))
    source = SceneInspector(scene)
    source.set_parent(child, root)
    state = capture_editor_hierarchy(source)

    target = SceneInspector(scene)
    restore_editor_hierarchy(target, state, clear_history=False)

    assert target.parent(child) is root
    assert target.can_undo


def test_restore_resolves_every_reference_before_mutating_live_hierarchy():
    scene = Scene()
    first = scene.add(Actor("First"))
    second = scene.add(Actor("Second"))
    inspector = SceneInspector(scene)
    inspector.set_parent(second, first)
    inspector.clear_history()
    before = capture_editor_hierarchy(inspector)

    broken = EditorHierarchyState(
        (
            EditorHierarchyNode(EditorTargetRef("object", 0), None, 0),
            EditorHierarchyNode(
                EditorTargetRef("object", 9),
                EditorTargetRef("object", 0),
                0,
            ),
        )
    )

    with pytest.raises(LookupError):
        restore_editor_hierarchy(inspector, broken)

    assert capture_editor_hierarchy(inspector) == before
    assert not inspector.can_undo


def test_editor_hierarchy_state_rejects_duplicate_targets_cycles_and_foreign_selection():
    root = EditorTargetRef("object", 0)
    child = EditorTargetRef("object", 1)

    with pytest.raises(ValueError, match="duplicate"):
        EditorHierarchyState(
            (
                EditorHierarchyNode(root, None, 0),
                EditorHierarchyNode(root, None, 1),
            )
        )

    with pytest.raises(ValueError, match="cycle"):
        EditorHierarchyState(
            (
                EditorHierarchyNode(root, child, 0),
                EditorHierarchyNode(child, root, 0),
            )
        )

    with pytest.raises(ValueError, match="selection"):
        EditorHierarchyState(
            (EditorHierarchyNode(root, None, 0),),
            selection=child,
        )
