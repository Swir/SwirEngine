from __future__ import annotations

import threading

from swirengine.shader_cache17 import ShaderMaterialPreparationCache

VERTEX = """#version 330
void main() {
    gl_Position = vec4(0.0, 0.0, 0.0, 1.0);
}
"""
FRAGMENT = """#version 330
out vec4 color;
void main() {
    color = vec4(0.10, 0.45, 1.00, 1.0);
}
"""


def main() -> None:
    owner_thread = threading.get_ident()
    worker_threads: list[int] = []

    def preprocess(source, context):
        worker_threads.append(threading.get_ident())
        context.raise_if_cancelled()
        quality = source.defines().get("QUALITY", 1)
        return {
            name: f"#define QUALITY_LEVEL {quality}\n{text}"
            for name, text in source.stage_mapping().items()
        }

    def finalize(prepared):
        if threading.get_ident() != owner_thread:
            raise RuntimeError("GPU finalization escaped the owner thread")
        return {
            "program": prepared.source_fingerprint[:12],
            "stages": tuple(prepared.stage_mapping()),
            "material": dict(prepared.material()),
        }

    cache = ShaderMaterialPreparationCache(max_workers=2, max_cache_entries=32)
    try:
        request = cache.submit(
            {"vertex": VERTEX, "fragment": FRAGMENT},
            defines={"QUALITY": 2},
            material={"name": "neon-blue", "roughness": 0.35},
            preprocess=preprocess,
            finalize=finalize,
        )
        cache.wait_workers(timeout=2.0)
        result = cache.poll()[0]
        if not result.successful:
            raise RuntimeError(result.error_message or "shader preparation failed")

        repeated = cache.submit(
            {"fragment": FRAGMENT, "vertex": VERTEX},
            defines={"QUALITY": 2},
            material={"roughness": 0.35, "name": "neon-blue"},
            preprocess=preprocess,
            finalize=finalize,
        )
        cache.wait_workers(timeout=2.0)
        cached_result = cache.poll()[0]
        if not cached_result.successful or not cached_result.cache_hit:
            raise RuntimeError("deterministic preparation cache was not reused")

        print(
            "shader_cache",
            {
                "fingerprint": request.fingerprint[:12],
                "compiled": result.value,
                "cache_hit": cached_result.cache_hit,
                "worker_thread_isolated": all(
                    worker_thread != owner_thread for worker_thread in worker_threads
                ),
                "diagnostics": dict(cache.diagnostics().portable()),
            },
        )
    finally:
        cache.shutdown()


if __name__ == "__main__":
    main()
