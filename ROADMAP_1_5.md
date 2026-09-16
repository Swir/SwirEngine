# SwirEngine 1.5 Roadmap — Production Runtime & Creator Scale

SwirEngine 1.5 builds on the released and locked 1.4 line. The compatibility rule remains unchanged: existing stable 1.x projects must continue to work, and new 1.5 systems should be additive or explicitly opt-in until their contracts are hardened.

Current development progress:

```text
████████░░░░░░░░░░░░ 40.0% — 4/10
```

## Milestones

- [x] **1. Deterministic Simulation & Replay** — fixed-step clock, canonical portable replay format, state fingerprints, bounded recording, checkpoints, verified playback, seeking, docs, demo, benchmark and dedicated CI.
- [x] **2. Save & Profile 2.0** — versioned integrity-checked save envelopes, atomic backup recovery, ordered migrations, metadata/revisions, bounded autosave rotation, legacy 1.x import, health inspection and corruption-safe recovery.
- [x] **3. Audio 2.0** — bounded SFX voice budgets, creator priorities, deterministic voice stealing/protection, mixer snapshots, stable spatial audio composition, headless diagnostics and portable state fingerprints.
- [x] **4. Animation Graphs 2.0** — reusable clips/state graphs, transitions, parameters, blending contracts and headless validation.
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

## Milestone 3 contract

Audio 2.0 lives in `swirengine.audio15` and composes the released `swirengine.audio.AudioEngine` instead of changing the stable root audio API. Completion requires:

- bounded SFX voice budgets with creator priorities, deterministic lowest-priority/oldest-first stealing and protected voices;
- music remaining outside the SFX voice budget;
- portable mixer snapshots with deterministic timed interpolation and fade-safe mute/unmute behavior;
- reuse of stable 1.x spatial attenuation, panning, bus and fade semantics;
- a deterministic headless backend plus portable diagnostics and state fingerprints for CI/server/replay validation;
- focused Python 3.10/3.13/3.14 tests, strict Ruff, compile, runnable demo and a 5,000-operation workload gate;
- the repository's triggered compatibility/regression workflows remaining green on the final milestone head.

## Milestone 4 contract

Animation Graphs 2.0 lives in the additive `swirengine.animation15` layer while the stable 1.x tween, timeline and state-machine APIs remain unchanged. Completion requires:

- reusable named clips with validated property-binding tracks, strictly ordered keyframes and explicit clamp/loop sampling;
- linear and step interpolation contracts plus generic portable poses that can blend and apply nested bindings;
- typed bool/float/int/trigger graph parameters with deterministic trigger consumption;
- prioritized transitions with declaration-order tie breaking, wildcard sources, normalized exit-time gates and explicit self-transition opt-in;
- deterministic timed source/target cross-fades with both state clocks advancing during the blend;
- renderer-independent headless diagnostics plus portable pose/runtime SHA-256 fingerprints;
- focused Python 3.10/3.13/3.14 tests, strict Ruff, compile, runnable demo and a 5,000-update / 8-channel workload gate;
- the repository's triggered compatibility/regression workflows remaining green on the final milestone head.

Progress is based on milestone completion, not file count or commit count. A milestone is 10 percentage points. SwirEngine 1.5 must not be tagged or published until all 10 milestones are complete and the release gate is green.
