# SwirEngine 2.1.0 — release candidate notes

> Publication status: **NOT PUBLISHED — candidate preparation only.**
>
> These notes describe the source currently being validated for a possible SwirEngine 2.1.0 release. The public stable release remains SwirEngine 2.0.0 until a separate Phase C publication decision succeeds.

SwirEngine 2.1 focuses on **SwirEditor & Creator Workflow**. The finite 2.1 source roadmap is accepted at **10/10 milestones = 100.0%**, with publication intentionally separated from roadmap completion.

## Highlights

- Project-backed SwirEditor desktop workflow with Project Hub and unified CLI entry points.
- Multi-scene authoring, hierarchy editing, inspector/component workflows and prefab create/instantiate/apply/revert.
- Production 2D/3D viewport workflows with picking, navigation, transform gizmos, snapping and live rendering gates.
- Creator-facing asset import/reimport, dependency visibility, previews, background processing and drag/drop.
- Integrated play/pause/stop/step, isolated runtime state, diagnostics, console and profiling workflows.
- Runtime-backed gameplay tooling for input/rebinding, settings, animation, physics/collision, navigation/AI, audio, UI/HUD and save/profile systems.
- Build/export wizard with profiles, icon/metadata configuration, artifact inspection, integrity checks and truthful host/platform gating.
- Representative source-only 2D, 3D and multiplayer project gates covering authoring through run, diagnostics, export and staged runtime validation.

## Compatibility candidate

- CPython: 3.10, 3.11, 3.12, 3.13 and 3.14, 64-bit environments only where the repository matrix verifies them.
- Package range: `requires-python = ">=3.10,<3.15"`.
- Stable compatibility is preserved unless a documented 2.1 migration requires otherwise; see `docs/MIGRATING_TO_2_1.md`.

## Release gate

A 2.1.0 publication must not proceed from these notes alone. The exact candidate head must pass the dedicated release-candidate contract, wheel/sdist builds, clean-install checks, supported platform/Python matrix, representative real-game workflows, export/build validation, documentation checks and provenance/checksum preparation described in `docs/RELEASE_GATE_2_1.md`.

The candidate workflow is deliberately non-publishing: it must not create a tag, GitHub Release or PyPI upload.

## Installation before publication

Use the current public stable release:

```bash
python -m pip install swirengine==2.0.0
```

Do not advertise or depend on `swirengine==2.1.0` from PyPI until the guarded publication and post-publication verification are complete.
