from __future__ import annotations

import argparse
import statistics
import time

from swirengine import Cube3D, Vec3
from swirengine.graphics.static_batch import build_static_cube_batches


def _measure_ns(callable_, *, rounds: int, frames_per_round: int) -> float:
    samples: list[float] = []
    for _ in range(rounds):
        start = time.perf_counter_ns()
        checksum = 0.0
        for _ in range(frames_per_round):
            checksum += callable_()
        elapsed = time.perf_counter_ns() - start
        if checksum == float("inf"):
            raise RuntimeError("unreachable benchmark checksum")
        samples.append(elapsed / frames_per_round)
    return statistics.median(samples)


def benchmark_static_batch(
    *, cube_count: int = 1000, rounds: int = 9, frames_per_round: int = 30
) -> tuple[float, float, int, int]:
    cubes = [Cube3D(position=Vec3(float(index % 50), 0.0, float(index // 50))) for index in range(cube_count)]
    batch = build_static_cube_batches(cubes)

    def unbatched_frame() -> float:
        # Mirrors the per-object model-matrix preparation required by the normal Cube3D path.
        return sum(float(cube.transform.matrix()[0, 0]) for cube in cubes)

    def batched_frame() -> float:
        # Baked geometry needs one model transform per combined Mesh3D at frame time.
        return sum(float(mesh.transform.matrix()[0, 0]) for mesh in batch.meshes)

    unbatched_ns = _measure_ns(unbatched_frame, rounds=rounds, frames_per_round=frames_per_round)
    batched_ns = _measure_ns(batched_frame, rounds=rounds, frames_per_round=frames_per_round)
    return (
        unbatched_ns,
        batched_ns,
        batch.metrics.draw_calls_before,
        batch.metrics.draw_calls_after,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure static 3D batching CPU frame-preparation overhead.")
    parser.add_argument("--cubes", type=int, default=1000)
    parser.add_argument("--rounds", type=int, default=9)
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--assert-win", action="store_true")
    args = parser.parse_args()

    unbatched_ns, batched_ns, draws_before, draws_after = benchmark_static_batch(
        cube_count=args.cubes,
        rounds=args.rounds,
        frames_per_round=args.frames,
    )
    speedup = unbatched_ns / max(batched_ns, 1.0)
    reduction = 1.0 - (batched_ns / max(unbatched_ns, 1.0))

    print(f"cubes={args.cubes}")
    print(f"draw_calls={draws_before}->{draws_after}")
    print(f"cpu_frame_prep_ns={unbatched_ns:.0f}->{batched_ns:.0f}")
    print(f"cpu_frame_prep_reduction={reduction:.2%}")
    print(f"cpu_frame_prep_speedup={speedup:.2f}x")

    if args.assert_win and not batched_ns < unbatched_ns:
        raise SystemExit("static batching did not reduce measured CPU frame-preparation time")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
