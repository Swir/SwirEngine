# Advanced Material & Shader Pipeline — SwirEngine 1.3

SwirEngine 1.3 adds a creator-facing shader-variant layer for controlled material customization without turning the renderer into an unbounded compile-per-frame system. Existing `Material3D`, Phong and PBR rendering remain unchanged; custom shader materials use the additive `ShaderMesh3D` path.

## Core contracts

The pipeline is built around five rules:

1. **Prepare once, resolve cheaply** — source expansion, define normalization and hook validation happen before drawing. A prepared `ShaderVariantSpec` is resolved through a bounded LRU program cache.
2. **Deterministic variants** — template source, sorted defines and normalized hooks produce a deterministic `ShaderVariantKey`.
3. **Engine-owned production template** — `ShaderMesh3D` only accepts variants derived from `SURFACE_3D_TEMPLATE`; creator code cannot replace the production vertex layout through this API.
4. **Explicit customization seams** — creator GLSL is inserted only at declared `ShaderHookPoint` markers.
5. **Creator-visible diagnostics** — cache hits/misses, compile failures, evictions, invalidations and live program count are tracked.

## Creator path

The normal game-facing API does not require an OpenGL context while the scene is being authored:

```python
from swirengine import Color, ShaderMesh3D, Vec3, cube_mesh, shader_material_3d

material = shader_material_3d(
    hooks={
        "fragment_globals": "uniform float pulse;",
        "fragment_surface": "surface_rgba.rgb *= vec3(pulse, 1.0, 0.5);",
    },
    uniforms={"pulse": 0.75},
)

obj = ShaderMesh3D(
    cube_mesh(),
    material,
    position=Vec3(0.0, 0.0, -4.0),
    color=Color(0.25, 0.75, 1.0, 1.0),
)
```

`Game.add(obj)` places the object in the normal scene. The production `ShadowedImageBasedPostProcessRenderer` owns the `ShaderMaterialRenderPipeline` and renders `ShaderMesh3D` objects during its direct 3D pass.

## Engine-owned hook surface

`SURFACE_3D_TEMPLATE` exposes these points:

- `vertex_globals` — declarations/functions needed by a vertex variant,
- `vertex_surface` — modify `local_position` / `local_normal` before engine matrices are applied,
- `fragment_globals` — declarations/functions needed by a fragment variant,
- `fragment_surface` — modify `surface_rgba` / `surface_normal`,
- `fragment_lighting` — post-process the direct-lighting result before final output.

The template keeps `in_pos`, `in_normal`, `in_uv`, engine model/MVP transforms and direct directional-light integration under engine control. Vertex buffers are shared across variants; only the inexpensive VAO binding is cached per mesh/variant pair.

## Safe hook policy

Hooks are intentionally not whole-shader replacements. Unknown hook names fail before compilation.

The default policy blocks directives and operations that could escape the intended material surface contract, including `#version`, `#extension`, `#include`, explicit `layout(...)`, `gl_FragDepth`, clip-distance writes, image stores, atomics, storage buffers and barrier primitives.

Defines are normalized: names must be identifiers and values are limited to booleans, integers, finite floats or identifier-like tokens. Raw multiline define injection is rejected.

These rules form an engine API safety boundary; they are not a claim that arbitrary GLSL is sandboxed from the GPU driver. Backend compilation errors are surfaced as `ShaderCompileError`.

## Bounded compilation and GPU-resource cache

`ShaderProgramCache` uses deterministic keys and LRU eviction. Evicted or invalidated program objects are released. `ShaderMaterialRenderPipeline` separately shares one uploaded vertex buffer for compatible variants of the same `MeshData`, then caches VAOs by mesh/variant key.

The regression contract resolves one prepared variant 1,000 times and requires exactly:

- 1 backend compile,
- 1 cache miss,
- 999 cache hits.

The production-pipeline regression also requires two `ShaderMesh3D` objects using the same mesh and material to share one program compile, one VBO upload and one VAO binding.

`tools/benchmark_shader_pipeline.py` repeats the program-cache contract for 10,000 resolves. Its elapsed time is diagnostic only and is not converted into an FPS claim.

## Custom uniforms

`ShaderMaterial3D` supports booleans, integers, finite floats and float tuples of length 1–4. Names are validated and the reserved `gl_` prefix is rejected. Values can be changed while the game runs without recompiling the variant.

Strict mode reports a missing backend uniform. Non-strict mode can be used when a variant intentionally compiles a uniform out.

## Diagnostics

The cache reports preparation requests, compile requests, hits, misses, compile failures, evictions, invalidations and live programs. Production renderer stats also expose `shader_meshes`, while ordinary draw/triangle/mesh-upload counters continue to include the actual submitted work.

## Compatibility and current boundaries

The 1.3 shader path is additive. Existing `Mesh3D` + `Material3D`, Phong/PBR materials, static batching, instancing and skeletal rendering keep their established paths.

`ShaderMesh3D` currently participates in the production direct-forward pass with base color, normals/UVs available to hooks and one selected directional light. It does **not** silently claim support in auxiliary directional-shadow or additive cubemap-IBL passes, and this milestone does not yet provide creator texture/sampler binding for arbitrary custom samplers.

The roadmap checkbox remains open until the dedicated real-OpenGL smoke plus the full CI/runtime/demo/export matrix are green on the exact final head.

See `examples/demo_shader_variants.py`, `tests/test_shader_pipeline.py`, `tests/test_shader_mesh.py`, `tools/benchmark_shader_pipeline.py` and `tools/verify_shader_pipeline_opengl.py`.
