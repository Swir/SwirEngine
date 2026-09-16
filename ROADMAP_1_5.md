# SwirEngine 1.5 Roadmap — Production Runtime & Creator Scale

SwirEngine 1.5 builds on the released and locked 1.4 line. The compatibility rule remains unchanged: existing stable 1.x projects must continue to work, and new 1.5 systems should be additive or explicitly opt-in until their contracts are hardened.

Current development progress:

```text
██████████████░░░░░░ 70.0% — 7/10
```

## Milestones

- [x] **1. Deterministic Simulation & Replay** — fixed-step clock, canonical portable replay format, state fingerprints, bounded recording, checkpoints, verified playback, seeking, docs, demo, benchmark and dedicated CI.
- [x] **2. Save & Profile 2.0** — versioned integrity-checked save envelopes, atomic backup recovery, ordered migrations, metadata/revisions, bounded autosave rotation, legacy 1.x import, health inspection and corruption-safe recovery.
- [x] **3. Audio 2.0** — bounded SFX voice budgets, creator priorities, deterministic voice stealing/protection, mixer snapshots, stable spatial audio composition, headless diagnostics and portable state fingerprints.
- [x] **4. Animation Graphs 2.0** — reusable clips/state graphs, transitions, parameters, blending contracts and headless validation.
- [x] **5. Navigation 2.0** — runtime navigation queries, agents, path following, avoidance contracts and scalable diagnostics.
- [x] **6. World Streaming 2.0** — partitioned scene streaming, lifecycle hooks, budgets and deterministic activation/deactivation rules.
- [x] **7. UI Toolkit 2.0** — retained creator UI model, layout, focus/input navigation, theming and resolution-independent scaling.
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

## Milestone 5 contract

Navigation 2.0 lives in the additive `swirengine.navigation15` layer while the stable 1.x navigation surface remains unchanged. Completion requires:

- a validated deterministic waypoint graph with node-id and world-position path queries, bounded endpoint snapping and stable graph fingerprints;
- deterministic lowest-cost routing with blocked-node/edge filters, allowed navigation areas and cached per-area traversal multipliers;
- creator-facing agents with bounded multi-waypoint following, stable arrival semantics, target assignment and deterministic local separation avoidance;
- snapshot-based crowd stepping so avoidance does not depend on agent update order, plus a spatial-bucket broad phase instead of unconditional all-pairs neighbor checks;
- portable query/runtime diagnostics and state fingerprints covering route-search work, moving/arrived agents and avoidance candidate counts;
- focused Python 3.10/3.13/3.14 tests, strict Ruff, compile and a runnable headless demo;
- a 400-node / 208-query / 128-agent workload remaining below the documented 2.0-second CI budget without making an FPS claim;
- the repository's normal CI, Desktop Export, game-demo and 1.4 compatibility/hardening regression workflows remaining green on the verified milestone head.

## Milestone 6 contract

World Streaming 2.0 lives in the additive `swirengine.world_streaming15` and `swirengine.world_streaming_easy15` layers while the stable 1.x `Scene`, `LargeWorldStreamer`, `ChunkRegistry` and asset-streaming APIs remain unchanged. Completion requires:

- a finite partition registry with deterministic dependency validation, cycle/missing-dependency rejection, strict 2D `z=0` rules and stable registry fingerprints;
- deterministic priority/distance admission with hard active-cost budgets, bounded activation/deactivation work and retention hysteresis;
- dependency-first activation, safe reverse-order deactivation, lifecycle rollback, isolated failures and explicit retry without half-mounted scene content;
- a creator-first `WorldStream` facade with decorator/direct registration, object/ECS content normalization, loading-screen warmup and registration-safe pre-start inspection;
- Game-aware cleanup through the owner's `remove(...)` path during normal unload and activation rollback so Game-managed physics/UI resources are not stranded;
- portable runtime diagnostics, deterministic state fingerprints, finite-focus validation and diagnostics that remain coherent after explicit `unload_all()`;
- O(1) cell-id/key-bucket lookup plus maintained active/failure sets and active-cost accounting so per-update work is bounded by the local streaming window and resident state rather than total authored-world size;
- focused Python 3.10/3.13/3.14 tests, strict Ruff, compile and a runnable creator demo;
- a 10,000-cell / 1,200-focus-update workload remaining below the documented 3.0-second CI budget while preserving the bounded local-window contract, without making an FPS claim;
- the repository's normal CI, Desktop Export, game-demo and 1.4 compatibility/hardening regression workflows remaining green on the verified milestone head.

## Milestone 7 contract

UI Toolkit 2.0 lives in the additive `swirengine.ui15` layer and composes the released 1.x `UILabel`, `UIPanel`, `UIButton`, `UIProgressBar` and `UIManager` controls instead of changing their public behavior. Completion requires:

- a retained widget tree with stable unique ids, explicit parentage, cycle-safe reparenting and recursive renderer-control cleanup;
- deterministic vertical/horizontal layout with padding, gaps, start/center/end/stretch alignment and start/center/end/space-between justification;
- reference-resolution scaling with configurable finite scale limits and inherited visibility/enabled state;
- one focus model shared by direct creator calls, mouse press/release activation, `Tab`/`Shift+Tab`, arrow-key spatial navigation and standardized gamepad D-pad/A navigation;
- centralized theme propagation, including a built-in high-contrast preset, without changing global stable 1.x defaults;
- portable creator-state snapshots/fingerprints plus runtime diagnostics covering layout generations, focus, pointer hits, activations, visibility and effective scale;
- focused Python 3.10/3.13/3.14 tests, strict Ruff, compile and a runnable creator demo;
- a 240-button / 320-responsive-layout workload remaining below the documented 5.0-second CI budget while making no renderer-FPS claim;
- the repository's full CI, Desktop Export, Full Game 1.3, game-demo and 1.4 compatibility/hardening regression workflows remaining green on the verified milestone head.

## Milestone 8 contract

Editor Productivity 2.0 lives in the additive `swirengine.editor15` layer and leaves the released 1.x editor, prefab, serializer and project formats unchanged. Completion requires:

- a non-destructive prefab authoring document with deterministic instance diff, selective apply/revert and strict selector/property validation;
- graph-safe prefab apply/revert so references between members stay internal to the authored template or live instance rather than leaking detached clones;
- creator variants that materialize as ordinary stable `Prefab` objects with source/diff metadata and no hidden runtime dependency on the editor document;
- a bounded shared creator command history with grouped undo/redo, redo-branch invalidation and unchanged cursor state when callbacks fail;
- previewable multi-object batch edits with full preflight, stale-plan detection before the first write and rollback of already-applied fields if a setter fails;
- asset-reference diagnostics that find missing/unsafe project paths, broken aliases and unused scanned assets without loading asset contents;
- the stable 1.4 edit/play separation and existing editor authoring/history behavior remaining unchanged and covered by regression tests;
- focused Python 3.10/3.13/3.14 tests, strict Ruff, compile and a runnable headless creator demo;
- a 120-object / 200-authoring-iteration workload remaining below the documented 5.0-second CI budget without making an FPS claim;
- the repository's normal CI, Desktop Export, game-demo, creator-editor and 1.4 compatibility/hardening regression workflows remaining green on the verified milestone head.

Progress is based on milestone completion, not file count or commit count. A milestone is 10 percentage points. SwirEngine 1.5 must not be tagged or published until all 10 milestones are complete and the release gate is green.
