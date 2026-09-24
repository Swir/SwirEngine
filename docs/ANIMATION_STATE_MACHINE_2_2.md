# SwirEngine 2.2 — Animation State Machine development slice

This document describes the first integrated implementation slice for roadmap milestone 5.
It is **development evidence**, not milestone acceptance and not a public 2.2 release.
The authoritative 2.2 roadmap remains at **4/10 = 40.0%** until the complete M5
acceptance gate is satisfied on an exact green head.

## What this slice adds

- A runtime skeletal animation state machine backed by the shipping `Skeleton3D`,
  `SkeletalAnimationClip3D`, `sample_skeletal_clip`, and skeletal pose blender.
- Numeric and trigger parameters with prioritized transition conditions.
- Transition exit-time support and cross-fade blending between real skeletal poses.
- One-dimensional synchronized blend trees for creator-authored locomotion.
- A deterministic `.swiranimgraph` asset format with visual node coordinates.
- Project-scoped save/load, compile, and preview sessions for editor integration.
- Focused tests covering a representative walk → run → jump creator workflow.

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

## Runtime example

```python
from swirengine.editor_animation_state_machine22 import AnimationMachineEditorSession22

session = AnimationMachineEditorSession22.open(project_root, "hero")
player = session.preview(skeleton, imported_clips)

player.set_parameter("speed", 0.75)
player.update(1 / 60)
player.trigger("jump")
pose = player.update(1 / 60)
```

The resulting `SkeletalPose` can flow into the existing skinning/render path.

## Current M5 boundary

This slice deliberately does not claim M5 complete. Remaining milestone work includes
the interactive SwirEditor graph surface, richer creator validation/diagnostics, visual
transition editing, preview controls, skeleton/rig presentation, and the final
representative walk/run/jump acceptance workflow on a fully green exact head.
