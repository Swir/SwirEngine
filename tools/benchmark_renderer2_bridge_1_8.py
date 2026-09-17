from __future__ import annotations

from time import perf_counter
from types import SimpleNamespace

from swirengine.graphics.primitives import Rectangle2D
from swirengine.renderer2_bridge18 import Renderer2BridgeCompiler


class BenchmarkRenderer:
    mode = "2d"
    width = 1920
    height = 1080


WORLD = SimpleNamespace(
    objects=[
        Rectangle2D(float(index), float(index % 17), 8.0, 8.0, layer=index)
        for index in range(128)
    ]
)


def main() -> None:
    compiler = Renderer2BridgeCompiler()
    renderer = BenchmarkRenderer()
    frames = 500
    expected = None
    started = perf_counter()
    for _ in range(frames):
        frame = compiler.prepare(renderer, WORLD)
        if expected is None:
            expected = frame.fingerprint
        elif frame.fingerprint != expected:
            raise RuntimeError("Renderer2 bridge fingerprint changed for an identical workload")
    elapsed = perf_counter() - started
    logical_runs = frames * len(WORLD.objects)
    if elapsed >= 5.0:
        raise RuntimeError(
            f"Renderer2 bridge workload exceeded 5.0s budget: {elapsed:.4f}s"
        )
    print(
        "renderer2-bridge-1.8:",
        f"frames={frames}",
        f"logical_runs={logical_runs}",
        f"elapsed={elapsed:.4f}s",
    )


if __name__ == "__main__":
    main()
