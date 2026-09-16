# SwirEngine 1.4 Editor Authoring

SwirEngine 1.4 extends the existing 1.3 editor model additively. The legacy `SceneInspector`,
`EditorWorkspace`, and `EditorFrontendController` behavior remains the compatibility baseline;
1.4-aware front-ends opt into `EditorAuthoringWorkspace` and
`EditorAuthoringFrontendController`.

## Multi-selection

`EditorAuthoringWorkspace.select(...)` keeps replace selection as the default, while `mode="add"`
and `mode="toggle"` build an ordered multi-selection. The last selected target is the primary target
and is mirrored into the legacy inspector so existing inspector rendering can continue to operate.
Range selection follows the deterministic hierarchy order.

```python
from swirengine import Scene
from swirengine.editor_authoring_workspace import EditorAuthoringWorkspace

scene = Scene()
first = scene.add(...)
second = scene.add(...)
workspace = EditorAuthoringWorkspace(scene)
workspace.select(first)
workspace.select(second, mode="add")
```

Live-selection validation builds one scene key index per authoring operation instead of repeatedly
resolving each selected object through linear scene scans. This keeps large ordered selections
responsive while preserving stale-selection pruning and legacy primary-selection synchronization.

## Grouped edits and transforms

Property edits and transform gizmo gestures preflight the complete selection before the first
mutation. A successful gesture records only the history entries that actually changed state and is
exposed as one `EditorAuthoringTransaction` for authoring-level undo/redo. This prevents a target
that already held the requested value from corrupting the grouped history boundary.

The 1.4 workspace also reuses the existing viewport snap settings for grouped translate, rotate, and
scale gestures.

## Asset drag/drop contract

`EditorAssetBrowser.drag_payload(...)` creates a small toolkit-neutral
`EditorAssetDragPayload`. The payload contains only project-relative metadata; it never loads asset
contents and never embeds an absolute host path.

A front-end can complete a drag gesture by dropping the payload on an editable inspector property:

```python
from swirengine import AssetManager
from swirengine.editor_assets import EditorAssetBrowser

browser = EditorAssetBrowser(AssetManager("assets"))
payload = browser.drag_payload("textures/hero.png")
workspace.drop_asset_on_selected_property(payload, "texture")
```

Payload creation and the authoring drop layer independently reject POSIX absolute paths, Windows
drive/root paths, UNC-style paths, and parent traversal. This keeps project state portable even when
front-end code manually constructs a drag payload instead of obtaining it from the browser.

Asset property drops are atomic across the selection. String and `None` fields receive the portable
POSIX relative path; existing `pathlib` path fields preserve their concrete path type. If any selected
target is missing the property, exposes it read-only, or has an incompatible value type, the entire
drop is rejected before mutation.

## Persistence and compatibility

Multi-selection persistence is stored by the 1.4 authoring sidecar and is layered on top of the
existing editor project/hierarchy formats. Legacy primary-selection behavior remains synchronized so
1.3 consumers do not need to understand the full 1.4 selection.

Scene switching and project restore create a fresh authoring session bound to the new legacy
inspector. This avoids carrying process-local selection keys or undo transaction boundaries across
scene instances.

## Validation

The `Editor Authoring 1.4 Validation` workflow gates the authoring modules with focused regression
coverage, legacy editor/workspace/runtime regressions, strict Ruff checks, compilation, a 500-target
grouped-edit workload benchmark, and the runnable `examples/demo_editor_authoring_1_4.py` example.
The 500-target selection/edit/undo workload has a one-second CI budget so regressions cannot silently
return the authoring path to the earlier multi-second behavior.

The roadmap percentage must not advance solely because these slices exist. Milestone #8 remains
incomplete until the remaining specialized inspector, Play/Edit hardening, API, documentation/demo,
performance, and full repository validation requirements are all satisfied and green.
