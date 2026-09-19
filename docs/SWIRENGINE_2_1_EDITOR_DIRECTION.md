# SwirEngine 2.1 — SwirEditor development direction

This document records the first 2.1 editor workstream while the authoritative product-quality
status remains `docs/SWIRENGINE_2_0_POST_RELEASE_AUDIT.md`. It is intentionally not a second
progress ledger and does not change the verified post-release audit percentage.

## Product goal

SwirEngine 2.1 turns the existing toolkit-neutral editor foundations into a practical desktop
creator workflow for building and shipping real 2D, 3D and multiplayer projects.

## First vertical slice

The initial package must prove a real creator path rather than an empty shell:

- create a new 2D or 3D project from a desktop Project Hub,
- open an existing `swirproject.toml`,
- build a live `EditorWorkspace` with hierarchy, inspector, assets, diagnostics and runtime preview,
- persist the active scene to `scenes/main.swirscene`,
- persist portable workspace/layout state to `.swir/editor.json`,
- support Ctrl/Cmd+S plus safe autosave on editor close,
- keep editor state outside shipping content by default,
- expose a dedicated `swireditor` console entry point,
- reject project-state paths that escape the project root.

## Next editor milestones

1. Integrate the editor entry point into the main `swirengine` CLI after the first vertical slice is green.
2. Add project-run process controls with non-blocking Run/Stop and captured diagnostics.
3. Add creator object/component palette plus scene creation/switching UX.
4. Connect multi-selection, gizmo manipulation and prefab authoring to the desktop shell.
5. Add richer asset previews/import diagnostics and drag/drop assignment.
6. Add visual input/rebinding, settings and save/profile editors.
7. Add animation, physics, navigation and audio authoring/debug panels.
8. Add packaging/export wizard backed by verified shipping profiles.
9. Add multiplayer/dedicated-server session tooling and diagnostics.
10. Harden keyboard navigation, docking/layout persistence, crash recovery and large-project performance.

No 2.1 release is implied by this branch. The public 2.0.0 release and its post-release audit remain
the verified public baseline until a later 2.1 release gate is explicitly defined and passed.