# SwirEngine 1.4 Play/Edit Authoring Isolation

`EditorAuthoringPlayController` is an additive coordinator between `EditorAuthoringSession` and
`EditorRuntimeSession`. It strengthens Play/Edit round-trips without changing the stable 1.3
runtime or inspector contracts.

## Guarantees

On the first Edit -> Play transition the controller captures:

- portable multi-selection state;
- the serialized edit-scene payload;
- inspector undo history;
- inspector redo history.

The runtime still uses `EditorRuntimeSession`, so gameplay executes in a cloned scene. Authoring
mutations routed through the controller are locked until Play ends. Selection-only changes made by
other UI code during Play are discarded on stop and the portable pre-Play selection is restored.

Before the runtime scene is discarded, `stop()` verifies that the edit scene and inspector history
still match their captured baselines. Unexpected direct mutations raise
`EditorAuthoringIsolationError` while leaving Play active so the editor can report the violation
instead of silently losing the diagnostic context.

`stop(force=True)` is the explicit escape hatch for intentional external edit-scene changes. It
discards the runtime scene and performs best-effort selection restoration, but it never pretends to
roll back those intentional edits.

## Example

```python
from swirengine.editor import SceneInspector
from swirengine.editor_authoring import EditorAuthoringSession
from swirengine.editor_authoring_runtime import EditorAuthoringPlayController
from swirengine.editor_runtime import EditorRuntimeSession

authoring = EditorAuthoringSession(SceneInspector(scene))
runtime = EditorRuntimeSession(scene, serializer=project_serializer)
play = EditorAuthoringPlayController(authoring, runtime)

play.play()
play.update(1 / 60)
play.pause()
play.step(1 / 60)
play.play()
play.stop()
```

Creator-facing front-ends should route property, asset, gizmo, undo, and redo actions through this
controller while Play mode is active. The underlying 1.3 classes remain independently usable for
backwards compatibility.
