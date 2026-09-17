# Renderer2 Integration & Compatibility Bridge — SwirEngine 1.8

SwirEngine 1.8 adds an **opt-in**, renderer-independent compatibility layer that turns existing 2D and Renderer2 3D submission work into deterministic Render Graph 3.0 frame contracts before GPU submission.

This milestone is intentionally additive. It does **not** replace the stable 1.x `Renderer` API, does not change default rendering behavior, and does not require a backend to implement a new capability.

## What the bridge does

`Renderer2BridgeCompiler` prepares a portable `Renderer2BridgeFrame` before submission:

- 2D work is inspected using the same layer sorting and sprite-run batching contract as the stable renderer;
- Renderer2 3D work reuses the existing backend-independent `Renderer2Planner` pass schedule;
- active `InstancedMesh3D` batches and visible instances are accounted for explicitly;
- the frame is converted into a bounded `RenderGraphPlan` with deterministic pass/resource ordering;
- the currently selected `DynamicQualityController` step can be carried into the frame contract without mutating legacy renderer dimensions;
- a SHA-256 frame-contract fingerprint makes identical submission structure reproducible for tests, capture tooling and diagnostics.

The bridge never opens texture files, allocates GPU objects or performs rendering during `prepare()`. This keeps planning usable in tests, editor tooling and headless diagnostics.

## Execution paths

`Renderer2CompatibilityBridge` supports three explicit execution paths:

1. **`graph-backend`** — a backend exposes `render_graph18(...)`; the compiled frame is handed directly to that backend.
2. **`graph-compat`** — an existing renderer has no native graph hook, so the bridge validates/builds the graph contract and then calls the renderer's historical `render(...)` method exactly once.
3. **`fallback`** — graph preparation cannot be used, or a creator requires a native graph hook and it is unavailable; the historical renderer path is used explicitly when allowed.

Preparation failures are contained before backend submission. Creators can disable fallback for strict validation workflows.

## Example

```python
from swirengine.renderer2_bridge18 import Renderer2CompatibilityBridge

bridge = Renderer2CompatibilityBridge(renderer)
result = bridge.render(scene, camera=camera)

print(result.execution)
if result.frame is not None:
    print(result.frame.graph.passes)
    print(result.frame.fingerprint)
```

For dynamic quality integration:

```python
from swirengine.render_quality18 import DynamicQualityController, default_render_quality_steps
from swirengine.renderer2_bridge18 import Renderer2CompatibilityBridge

quality = DynamicQualityController(default_render_quality_steps())
bridge = Renderer2CompatibilityBridge(renderer, quality=quality)
```

The selected quality step is included in the portable frame contract. Compatibility execution deliberately keeps the legacy renderer's current framebuffer dimensions unchanged; a native graph backend may consume the quality step at its own safe frame boundary.

## Hard bounds and failure behavior

`Renderer2BridgeSettings` exposes hard limits for graph passes, graph resources and 2D render runs. A frame that exceeds a configured bound fails during preparation, before any backend call. With default fallback enabled, the bridge contains that preparation failure and invokes the historical renderer once. Strict workflows may set `fallback_on_prepare_error=False`.

`allow_compat_execution=False` can be used to require a native `render_graph18` backend. If the hook is unavailable, the result is an explicit fallback rather than a silent claim that graph execution occurred.

## Diagnostics

`bridge.diagnostics()` reports numeric/portable counters for:

- prepared frames;
- native graph-backend frames;
- graph-validated compatibility frames;
- fallback frames and preparation failures;
- the most recent graph pass/resource counts;
- 2D render-run count;
- active instanced batch/instance counts;
- last execution path.

No GPU/backend payload objects are placed in portable diagnostics.

## Compatibility contract

- Existing `swirengine.Renderer`, `swirengine.Renderer2`, `Game`, 2D primitives and 3D scene APIs remain unchanged.
- Importing the bridge does not monkey-patch or replace stable renderer classes.
- A creator must explicitly construct `Renderer2CompatibilityBridge` to use it.
- Native graph execution is capability-driven and is never claimed when the backend hook is absent.
- Unsupported/invalid planning conditions fail before submission and may use the documented compatibility fallback.

## Verification scope

The milestone gate covers:

- deterministic 2D ordering and sprite batching;
- 3D Renderer2 pass planning without a GPU context;
- instancing accounting;
- dynamic-quality frame-contract integration;
- native graph hook dispatch;
- legacy compatibility execution and explicit fallback;
- run-limit containment and deterministic fingerprints;
- stable Renderer2 and accelerated Renderer2 regressions;
- Render Graph 1.8, dynamic quality and visibility/LOD regressions;
- Python 3.10, 3.13 and 3.14;
- a deterministic 64,000 logical-run planning workload.

SwirEngine 1.8 remains a source-only development checkpoint. This milestone does not create a release, tag or PyPI publication.
