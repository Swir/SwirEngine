# SwirEngine 1.4 — Scene Acceleration + Occlusion

SwirEngine 1.4 adds an opt-in scene-visibility path for large 3D worlds without changing the stable 1.x renderer contract. The milestone combines conservative world bounds, a deterministic static BVH, cheap dynamic refits, Renderer2 integration, and CPU/GPU Hi-Z foundations for occlusion work.

The design rule is conservative visibility: when SwirEngine is not certain that an object can be rejected, the object stays visible. This favors a little extra rendering work over false-positive culling.

## What this milestone adds

- `VisibilityAABB3D` conservative world-space bounds.
- `SceneVisibilityIndex3D` with a deterministic median-split static BVH.
- A separate dynamic-entry layer so moving objects can refit without rebuilding the static BVH.
- Built-in conservative bounds for `Cube3D` and `Mesh3D`.
- Custom bounds through a `visibility_bounds` attribute or property.
- Cached scene-membership synchronization through `Scene.render_objects`.
- Renderer-facing `AcceleratedSceneView3D` candidate snapshots.
- `SceneAcceleratedRenderer2`, an additive Renderer2 integration.
- CPU `HiZDepthPyramid3D` for deterministic occlusion-contract tests and tooling.
- GPU `HiZPyramidPass3D` for OpenGL 3.3 maximum-depth reduction without CPU readback.
- Creator-facing diagnostics for indexed/fallback entries, BVH work, frustum rejection, occlusion rejection, and visible candidates.
- A deterministic 16,384-object validation workload whose gate is based on work counts rather than host FPS.

## Quick start

```python
from swirengine import (
    Camera3D,
    Cube3D,
    Scene,
    SceneAccelerationRuntime3D,
    Vec3,
    enable_scene_acceleration,
)

scene = Scene()
scene.add(Cube3D(position=Vec3(0.0, 0.0, -5.0)))
scene.add(Cube3D(position=Vec3(100.0, 0.0, -5.0)))

runtime = enable_scene_acceleration(scene)
frame = runtime.frame(scene, Camera3D(), width=1280, height=720)

print(frame.view.objects)
print(frame.diagnostics.query.object_test_reduction)
```

`enable_scene_acceleration(scene)` attaches a `SceneAccelerationRuntime3D` to the scene. The default stable render path is unchanged until an integration consumes that runtime.

## Static and dynamic objects

`Cube3D` and `Mesh3D` are static from the visibility system's point of view by default. Static entries are organized in the BVH and do not need per-frame bounds refreshes.

For a moving object, opt into the dynamic layer:

```python
moving = Cube3D(
    position=Vec3(0.0, 0.0, -8.0),
    visibility_dynamic=True,
)
scene.add(moving)
```

Dynamic entries refresh their bounds each visibility query. They do not force a rebuild of the static BVH.

If a static indexed object's transform changes, either mark it dynamic before using it as a mover or explicitly refit/rebuild through the lower-level visibility API. Treating a moving object as static can leave stale visibility bounds.

## Custom visibility bounds

Objects outside the built-in `Cube3D`/`Mesh3D` types can participate by exposing `visibility_bounds`:

```python
from swirengine import VisibilityAABB3D, Vec3

class WorldObject:
    enabled = True
    visible = True

    @property
    def visibility_bounds(self):
        return VisibilityAABB3D.from_center_extent(
            Vec3(10.0, 2.0, -30.0),
            Vec3(2.0, 2.0, 2.0),
        )
```

The bounds must be conservative. A conservative AABB may be larger than the exact mesh, but it must never be smaller in a way that could make visible geometry disappear.

Custom moving objects can also expose `visibility_dynamic = True`.

## Conservative fallback behavior

Objects for which SwirEngine does not know visibility bounds are preserved as fallback entries. The acceleration runtime never drops those objects simply because it cannot index them.

This is important for additive compatibility with renderer paths such as lights, decals, particles, instancing, custom renderables, and future object types. They continue through the scene view until a dedicated bounds integration exists.

## Scene membership caching

`SceneAccelerationRuntime3D` uses the cached `Scene.render_objects` tuple as the membership token. If scene membership did not change, the runtime does not rescan and rebuild the membership map every frame.

When an object is added or removed, `Scene.render_objects` changes and the visibility runtime rebuilds its membership snapshot. Static BVH rebuilds are therefore tied to meaningful static-scene changes rather than every frame.

## Renderer2 integration

`SceneAcceleratedRenderer2` is an opt-in subclass of the normal Renderer2 path. When a scene has an attached `SceneAccelerationRuntime3D`, the renderer builds an accelerated candidate view before the 3D passes consume scene geometry.

If no acceleration runtime is attached, `SceneAcceleratedRenderer2` falls back to normal Renderer2 behavior.

The integration is intentionally additive. Stable 1.x APIs and the normal `Renderer2` class remain available and unchanged.

## Frustum culling

A camera view-projection matrix is converted to `Frustum3D`. Static BVH nodes are rejected using conservative AABB/frustum tests before individual leaf entries are tested.

The query diagnostics expose:

- `source_entries`
- `static_entries`
- `dynamic_entries`
- `bvh_nodes`
- `node_tests`
- `leaf_tests`
- `frustum_rejected`
- `occlusion_tests`
- `occlusion_rejected`
- `visible_entries`
- `object_test_reduction`

`object_test_reduction` is the primary deterministic large-scene work metric. It describes how much per-object visibility work the BVH avoided compared with scanning every indexed object.

## Occlusion predicate stage

`SceneVisibilityIndex3D.query()` accepts an optional occlusion predicate after frustum pruning. The callback receives the object and its conservative bounds and returns `True` to keep the object visible.

This stage deliberately does not force a particular GPU implementation. It is the stable bridge for CPU tooling, temporal visibility data, and future GPU-driven submission paths.

## CPU Hi-Z contract

`HiZDepthPyramid3D` implements the reference conservative depth-pyramid behavior.

SwirEngine uses regular OpenGL depth semantics for this contract: near values approach `0`, far/background values approach `1`. Every coarser Hi-Z texel stores the **maximum** of its source region.

Why maximum depth? If even one source sample is a far/background hole, that far value propagates upward. The coarse level then refuses to claim that geometry behind the region is fully occluded. This intentionally favors false negatives over false-positive object removal.

Example:

```python
import numpy as np
from swirengine import HiZDepthPyramid3D

depth = np.full((128, 128), 0.25, dtype="f4")
pyramid = HiZDepthPyramid3D(depth)
result = pyramid.query_occluded((0.25, 0.25, 0.75, 0.75), 0.8)
print(result.occluded)
```

`query_occluded()` also supports a depth bias so nearly coincident surfaces are kept visible instead of flickering at the threshold.

## GPU Hi-Z pass

`HiZPyramidPass3D` builds the same maximum-depth reduction contract on OpenGL 3.3 textures.

Important properties:

- no CPU depth readback during pyramid construction;
- R32F reduction targets;
- odd texture dimensions are supported through clamped 2×2 sampling;
- the input depth texture size is validated against the requested dimensions;
- ModernGL scopes isolate framebuffer and enable-state changes;
- the previous viewport is restored after the pass;
- generated levels can be retained as a temporal occlusion resource for later GPU visibility stages.

The dedicated validation workflow runs this against a real Mesa EGL/OpenGL 3.3 context, not only mocked GPU objects.

## Performance gate

`tools/benchmark_scene_visibility_1_4.py` builds a deterministic 128×128 scene: **16,384 indexed objects**.

The milestone gate checks work, not synthetic FPS:

```bash
python tools/benchmark_scene_visibility_1_4.py \
  --side 128 \
  --queries 150 \
  --max-leaf-tests 256
```

The required contract is:

- stable leaf-test count across repeated queries;
- no more than the configured leaf-test budget;
- at least `98%` per-object visibility-test reduction for the benchmark layout;
- at least one visible object in the query volume.

Host timing is printed only as diagnostics. It is not used as a release claim or CI pass/fail threshold.

## Diagnostics example

```python
runtime = enable_scene_acceleration(scene)
frame = runtime.frame(scene, camera, width=1920, height=1080)

diag = frame.diagnostics
print("snapshot rebuilds:", diag.snapshot_rebuilds)
print("indexed:", diag.indexed_entries)
print("fallback:", diag.fallback_entries)
print("leaf tests:", diag.query.leaf_tests)
print("visible:", diag.query.visible_entries)
print("reduction:", diag.query.object_test_reduction)
```

For the renderer integration, `SceneAcceleratedRenderer2.scene_acceleration_diagnostics` exposes the last accelerated scene-frame diagnostics.

## Validation coverage

Milestone validation includes:

- visibility AABB and BVH unit tests;
- sparse-scene pruning checks;
- deterministic ordering checks;
- dynamic refit without static rebuild;
- cached scene-membership synchronization;
- conservative fallback behavior;
- Renderer2 bridge tests;
- CPU Hi-Z solid-occluder, hole-safety, bias, and validation tests;
- a real Mesa EGL/OpenGL 3.3 GPU Hi-Z smoke;
- the deterministic 16k visibility-work gate;
- an integration demo;
- strict Ruff;
- compileall;
- the repository-wide CI/export/regression matrix.

## Compatibility policy

Scene Acceleration + Occlusion is additive SwirEngine 1.4 development work. The stable package version remains `1.3.0` until the complete 1.4 release gate is finished.

Existing projects do not need to enable scene acceleration. Projects that opt in can incrementally mark moving objects dynamic and add custom bounds without changing the rest of their scene API.
