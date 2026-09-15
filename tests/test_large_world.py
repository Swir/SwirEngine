from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path

import pytest

from swirengine.asset_pipeline import AssetLoadResult
from swirengine.core.scene import Scene
from swirengine.graphics.primitives import Cube3D, Rectangle2D
from swirengine.large_world import (
    ChunkContent,
    ChunkDefinition,
    ChunkKey,
    ChunkRegistry,
    LargeWorldSettings,
    LargeWorldStreamer,
)
from swirengine.math.types import Vec2, Vec3


class _FakeAssets:
    def __init__(self, root: Path) -> None:
        self.root = root

    def require(self, asset: str | Path) -> Path:
        path = Path(asset)
        if not path.is_absolute():
            path = self.root / path
        return path


class _FakeStreamer:
    def __init__(self, root: Path) -> None:
        self.assets = _FakeAssets(root)
        self.staged: list[tuple[Path, bool]] = []
        self.touched: list[Path] = []
        self.unpinned: list[Path] = []
        self.pump_budgets: list[int] = []

    def stage(self, asset: str | Path, *, pin: bool = False) -> Future[AssetLoadResult]:
        path = self.assets.require(asset).expanduser().resolve()
        self.staged.append((path, pin))
        future: Future[AssetLoadResult] = Future()
        future.set_result(
            AssetLoadResult(
                asset=str(asset),
                path=path,
                value=object(),
                duration_ns=0,
                cache_hit=False,
            )
        )
        return future

    def pump(self, *, max_completions: int = 4) -> tuple[AssetLoadResult, ...]:
        self.pump_budgets.append(max_completions)
        return ()

    def touch(self, asset: str | Path) -> bool:
        self.touched.append(Path(asset).resolve())
        return True

    def unpin(self, asset: str | Path) -> bool:
        self.unpinned.append(Path(asset).resolve())
        return True


def _empty_definition(key: ChunkKey) -> ChunkDefinition:
    return ChunkDefinition(key, lambda _context: ChunkContent())


def test_settings_reject_invalid_radius_and_budget_relationships():
    with pytest.raises(ValueError, match="chunk_size"):
        LargeWorldSettings(chunk_size=0)
    with pytest.raises(ValueError, match="dimensions"):
        LargeWorldSettings(dimensions=4)
    with pytest.raises(ValueError, match="preload_radius_chunks"):
        LargeWorldSettings(active_radius_chunks=2, preload_radius_chunks=1)
    with pytest.raises(ValueError, match="retention_radius_chunks"):
        LargeWorldSettings(preload_radius_chunks=2, retention_radius_chunks=1)
    with pytest.raises(ValueError, match="max_activations"):
        LargeWorldSettings(max_activations_per_update=0)


def test_focus_keys_use_floor_for_positive_and_negative_world_coordinates():
    scene = Scene()
    world_2d = LargeWorldStreamer(
        scene,
        lambda _key: None,
        settings=LargeWorldSettings(chunk_size=10, dimensions=2),
    )
    world_3d = LargeWorldStreamer(
        scene,
        lambda _key: None,
        settings=LargeWorldSettings(chunk_size=10, dimensions=3),
    )

    assert world_2d.focus_key(Vec2(19.9, -0.1)) == ChunkKey(1, -1, 0)
    assert world_2d.focus_key((20.0, -10.0)) == ChunkKey(2, -1, 0)
    assert world_3d.focus_key(Vec3(-0.1, 20.0, -10.1)) == ChunkKey(-1, 2, -2)
    assert world_3d.focus_key((0, 0, 29.9)) == ChunkKey(0, 0, 2)


def test_2d_provider_work_is_exactly_local_preload_window_not_world_size():
    calls: list[ChunkKey] = []

    def provider(key: ChunkKey) -> ChunkDefinition:
        calls.append(key)
        return _empty_definition(key)

    streamer = LargeWorldStreamer(
        Scene(),
        provider,
        settings=LargeWorldSettings(
            chunk_size=32,
            dimensions=2,
            active_radius_chunks=0,
            preload_radius_chunks=2,
            retention_radius_chunks=3,
            max_activations_per_update=1,
        ),
    )

    first = streamer.update((0.0, 0.0))
    second = streamer.update((0.0, 0.0))

    assert first.diagnostics.candidate_keys == 25
    assert first.diagnostics.provider_queries == 25
    assert len(calls) == 25
    assert second.diagnostics.candidate_keys == 25
    assert second.diagnostics.provider_queries == 0
    assert len(calls) == 25


def test_3d_provider_work_is_exactly_local_preload_cube():
    calls = 0

    def provider(key: ChunkKey) -> ChunkDefinition:
        nonlocal calls
        calls += 1
        return _empty_definition(key)

    streamer = LargeWorldStreamer(
        Scene(),
        provider,
        settings=LargeWorldSettings(
            chunk_size=16,
            dimensions=3,
            active_radius_chunks=0,
            preload_radius_chunks=1,
            retention_radius_chunks=2,
            max_activations_per_update=1,
        ),
    )

    result = streamer.update(Vec3())

    assert result.diagnostics.candidate_keys == 27
    assert result.diagnostics.provider_queries == 27
    assert calls == 27


def test_activation_budget_is_nearest_first_and_scene_mounts_are_reversible():
    scene = Scene()

    def provider(key: ChunkKey) -> ChunkDefinition:
        return ChunkDefinition(
            key,
            lambda context: ChunkContent(
                objects=(
                    Rectangle2D(
                        context.center.x,
                        context.center.y,
                        4,
                        4,
                        name=f"chunk-{context.key.x}-{context.key.y}",
                    ),
                )
            ),
        )

    streamer = LargeWorldStreamer(
        scene,
        provider,
        settings=LargeWorldSettings(
            chunk_size=10,
            dimensions=2,
            active_radius_chunks=1,
            preload_radius_chunks=1,
            retention_radius_chunks=1,
            max_activations_per_update=2,
            max_deactivations_per_update=32,
        ),
    )

    first = streamer.update((0.0, 0.0))
    assert first.activated == (ChunkKey(0, 0), ChunkKey(-1, 0))
    assert len(scene.objects) == 2

    for _ in range(4):
        streamer.update((0.0, 0.0))
    assert len(streamer.active_keys) == 9
    assert len(scene.objects) == 9

    moved = streamer.update((100.0, 0.0))
    assert moved.deactivated
    assert all(key.x >= 9 for key in streamer.active_keys)
    assert all("chunk-" in obj.name for obj in scene.objects)


def test_visibility_hook_keeps_chunk_ready_without_activating_it():
    streamer = LargeWorldStreamer(
        Scene(),
        _empty_definition,
        settings=LargeWorldSettings(
            dimensions=2,
            active_radius_chunks=0,
            preload_radius_chunks=0,
            retention_radius_chunks=0,
        ),
    )

    hidden = streamer.update((0.0, 0.0), visibility=lambda _context, _definition: False)
    visible = streamer.update((0.0, 0.0), visibility=lambda _context, _definition: True)

    assert hidden.activated == ()
    assert hidden.diagnostics.ready_chunks == 1
    assert visible.activated == (ChunkKey(0, 0),)


def test_factory_failure_is_reported_and_never_claimed_as_activation():
    attempts = 0

    def factory(_context):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("broken chunk")
        return ChunkContent()

    key = ChunkKey(0, 0)
    streamer = LargeWorldStreamer(
        Scene(),
        ChunkRegistry((ChunkDefinition(key, factory),)),
        settings=LargeWorldSettings(
            dimensions=2,
            active_radius_chunks=0,
            preload_radius_chunks=0,
            retention_radius_chunks=0,
        ),
    )

    failed = streamer.update((0.0, 0.0))
    assert failed.activated == ()
    assert streamer.active_keys == ()
    assert len(streamer.failures()) == 1
    assert "broken chunk" in streamer.failures()[0].message

    assert streamer.retry(key)
    recovered = streamer.update((0.0, 0.0))
    assert recovered.activated == (key,)
    assert streamer.failures() == ()


def test_shared_chunk_asset_is_unpinned_only_after_last_reference_leaves(tmp_path):
    shared = (tmp_path / "shared.bin").resolve()
    fake_streamer = _FakeStreamer(tmp_path)
    definitions = ChunkRegistry(
        (
            ChunkDefinition(ChunkKey(0, 0), lambda _context: ChunkContent(), assets=(shared,)),
            ChunkDefinition(ChunkKey(1, 0), lambda _context: ChunkContent(), assets=(shared,)),
        )
    )
    streamer = LargeWorldStreamer(
        Scene(),
        definitions,
        settings=LargeWorldSettings(
            chunk_size=10,
            dimensions=2,
            active_radius_chunks=1,
            preload_radius_chunks=1,
            retention_radius_chunks=1,
            max_activations_per_update=8,
            max_deactivations_per_update=32,
            max_asset_completions_per_update=7,
        ),
        asset_streamer=fake_streamer,
    )

    streamer.update((0.0, 0.0))
    streamer.update((0.0, 0.0))
    assert len(fake_streamer.staged) == 2
    assert all(pin for _, pin in fake_streamer.staged)
    assert fake_streamer.pump_budgets == [7, 7]
    assert fake_streamer.unpinned == []

    streamer.update((100.0, 0.0))
    assert fake_streamer.unpinned == [shared]


def test_long_distance_travel_does_not_accumulate_entire_world_state():
    streamer = LargeWorldStreamer(
        Scene(),
        _empty_definition,
        settings=LargeWorldSettings(
            chunk_size=8,
            dimensions=2,
            active_radius_chunks=0,
            preload_radius_chunks=1,
            retention_radius_chunks=2,
            max_activations_per_update=1,
            max_deactivations_per_update=16,
        ),
    )

    max_tracked = 0
    max_candidates = 0
    for step in range(250):
        result = streamer.update((step * 80.0, 0.0))
        max_tracked = max(max_tracked, result.diagnostics.tracked_chunks)
        max_candidates = max(max_candidates, result.diagnostics.candidate_keys)

    assert max_candidates == 9
    assert max_tracked <= 10
    assert streamer.diagnostics.total_unloads > 100


def test_chunk_factory_can_mount_existing_scene_entities_and_unmount_destroys_them():
    scene = Scene()

    def factory(context):
        entity = context.scene.create_entity(name=f"entity-{context.key.x}")
        return ChunkContent(
            objects=(Cube3D(position=context.center),),
            entities=(entity,),
        )

    streamer = LargeWorldStreamer(
        scene,
        lambda key: ChunkDefinition(key, factory),
        settings=LargeWorldSettings(
            chunk_size=10,
            dimensions=2,
            active_radius_chunks=0,
            preload_radius_chunks=0,
            retention_radius_chunks=0,
            max_deactivations_per_update=8,
        ),
    )

    streamer.update((0.0, 0.0))
    assert len(scene.objects) == 1
    assert len(scene.entities) == 1

    streamer.update((100.0, 0.0))
    assert len(scene.objects) == 1  # new focus chunk replaces the previous mount
    assert len(scene.entities) == 1
