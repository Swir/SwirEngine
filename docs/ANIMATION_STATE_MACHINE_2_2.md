# SwirEngine 2.2 — Animation State Machine development slice

This document describes the integrated implementation slices for roadmap milestone 5.
They are **development evidence**, not milestone acceptance and not a public 2.2 release.
The authoritative 2.2 roadmap remains at **4/10 = 40.0%** until the complete M5
acceptance gate is satisfied on an exact green head.

## Runtime and asset foundation

- A runtime skeletal animation state machine backed by the shipping `Skeleton3D`,
  `SkeletalAnimationClip3D`, `sample_skeletal_clip`, and skeletal pose blender.
- Numeric, bool and trigger parameters with prioritized transition conditions.
- Transition exit-time support and cross-fade blending between real skeletal poses.
- One-dimensional synchronized blend trees for creator-authored locomotion.
- A deterministic `.swiranimgraph` asset format with visual node coordinates.
- Project-scoped save/load, compile, and preview sessions for editor integration.
- Focused tests covering a representative walk → run → jump creator workflow.

## Creator graph controller

`AnimationMachinePanelController22` is the toolkit-neutral creator layer over the
`.swiranimgraph` session. It keeps runtime behavior and editor authoring on the same
shipping contracts rather than creating a disconnected editor-only graph.

The controller provides:

- state selection, positioning, creation, removal, renaming and initial-state editing;
- clip-state and 1D blend-tree configuration with numeric-parameter validation;
- parameter creation, default editing, safe removal and reference-preserving rename;
- transition creation/update/removal with condition validation, exit time, duration and
  priority controls;
- structural diagnostics plus runtime compile validation against a real skeleton and
  imported clip map;
- preview start/stop/restart/step, runtime parameter and trigger controls, force-state
  debugging and live transition state inspection;
- skeleton-node preview snapshots backed by the sampled `SkeletalPose`, so the future
  visual rig panel observes exactly the same pose that reaches the skinning path;
- stale-preview invalidation after graph edits while retaining bound resources for a
  deliberate restart; and
- deterministic project save through the existing `AnimationMachineEditorSession22`.

## Creator asset

A graph stores logical clip references rather than copying imported animation data.
This keeps the state machine independent from the source model and lets the editor
resolve imported clips at compile/preview time.

```json
{
  "format": "swir.animation-machine.v1",
  "initial": "Locomotion",
  "parameters": [
    {"name": "speed", "kind": "float", "default": 0.0},
    {"name": "jump", "kind": "trigger", "default": false}
  ]
}
```

State nodes preserve canvas `x/y` positions. A state can reference one skeletal clip or
a 1D blend tree. Transition conditions use the stable animation parameter contract from
`animation15.py`.

## Runtime preview example

```python
from swirengine.editor_animation_state_machine22 import AnimationMachineEditorSession22
from swirengine.editor_animation_state_machine_frontend22 import (
    AnimationMachinePanelController22,
)

session = AnimationMachineEditorSession22.open(project_root, "hero")
controller = AnimationMachinePanelController22(session)
controller.start_preview(skeleton, imported_clips)

controller.set_preview_parameter("speed", 0.75)
controller.step_preview(1 / 60)
controller.trigger_preview("jump")
frame = controller.step_preview(1 / 60)
print(frame.preview_state, frame.preview_next_state, frame.rig)
```

The preview `rig` rows come from the sampled `SkeletalPose`; no parallel editor animation
simulation is used.

## Safety and validation behavior

Creator edits invalidate the compiled preview player so stale runtime state cannot hide
an asset change. The bound skeleton/clip resources may be retained for an explicit
`restart_preview()`, which recompiles the edited graph. Parameters used by blend trees or
transition conditions cannot be removed accidentally, and state/parameter renames rewire
their graph references deterministically.

`validate_runtime(...)` combines creator-graph diagnostics with a real compile against
`Skeleton3D` and imported skeletal clips. Unknown clips, invalid condition kinds and
invalid blend-parameter types therefore fail before the asset is treated as production
ready.

## Current M5 boundary

Milestone 5 is still open. The runtime, deterministic asset, graph-editing controller,
transition editor model, parameter inspector model, runtime-backed preview/debug controls
and rig snapshot are implemented. Remaining acceptance work is the interactive SwirEditor
surface (canvas and inspectors), creator-facing clip/rig resource binding, and final
representative walk/run/jump acceptance evidence on a fully green exact head. No M6 work
starts until M5 is formally accepted.
