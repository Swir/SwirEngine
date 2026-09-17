# SwirEngine 1.6 Roadmap

SwirEngine 1.5.0 is released and locked as the stable compatibility baseline. The 1.6 line is additive: existing 1.x imports and behavior stay stable unless a genuine maintenance fix is required.

**Current verified progress: 1/10 milestones = 10.0%.**

A milestone is checked only after its implementation, focused tests, documentation, and dedicated validation gate pass on the exact commit that is merged to `main`. Repository activity, scaffolding, or an open pull request does not count as completion.

## Release policy

- Keep `v1.5.0` immutable; do not rewrite the tag or release assets.
- Keep 1.6 systems additive or opt-in when they could change existing 1.x behavior.
- Do not tag `v1.6.0`, create the GitHub Release, or publish PyPI until all 10 milestones below are verified and the complete compatibility/runtime/packaging release gate is green.
- Before release, re-run the locked 1.3, 1.4, and 1.5 compatibility contracts, the full test suite, lint/compile checks, package build/install checks, supported Python matrix, and source showcase smokes.
- After publication, verify a clean public `pip install swirengine==1.6.0` before moving to the next development line.

## Milestones

- [x] **1. Interest-aware Replication Streaming 2.0**
  - deterministic spatial/channel interest filtering separated from creator-owned replicated state;
  - per-client entity budgets with stable priority/distance ordering;
  - explicit client ACK baselines so lost packets never silently become delta dependencies;
  - relevance exits encoded as removals and relevance entries encoded as upserts/full state;
  - bounded server/client baseline history, strict missing-baseline failure, and explicit full-state resynchronization;
  - packet bridge layered on the stable 1.x `NetworkPacket` transport;
  - focused contract tests, workload benchmark, creator documentation/demo, and Python 3.10/3.13/3.14 CI gate.

- [ ] **2. Prediction & Reconciliation 2.0**
  - authoritative command acknowledgements tied to replication ticks;
  - configurable prediction windows and deterministic replay budgets;
  - correction smoothing hooks without changing simulation truth;
  - packet-loss/reordering regression coverage and creator diagnostics.

- [ ] **3. Session, Lobby & Match Lifecycle**
  - explicit host/join/leave/ready/match state model;
  - deterministic roster and role ownership;
  - reconnect/resume foundations with bounded session tokens;
  - creator-facing lifecycle events and failure diagnostics.

- [ ] **4. Transport QoS & Channel Policies**
  - additive reliable/unreliable policy abstraction above existing transports;
  - sequencing, duplicate suppression, packet budgets, and back-pressure contracts;
  - channel-level telemetry and deterministic scheduling priorities;
  - transport-independent tests with stable TCP compatibility retained.

- [ ] **5. Dedicated Server Runtime**
  - headless server loop and configuration surface;
  - fixed-tick scheduling, graceful shutdown, and health/readiness reporting;
  - server-safe asset/runtime boundaries and deterministic startup validation;
  - Linux packaging/smoke coverage suitable for container hosting.

- [ ] **6. Content Delivery & Patch Manifests**
  - deterministic content manifests with hashes and version metadata;
  - incremental patch planning and cache-safe verification;
  - resumable/local content staging foundations;
  - no implicit remote execution or unverified content loading.

- [ ] **7. Platform Services Abstraction**
  - opt-in identity, cloud-save, achievements/stats, and entitlement interfaces;
  - local/offline reference providers for tests and creator development;
  - explicit capability discovery and failure isolation;
  - no hard dependency on a single storefront or external service.

- [ ] **8. Multiplayer Diagnostics & Network Profiler**
  - per-client replication, prediction, transport, and session counters;
  - bounded timeline/event capture with deterministic exports;
  - bandwidth/entity-budget hotspot reporting;
  - creator-readable diagnostics that remain safe in headless runtimes.

- [ ] **9. Multiplayer Showcase & Soak Gate**
  - source-only multiplayer example integrating the verified 1.6 systems;
  - deterministic headless multi-client soak workload;
  - packet loss/reordering/jitter simulation with bounded budgets;
  - Windows/Linux source showcase validation without a separate demo release.

- [ ] **10. 1.6 Hardening & Release Gate**
  - complete 1.x compatibility re-check and full supported-Python matrix;
  - runtime, packaging, wheel/sdist, clean-install, and source-showcase gates;
  - release auditor that refuses publication unless this roadmap is 10/10;
  - only after the exact release candidate is fully green: tag, GitHub Release, PyPI publish, and clean public-install verification.

## Milestone 1 verification contract

Milestone 1 is complete only when the exact candidate commit satisfies all of the following:

1. `swirengine.multiplayer16` is additive and does not change stable 1.x root imports.
2. Interest queries are deterministic across insertion order and enforce radius, channel, always-relevant, priority, and entity-budget semantics.
3. First delivery is a full filtered snapshot; later deltas use only an explicitly acknowledged client baseline.
4. An unacknowledged/lost update is never selected as the next baseline.
5. Entities leaving interest produce removals; entering/changing entities produce current state.
6. Server ACKs are monotonic and reject unsent ticks.
7. Client application keeps bounded baseline history, fails loudly when a requested baseline is unavailable, and can recover through explicit full-state resynchronization without creating a stale delta dependency.
8. Packet encoding round-trips through the stable `NetworkPacket` framing model.
9. Strict metadata mode prevents silent omission of replicated entities; custom interest sources can opt out explicitly.
10. Focused tests, lint, compile, benchmark, demo, and the locked 1.4 multiplayer contract pass on Python 3.10, 3.13, and 3.14 in the dedicated CI workflow.

## Milestone 2 verification contract

Milestone 2 remains unchecked until the exact candidate commit satisfies all of the following:

1. `swirengine.prediction16` remains additive and the stable 1.4 `ClientPredictor` contract is unchanged.
2. Every authoritative correction binds a command acknowledgement to a monotonically increasing replication tick.
3. Duplicate/out-of-order authoritative ticks are ignored without rolling simulation state or acknowledgements backward.
4. Newer authoritative ticks cannot regress the acknowledged command sequence or acknowledge commands the client never predicted.
5. Prediction commands are rejected atomically when they fall behind the authoritative timeline or exceed the configured future tick window.
6. Pending command history and per-reconciliation replay work have independent hard bounds.
7. Replay-budget rejection is atomic: simulation truth, pending commands, acknowledgement and authoritative tick remain unchanged.
8. Corrected simulation truth is committed immediately while `CorrectionTransition` smoothing remains presentation-only and supports a creator blend hook.
9. Correction packets round-trip through the stable `NetworkPacket` transport and deterministic diagnostics account for prediction, replay, stale input and budget rejection.
10. Focused tests, lint, compile, deterministic workload benchmark, creator demo, and the locked 1.4 multiplayer contract pass on Python 3.10, 3.13, and 3.14 in the dedicated CI workflow.
