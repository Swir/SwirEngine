# SwirEngine 1.5 Roadmap — Production Runtime & Creator Scale

SwirEngine 1.5 builds on the released and locked 1.4 line. The compatibility rule remains unchanged: existing stable 1.x projects must continue to work, and new 1.5 systems should be additive or explicitly opt-in until their contracts are hardened.

Current development progress:

```text
████░░░░░░░░░░░░░░░░ 20.0% — 2/10
```

## Milestones

- [x] **1. Deterministic Simulation & Replay** — fixed-step clock, canonical portable replay format, state fingerprints, bounded recording, checkpoints, verified playback, seeking, docs, demo, benchmark and dedicated CI.
- [x] **2. Save & Profile 2.0** — versioned integrity-checked save envelopes, atomic primary/backup writes, ordered migrations, metadata/revisions, bounded autosave rotation, legacy 1.x import, health inspection and corruption-safe recovery.
- [ ] **3. Audio 2.0** — creator-facing buses, spatial attenuation, priorities, snapshots and deterministic/headless diagnostics.
- [ ] **4. Animation Graphs 2.0** — reusable clips/state graphs, transitions, parameters, blending contracts and headless validation.
- [ ] **5. Navigation 2.0** — runtime navigation queries, agents, path following, avoidance contracts and scalable diagnostics.
- [ ] **6. World Streaming 2.0** — partitioned scene streaming, lifecycle hooks, budgets and deterministic activation/deactivation rules.
- [ ] **7. UI Toolkit 2.0** — retained creator UI model, layout, focus/input navigation, theming and resolution-independent scaling.
- [ ] **8. Editor Productivity 2.0** — prefab/variant authoring, safer batch workflows, command history improvements and creator diagnostics.
- [ ] **9. Runtime Diagnostics & Profiling 2.0** — structured frame/runtime counters, capture/export surfaces and regression-friendly performance contracts.
- [ ] **10. Showcase, Hardening & 1.5 Release Gate** — integrated 2D/3D validation, complete compatibility matrix, documentation closeout, packaging and strict release/PyPI verification.

## Milestone 1 contract

The deterministic replay layer lives in `swirengine.simulation15` and does not modify stable root imports. Completion requires all of the following to remain green:

- focused replay tests on Python 3.10, 3.13 and 3.14;
- strict Ruff and compile gates;
- deterministic replay demo;
- 5,000-frame record/serialize/parse/replay workload within the documented generous CI contract;
- the repository's normal compatibility CI.

## Milestone 2 contract

Save & Profile 2.0 lives in `swirengine.storage15` and keeps the stable `SaveStore`, `SettingsStore`, `ProfileStore` and their 1.x disk layouts unchanged. Completion requires:

- versioned save envelopes with SHA-256 integrity records and monotonically increasing per-slot revisions;
- atomic primary writes plus last-known-good backup preservation;
- verified backup fallback, explicit repair and safe refusal when no trustworthy copy remains;
- ordered project migrations through the existing `MigrationRegistry`;
- additive profile storage under `profiles/<profile>/saves-v2` with legacy slot import that never rewrites the original 1.x file;
- bounded autosave retention with inspectable generation metadata;
- focused Python 3.10/3.13/3.14 tests, strict Ruff, compile, runnable demo and filesystem workload gate;
- the repository's normal regression matrix remaining green.

Progress is based on milestone completion, not file count or commit count. A milestone is 10 percentage points. SwirEngine 1.5 must not be tagged or published until all 10 milestones are complete and the release gate is green.
