# SwirEngine 1.3 Creator / Editor Integration

Milestone 9/10 extends the **existing** SwirEngine editor architecture. It does not start a new editor project and it does not replace the stable workspace, hierarchy, inspector, viewport, diagnostics or playtest APIs.

## Architecture

`EditorSystemRegistry` is a toolkit-neutral diagnostics registry for engine subsystems. `CreatorEditorIntegration` composes that registry with the existing `EditorFrontendController` and returns one combined immutable frame:

- existing editor frontend frame: hierarchy, inspector, viewport state, assets, console, profiler and preview/playtest state
- 1.3 systems frame: deterministic subsystem diagnostics grouped by category

This keeps editor presentation separate from engine/runtime systems and lets the current desktop frontend or another future frontend render the same model.

## Registering a subsystem

Most 1.3 systems already expose a `diagnostics` object. Register the runtime object directly:

```python
from swirengine.editor_systems import EditorSystemRegistry

systems = EditorSystemRegistry()
systems.register(
    "large-world",
    large_world_streamer,
    title="Large World",
    category="world",
)
systems.register(
    "gameplay",
    gameplay_runtime.scheduler,
    title="Gameplay Runtime",
    category="gameplay",
)
```

The registry reads `.diagnostics` lazily. A mapping or plain public-attribute object can also be registered directly. An explicit `provider=` callback is available when a subsystem needs a derived snapshot.

## 1.3 system mapping

The same registry contract can expose the creator-facing diagnostics from the active 1.3 systems:

- GPU instancing / frustum culling: instance candidates, culled/submitted instances and batches
- skeletal animation: skinned meshes, animated vertices and submitted joints
- collision / physics: broad-phase candidates, query/step diagnostics supplied by the gameplay world
- navigation: cache hits/misses, search expansion and agent/path diagnostics
- large world: candidate/provider queries, tracked/ready/active/waiting/failed chunks
- shader/material pipeline: compile/cache hits, misses, failures, evictions and invalidations
- 2D renderer: render roots, culling, tilemap candidates and visible cells
- gameplay framework: timers, signals, pools and creator-composed runtime diagnostics

Milestone 9 deliberately uses one generic diagnostics seam instead of adding eight editor-specific copies of runtime state.

## Filtering and performance contract

Registration performs no background polling. Providers are invoked only when an editor systems frame is requested. Category and text metadata filters run **before** provider calls.

The regression/benchmark contract registers **10,000 systems** in groups of 100, requests one category and requires exactly **100 provider calls**, not 10,000. Host elapsed time is printed only as diagnostic data; it is not converted into an FPS claim.

That means adding the registry does not add work to ordinary game frames when the creator/editor snapshot is not requested.

## Existing editor behavior stays authoritative

`CreatorEditorIntegration` wraps `EditorFrontendController` rather than subclassing or replacing it. Existing behavior remains on its established path:

- `EditorWorkspace` owns scene/project state, selection, panel state, viewport preferences and undo/redo
- `SceneInspector` remains the property editing authority
- `EditorPreviewSession` remains the reversible edit/play/pause/step path
- `EditorConsole` and `EditorProfiler` remain the existing diagnostic panels
- assets, gizmos, hierarchy filtering and project persistence are unchanged

The new systems frame is additive and can be rendered beside those existing panels.

## Example

Run:

```bash
python examples/demo_creator_editor_integration.py
```

The example attaches gameplay, 2D-renderer and large-world diagnostic snapshots to the current editor frontend and demonstrates category filtering.

## Boundaries

This milestone does **not** claim a new Qt/ImGui/web editor, a rewritten inspector, visual shader graph, terrain editor, navmesh painting UI or a 2.0 editor architecture. It exposes the 1.3 systems through the editor model that SwirEngine already ships, while preserving the stable 1.x creator workflow.
