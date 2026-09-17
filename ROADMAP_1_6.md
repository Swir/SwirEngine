# SwirEngine 1.6 Roadmap

SwirEngine 1.5.0 is released and locked as the stable compatibility baseline. The 1.6 line is additive: existing 1.x imports and behavior stay stable unless a genuine maintenance fix is required.

**Current verified progress: 6/10 milestones = 60.0%.**

A milestone is checked only after its implementation, focused tests, documentation, and dedicated validation gate pass on the exact commit that is merged to `main`. Repository activity, scaffolding, or an open pull request does not count as completion.

## Release policy

- Keep `v1.5.0` immutable; do not rewrite the tag or release assets.
- Keep 1.6 systems additive or opt-in when they could change existing 1.x behavior.
- SwirEngine 1.6 is a **source-development checkpoint only**. Do not create a `v1.6.0` tag, GitHub Release, or PyPI publication even after this roadmap reaches 10/10.
- When 1.6 reaches verified 10/10, run the complete 1.x compatibility/runtime/packaging gate, record the verified source checkpoint, and continue the planned source-development stages toward 2.0.
- The next public GitHub Release and next PyPI publication after 1.5.0 are reserved for **SwirEngine 2.0**.
- SwirEngine 2.0 may be published only after its own dedicated roadmap reaches verified 10/10 and the full final release gate passes on the exact candidate commit, followed by clean public-index installation verification.

## Milestones

- [x] **1. Interest-aware Replication Streaming 2.0**
  - deterministic spatial/channel interest filtering separated from creator-owned replicated state;
  - per-client entity budgets with stable priority/distance ordering;
  - explicit client ACK baselines so lost packets never silently become delta dependencies;
  - relevance exits encoded as removals and relevance entries encoded as upserts/full state;
  - bounded server/client baseline history, strict missing-baseline failure, and explicit full-state resynchronization;
  - packet bridge layered on the stable 1.x `NetworkPacket` transport;
  - focused contract tests, workload benchmark, creator documentation/demo, and Python 3.10/3.13/3.14 CI gate.

- [x] **2. Prediction & Reconciliation 2.0**
  - authoritative command acknowledgements tied to replication ticks;
  - configurable prediction windows and deterministic replay budgets;
  - correction smoothing hooks without changing simulation truth;
  - packet-loss/reordering regression coverage and creator diagnostics.

- [x] **3. Session, Lobby & Match Lifecycle**
  - explicit host/join/leave/ready/match state model;
  - deterministic roster and role ownership;
  - reconnect/resume foundations with bounded session tokens;
  - creator-facing lifecycle events and failure diagnostics.

- [x] **4. Transport QoS & Channel Policies**
  - additive reliable/unreliable policy abstraction above existing transports;
  - sequencing, duplicate suppression, packet budgets, and back-pressure contracts;
  - channel-level telemetry and deterministic scheduling priorities;
  - transport-independent tests with stable TCP compatibility retained.

- [x] **5. Dedicated Server Runtime**
  - headless server loop and configuration surface;
  - fixed-tick scheduling, graceful shutdown, and health/readiness reporting;
  - server-safe asset/runtime boundaries and deterministic startup validation;
  - Linux packaging/smoke coverage suitable for container hosting.

- [x] **6. Content Delivery & Patch Manifests**
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

- [ ] **10. 1.6 Hardening & Source Checkpoint Gate**
  - complete 1.x compatibility re-check and full supported-Python matrix;
  - runtime, packaging, wheel/sdist, clean-install, and source-showcase gates;
  - checkpoint auditor that refuses 1.6 completion unless this roadmap is 10/10;
  - after the exact 10/10 source checkpoint is fully green, mark 1.6 complete and continue development toward 2.0 without tagging, GitHub Release creation, or PyPI publication.

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

Milestone 2 is complete only when the exact candidate commit satisfies all of the following:

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

## Milestone 3 verification contract

Milestone 3 is complete only when the exact candidate commit satisfies all of the following:

1. `swirengine.session16` is additive and does not change stable 1.x root imports or the verified 1.6 replication/prediction contracts.
2. Lobby, match, and closed phases enforce host/join/leave/ready/start/end transitions atomically with stable failure codes.
3. The public roster uses immutable join order and remains deterministic independently of client identifier or mapping order.
4. Creator roles are single-owner, the host role is protected, and host transfer is explicit rather than silently electing a replacement.
5. Match start is host-only and requires every retained roster member to be connected and ready; match end returns to lobby and resets readiness.
6. Disconnect retains roster membership and roles while clearing readiness; resume accepts only a bound active token and rotates that token before further use.
7. Resume-token storage and lifecycle event history have creator-configurable hard bounds with deterministic eviction diagnostics.
8. Lifecycle events are monotonically sequenced and bounded, while rule failures expose stable `SessionOperationError.code` values and deterministic counters without leaking tokens.
9. Immutable session snapshots exclude resume secrets, round-trip through the stable `NetworkPacket` framing model, and reject inconsistent roster/role ownership data.
10. Focused tests, lint, compile, deterministic workload benchmark, creator demo, verified 1.6 replication/prediction regressions, and the locked 1.4 multiplayer contract pass on Python 3.10, 3.13, and 3.14 in the dedicated CI workflow.

## Milestone 4 verification contract

Milestone 4 is complete only when the exact candidate commit satisfies all of the following:

1. `swirengine.transport16` is additive and leaves the stable 1.x `networking` API and root imports unchanged.
2. Logical channels have validated reliable/unreliable delivery policy, deterministic priority, encoded-packet size bounds, and hard packet/byte queue bounds.
3. Accepted outbound packets receive monotonic per-channel sequences; rejected reliable/oversized enqueues do not consume a sequence number.
4. Reliable pressure rejects atomically with stable `backpressure` diagnostics and never evicts an accepted queued packet.
5. Unreliable pressure deterministically evicts oldest queued packets until the newest valid packet fits, with exact drop counters.
6. Drain work obeys hard packet/byte budgets and deterministic priority/FIFO ordering among packets that fit the remaining budget, without discarding blocked heads.
7. Reliable receive sequencing suppresses duplicate/stale traffic and refuses forward gaps without advancing the accepted baseline; unreliable sequencing accepts fresh traffic while accounting for skipped sequences.
8. Unknown channels, delivery-policy mismatches, malformed envelopes, and oversize traffic fail explicitly without silently changing accepted receive state.
9. QoS envelopes round-trip through stable `NetworkPacket` framing and flow through the existing `TCPPeer` transport unchanged; per-channel telemetry remains payload-free and deterministically ordered.
10. Focused tests, lint, compile, deterministic workload benchmark, creator demo, stable networking/TCP tests, verified 1.6 replication/prediction/session regressions, and the locked 1.4 multiplayer contract pass on Python 3.10, 3.13, and 3.14 in the dedicated CI workflow.

## Milestone 5 verification contract

Milestone 5 is complete only when the exact implementation head satisfies all of the following before the roadmap completion marker is committed:

1. `swirengine.server16` remains additive and does not change stable 1.x root imports, `Game`, or previously verified 1.6 multiplayer contracts.
2. `DedicatedServerConfig` validates fixed-tick, catch-up, shutdown and deployment settings and supports explicit environment-driven configuration without silently accepting unknown keys.
3. Server components declare deterministic dependencies; missing dependencies and cycles fail before any startup hook runs, while startup failures roll back entered components in reverse dependency order.
4. Authoritative ticks use constant `dt` and monotonic tick/simulation-time values; tick callback failure does not advance authoritative tick state.
5. Wall-clock serving bounds catch-up work through `max_catchup_ticks`, records dropped overdue scheduler slots, and never mutates deterministic tick delta to hide overload.
6. Shutdown requests are idempotent, remove readiness immediately, execute cleanup in reverse dependency order, continue after individual cleanup failures, and expose shutdown-grace overruns through diagnostics.
7. Health/readiness probes are creator-facing and fault-contained; runtime diagnostics expose stable state/counter/error payloads rather than callback or asset contents.
8. `HeadlessRuntimeBoundary` rejects undeclared client-only runtime capabilities and unsafe asset kinds, while `ServerAssetRequirement` rejects absolute/traversal paths and optional asset probes validate required server data before startup without implicit loading or remote execution.
9. Focused lifecycle/boundary/scheduling tests, strict Ruff, compile checks, deterministic 50,000-tick workload, creator demo, and the locked networking/1.4/1.6 multiplayer regression contracts pass on Python 3.10, 3.13 and 3.14 in the dedicated workflow.
10. A clean Linux wheel is built, installed into a fresh Python 3.13 virtual environment with display variables removed, imports `swirengine.server16`, reaches readiness, executes 256 authoritative ticks and shuts down cleanly; normal CI, Desktop Export, game demos, and locked 1.4/1.5 hardening workflows remain green on the verified implementation head.

## Milestone 6 verification contract

Milestone 6 is complete only when the exact implementation head satisfies all of the following before the roadmap completion marker is committed:

1. `swirengine.content16` remains additive and does not change stable 1.x root imports, asset APIs, or previously verified 1.6 multiplayer/server contracts.
2. Content manifests are canonical and deterministic, validate portable relative paths, include version/size/SHA-256 metadata, and reject malformed, duplicate, unsafe, or inconsistent entries before staging.
3. Patch planning compares trusted current/target manifests deterministically and emits bounded add/update/remove work without treating manifest metadata as executable instructions.
4. The content-addressed cache verifies bytes against the expected digest before acceptance, isolates corrupted entries, and never serves unverified payloads as trusted content.
5. Local staging supports resumable verified writes with explicit expected sizes/digests, safe temporary paths, deterministic restart behavior, and no implicit network downloader or remote execution path.
6. Promotion into the verified cache is integrity-gated and atomic from the creator contract's perspective; failed verification leaves the previously trusted cache state unchanged.
7. Patch materialization applies only verified cached objects into a bounded local destination, refuses path traversal/absolute paths/symlink escapes, and removes only manifest-authorized obsolete files.
8. Creator-facing diagnostics and portable state/fingerprints remain deterministic and payload-safe, exposing counts/status/hash metadata rather than arbitrary content bytes.
9. Focused tests, strict Ruff, compile checks, creator demo, deterministic workload benchmark, and the locked asset-pipeline/cache/streaming regression contracts pass on Python 3.10, 3.13, and 3.14 in the dedicated workflow.
10. Normal CI, Desktop Export, source game demos, and locked 1.4/1.5 hardening workflows remain green on the verified implementation head before merge to `main`.
