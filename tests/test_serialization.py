from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from swirengine import (
    Color,
    Prefab,
    Rectangle2D,
    Scene,
    SceneCodecRegistry,
    SceneSerializationError,
    SceneSerializer,
    Sprite2D,
)


def test_scene_round_trip_preserves_builtin_values_and_order(tmp_path: Path) -> None:
    scene = Scene()
    scene.add(
        Rectangle2D(
            10,
            20,
            30,
            40,
            color=Color(0.1, 0.2, 0.3, 0.4),
            name="panel",
            tags={"ui", "solid"},
            layer=3,
        )
    )
    scene.add(Sprite2D(tmp_path / "hero.png", x=5, y=7, uv_rect=(0.0, 0.0, 0.5, 1.0)))

    serializer = SceneSerializer()
    text = serializer.dumps_scene(scene)
    restored = serializer.loads_scene(text)

    assert len(restored) == 2
    rectangle = restored.objects[0]
    sprite = restored.objects[1]
    assert isinstance(rectangle, Rectangle2D)
    assert rectangle.name == "panel"
    assert rectangle.tags == {"ui", "solid"}
    assert rectangle.color == Color(0.1, 0.2, 0.3, 0.4)
    assert isinstance(sprite, Sprite2D)
    assert sprite.texture == tmp_path / "hero.png"
    assert sprite.uv_rect == (0.0, 0.0, 0.5, 1.0)


def test_scene_file_helpers_can_replace_an_existing_scene(tmp_path: Path) -> None:
    serializer = SceneSerializer()
    source = Scene()
    source.add(Rectangle2D(1, 2, 3, 4, name="saved"))
    path = serializer.dump_scene(source, tmp_path / "levels" / "one.swirscene")

    target = Scene()
    target.add(Rectangle2D(0, 0, 1, 1, name="old"))
    loaded = serializer.load_scene(path, scene=target, clear=True)

    assert loaded is target
    assert len(target) == 1
    assert target.find("saved") is not None
    assert target.find("old") is None


def test_prefab_round_trip_keeps_name_and_independent_spawns() -> None:
    serializer = SceneSerializer()
    prefab = Prefab(Rectangle2D(1, 2, 3, 4, name="crate", tags={"loot"}), name="crate_prefab")

    restored = serializer.loads_prefab(serializer.dumps_prefab(prefab))
    first = restored.instantiate()
    second = restored.instantiate()

    assert restored.name == "crate_prefab"
    assert first.root is not second.root
    assert first.find("crate") is not None
    assert first.tagged("loot")


@dataclass(slots=True)
class LinkNode:
    name: str
    peer: LinkNode | None = None
    tags: set[str] | None = None


def test_custom_registered_dataclasses_preserve_cross_object_references() -> None:
    registry = SceneCodecRegistry.default()
    registry.register(LinkNode, name="tests.LinkNode")
    serializer = SceneSerializer(registry)
    left = LinkNode("left", tags={"a"})
    right = LinkNode("right", tags={"b"})
    left.peer = right
    right.peer = left
    scene = Scene()
    scene.add_many(left, right)

    restored = serializer.loads_scene(serializer.dumps_scene(scene))
    restored_left, restored_right = restored.objects

    assert isinstance(restored_left, LinkNode)
    assert isinstance(restored_right, LinkNode)
    assert restored_left.peer is restored_right
    assert restored_right.peer is restored_left
    assert restored_left.tags == {"a"}


def test_unknown_types_are_rejected_without_dynamic_imports() -> None:
    document = {
        "format": "swirengine.scene",
        "version": 1,
        "objects": [{"type": "evil.module.Payload", "data": {}}],
    }

    with pytest.raises(SceneSerializationError, match="not registered"):
        SceneSerializer().loads_scene(json.dumps(document))


def test_version_and_schema_errors_are_explicit() -> None:
    serializer = SceneSerializer()
    with pytest.raises(SceneSerializationError, match="version"):
        serializer.loads_scene('{"format":"swirengine.scene","version":999,"objects":[]}')

    bad = {
        "format": "swirengine.scene",
        "version": 1,
        "objects": [
            {
                "type": "swirengine.graphics.primitives.Rectangle2D",
                "data": {"x": 1},
            }
        ],
    }
    with pytest.raises(SceneSerializationError, match="missing fields"):
        serializer.loads_scene(json.dumps(bad))


def test_unsupported_scene_object_points_to_registry() -> None:
    class Unsupported:
        pass

    scene = Scene()
    scene.add(Unsupported())
    with pytest.raises(SceneSerializationError, match="register"):
        SceneSerializer().dumps_scene(scene)
