# SwirEngine 1.4 Specialized Inspector Adapters

This document covers the additive material, physics, and navigation authoring adapters introduced
for the SwirEngine 1.4 editor milestone. The stable 1.x `SceneInspector` contract remains the source
of truth for mutations and undo/redo.

## API

```python
from swirengine.editor import SceneInspector
from swirengine.editor_authoring import EditorAuthoringSession
from swirengine.editor_specialized import EditorSpecializedInspectors

authoring = EditorAuthoringSession(SceneInspector(scene))
specialized = EditorSpecializedInspectors(authoring)

authoring.select(target)
snapshot = specialized.inspect("material")
result = specialized.set_property("material", "roughness", 0.45)
authoring.undo()
```

`EditorSpecializedInspectors` supports three toolkit-neutral views:

- `material` — `Material3D` fields on selected objects exposing a `material` attribute.
- `physics` — safe configuration shared by `RigidBody2D` and `RigidBody3D` ECS components.
- `navigation` — safe configuration shared by `NavigationAgent2D` and `NavigationAgent3D`
  ECS components.

The adapter reports mixed values explicitly through `EditorSpecializedField.mixed`. A mixed field
uses `value=None` only as a display sentinel; an actual shared `None` value reports `mixed=False`.

## Atomic multi-selection edits

Every selected target is resolved and the requested value is validated before the first mutation.
A mixed incompatible selection therefore fails without partially editing earlier targets.

Successful multi-target edits reuse `SceneInspector` history and are registered as one
`EditorAuthoringTransaction`. Undo and redo continue to obey the authoring transaction safety rules
already used by grouped property and gizmo edits.

Material edits replace the complete selected `Material3D` value. That gives material changes the
same deterministic undo/redo semantics as ordinary inspector properties and also allows a mesh with
`material=None` to receive its first material safely.

Physics and navigation edits use `SceneInspector.set_component_property`, preserving ECS component
identity and component-aware history.

## Safety policy

The specialized views intentionally expose configuration rather than volatile runtime state.

Physics exposes:

- `body_type`
- `mass`
- `gravity_scale`
- `linear_damping`
- `restitution`
- `enabled`

Navigation exposes:

- `speed`
- `stopping_distance`
- `auto_repath`

Runtime velocity, accumulated forces, path internals, providers, targets, diagnostics, and private
state are not authoring fields. Material values receive the same range/type constraints as the
corresponding runtime material controls.

## Compatibility

This layer is additive. Existing `SceneInspector`, `EditorAuthoringSession`, single-selection,
serialization, and 1.3 editor front-ends do not need to opt in. Specialized edits still appear in
the existing inspector undo/redo history, so legacy tooling does not need a second history system.
