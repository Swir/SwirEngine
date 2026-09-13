# Responsive UI layout and navigation

SwirEngine 1.1 adds a creator-facing responsive UI foundation without replacing the stable 1.x controls API.

## Anchors and scaling

`UILayout` resolves UI origins against the current viewport using center, edge, and corner anchors. Optional reference-resolution scaling uses the smaller viewport ratio so UI keeps its proportions across aspect ratios. `min_scale` and `max_scale` prevent unusable extremes.

```python
from swirengine.ui import UIButton
from swirengine.ui_layout import UIAnchor, UIContainer, UILayout

play = UIButton("Play", 0, 0)
options = UIButton("Options", 0, 0)
menu = UIContainer(
    play,
    options,
    spacing=18,
    layout=UILayout(
        anchor=UIAnchor.CENTER,
        scale_with_viewport=True,
        reference_width=1280,
        reference_height=720,
    ),
)

# Call when the viewport changes or once per frame for dynamic layouts.
menu.arrange(window_width, window_height)
```

Containers support vertical and horizontal flow while preserving creator-defined order. Controls are scaled from their original dimensions rather than compounding scale on every resize.

## Keyboard and gamepad focus

`UIFocusManager` gives menus deterministic focus order and activation without requiring mouse input.

```python
from swirengine.ui_navigation import UIFocusManager

focus = UIFocusManager((play, options))

# In the game update loop:
focus.update(game.input)
```

Default navigation:

- keyboard: `Tab`, arrows to move; `Enter` or `Space` to activate,
- gamepad: D-pad to move; standardized `A` to activate,
- disabled or hidden buttons are skipped,
- navigation wraps at the beginning/end of the list.

The controller works with the standardized hot-plug gamepad API introduced earlier in the 1.1 roadmap and checks all connected pads deterministically.

## Design notes

The responsive layer is intentionally independent from rendering backends and editor UI. It operates on existing SwirEngine controls, which keeps the public 1.x API stable and makes the same layout/navigation primitives usable in HUDs, pause menus, gamepad-first interfaces, and future editor workflows.
