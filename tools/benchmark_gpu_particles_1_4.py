from __future__ import annotations

import time

from swirengine import GPUParticleEmitter3D


ITERATIONS = 50_000
DT = 1.0 / 120.0


def schedule_cost(capacity: int) -> float:
    emitter = GPUParticleEmitter3D(capacity=capacity, rate=240.0)
    start = time.perf_counter()
    for _ in range(ITERATIONS):
        emitter.update(DT)
        emitter._consume_gpu_frame()
    elapsed = time.perf_counter() - start
    assert not hasattr(emitter, "children")
    assert emitter.diagnostics.simulation_frames == ITERATIONS
    return elapsed


def main() -> None:
    small = schedule_cost(128)
    large = schedule_cost(65_536)
    ratio = large / max(small, 1e-9)
    print(
        "GPU particle CPU scheduler benchmark: "
        f"capacity=128 {small:.6f}s, capacity=65536 {large:.6f}s, ratio={ratio:.3f}x"
    )
    # The CPU scheduler must stay independent from particle capacity. Timing is used only as a
    # regression guard with deliberately generous noise tolerance; this is not an FPS claim.
    if large > small * 4.0 + 0.05:
        raise SystemExit(
            "GPU particle CPU scheduling appears to scale with particle capacity: "
            f"{ratio:.3f}x"
        )


if __name__ == "__main__":
    main()
