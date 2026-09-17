from __future__ import annotations

from time import perf_counter

from swirengine.render_submission18 import (
    MaterialKey,
    MaterialSubmissionQueue,
    PipelineStateCache,
    PipelineStateKey,
)

FRAMES = 20
DRAWS_PER_FRAME = 4096
MAX_SECONDS = 5.0


def main() -> None:
    pipelines = tuple(PipelineStateKey(f"shader-{index}") for index in range(32))
    materials = tuple(
        MaterialKey(f"material-{index}", (f"texture-{index % 16}",))
        for index in range(96)
    )
    cache = PipelineStateCache(
        create=lambda key: ("pipeline", key.fingerprint),
        destroy=lambda _: None,
        max_entries=64,
    )

    saved_switches = 0
    ordered_draws = 0
    start = perf_counter()
    for frame in range(FRAMES):
        queue = MaterialSubmissionQueue(max_draws=DRAWS_PER_FRAME)
        for index in range(DRAWS_PER_FRAME):
            pipeline = pipelines[(index * 17 + frame) % len(pipelines)]
            material = materials[(index * 29 + frame) % len(materials)]
            queue.submit(
                f"{frame}:{index}",
                pipeline,
                material,
                f"mesh-{index % 256}",
                layer=index % 4,
                sort_depth=index % 1024,
                preserve_order=index > 0 and index % 257 == 0,
            )
        plan = queue.compile()
        cache.prepare(plan)
        saved_switches += plan.diagnostics.pipeline_switches_saved
        ordered_draws += plan.diagnostics.ordered_draws

    elapsed = perf_counter() - start
    diagnostics = cache.diagnostics()
    total_draws = FRAMES * DRAWS_PER_FRAME

    assert saved_switches > total_draws // 2
    assert diagnostics.creates == len(pipelines)
    assert diagnostics.resident_entries == len(pipelines)
    assert diagnostics.hits == total_draws - len(pipelines)
    assert elapsed < MAX_SECONDS

    print(
        "material submission workload:",
        f"draws={total_draws}",
        f"ordered_barriers={ordered_draws}",
        f"pipeline_switches_saved={saved_switches}",
        f"pipeline_cache_hits={diagnostics.hits}",
        f"pipeline_creates={diagnostics.creates}",
        f"elapsed={elapsed:.4f}s",
        f"budget={MAX_SECONDS:.1f}s",
    )


if __name__ == "__main__":
    main()
