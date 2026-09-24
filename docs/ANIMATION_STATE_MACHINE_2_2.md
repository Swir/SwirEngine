# SwirEngine 2.2 — Animation State Machine development slice

This document records the accepted implementation evidence for roadmap Milestone 5.
Milestone 5 is verified at **5/10 = 50.0%** after its exact-head and post-merge
acceptance gates completed green. This is source-development evidence only; it does not
publish SwirEngine 2.2 or change the stable 2.1.0 release.

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
- skeleton-node preview snapshots backed by the sampled `SkeletalPose`, so the visual rig
  panel observes exactly the same pose that reaches the skinning path;
- stale-preview invalidation after graph edits while retaining bound resources for a
  deliberate restart; and
- deterministic project save through the existing `AnimationMachineEditorSession22`.

## Creator asset and resource bindings

A graph stores logical clip IDs rather than copying imported animation data. SwirEditor
persists the corresponding project/import resource references in a deterministic
sidecar named `<graph>.swiranimgraph.resources.json`. Keeping loader-specific source
references outside the graph schema preserves compatibility with existing
`swir.animation-machine.v1` assets while still making rig/clip selection durable across
editor restarts.

```json
{
  "format": "swir.animation-preview-resources.v1",
  "skeleton": "imports/hero.glb#skeleton",
  "clips": {
    "walk": "imports/hero.glb#clip:Walk",
    "run": "imports/hero.glb#clip:Run",
    "jump": "imports/hero.glb#clip:Jump"
  }
}
```

The animation workspace accepts a project/import resolver callable. Resolution is strongly
typed: the rig reference must produce `Skeleton3D`, and every clip reference must produce
`SkeletalAnimationClip3D`. Wrong or missing resources fail before runtime validation.
Legacy graph assets without a resource sidecar continue to open unchanged.

`AnimationProjectResourceResolver22` is the production project resolver used by the
integrated SwirEditor session. It accepts project-relative `.gltf` / `.glb` references,
confines every resolved path to the open project, loads through the shipping
`load_gltf_skeletal(...)` path, resolves one shared skeleton or an exact named clip, and
caches one loaded skeletal asset per source fingerprint. A changed source file therefore
invalidates the cache without allowing stale imported animation objects to survive.

SwirEditor's Animation window exposes **Rig ref** and **Clip refs** fields. Clip references
use `id=resource` pairs separated by commas. Applying bindings invalidates any stale live
preview objects; saving persists the sidecar. The integrated editor installs the project
resolver for the active project, so open/validate/preview rebuild the live runtime binding
from the same stored references without a separate editor-only resource path.

State nodes preserve canvas `x/y` positions. A state can reference one skeletal clip or
a 1D blend tree. Transition conditions use the stable animation parameter contract from
`animation15.py`.

## Runtime preview example

```python
from swirengine.editor_animation_project_resources22 import AnimationProjectResourceResolver22
from swirengine.editor_animation_workspace22 import AnimationMachineWorkspace22

workspace = AnimationMachineWorkspace22(project_root)
workspace.open("hero")
workspace.resolve_preview_resources(AnimationProjectResourceResolver22(project_root))

workspace.start_preview()
workspace.controller.set_preview_parameter("speed", 0.75)
workspace.controller.step_preview(1 / 60)
workspace.controller.trigger_preview("jump")
frame = workspace.controller.step_preview(1 / 60)
print(frame.preview_state, frame.preview_next_state, frame.rig)
```

The preview `rig` rows come from the sampled `SkeletalPose`; no parallel editor animation
simulation is used.

## Safety and validation behavior

Creator edits invalidate the compiled preview player so stale runtime state cannot hide
an asset change. Changing resource references also drops live runtime objects. Switching to
a different graph clears the previous graph's runtime binding, preventing cross-asset
preview leakage.

The project resolver rejects absolute paths, project-root escapes, unsupported asset
suffixes, invalid fragments, missing clips and ambiguous clip/skeleton results before they
reach the preview runtime. The focused acceptance fixture authors a source-only project,
loads a real glTF skin plus Walk/Run/Jump clips, reopens the persisted graph/sidecar, then
runs blend-tree locomotion and a trigger transition through the shipping preview runtime.

`validate_runtime(...)` combines creator-graph diagnostics with a real compile against
`Skeleton3D` and imported skeletal clips. Persisted-but-unresolved references are reported
separately from a graph with no configured references. Unknown clips, invalid condition
kinds and invalid blend-parameter types therefore fail before the asset is treated as
production ready.

## M5 acceptance status

Milestone 5 is accepted. PRs #227–#231 delivered the runtime, deterministic graph asset,
graph-editing controller, integrated SwirEditor canvas, transition/parameter presentation,
runtime-backed preview/debug controls, sampled rig snapshot, persistent creator-facing
rig/clip references, production project resolver wiring and source-only Walk/Run/Jump
acceptance fixture. Final PR #231 exact head
`ac30cb0149099fce7c4eebc9a7cb9f7ba6ebb495` completed all 23 triggered pull-request
workflows successfully; merged `main` commit
`8fb851bd6679671d66198721f2a5a535df94c942` then completed all 12 triggered post-merge
workflows successfully. The authoritative 2.2 roadmap therefore advances to **5/10 =
50.0%**. No M6 implementation is part of this acceptance record; Particle/VFX Editor is
the next roadmap milestone.
