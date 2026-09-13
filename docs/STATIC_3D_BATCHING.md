# Static 3D cube batching

SwirEngine 1.1 includes a larger-batch path for static cube-heavy scenery. `build_static_cube_batches(...)` bakes visible `Cube3D` transforms into combined `Mesh3D` geometry and groups compatible cubes by color. Because the normal renderer already submits each `Mesh3D` in one draw, a group of 100 same-color cubes becomes one draw call instead of 100.

```python
from swirengine import Cube3D, Vec3
from swirengine.graphics.static_batch import build_static_cube_batches

walls = [Cube3D(position=Vec3(x * 2.0, 0.0, -12.0)) for x in range(100)]
result = build_static_cube_batches(walls)

for mesh in result.meshes:
    game.add(mesh)

print(result.metrics.draw_calls_before)   # 100
print(result.metrics.draw_calls_after)    # 1
print(result.metrics.draw_call_reduction) # 0.99
```

## Intended use

Use this path for geometry that does not move every frame: walls, floor blocks, buildings, repeated props and level dressing. Positions, rotations and scale are baked into the combined mesh, including inverse-transpose normal transformation, so rebuild the batch after changing a source cube transform or color.

The batch builder ignores disabled and hidden cubes. Different colors become separate batches because the current 1.x renderer uses one material/color state per mesh draw. This keeps visual output compatible while still giving large reductions for repeated scenery.

## Performance model

The result reports deterministic metrics: source object count, output batch count, draw calls before/after and reduction ratio. For 1,000 visible cubes sharing one color, the renderer-facing draw count changes from 1,000 object draws to one combined mesh draw. The trade-off is a one-time CPU geometry build and higher combined vertex-buffer size, which is appropriate for static scenery rather than continuously animated objects.

A future fully dynamic GPU-instancing path can reuse the same creator-level grouping concepts without breaking the stable 1.x API.
