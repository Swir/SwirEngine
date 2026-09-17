from __future__ import annotations

from swirengine.render_submission18 import (
    MaterialKey,
    MaterialSubmissionQueue,
    PipelineStateCache,
    PipelineStateKey,
)


def main() -> None:
    opaque = PipelineStateKey("lit")
    alpha = PipelineStateKey("lit", blend_mode="alpha", depth_mode="less-read")
    metal = MaterialKey("metal", ("metal-albedo", "metal-normal"))
    plastic = MaterialKey("plastic", ("plastic-albedo",))
    glass = MaterialKey("glass", ("glass-albedo",))

    queue = MaterialSubmissionQueue()
    queue.submit("crate-b", opaque, plastic, "crate", layer=0)
    queue.submit("pipe-a", opaque, metal, "pipe", layer=0)
    queue.submit("crate-a", opaque, plastic, "crate", layer=0)
    queue.submit(
        "glass-window",
        alpha,
        glass,
        "window",
        layer=1,
        sort_depth=120,
        preserve_order=True,
    )
    queue.submit("pipe-b", opaque, metal, "pipe", layer=2)
    queue.submit("crate-c", opaque, plastic, "crate", layer=2)

    plan = queue.compile()
    created: list[str] = []
    cache = PipelineStateCache(
        create=lambda key: created.append(key.fingerprint) or f"pipeline:{key.shader}:{key.blend_mode}",
        destroy=lambda _: None,
        max_entries=8,
    )
    prepared = cache.prepare(plan)

    assert [draw.draw_id for draw, _ in prepared][3] == "glass-window"
    assert len(created) == 2

    diagnostics = plan.diagnostics
    cache_diagnostics = cache.diagnostics()
    print("compiled order:", [draw.draw_id for draw in plan.draws])
    print(
        "pipeline switches:",
        f"authored={diagnostics.authored_pipeline_switches}",
        f"compiled={diagnostics.compiled_pipeline_switches}",
        f"saved={diagnostics.pipeline_switches_saved}",
    )
    print(
        "pipeline cache:",
        f"creates={cache_diagnostics.creates}",
        f"hits={cache_diagnostics.hits}",
        f"resident={cache_diagnostics.resident_entries}",
    )
    print("plan fingerprint:", plan.fingerprint)


if __name__ == "__main__":
    main()
