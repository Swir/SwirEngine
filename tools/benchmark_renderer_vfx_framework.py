from __future__ import annotations

import argparse
import time
import tracemalloc
from pathlib import Path

from swirengine import ParticleEmitter2D, Sprite2D
from swirengine.graphics import batching
from swirengine.graphics.batching import build_render_runs, iter_render_runs
from swirengine.math.types import Color


def _measure_peak(callback, *, repeats: int) -> tuple[float, int]:
    tracemalloc.start()
    started = time.perf_counter()
    for _ in range(repeats):
        callback()
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return elapsed, peak


def main() -> None:
    parser = argparse.ArgumentParser(description="SwirEngine 1.2 renderer/VFX frame-work benchmark")
    parser.add_argument("--sprites", type=int, default=5000)
    parser.add_argument("--repeats", type=int, default=50)
    parser.add_argument("--particles", type=int, default=2000)
    args = parser.parse_args()

    texture = Path("benchmark-atlas.png")
    sprites = [Sprite2D(texture, x=float(index)) for index in range(max(1, args.sprites))]

    def materialized_runs() -> None:
        tuple(iter_render_runs(sprites))

    def streamed_runs() -> None:
        for _ in build_render_runs(sprites):
            pass

    materialized_time, materialized_peak = _measure_peak(
        materialized_runs,
        repeats=max(1, args.repeats),
    )
    streamed_time, streamed_peak = _measure_peak(
        streamed_runs,
        repeats=max(1, args.repeats),
    )

    batching._canonical_texture_key.cache_clear()
    batching._cached_sprite_batch_key.cache_clear()
    probe = sprites[0]
    first_key = batching.sprite_batch_key(probe)
    identity_hits = sum(batching.sprite_batch_key(probe) is first_key for _ in range(10_000))

    color = Color(0.2, 0.4, 0.6, 1.0)
    color_identity_hits = sum(color.clamped() is color for _ in range(10_000))

    emitter = ParticleEmitter2D(
        max_particles=max(1, args.particles),
        emitting=False,
        seed=42,
    )
    started = time.perf_counter()
    emitter.emit(max(1, args.particles))
    particle_emit_time = time.perf_counter() - started

    print(f"sprites={len(sprites)} repeats={max(1, args.repeats)}")
    print(f"materialized_runs_seconds={materialized_time:.6f}")
    print(f"streamed_runs_seconds={streamed_time:.6f}")
    print(f"materialized_peak_bytes={materialized_peak}")
    print(f"streamed_peak_bytes={streamed_peak}")
    print(f"batch_key_identity_hits={identity_hits}/10000")
    print(f"color_identity_hits={color_identity_hits}/10000")
    print(f"particle_emit_seconds={particle_emit_time:.6f}")


if __name__ == "__main__":
    main()
