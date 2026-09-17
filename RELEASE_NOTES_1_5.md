# SwirEngine 1.5.0 Release Notes

SwirEngine 1.5.0 — **Production Runtime & Creator Scale** — extends the stable 1.x engine with deterministic simulation/replay, resilient save/profile storage, richer audio/animation/navigation/world-streaming/UI/editor systems, and a reproducible runtime diagnostics layer. The 1.5 systems are additive or opt-in so existing stable 1.x projects can continue using their established APIs.

## Highlights

### Deterministic Simulation & Replay

- Opt-in fixed-step simulation clock and deterministic replay recording/playback.
- Canonical portable replay data, state fingerprints, checkpoints and seeking.
- Focused cross-version validation and a deterministic long-run workload contract.

### Save & Profile 2.0

- Versioned integrity-checked save envelopes with atomic primary/backup writes.
- Ordered project migrations, profile isolation and legacy 1.x import without rewriting old saves.
- Bounded autosaves, inspection metadata and corruption-safe recovery.

### Audio 2.0

- Bounded priority-aware SFX voice budgets with deterministic stealing and protected voices.
- Mixer snapshots with deterministic interpolation and stable spatial composition.
- Headless diagnostics and portable state fingerprints.

### Animation Graphs 2.0

- Reusable clips, typed graph parameters, transition priorities and wildcard sources.
- Deterministic cross-fades, generic portable poses and headless state fingerprints.
- Additive runtime surface that leaves stable 1.x animation APIs unchanged.

### Navigation 2.0

- Deterministic waypoint graph queries with filters, area costs and endpoint snapping.
- Creator-facing agents, path following, arrival semantics and bounded local avoidance.
- Spatial-bucket crowd stepping and portable diagnostics.

### World Streaming 2.0

- Finite partition registry with deterministic dependency validation and stable fingerprints.
- Budgeted activation/deactivation, retention hysteresis, lifecycle rollback and isolated retry.
- Creator-first `WorldStream` facade plus Game-aware cleanup for managed resources.

### UI Toolkit 2.0

- Retained widget trees with responsive vertical/horizontal layout and resolution-independent scaling.
- Shared keyboard/mouse/gamepad focus model and deterministic spatial navigation.
- Centralized themes, portable UI snapshots and runtime diagnostics.

### Editor Productivity 2.0

- Non-destructive prefab authoring, selective apply/revert and materialized variants.
- Bounded shared command history and transactional multi-object batch editing.
- Asset-reference diagnostics and preserved 1.4 Edit/Play isolation.

### Runtime Diagnostics & Profiling 2.0

- Bounded frame/update/physics/render timing history plus arbitrary timing domains.
- Generic subsystem counters, explicit resource accounting and opt-in Python allocation snapshots.
- Fault-contained diagnostics providers and deterministic versioned capture/export with SHA-256 fingerprints.

## Integrated hardening

The 1.5 release gate validates the complete repository and both source-only game showcases rather than creating separate releases for those examples. The final candidate must pass:

- full pytest, Ruff and compile validation;
- Python 3.10-3.13 cross-platform CI plus the dedicated Windows CPython 3.14 native-wheel path;
- all nine 1.5 deterministic/workload-specific benchmark contracts;
- headless and real Linux OpenGL 3.3 execution of the SwirEngine 2D Game Demo and SwirEngine 3D Game Demo;
- clean wheel installation outside the editable source tree;
- Windows one-file packaging/runtime probes;
- the locked 1.3 and 1.4 compatibility/release contracts;
- strict `tools/verify_1_5_release_candidate.py --require-complete` validation;
- tag-only Trusted Publishing to PyPI;
- public-index clean-install verification after publication.

## Compatibility

SwirEngine 1.5.0 preserves established stable 1.x root imports and keeps the new 1.5 systems additive or opt-in. Projects using stable 1.4 APIs do not need to migrate simply to install 1.5.0.

Python support remains `>=3.10,<3.15`. The normal cross-platform matrix covers Python 3.10-3.13; Windows x86-64 additionally uses the dedicated validated CPython 3.14 native-wheel path.

## Install / upgrade

```bash
python -m pip install -U swirengine==1.5.0
```

Optional audio support:

```bash
python -m pip install -U "swirengine[audio]==1.5.0"
```

## Documentation

See `ROADMAP_1_5.md` for the milestone contracts and `docs/RELEASE_HARDENING_1_5.md` for the final publication gate.
