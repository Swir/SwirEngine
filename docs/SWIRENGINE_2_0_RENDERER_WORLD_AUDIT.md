# SwirEngine 2.0 Renderer / Assets / World Production Audit

Status: **ACTIVE EVIDENCE — Domain 6 is not complete yet.**

This document records current post-release evidence for Domain 6 of `SWIRENGINE_2_0_POST_RELEASE_AUDIT.md`. It does not change the authoritative post-release audit percentage. The active audit remains **5/10 = 50.0%** until the Domain 6 implementation/evidence package is fully verified and its closeout gate is green.

## Scope

The Domain 6 production workload intentionally crosses subsystem boundaries instead of testing isolated feature islands. It exercises:

- bounded transient render-resource reuse, eviction, trim/close ownership and zero-residency teardown;
- shader/material preparation caching, bounded cache eviction, owner-thread finalization and terminal request reclamation;
- terrain local-window selection, distance LOD, bounded mesh caching and repeat-selection reuse;
- large-world local preload/retention windows, visibility filtering, long-distance travel, deactivation/unload pressure and final teardown.

The deterministic source workload lives in `tools/audit_renderer_world_2_0.py`. Regression coverage lives in `tests/test_post_release_renderer_world_2_0.py`.

## Verified invariants required by the harness

The harness fails instead of merely reporting success-looking counters when any production invariant is violated:

1. The transient render pool never exceeds four resident resources or 4096 configured bytes in the audit workload, and `close()` returns resource count and resident bytes to zero.
2. Every renderer resource created by the audit is destroyed exactly once by eviction or shutdown ownership.
3. Shader/material preparation never exceeds eight cached entries, leaves zero pending work after every finalized request, and every terminal request is explicitly forgotten from scheduler/request bookkeeping.
4. Terrain selection never scans more than the requested 3x3 local window, and the mesh cache never exceeds its configured twelve-entry budget while revisited positions produce cache hits.
5. Large-world travel keeps candidate work at the 3x3 preload window, bounds retained tracked chunk state, performs real unloads during long-distance travel, and `unload_all()` returns tracked state to zero.
6. A second complete workload in the same Python process must remain clean, guarding against retained process-global production state.

## Current interpretation

The audited implementations already contain meaningful production safeguards: `TransientRenderResourcePool` has explicit ownership and bounded capacity, `ShaderMaterialPreparationCache` has bounded prepared-data caching and explicit `forget()`, `HeightmapTerrain` uses bounded local selection plus an LRU mesh cache, and `LargeWorldStreamer` uses preload/active/retention windows rather than scanning or retaining an entire authored world.

This package is deliberately evidence-first. Domain 6 must remain open if CI, the deterministic workload, or follow-up stress reveals a renderer/resource/world lifetime or scalability defect. A documentation-only change cannot close the domain.

## Closeout requirements

Domain 6 may move to complete only after all of the following are true on the exact final PR head:

- the new integrated audit tests are green;
- existing render-resource, shader-cache, terrain/LOD, visibility, large-world and world-streaming tests remain green;
- the normal supported CI/platform/packaging gates remain green;
- no unresolved critical/high or release-blocking finding exists in this scope;
- the authoritative post-release audit, README presentation and deterministic SVG assets are updated only after the evidence gate is satisfied.

Historical SwirEngine 2.0 release readiness remains complete and immutable as historical evidence. This document tracks post-release hardening only.
