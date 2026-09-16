# Editor Productivity 2.0 — SwirEngine 1.5

Editor Productivity 2.0 is an additive creator-authoring layer in
`swirengine.editor15`. It does not replace or change the released 1.x editor,
prefab, serializer, asset, or runtime APIs.

## Goals

The 1.5 layer focuses on four workflows that are expensive or risky when done
manually:

- prefab instance diff/apply/revert without mutating the stable source `Prefab`;
- materialized prefab variants with preserved internal object references;
- previewable atomic batch edits with stale-plan protection;
- creator diagnostics for project asset references and a bounded shared command
  history.

The module is headless. Desktop/editor front-ends can render the immutable
result objects without depending on a GUI toolkit.

## Prefab documents

```python
from swirengine.editor15 import EditorPrefabDocument
from swirengine.prefab import Prefab
from swirengine.graphics.primitives import Rectangle2D

source = Prefab(Rectangle2D(0, 0, 32, 32, name="enemy"), name="enemy")
document = EditorPrefabDocument(source)

instance = document.instantiate()
instance.root.x = 128

diff = document.diff(instance)
assert diff.changed_fields == 1

document.apply(instance, properties=["x"])
updated = document.build()
```

`EditorPrefabDocument` owns a defensive copy of the source templates.
`apply()` updates only that document. The original stable `Prefab` remains
unchanged until the creator explicitly persists `document.build()`.

`revert()` copies selected authored values back to a live instance. Both apply
and revert preserve references between objects that belong to the same prefab
graph. Selectors can use a strict integer index or a unique object `name`.
Ambiguous names, booleans, invalid indexes, and private property names are
rejected before mutation.

### Materialized variants

`create_variant(name, instance)` captures the current instance as an independent
stable `Prefab`. The returned `EditorPrefabVariant` also carries the base name
and diff metadata for editor UI. The runtime variant is intentionally
materialized rather than linked to the editor document, so deleting or changing
the authoring document cannot silently change an already exported runtime
prefab.

## Shared command history

`EditorCommandHistory` is a bounded additive history used by the 1.5 creator
tools. It exposes immutable history frames suitable for menus/timelines and
keeps undo/redo callbacks internal.

```python
from swirengine.editor15 import EditorCommandHistory

history = EditorCommandHistory(capacity=128)
document = EditorPrefabDocument(source, history=history)
```

A new command after undo clears the redo branch. Failed undo/redo callbacks do
not move the history cursor. The stable 1.4 editor history remains untouched.

## Safe batch editing

`EditorBatchEditor.preview()` validates a complete multi-object edit and returns
an immutable plan before anything changes.

```python
from swirengine.editor15 import EditorBatchEditor

batch = EditorBatchEditor(history=history)
plan = batch.preview(enemies, {"visible": False, "layer": 3}, label="Hide enemies")

# Render/confirm plan in an editor UI, then:
result = batch.commit(plan)
```

A plan is stale-safe: every source value is checked again before the first
write. If a target changed after preview, commit fails without partial mutation.
If a setter raises while commit is in progress, already-applied fields are
rolled back. Successful commits are one undoable history command.

Private fields, missing properties, callables, and read-only properties are
rejected during preview.

## Asset reference audit

`EditorAssetAuditor` scans public creator fields for project asset references
without loading textures, audio, models, fonts, or data.

```python
from swirengine.assets import AssetManager
from swirengine.editor15 import EditorAssetAuditor

audit = EditorAssetAuditor(AssetManager("assets")).scan(scene.objects)

for reference in audit.missing:
    print(reference.object_name, reference.field, reference.path)
```

The audit reports:

- existing, missing, and unsafe project-relative references;
- broken `AssetManager` aliases;
- project assets that were not referenced by the scanned objects.

Ordinary text fields without an asset-like suffix are ignored. Absolute paths,
drive-qualified paths, and `..` traversal are reported as unsafe when they look
like asset references. Aliases resolving outside the asset root are also unsafe.

## Compatibility contract

Editor Productivity 2.0 is opt-in through `swirengine.editor15`.

- no stable root import changes;
- no changes to `Prefab`, `PrefabInstance`, `EditorAuthoringSession`,
  `EditorWorkflow`, or serialized 1.x formats;
- no 1.5-only metadata is required at runtime;
- materialized variants are regular stable `Prefab` objects when exported.

## Performance gate

The dedicated benchmark exercises repeated prefab diff/apply/revert cycles and
atomic batch commits. The CI budget is deliberately generous and is not an FPS
claim: the documented 120-object / 200-authoring-iteration workload must finish
within 5.0 seconds on the repository's Ubuntu Python 3.13 validation runner.
