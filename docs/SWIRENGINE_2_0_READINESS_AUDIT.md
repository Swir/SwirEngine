# SwirEngine 2.0 Readiness Audit

This audit is the evidence hand-off from the source-only SwirEngine 1.9 production checkpoint to the
future dedicated SwirEngine 2.0 roadmap. It deliberately does **not** assign a 2.0 completion
percentage: no dedicated 2.0 roadmap or final release gate exists yet, so 2.0 readiness is **N/A**.

The audit is based on repository contracts and representative game workflows rather than feature
counting. A source subsystem is treated as useful evidence only when it is integrated into a creator
workflow, covered by deterministic tests, or exercised by the maintained 2D, 3D or multiplayer
fixtures.

## Verified 1.9 foundations

The 1.9 source line has evidence for the production path that a real game needs before release:

- project manifests, named production profiles, diagnostics and deterministic project identity;
- unified run sessions for generated and maintained 2D/3D projects;
- shipping action maps, rebinding, retained-UI focus and display/accessibility settings;
- save/profile/config lifecycle, rotating autosaves, recovery and portable user-data policy;
- explicit scene/prefab packages, boot scenes and dependency validation;
- deterministic content build graphs with preload/warmup/streaming plans;
- privacy-bounded crash reports and deterministic creator support bundles;
- reproducible desktop staging/build manifests and host-native shipping validation;
- representative 2D, 3D and multiplayer source-to-staged runtime workflows;
- locked 1.4/1.5 release contracts plus completed 1.6, 1.7 and 1.8 source checkpoints.

These foundations are not a declaration that 2.0 is release-ready. They are the measured starting
point for the 2.0 roadmap.

## Evidence-backed gaps before 2.0

### 1. Freeze the public 2.0 API and migration contract

The repository contains additive systems developed after the public 1.5.0 baseline. Before 2.0, the
project must decide which surfaces graduate to public API, document intentional renames/deprecations,
and prove representative 1.x projects can migrate without silent behavior changes. This needs a
dedicated compatibility/migration gate, not a version-number change alone.

### 2. Create the dedicated 2.0 roadmap and release-readiness source of truth

SwirEngine 1.9 measures the source checkpoint. It must not be reused as a proxy percentage for 2.0.
The 2.0 roadmap needs explicit milestones for migration, supported platform/Python policy, package
publication, real-game workflows, performance regressions, export/build validation and final public
verification.

### 3. Promote creator workflow evidence beyond command-line integration

The real-game gate proves that manifests, settings, saves, scenes, content and export compose correctly.
Before 2.0, creator/editor tooling still needs a dedicated end-to-end usability pass so common authoring,
asset-import, scene/prefab editing, diagnostics and build/export actions do not require unnecessary
manual glue. Improvements must be justified by the maintained games rather than by adding isolated UI.

### 4. Promote multiplayer from integration fixture to a shipping contract

The multiplayer fixture exercises replication, prediction/reconciliation, session, QoS and profiler
paths under deterministic adverse-network conditions. The 2.0 gate should additionally prove clean
client/server installation, dedicated-server packaging, reconnect/failure recovery and a bounded soak
that reflects the supported public deployment model.

### 5. Define the exact public platform and Python matrix

Current source gates exercise Python 3.10, 3.13 and 3.14 contracts and native Windows/Linux/macOS
shipping on matching hosts, while the public 1.5.0 support statement is intentionally narrower in
places. The 2.0 release must publish one explicit supported matrix and prove wheels/sdist, clean
installation, runtime and export/build behavior for every claimed cell. Unsupported cross-compilation
must remain an explicit non-claim.

### 6. Add reproducible comparative performance evidence

Existing workloads are regression ceilings, not marketing benchmarks. Before 2.0, retain workload
regressions and add reproducible, technically comparable measurements for creator-critical operations
where comparison is meaningful. Do not turn CI timings into FPS claims and do not claim superiority
without comparable evidence.

### 7. Perform the final architecture, resource and failure-path audit

The final 2.0 gate still needs an integrated audit of public API consistency, resource lifetime,
rendering, audio, input, physics, networking, editor workflow, crash handling, security/safety
boundaries, diagnostics and packaging. Critical/high-severity or release-blocking findings must be
closed before publication.

### 8. Complete 2.0 documentation and public-package verification

README, API/migration guidance, examples, limitations and packaging docs must describe the same verified
behavior as CI. The final workflow must build wheel and sdist, validate metadata, install from the
public PyPI artifact after publication, and run representative games through documented workflows.

## 2.0 readiness status

**2.0 readiness: N/A** until a dedicated SwirEngine 2.0 roadmap and final release gate define the
measured denominator. SwirEngine 1.9 completion is a source-checkpoint result only and must never be
presented as 2.0 completion or release readiness.

`Release/PyPI: frozen until SwirEngine 2.0`
