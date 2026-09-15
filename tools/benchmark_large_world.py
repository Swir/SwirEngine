from __future__ import annotations

from time import perf_counter

from swirengine.core.scene import Scene
from swirengine.large_world import (
    ChunkContent,
    ChunkDefinition,
    ChunkKey,
    LargeWorldSettings,
    LargeWorldStreamer,
)
from swirengine.math.types import Vec3


def main() -> None:
    provider_calls = 0

    def procedural_provider(key: ChunkKey) -> ChunkDefinition:
        nonlocal provider_calls
        provider_calls += 1
        return ChunkDefinition(key, lambda _context: ChunkContent())

    settings = LargeWorldSettings(
        chunk_size=64.0,
        dimensions=3,
        active_radius_chunks=1,
        preload_radius_chunks=2,
        retention_radius_chunks=3,
        max_activations_per_update=8,
        max_deactivations_per_update=64,
    )
    streamer = LargeWorldStreamer(Scene(), procedural_provider, settings=settings)

    expected_window = (settings.preload_radius_chunks * 2 + 1) ** settings.dimensions
    max_candidates = 0
    max_tracked = 0
    updates = 600

    started = perf_counter()
    for step in range(updates):
        # Jump far enough that the previous local residency window cannot grow without bound.
        focus = Vec3(step * settings.chunk_size * 10.0, 0.0, 0.0)
        result = streamer.update(focus)
        max_candidates = max(max_candidates, result.diagnostics.candidate_keys)
        max_tracked = max(max_tracked, result.diagnostics.tracked_chunks)
    elapsed = perf_counter() - started

    if max_candidates != expected_window:
        raise SystemExit(
            f"large-world regression: expected {expected_window} local candidates, "
            f"observed {max_candidates}"
        )
    if max_tracked > expected_window + 8:
        raise SystemExit(
            "large-world regression: tracked residency grew beyond the bounded local window "
            f"({max_tracked} > {expected_window + 8})"
        )

    print("SwirEngine large-world local-window benchmark")
    print(f"updates={updates}")
    print(f"preload_window_candidates={max_candidates}")
    print(f"max_tracked_chunks={max_tracked}")
    print(f"provider_calls={provider_calls}")
    print(f"elapsed_seconds={elapsed:.6f}")
    print("contract=streaming work scales with local chunk window, not conceptual world extent")
    print("note=host timing is diagnostic only; this benchmark makes no FPS claim")


if __name__ == "__main__":
    main()
