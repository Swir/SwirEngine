"""Deterministic 3D collision broad-phase workload for SwirEngine 1.3.

Wall-clock values are informational only. The regression contract is candidate reduction, not FPS.
"""

from __future__ import annotations

from time import perf_counter

from swirengine import BoxCollider3D, CollisionWorld3D, Cube3D, Vec3


def main() -> None:
    count = 10_000
    world = CollisionWorld3D(cell_size=4.0)
    for index in range(count):
        world.add(BoxCollider3D(Cube3D(position=Vec3(index * 8.0, 0.0, 0.0), size=1.0)))

    brute_force_pairs = count * (count - 1) // 2
    started = perf_counter()
    pairs = world.pairs()
    pair_seconds = perf_counter() - started
    pair_diagnostics = world.diagnostics

    started = perf_counter()
    ray_hits = world.raycast(Vec3(-2.0, 0.0, 0.0), Vec3(1.0, 0.0, 0.0), max_distance=20.0)
    ray_seconds = perf_counter() - started
    ray_diagnostics = world.diagnostics

    if pairs:
        raise SystemExit("sparse broad-phase workload unexpectedly produced collision pairs")
    if pair_diagnostics.candidate_count >= brute_force_pairs // 100:
        raise SystemExit("3D broad phase did not reduce pair candidates by at least 100x")
    if ray_diagnostics.candidate_count >= 10:
        raise SystemExit("finite raycast visited too many spatial candidates")
    if not ray_hits:
        raise SystemExit("finite raycast should hit the first sparse collider")

    reduction = brute_force_pairs / max(1, pair_diagnostics.candidate_count)
    print(f"colliders={count}")
    print(f"brute_force_pairs={brute_force_pairs}")
    print(f"broad_phase_candidates={pair_diagnostics.candidate_count}")
    print(f"candidate_reduction_x={reduction:.1f}")
    print(f"pair_workload_seconds={pair_seconds:.6f}")
    print(f"finite_ray_candidates={ray_diagnostics.candidate_count}")
    print(f"finite_ray_tests={ray_diagnostics.narrow_phase_tests}")
    print(f"finite_ray_workload_seconds={ray_seconds:.6f}")
    print("Timing is host-dependent diagnostic data; this benchmark makes no FPS claim.")


if __name__ == "__main__":
    main()
