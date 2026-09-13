# Animation, Tween and State Machine Runtime

SwirEngine 1.1 includes a renderer-independent animation runtime for gameplay, UI and editor tooling. It is designed to work with ordinary Python objects, dictionaries and engine objects, so the same API can drive 2D sprites, 3D transforms, camera values, UI opacity or gameplay state.

## Tween a property

```python
from swirengine.animation_runtime import Ease, Tween

move = Tween(player, "transform.position", [8.0, 0.0, -3.0], duration=0.4, ease=Ease.OUT_QUAD)

# In your update loop:
move.update(dt)
```

Nested property paths are supported. A tween captures its start value lazily on the first update unless an explicit `start=` value is supplied. Delays, repeats, yoyo playback and completion callbacks are built in.

## Parallel timelines and event markers

```python
from swirengine.animation_runtime import AnimationTimeline, Tween

attack = AnimationTimeline()
attack.add(Tween(player, "transform.position", [0.0, 0.0, -1.0], duration=0.12))
attack.add(Tween(weapon, "alpha", 0.2, duration=0.12))
attack.add_marker(0.08, "hit_window")
attack.on_marker = lambda marker: combat.handle_animation_marker(marker.name)

attack.update(dt)
```

A timeline advances all tracks together. Markers provide deterministic gameplay hooks for hit windows, footsteps, VFX, audio or scripted events. `seek()` reconstructs tween state without replaying marker callbacks, which is useful for editor previews and scrubbing.

## Sequential tweens

```python
from swirengine.animation_runtime import Tween, TweenSequence

sequence = TweenSequence([
    Tween(panel, "alpha", 1.0, duration=0.2),
    Tween(panel, "y", 40.0, duration=0.35),
])
sequence.update(dt)
```

Set `loop=True` for repeating sequences.

## Gameplay state machines

```python
from swirengine.animation_runtime import State, StateMachine

machine = StateMachine([
    State("idle", on_enter=lambda previous: player.play("idle")),
    State("run", on_enter=lambda previous: player.play("run")),
    State("dead", on_enter=lambda previous: player.play("dead")),
], initial="idle")

machine.add_transition("*", "dead", lambda: player.health <= 0, priority=100)
machine.add_transition("idle", "run", lambda: player.speed > 0.1)
machine.add_transition("run", "idle", lambda: player.speed <= 0.1)

machine.update(dt)
```

Transitions are evaluated by descending priority. `"*"` is a global source state, useful for death, pause, stun or cutscene overrides. Each state can define enter, update and exit callbacks, and `time_in_state` is tracked automatically.

## Unified animation system

`AnimationSystem` owns timelines, sequences and state machines and advances all of them from one `update(dt)` call. `prune_finished()` removes completed timelines and sequences while leaving persistent state machines alive.

The runtime intentionally does not depend on a specific renderer. It complements `AnimatedSprite2D`: sprite-sheet frame playback can remain visual while the new runtime handles movement, UI, 3D values, gameplay transitions and event timing.

## Determinism and performance notes

- No per-frame threads or background workers are created.
- Easing functions are pure and deterministic for a given input.
- Timelines and sequences keep their own elapsed state and do not depend on wall-clock time.
- `AnimationSystem.update()` iterates stable snapshots so gameplay code can safely schedule future animation work.
- Use engine `dt` values rather than `time.time()` so pause, replay and fixed-step systems remain controllable.
