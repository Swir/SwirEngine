# Input actions and rebinding

SwirEngine 1.1 adds a semantic input layer on top of `InputManager`. Gameplay code can now ask for actions such as `jump`, `fire` or `move_left` instead of hard-coding a keyboard key or controller button.

```python
from swirengine.input import InputActions

controls = InputActions(game.input)
controls.key("jump", "SPACE")
controls.gamepad_button("jump", "A")
controls.mouse_button("fire", 0)
controls.gamepad_button("fire", "RIGHT_BUMPER")
controls.gamepad_axis("move_left", "left_x", direction=-1, threshold=0.25)

if controls.pressed("jump"):
    player.jump()

player.throttle_left = controls.value("move_left")
```

## Runtime rebinding

Pass `replace=True` to replace an action's existing binding, or use `unbind(...)` before adding a new binding. Multiple bindings can coexist, so keyboard and controller defaults can remain active together.

```python
controls.key("jump", "J", replace=True)
controls.gamepad_button("jump", "A")
```

`InputBinding` is immutable and serializable. Supported binding kinds are `key`, `mouse_button`, `gamepad_button` and `gamepad_axis`.

## Persistent profiles

Profiles use a versioned JSON format and can be edited by a game's controls/settings screen.

```python
controls.save("settings/controls.json")
controls.load("settings/controls.json")
```

The profile stores action names plus their physical bindings, gamepad ID, axis direction, threshold and scale. Unknown profile versions are rejected instead of being silently misread.

## Queries

- `down(action, threshold=0.5)` — digital-style held state derived from any binding.
- `pressed(action)` — edge query for keyboard, mouse and gamepad buttons.
- `released(action)` — release edge query for keyboard, mouse and gamepad buttons.
- `value(action)` — strongest absolute analog/digital value across all bindings.
- `bindings(action)` — immutable snapshot suitable for a controls UI.
- `actions()` — deterministic list of configured action names.

Axis actions preserve analog magnitude and can invert direction with `direction=-1`. This lets one physical stick axis feed separate semantic actions such as `move_left` and `move_right` without per-frame allocation-heavy mapping code in game logic.
