# Advanced Material & Shader Pipeline — SwirEngine 1.3

SwirEngine 1.3 introduces a creator-facing shader-variant layer designed to add controlled customization without turning the renderer into an unbounded compile-per-frame system.

## Goals

The pipeline is built around four contracts:

1. **Prepare once, resolve cheaply** — source expansion, define normalization and hook validation happen in `ShaderProgramCache.prepare()`. A prepared `ShaderVariantSpec` is then resolved through a bounded LRU cache.
2. **Deterministic variants** — template source, sorted defines and normalized hooks produce a deterministic `ShaderVariantKey`.
3. **Explicit customization seams** — creator GLSL can only be inserted at `ShaderHookPoint` markers declared by the engine template.
4. **Creator-visible diagnostics** — cache hits/misses, compile failures, evictions, invalidations and live program count are tracked.

## Basic use

```python
from swirengine.graphics.shader_pipeline import (
    ShaderHookPoint,
    ShaderMaterial3D,
    ShaderProgramCache,
    ShaderTemplate,
)


template = ShaderTemplate(
    "surface",
    "#version 330\n/* SWIR_HOOK:vertex_custom */\nvoid main(){gl_Position=vec4(0.0);}",
    "#version 330\nuniform float pulse;\nout vec4 fragColor;\n/* SWIR_HOOK:fragment_custom */\nvoid main(){fragColor=vec4(pulse);}",
    hook_points=(
        ShaderHookPoint("vertex_custom", "vertex"),
        ShaderHookPoint("fragment_custom", "fragment"),
    ),
)

cache = ShaderProgramCache(ctx, max_programs=64)
variant = cache.prepare(
    template,
    defines={"USE_FOG": True, "QUALITY": 2},
    hooks={"fragment_custom": "float creator_gain = 1.0;"},
)
program = cache.resolve(variant)
material = ShaderMaterial3D(variant, uniforms={"pulse": 0.5})
material.apply_uniforms(program)
```

## Safe hook policy

Hooks are intentionally not whole-shader replacements. A hook must target a marker explicitly declared by the template. Unknown hook names fail before compilation.

The default safety policy blocks directives and operations that could escape the intended material surface contract, including `#version`, `#extension`, `#include`, explicit `layout(...)`, `gl_FragDepth`, clip-distance writes, image stores, atomics, storage buffers and barrier primitives.

Defines are similarly normalized: names must be valid identifiers and values are limited to booleans, integers, finite floats or identifier-like tokens. Raw multiline define injection is rejected.

These rules are a renderer-safety boundary, not a claim that arbitrary GLSL is sandboxed from the GPU driver. Backend compilation errors are wrapped as `ShaderCompileError` and surfaced to creators.

## Bounded compilation cache

`ShaderProgramCache` uses deterministic keys and LRU eviction. Evicted or invalidated backend program objects are released when the backend exposes `release()`.

The regression contract resolves one prepared variant 1,000 times and requires exactly:

- 1 backend compile,
- 1 cache miss,
- 999 cache hits.

`tools/benchmark_shader_pipeline.py` repeats the same contract for 10,000 resolves. Its elapsed time is diagnostic only and is not converted into an FPS claim.

## Custom uniforms

`ShaderMaterial3D` stores a prepared variant plus creator uniform values. Supported values are booleans, integers, finite floats and float tuples of length 1–4. Names are validated and the reserved `gl_` prefix is rejected.

Strict mode reports a missing backend uniform instead of silently dropping it. Non-strict mode can be used when a template intentionally compiles a uniform out in some variants.

## Current milestone boundary

This foundation provides deterministic variants, safe hook expansion, compile caching, diagnostics and validated creator uniforms. Existing `Material3D` behavior is unchanged.

Before the roadmap item is marked complete, the pipeline still needs production-renderer integration and a real OpenGL validation path proving that engine-owned vertex layout/state and existing Phong/PBR material behavior remain compatible while custom variants are active.

See `examples/demo_shader_variants.py`, `tests/test_shader_pipeline.py` and `tools/benchmark_shader_pipeline.py`.
