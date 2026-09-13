# Responsive UI layout and navigation

SwirEngine 1.1 adds a creator-facing responsive UI foundation without replacing the stable 1.x controls API. Existing `UILabel`, `UIPanel`, `UIButton` and `UIProgressBar` controls can still be positioned manually, while responsive menus can opt into layout, scaling and focus navigation.

## Integrated creator workflow

The responsive API is exported directly from `swirengine`, and `UIManager` owns both layout and focus so normal games do not need a second UI update loop.

```python
from swirengine import Game, UIAnchor, UILayout


game = Game("Menu", 1280, 720)
play = game.button("Play", 0, 0, 260, 58, on_click=lambda _button: print("play"))
options = game.button("Options", 0, 0, 260, 58)

menu = game.ui.container(
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

game.run()
```

`Game` already calls `UIManager.update()`, so the container is arranged against the current viewport every frame and focus navigation is processed automatically.

## Anchors and scaling

`UILayout` resolves UI origins against the current viewport using center, edge, and corner anchors. Optional reference-resolution scaling uses the smaller viewport ratio so UI keeps its proportions across aspect ratios. `min_scale` and `max_scale` prevent unusable extremes.

Available anchors are `CENTER`, `TOP_LEFT`, `TOP`, `TOP_RIGHT`, `LEFT`, `RIGHT`, `BOTTOM_LEFT`, `BOTTOM`, and `BOTTOM_RIGHT`.

Containers support vertical and horizontal flow while preserving creator-defined order. Controls are always scaled from their original authored dimensions, so repeatedly resizing a window does not compound scale. Button/label text scale is derived from the same reference scale, and progress bars/panels resynchronize their render geometry after a layout change.

For lower-level or custom loops, `UIContainer.arrange(width, height)` and `place_control()` remain available directly.

## Keyboard, mouse and gamepad focus

`UIManager` maintains a `UIFocusManager` for every button it owns. Default navigation is:

- keyboard: `Tab`, arrows to move; `Enter` or `Space` to activate,
- gamepad: D-pad to move; standardized `A` to activate,
- mouse: hovering a button transfers focus to it while preserving press/release click semantics,
- disabled, hidden or `focusable=False` buttons are skipped,
- navigation wraps at the beginning/end of the list.

Focused buttons expose `button.focused` and use `focused_color`. Creators can override that color without replacing pointer hover/pressed states. The controller uses the standardized hot-plug gamepad API introduced earlier in the 1.1 roadmap and checks all connected pads deterministically.

Advanced users can also instantiate `UIFocusManager` directly when they need a custom focus group independent of `UIManager`.

## Stable 1.x behavior

The milestone is additive: existing manually positioned UI code and pointer interactions remain valid. Layout containers do not take ownership of rendering objects; they only place existing controls. Removing a control from `UIManager` also removes it from registered layout containers and focus order, preventing stale navigation targets.

This foundation is deliberately renderer-independent so the same primitives can serve HUDs, pause menus, settings screens, gamepad-first games and later editor workflows.

See `examples/demo_responsive_ui.py` for a complete resize-aware keyboard/gamepad menu.
