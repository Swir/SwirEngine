from __future__ import annotations

from time import perf_counter

from swirengine.graphics.shader_pipeline import ShaderProgramCache, ShaderTemplate


class _Program:
    def release(self) -> None:
        pass


class _Context:
    def __init__(self) -> None:
        self.compiles = 0

    def program(self, *, vertex_shader: str, fragment_shader: str) -> _Program:
        assert vertex_shader
        assert fragment_shader
        self.compiles += 1
        return _Program()


def main() -> None:
    template = ShaderTemplate(
        "benchmark",
        "#version 330\nvoid main(){gl_Position=vec4(0.0);}",
        "#version 330\nout vec4 fragColor; void main(){fragColor=vec4(1.0);}",
    )
    ctx = _Context()
    cache = ShaderProgramCache(ctx, max_programs=8)
    variant = cache.prepare(template, defines={"QUALITY": 2})

    resolves = 10_000
    start = perf_counter()
    for _ in range(resolves):
        cache.resolve(variant)
    elapsed = perf_counter() - start

    assert ctx.compiles == 1
    assert cache.diagnostics.cache_misses == 1
    assert cache.diagnostics.cache_hits == resolves - 1
    assert cache.diagnostics.live_programs == 1

    print("SwirEngine shader-variant cache benchmark")
    print(f"resolves={resolves}")
    print(f"backend_compiles={ctx.compiles}")
    print(f"cache_hits={cache.diagnostics.cache_hits}")
    print(f"cache_misses={cache.diagnostics.cache_misses}")
    print(f"elapsed_seconds={elapsed:.6f}")
    print("contract=repeated prepared variants do not trigger repeated shader compilation")
    print("note=host timing is diagnostic only; this benchmark makes no FPS claim")


if __name__ == "__main__":
    main()
