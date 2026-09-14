# GPU instancing and frustum culling — SwirEngine 1.3

SwirEngine 1.3 opens with a dynamic 3D rendering path that complements the existing
CPU-baked static batching system.

## Why this exists

`build_static_cube_batches(...)` is excellent for level geometry that never moves, because
it bakes many source transforms into one large mesh. Dynamic crowds, vegetation, pickups,
projectiles and repeated props need a different strategy: keep one mesh on the GPU and
submit many transforms as per-instance attributes.

`InstancedMesh3D` and `InstancedCube3D` do exactly that.

```python
from swirengine import Game, InstancedCube3D, Vec3

game = Game("Instancing", mode="3d")
rocks = InstancedCube3D()

for x in range(100):
    rocks.add_cube(position=Vec3(x - 50, 0, -20), size=0.8)

game.add(rocks)
game.run()
```

## Runtime design

Each visible batch uses:

- one shared mesh VBO,
- one grow-on-demand instance VBO,
- four `vec4` matrix columns plus RGBA as per-instance attributes,
- ModernGL's `/i` divisor so attributes advance once per instance,
- one `vao.render(..., instances=N)` submission for the visible instances.

The renderer keeps the GPU buffers and a reusable NumPy staging array alive between frames.
Packing writes transform columns directly instead of allocating a standalone 4x4 matrix for
every instance.

## Frustum culling

`Frustum3D` extracts six normalized planes from the active view-projection matrix. Every
active instance is tested with a conservative bounding sphere derived from the source mesh
and enlarged by the instance's largest absolute scale axis.

Culling can be disabled per batch with `cull=False` when a creator deliberately wants every
instance submitted.

## Diagnostics and regression contract

`InstancedMesh3D.prepare(...)` returns `InstancingDiagnostics` with source, active, visible and
culled counts plus the equivalent draw calls before and after instancing.

The deterministic regression case submits 1,000 active cubes, places 900 outside an identity
frustum, and requires exactly 100 visible / 900 culled. A separate 1,000-visible case requires
the draw-call model to reduce from 1,000 submissions to one instanced draw.

`tools/benchmark_gpu_instancing.py` measures host-dependent CPU cull+pack cost for 10,000
instances. It intentionally does not convert that timing into an FPS promise.

## Material support

The direct instanced pass supports the existing `Material3D` forward-lighting contract,
including legacy Phong constants, Cook-Torrance metallic/roughness mode, base-color,
metallic/roughness, normal, occlusion and emissive texture channels plus directional, point
and spot lights under the same deterministic light budgets.

Per-instance RGBA multiplies the batch/material color so one mesh batch can still carry
visual variation.

## Current auxiliary-pass boundary

The 1.3 opening milestone integrates instanced objects into the production direct forward
pass. Existing shadow-map overlay and additive cubemap IBL auxiliary passes still operate on
regular `Mesh3D` objects. The engine does not silently fall back to one draw per instance for
those passes. Extending auxiliary passes to native instancing remains explicit renderer work,
which keeps the performance contract honest.

## Compatibility

This is an additive 1.x API. Existing `Cube3D`, `Mesh3D`, static batching and rendering paths
remain unchanged. Static scenery can continue using baked batches; dynamic repeated geometry
can opt into instancing.
