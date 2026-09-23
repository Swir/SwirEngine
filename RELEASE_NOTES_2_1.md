# SwirEngine 2.1.0 Release Notes

SwirEngine 2.1.0 is the creator-workflow release built around **SwirEditor & Creator Workflow**. The finite 2.1 roadmap is complete at **10/10 milestones = 100.0%** and the publication gate revalidates the exact release source before any public upload.

## Highlights

- Project-backed SwirEditor desktop workflow with Project Hub and unified CLI entry points.
- Multi-scene authoring, hierarchy editing, typed Inspector workflows and prefab create/instantiate/apply/revert.
- Production 2D/3D viewport with picking, navigation, transform gizmos, snapping, overlays and live rendering.
- Asset import/reimport, dependency visibility, previews, background processing and native drag/drop.
- Integrated Play/Pause/Stop/Step, isolated runtime state, Console source navigation, diagnostics and Profiler.
- Runtime-backed creator tooling for input/rebinding, display/accessibility settings, animation, physics/collision, navigation/AI, audio, UI/HUD and save/profile systems.
- Build/Export Wizard with profiles, icon/metadata configuration, artifact inspection, integrity checks and host/platform validation.
- Representative 2D, 3D and multiplayer workflows exercised from authoring through staged export and runtime validation.

## Compatibility

- Python requirement: `>=3.10,<3.15`.
- Maintained verification covers the repository's supported 64-bit CPython 3.10–3.14 Windows, Linux and macOS matrix.
- Published 1.4.0, 1.5.0 and 2.0.0 releases remain immutable.
- 2.1 preserves the documented 2.0 runtime compatibility surface unless a migration note explicitly says otherwise.

## Install

```bash
python -m pip install -U "swirengine==2.1.0"
```

Optional audio support:

```bash
python -m pip install -U "swirengine[audio]==2.1.0"
```

## Verification and provenance

The guarded publication workflow rebuilds and validates exact-source wheel/sdist artifacts, the Windows CPython 3.14 vendored-native wheel, representative real-game workflows, supported clean-install combinations, release-safety checks, deterministic SHA-256 checksums and release provenance before creating the immutable `v2.1.0` release.

See:

- `ROADMAP_2_1.md`
- `docs/RELEASE_GATE_2_1.md`
- `docs/MIGRATING_TO_2_1.md`
- `README.md`
