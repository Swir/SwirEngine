from __future__ import annotations

from time import perf_counter

from swirengine.shader_cache17 import ShaderMaterialPreparationCache

VERTEX = "#version 330\nvoid main() { gl_Position = vec4(0.0); }"
FRAGMENT = "#version 330\nout vec4 color; void main() { color = vec4(1.0); }"
UNIQUE_VARIANTS = 512
TOTAL_REQUESTS = UNIQUE_VARIANTS * 2
BUDGET_SECONDS = 5.0


def stages(index: int) -> dict[str, str]:
    return {
        "vertex": VERTEX,
        "fragment": FRAGMENT + f"\n// deterministic variant {index}",
    }


def preprocess(source, context):
    context.raise_if_cancelled()
    return {
        name: text.replace("#version 330", "#version 330\n#define SWIR_PREPARED 1")
        for name, text in source.stage_mapping().items()
    }


def finalize(prepared):
    return prepared.source_fingerprint


def drain(cache: ShaderMaterialPreparationCache) -> None:
    cache.wait_workers(timeout=BUDGET_SECONDS)
    while cache.pending_request_ids():
        outcomes = cache.poll(max_items=128)
        if not outcomes:
            raise RuntimeError("worker completion was not available for pending shader requests")
        if not all(outcome.successful for outcome in outcomes):
            raise RuntimeError("shader preparation workload produced a failed outcome")


def main() -> None:
    cache = ShaderMaterialPreparationCache(
        max_workers=4,
        max_pending=1024,
        max_requests=1024,
        max_cache_entries=UNIQUE_VARIANTS,
    )
    started = perf_counter()
    try:
        for index in range(UNIQUE_VARIANTS):
            cache.submit(
                stages(index),
                preprocess=preprocess,
                finalize=finalize,
                material={"variant": index, "roughness": 0.5},
            )
        drain(cache)

        for index in range(UNIQUE_VARIANTS):
            cache.submit(
                stages(index),
                preprocess=preprocess,
                finalize=finalize,
                material={"variant": index, "roughness": 0.5},
            )
        drain(cache)
        elapsed = perf_counter() - started
        diagnostics = cache.diagnostics()
    finally:
        cache.shutdown()

    if diagnostics.completed_total != TOTAL_REQUESTS:
        raise RuntimeError("shader preparation workload did not complete every request")
    if diagnostics.cache_misses_total != UNIQUE_VARIANTS:
        raise RuntimeError("first shader preparation pass did not produce expected cache misses")
    if diagnostics.cache_hits_total != UNIQUE_VARIANTS:
        raise RuntimeError("second shader preparation pass did not produce expected cache hits")
    if diagnostics.preprocess_calls_total != UNIQUE_VARIANTS:
        raise RuntimeError("cache hits unexpectedly repeated background preprocessing")
    if diagnostics.finalize_calls_total != TOTAL_REQUESTS:
        raise RuntimeError("owning-thread finalization count does not match workload")
    if diagnostics.cache_evictions_total != 0:
        raise RuntimeError("workload cache unexpectedly evicted a prepared shader")
    if elapsed >= BUDGET_SECONDS:
        raise RuntimeError(
            f"shader preparation workload exceeded {BUDGET_SECONDS:.1f}s budget: {elapsed:.4f}s"
        )

    print(
        "shader_cache_1_7: "
        f"{TOTAL_REQUESTS} requests / {UNIQUE_VARIANTS} prepared variants / "
        f"{diagnostics.cache_hits_total} cache hits in {elapsed:.4f}s "
        f"(budget {BUDGET_SECONDS:.1f}s)"
    )


if __name__ == "__main__":
    main()
