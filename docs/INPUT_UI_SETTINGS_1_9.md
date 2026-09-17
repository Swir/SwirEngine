# SwirEngine 1.9 — Input, UI & Settings Shipping Contract

SwirEngine 1.9 Milestone 3 connects the existing input, gamepad and retained-UI foundations into a
portable production contract that a real game can use from its title screen through gameplay.

This remains **source-only 1.9 development**. It does not create a release, tag or PyPI publication.

## Goals

The contract solves four production problems without changing stable 1.x input behavior:

1. keep version-controlled project defaults separate from per-player rebinding/settings files;
2. use semantic actions for keyboard, mouse and standardized gamepads instead of hard-coded menu keys;
3. validate and persist display/accessibility settings with deterministic, bounded files;
4. apply display changes through explicit backend callbacks instead of guessing window/render APIs.

## Project defaults

By convention a project may carry:

```text
config/
  controls.json
  settings.json
```

Load those defaults with:

```python
from swirengine.shipping19 import ProjectShippingDefaults

shipping = ProjectShippingDefaults.load(".")
```

If either file does not exist, SwirEngine supplies safe built-in defaults. To materialize the defaults:

```python
shipping.write_templates()
```

The generated input profile always contains a shipping-safe navigation surface:

- `ui_up`
- `ui_down`
- `ui_left`
- `ui_right`
- `ui_accept`
- `ui_back`

The default bindings cover arrow keys/WASD, d-pad, left stick, Enter/Space/A and Escape/B. `pause`
also receives Escape/Start. Games can add semantic gameplay actions such as `jump`, `interact`,
`inventory` or `fire`.

## Rebinding without mutating the project

Project defaults should normally be committed to source control. Player overrides should be written
to the game's user-data location:

```python
from swirengine.input import InputBinding
from swirengine.shipping19 import InputOverrideStore

store = InputOverrideStore(shipping.actions, user_data / "controls.json")
controls = store.load()
controls = controls.replace_action(
    "jump",
    [
        InputBinding("key", "space"),
        InputBinding("gamepad_button", "A"),
    ],
)
store.save(controls)
```

Only actions that differ from project defaults are stored. That matters when a later game build adds
new default actions: unchanged project defaults still flow through while the player's explicit
rebinding survives.

The profile is bounded to 128 actions and eight bindings per action. Gamepad button/axis names are
validated through SwirEngine's standardized gamepad map. Empty shipping navigation actions are
rejected instead of allowing a player to accidentally make menus unreachable.

`ProductionActionMap.conflicts()` provides deterministic conflict diagnostics. Conflicts are not
automatically rejected because games often intentionally share a control (for example Escape for
both `ui_back` and `pause`).

## Semantic menu navigation

Install a production action map over the existing `InputManager`:

```python
actions = shipping.actions.install(game.input)
```

Then route those actions through retained UI focus:

```python
from swirengine.shipping19 import FocusActionRouter
from swirengine.ui_navigation import UIFocusManager

focus = UIFocusManager([play_button, settings_button, quit_button])
router = FocusActionRouter(focus, actions, on_back=close_menu)

@game.update
def update(_dt):
    router.update()
```

`FocusActionRouter` edge-detects semantic action state rather than raw key events. This means a menu
uses the same logic for keyboard, d-pad and analog-stick navigation. Holding a direction does not
produce an unbounded per-frame focus repeat; a new edge is required.

## Display and accessibility settings

`GameSettings` currently contains a bounded shipping contract for:

### Display

- width / height;
- fullscreen + explicit borderless fullscreen;
- VSync;
- optional frame cap (`0` means uncapped by this setting);
- UI scale.

### Accessibility

- text scale;
- reduced motion;
- high contrast;
- subtitles;
- hold-to-confirm preference.

Project defaults and player settings use the same validated schema:

```python
from swirengine.shipping19 import SettingsStore

settings_store = SettingsStore(shipping.settings, user_data / "settings.json")
settings = settings_store.load()
settings = settings.with_display(width=1920, height=1080, vsync=True)
settings = settings.with_accessibility(subtitles=True, reduced_motion=False)
settings_store.save(settings)
```

Unknown sections/options, non-finite numeric values and unsafe ranges fail explicitly rather than
being silently ignored.

## Backend-safe display bridge

Window/render backends do not all expose the same API. `apply_display_settings(...)` therefore uses
creator/backend callbacks and reports unsupported changes:

```python
from swirengine.shipping19 import apply_display_settings

result = apply_display_settings(
    old_settings.display,
    new_settings.display,
    resize=window.resize,
    fullscreen=window.set_fullscreen_mode,
    vsync=renderer.set_vsync,
    frame_limit=game.set_frame_limit,
    ui_scale=ui.set_scale,
)

if result.unsupported:
    print("Unsupported display options:", result.unsupported)
```

No hidden window mutation or backend guessing occurs. Initial startup can pass `previous=None` to
request all effective values.

## File-safety contract

Production control/settings data is intentionally constrained:

- configuration files are bounded to 256 KiB;
- project template paths must stay within the selected project root;
- absolute, Windows-drive and traversal escapes are rejected;
- symlink-resolved escapes are rejected where the host exposes symlinks;
- writes use a same-directory temporary file plus `os.replace`;
- fingerprints use canonical JSON and SHA-256 for deterministic diagnostics.

These fingerprints are content identity/diagnostic values, not security signatures.

## Creator example

Run the source-only end-to-end flow:

```bash
python examples/production_flow_1_9.py
```

The example exercises project defaults, user rebinding, settings persistence, backend display
application, title/settings/gameplay focus routing and deterministic fingerprints without requiring a
rendering window. The same contract is usable from both 2D and 3D projects.

## Verification

Focused gate:

```bash
pytest -q tests/test_input_ui_settings_1_9.py
python examples/production_flow_1_9.py
python tools/bench_input_ui_settings_1_9.py
ruff check src/swirengine/shipping19.py tests/test_input_ui_settings_1_9.py \
  examples/production_flow_1_9.py tools/bench_input_ui_settings_1_9.py
python -m compileall -q src/swirengine/shipping19.py tests/test_input_ui_settings_1_9.py \
  examples/production_flow_1_9.py tools/bench_input_ui_settings_1_9.py
```

The deterministic workload parses and fingerprints 5,000 action/settings cycles under a deliberately
generous 5-second Python 3.13 CI ceiling. That is a regression guard for Python-side configuration
work and **not** an FPS or input-latency claim.

Before Milestone 3 can be checked, its exact implementation head must pass the dedicated Python
3.10/3.13/3.14 gate and the repository-wide compatibility/runtime/packaging gates.

`Release/PyPI: frozen until SwirEngine 2.0`.
