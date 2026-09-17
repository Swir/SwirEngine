# SwirEngine 1.8 Render Showcase, Soak & Failure Injection

Milestone 9 is a **source-only validation layer** for the rendering systems accumulated during
SwirEngine 1.8. It does not publish a demo release and it does not replace the stable 1.x renderer
API. Its purpose is to prove that the Render Graph, transient resource reuse, texture upload
residency and Renderer2 compatibility bridge can survive sustained creator-like workloads and
recover from bounded backend failures.

## What the showcase validates

`swirengine.render_showcase18.run_render_showcase()` repeatedly drives an opt-in
`Renderer2CompatibilityBridge`. A workload can also attach a `TransientRenderResourcePool` and a
`TextureUploadQueue`, so each frame exercises the same bounded resource and upload contracts used by
the earlier 1.8 milestones.

The runner records only bounded, portable diagnostics:

- clean/rendered frame counts and graph-backend/compat/fallback execution counts;
- allocation, upload and render failures separated by stage;
- recovery count and peak consecutive failures;
- resource create/reuse counters and upload/duplicate-suppression counters;
- a bounded deque of recent failure events;
- a deterministic workload fingerprint containing no backend resource payloads.

Persistent backend faults are not hidden. If consecutive failed frames exceed the configured budget,
the runner raises `RenderShowcaseError("failure-budget-exceeded", ...)`.

## Failure containment contract

The soak harness deliberately treats a frame as the recovery boundary:

1. transient leases acquired before an allocation failure are released in `finally`;
2. `TextureUploadQueue` keeps failed submissions queued according to its existing retry-safe
   contract, so a later frame can retry without committing a false residency digest;
3. exceptions raised by a native `render_graph18` backend are contained by the showcase runner, not
   silently converted into successful frames;
4. later frames continue only while the configured consecutive-failure budget is respected;
5. retained failure history is strictly bounded.

The production bridge itself remains unchanged: applications that do not opt into this validation
runner keep the established 1.x/1.8 behavior.

## Source showcase

Run the small deterministic 2D + 3D source showcase:

```bash
python examples/demo_render_showcase_1_8.py
```

Run the longer workload gate:

```bash
python tools/benchmark_render_showcase_1_8.py --frames 1200
```

The benchmark executes the requested frame count for both a 2D and 3D scene. The 2D workload also
churns one transient resource and repeatedly stages the same texture, proving physical-resource reuse
and duplicate upload suppression instead of continuously increasing residency.

## CI coverage

The dedicated `Render Showcase 1.8` workflow provides:

- Python 3.10, 3.13 and 3.14 source/regression coverage on Linux;
- Windows/Python 3.13 source-showcase coverage;
- the deterministic long-run workload on Python 3.13;
- an existing real Renderer2 OpenGL 3.3 smoke under Mesa software rendering on Linux;
- Ruff and `compileall` coverage for the new surfaces.

This is deliberately source-only. SwirEngine 1.8 must not create a tag, GitHub Release or PyPI
publication; the next public release remains SwirEngine 2.0.
