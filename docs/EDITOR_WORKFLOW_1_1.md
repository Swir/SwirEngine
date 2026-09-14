# Editor workflow expansion (SwirEngine 1.1)

SwirEngine 1.1 extends the existing editor foundation with a project-oriented workflow that uses the same stable runtime scene, prefab, serialization and input APIs as shipped games.

## Project layout

`EditorWorkflow(root, scene)` creates a predictable project structure:

```text
project/
├─ scenes/
├─ prefabs/
└─ settings/
   └─ input.json
```

Scene files use `*.scene.json`; prefab files use `*.prefab.json`. Names are validated so editor actions cannot escape the project directories with path traversal.

## Scene authoring

```python
from swirengine.core.scene import Scene
from swirengine.editor_workflow import EditorWorkflow

scene = Scene()
workflow = EditorWorkflow("my_game", scene)
workflow.save_scene("level_one")
workflow.load_scene("level_one")
print(workflow.list_scenes())
```

The workflow composes `SceneSerializer`; it does not create a second editor-only scene format.

## Prefab workflow

A selection of runtime scene objects can be saved as a reusable prefab and instantiated back into the current scene with normal prefab overrides:

```python
workflow.save_prefab("enemy", enemy_body, enemy_label)
instance = workflow.instantiate_prefab(
    "enemy",
    overrides={"enemy_body": {"x": 320}},
)
```

`list_prefabs()` provides deterministic project discovery for visual frontends.

## Input setup

When `InputActions` is attached to the workflow, the editor can configure bindings through the same semantic action layer used by gameplay code and save them to `settings/input.json`.

```python
from swirengine.input import InputBinding

workflow.bind_input("jump", InputBinding("key", "SPACE"))
workflow.bind_input("jump", InputBinding("gamepad_button", "A"))
workflow.save_input_profile()
```

This keeps controls-menu rebinding and editor-time input setup on one format.

## Reversible playtest iteration

`begin_playtest()` captures the serialized authoring scene plus the current input profile. Gameplay then runs against the normal live scene. `end_playtest()` restores the edit snapshot, so runtime spawns, movement and temporary control changes do not leak back into authoring state.

```python
workflow.begin_playtest()
try:
    run_preview_loop()
finally:
    workflow.end_playtest()
```

For deliberate apply-back workflows, `keep_playtest_changes()` exits play mode without restoring the snapshot.

This is a headless/editor-backend milestone rather than a replacement for the existing visual frontend. It gives the current and future UI one deterministic API for scene creation, prefab authoring, input setup and Play/Edit iteration.
