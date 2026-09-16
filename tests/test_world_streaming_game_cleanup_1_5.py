from __future__ import annotations

from dataclasses import dataclass

from swirengine.core.scene import Scene
from swirengine.world_streaming_easy15 import world_stream


@dataclass
class Marker:
    name: str


class GameLikeOwner:
    def __init__(self) -> None:
        self.scene = Scene()
        self.removed: list[object] = []

    def remove(self, obj: object) -> bool:
        self.removed.append(obj)
        return self.scene.remove(obj)


class FailingRemoveOwner(GameLikeOwner):
    def __init__(self) -> None:
        super().__init__()
        self.fail_on: object | None = None

    def remove(self, obj: object) -> bool:
        self.removed.append(obj)
        if obj is self.fail_on:
            raise RuntimeError("owner cleanup failed")
        return self.scene.remove(obj)


def test_world_stream_uses_owner_remove_for_streamed_object_cleanup() -> None:
    owner = GameLikeOwner()
    marker = Marker("game-managed")
    world = world_stream(
        owner,
        dimensions=2,
        chunk_size=10,
        radius=0,
        budget=1,
        retention_updates=0,
    )
    world.add_chunk("managed", (0, 0), lambda _ctx: marker)

    world.update((1.0, 1.0))
    assert marker in owner.scene

    world.update((21.0, 1.0))
    assert marker not in owner.scene
    assert owner.removed == [marker]


def test_owner_remove_is_used_when_activation_hook_rolls_back() -> None:
    owner = GameLikeOwner()
    marker = Marker("activation-rollback")
    world = world_stream(
        owner,
        dimensions=2,
        chunk_size=10,
        radius=0,
        budget=1,
        retention_updates=0,
    )

    def fail_activation(_ctx, _content) -> None:
        raise RuntimeError("creator hook failed")

    world.add_chunk(
        "fragile",
        (0, 0),
        lambda _ctx: marker,
        on_activate=fail_activation,
    )
    result = world.update((1.0, 1.0))

    assert result.activated == ()
    assert marker not in owner.scene
    assert owner.removed == [marker]
    assert len(world.failures) == 1
    assert "creator hook failed" in world.failures[0].message


def test_owner_cleanup_continues_after_one_remover_error() -> None:
    owner = FailingRemoveOwner()
    first = Marker("first")
    second = Marker("second")
    owner.fail_on = first
    world = world_stream(
        owner,
        dimensions=2,
        chunk_size=10,
        radius=0,
        budget=1,
        retention_updates=0,
    )
    world.add_chunk("managed", (0, 0), lambda _ctx: [first, second])

    world.update((1.0, 1.0))
    result = world.update((21.0, 1.0))

    assert first not in owner.scene
    assert second not in owner.scene
    assert owner.removed == [first, second]
    assert len(result.failed) == 1
    assert "owner cleanup failed" in result.failed[0].message


def test_raw_scene_keeps_plain_scene_ownership() -> None:
    scene = Scene()
    marker = Marker("scene-owned")
    world = world_stream(
        scene,
        dimensions=2,
        chunk_size=10,
        radius=0,
        budget=1,
        retention_updates=0,
    )
    world.add_chunk("plain", (0, 0), lambda _ctx: marker)

    world.update((1.0, 1.0))
    assert marker in scene
    world.update((21.0, 1.0))
    assert marker not in scene
