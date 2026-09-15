from __future__ import annotations

from swirengine.core.scene import Scene
from swirengine.large_world import (
    ChunkContent,
    ChunkDefinition,
    ChunkKey,
    ChunkRegistry,
    LargeWorldSettings,
    LargeWorldStreamer,
)


def _settings() -> LargeWorldSettings:
    return LargeWorldSettings(
        chunk_size=16,
        dimensions=2,
        active_radius_chunks=1,
        preload_radius_chunks=1,
        retention_radius_chunks=2,
        max_activations_per_update=16,
        max_deactivations_per_update=16,
    )


def test_sparse_callable_provider_misses_are_cached_and_explicitly_invalidated():
    available: set[ChunkKey] = set()
    calls = 0

    def provider(key: ChunkKey) -> ChunkDefinition | None:
        nonlocal calls
        calls += 1
        if key not in available:
            return None
        return ChunkDefinition(key, lambda _context: ChunkContent())

    streamer = LargeWorldStreamer(Scene(), provider, settings=_settings())

    first = streamer.update((0.0, 0.0))
    second = streamer.update((0.0, 0.0))

    assert first.diagnostics.provider_queries == 9
    assert first.diagnostics.cached_missing_chunks == 9
    assert second.diagnostics.provider_queries == 0
    assert calls == 9

    key = ChunkKey(0, 0)
    available.add(key)
    streamer.invalidate_provider_cache(key)
    recovered = streamer.update((0.0, 0.0))

    assert recovered.diagnostics.provider_queries == 1
    assert recovered.activated == (key,)
    assert calls == 10


def test_chunk_registry_revision_invalidates_negative_cache_automatically():
    registry = ChunkRegistry()
    streamer = LargeWorldStreamer(Scene(), registry, settings=_settings())

    first = streamer.update((0.0, 0.0))
    second = streamer.update((0.0, 0.0))
    assert first.diagnostics.provider_queries == 9
    assert second.diagnostics.provider_queries == 0

    key = ChunkKey(1, 0)
    revision = registry.revision
    registry.add(ChunkDefinition(key, lambda _context: ChunkContent()))
    assert registry.revision == revision + 1

    updated = streamer.update((0.0, 0.0))
    assert updated.diagnostics.provider_queries == 9
    assert key in streamer.active_keys


def test_sparse_miss_cache_is_pruned_with_retention_instead_of_growing_forever():
    streamer = LargeWorldStreamer(Scene(), lambda _key: None, settings=_settings())

    max_cached_missing = 0
    for step in range(250):
        result = streamer.update((step * 160.0, 0.0))
        max_cached_missing = max(
            max_cached_missing,
            result.diagnostics.cached_missing_chunks,
        )

    assert max_cached_missing <= 9
    assert streamer.diagnostics.provider_queries == 9
