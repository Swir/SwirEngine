# Character Controllers — SwirEngine 1.4

SwirEngine 1.4 milestone #3 adds a gameplay-oriented kinematic character layer on top of the
Physics 2.0 sweep API. The stable 1.x rigid-body and collision APIs remain available unchanged.

## Goals

The controller stack is designed for creator code that needs responsive movement rather than a
dynamic rigid body that must be tuned through forces. Collision detection still comes from
`PhysicsBackend3D.sweep_box`, so characters share the same deterministic scene data and filtering
rules as Physics 2.0.

The milestone provides:

- `CharacterController3D` — reusable kinematic motor
- `FirstPersonController3D` — FPS look + movement + camera synchronization
- `ThirdPersonController3D` — orbit movement, smooth camera rig and camera collision
- `PlatformerController3D` — platformer movement with optional X/Z axis locking
- `CharacterActionBindings3D` — semantic `InputActions` adapter
- `CharacterNavigationDriver3D` — revision-aware `NavigationProvider3D` path follower
- `CharacterState3D` and `CharacterDiagnostics3D` — deterministic state and sweep diagnostics

## Movement model

`CharacterController3D` keeps gameplay motion kinematic. The target only needs a mutable
`position.x/y/z`. Each update accelerates horizontal velocity toward the requested movement vector,
applies gravity/jump velocity, then resolves the motion with Physics 2.0 box sweeps.

```python
from swirengine.character import CharacterController3D, CharacterInput3D

controller = CharacterController3D(player, physics_scene)

state = controller.update(
    CharacterInput3D(move_z=1.0, sprint=True),
    dt,
)
```

`move_z=1` means forward relative to the movement basis. Supply `forward=` and `right=` to the base
controller when movement should follow a custom camera or actor orientation. The FPS/TPS wrappers do
this automatically.

## Grounding and skin shell

The configured width/height/depth describe the gameplay character. Sweeps use a small inset shell
controlled by `skin_width`. This avoids a supported character treating the floor it already touches
as a blocking overlap when it starts a horizontal move or jumps. Safe travel restores the skin
margin before contact, so the configured character does not intentionally penetrate obstacles.

Ground state is refreshed with a downward sweep. `ground_snap_distance` keeps descending characters
attached to small surface changes without snapping a rising character back to the floor.

## Slopes

`CharacterConfig3D.slope_limit_degrees` converts to a minimum accepted upward normal. Walkable slope
hits are projected onto their contact plane; downhill motion is maintained through the ground-snap
probe. Surfaces steeper than the configured limit are treated as blockers rather than ground.

The stock Physics 2.0 AABB backend currently produces axis-aligned normals for box sweeps, while the
controller contract also accepts future backends that return arbitrary surface normals. This keeps
slope behavior ready for richer collision geometry without changing the creator-facing API.

## Steps

When horizontal motion hits a non-walkable face while grounded, the controller attempts a bounded
step sequence:

1. verify upward clearance up to `step_height`
2. test the requested horizontal travel from the raised position
3. sweep down to find a walkable landing surface
4. commit the step only when all three checks succeed

Tall obstacles therefore remain blockers and low stairs can be climbed without a jump.

## Jump quality

Two small timing aids are built into the base motor:

- `coyote_time` allows a jump briefly after leaving a ledge
- `jump_buffer_time` remembers a jump press briefly before landing

Both are deterministic timers advanced only by the supplied `dt`.

## First-person controller

```python
from swirengine.character import FirstPersonController3D

fps = FirstPersonController3D(player, physics_scene, camera)
fps.update(command, dt)
```

`look_yaw` and `look_pitch` are semantic deltas. `look_sensitivity` converts them into degrees per
second. Pitch is clamped to prevent camera inversion. The optional existing `CameraRig3D` can be
supplied when eye movement should be smoothed.

## Third-person controller

`ThirdPersonController3D` builds on the existing `CameraRig3D`. The orbit pivot tracks the character,
movement follows camera yaw, and a small Physics 2.0 sweep can shorten the camera boom when an
obstacle is between the pivot and the desired camera position.

```python
from swirengine.character import ThirdPersonController3D

third_person = ThirdPersonController3D(
    player,
    physics_scene,
    camera,
    camera_distance=5.0,
)
third_person.update(command, dt)
```

## Platformer controller

`PlatformerController3D` supports three movement modes:

- `"xz"` — free 3D platformer movement
- `"x"` — side-scroller movement along X
- `"z"` — side-scroller movement along Z

The controller inherits ground snapping, slope/step handling, coyote time and jump buffering from the
base motor. An optional `CameraRig3D` can follow a configurable camera offset.

## InputActions integration

The controller does not hard-code physical keys. `CharacterActionBindings3D` samples semantic actions
from the existing rebinding layer:

```python
from swirengine.character import CharacterActionBindings3D

bindings = CharacterActionBindings3D()
command = bindings.sample(actions)
controller.update(command, dt)
```

Default action names are `move_forward`, `move_backward`, `move_left`, `move_right`, `jump`, `sprint`
and four look actions. Games can replace any name in the bindings dataclass.

## Navigation integration

`CharacterNavigationDriver3D` accepts any `NavigationProvider3D`. It caches the current world-space
path and automatically repaths when the provider revision changes.

```python
from swirengine.character import CharacterNavigationDriver3D
from swirengine.math.types import Vec3

navigator = CharacterNavigationDriver3D(controller, navigation_grid)
navigator.set_goal(Vec3(20, 0, 8))

# game loop
navigator.update(dt)
```

A stateless `follow_character_path` helper is also available for projects that own path generation
and waypoint state themselves.

## Diagnostics and performance contract

`controller.diagnostics` reports sweeps, sweep hits, ground probes, step attempts and successful
steps for the most recent update. The dedicated 1.4 character-controller gate drives a grounded
character across repeated low obstacles and verifies a bounded sweep budget. Host timing is printed
for diagnostics only and is never converted into an unmeasured FPS claim.

## Compatibility

This milestone is additive:

- `RigidBody3D` / `PhysicsWorld3D` remain unchanged
- `PhysicsBody3D` / `PhysicsScene3D` remain the Physics 2.0 backend
- camera, input and navigation APIs are reused rather than replaced
- the stable package version remains 1.3.0 until the complete 1.4 roadmap reaches 10/10
