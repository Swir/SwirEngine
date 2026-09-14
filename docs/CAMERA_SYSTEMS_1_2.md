# Camera Systems — SwirEngine 1.2

SwirEngine 1.2 adds a shared creator-facing camera workflow for 2D and 3D without replacing the stable `Camera2D` and `Camera3D` APIs.

## Core pieces

- `CameraRig2D` wraps an existing `Camera2D`.
- `CameraRig3D` wraps an existing `Camera3D` and preserves its look direction while the rig moves.
- `CameraBounds2D` / `CameraBounds3D` constrain logical camera positions.
- `CameraRail2D` / `CameraRail3D` interpolate deterministic multi-segment camera paths.
- Both rigs expose the same `snap_to`, `follow`, `move_on_rail` and `shake` workflow.

## Stable smoothing

Follow smoothing uses an exponential time-step-aware interpolation factor:

```text
alpha = 1 - exp(-speed * dt)
```

This avoids tying follow responsiveness directly to a particular frame rate. `smoothing=0` disables automatic follow interpolation; creators can still use `snap_to` or rails directly.

## 2D dead zone

`CameraRig2D.dead_zone` is the width/height of the target region that can move without pulling the camera. Once the target exits that region, the rig follows the nearest edge rather than snapping directly to the target.

## Bounds

Bounds are applied to the logical camera position before shake. This keeps gameplay/world constraints stable while allowing short-lived visual shake to extend around the bounded position.

## Deterministic shake

Shake uses deterministic trigonometric oscillators rather than allocating random samples every frame. Equal amplitude, duration, frequency, seed and time steps yield equal shake output. The envelope decays over the configured duration.

```python
rig.shake(3.0, 0.35, frequency=16.0, seed=42.0)
```

## Rails

Rails accept at least two points and interpolate across equal logical segments. `progress` is clamped to `0..1`.

```python
rail = CameraRail2D((Vec2(0, 0), Vec2(20, 0), Vec2(20, 12)))
rig.move_on_rail(rail, progress=0.75, dt=1 / 60)
```

## Compatibility

Existing games can continue using `Camera2D` and `Camera3D` directly. The 1.2 runtime is additive: opt into camera rigs only where advanced follow, constraints, shake or rails are useful.
