# Render Graph 3.0 — SwirEngine 1.8

SwirEngine 1.8 starts a source-only rendering scalability line with an additive,
renderer-independent render-graph planner in `swirengine.render_graph18`. The stable 1.x
`Renderer`/`Renderer2` APIs are not replaced or changed by this milestone.

## Why this layer exists

Large renderers need a deterministic description of pass ordering and resource lifetimes before
backend-specific OpenGL/GPU work is submitted. The 1.8 planner provides that contract without
owning GPU objects or callbacks. Later 1.8 milestones can consume the plan from existing rendering
backends while keeping the stable public renderer surface intact.

## Core contract

`RenderGraphBuilder` supports:

- bounded named pass and resource registries;
- external resources for inputs/swapchain-style attachments;
- transient resources with declared byte sizes for planning diagnostics;
- implicit producer-to-consumer dependencies plus explicit dependencies;
- deterministic priority/declaration-order topological scheduling;
- marked outputs and side-effect roots with backwards pass culling;
- strict cycle, missing dependency, multi-writer, uninitialized-resource and in-place access
  validation;
- transient lifetime analysis and deterministic non-overlapping alias-slot assignment;
- transient unaliased/reserved/peak-live byte diagnostics;
- canonical SHA-256 plan fingerprints and portable snapshots.

The graph intentionally enforces a single writer per resource in this first milestone. A pass also
cannot read and write the same logical resource. Creators should model distinct versions such as
`hdr-before-bloom` and `hdr-after-bloom`; this keeps dependency construction unambiguous and makes
future backend resource barriers explicit.

## Culling behavior

When at least one output or side-effect pass is declared, compilation retains only the passes
needed to produce those roots. If no roots are declared, every authored pass is retained. This
makes early authoring convenient while still allowing production graphs to eliminate unrelated
work deterministically.

## Transient aliasing

Transient resources are assigned to the lowest available alias slot once the previous resource in
that slot is no longer live. Resources used by the same pass never alias. Slot reservation size is
the maximum declared size of all resources assigned to the slot.

The planner does **not** allocate GPU memory. The byte counts are deterministic planning metadata
for later backend/pool integration and diagnostics.

## Example

```python
from swirengine.render_graph18 import RenderGraphBuilder

graph = RenderGraphBuilder()
graph.add_resource("camera", external=True)
graph.add_resource("hdr", transient=True, size_bytes=16 * 1024 * 1024)
graph.add_resource("swapchain", external=True)
graph.add_pass("lighting", reads=("camera",), writes=("hdr",))
graph.add_pass("present", reads=("hdr",), writes=("swapchain",), side_effect=True)

plan = graph.compile()
print(plan.passes)
print(plan.diagnostics.transient_peak_live_bytes)
print(plan.fingerprint)
```

Run `examples/demo_render_graph_1_8.py` for a complete headless creator example.

## Performance contract

The focused workload compiles a deterministic 1,200-pass linear graph and validates transient
aliasing under a deliberately generous 5.0-second CI ceiling. This is a regression budget for the
planner; it is not an FPS claim and does not measure GPU execution.

## Compatibility and release policy

This module is additive and opt-in. Stable 1.x root imports and renderer behavior remain unchanged.
SwirEngine 1.8 is a source-only development checkpoint on the path to SwirEngine 2.0. It must not
create a release tag, GitHub Release, or PyPI publication.
