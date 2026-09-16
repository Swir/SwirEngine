# UI Toolkit 2.0 — SwirEngine 1.5

UI Toolkit 2.0 is an additive retained-mode creator UI layer for SwirEngine 1.5. It lives in `swirengine.ui15` and deliberately composes the released 1.x `UILabel`, `UIPanel`, `UIButton`, `UIProgressBar` and `UIManager` renderer-facing controls instead of replacing them.

## Goals

The 1.5 layer adds a retained hierarchy, deterministic responsive layout, unified mouse/keyboard/gamepad focus, theme propagation, diagnostics and portable state fingerprints. Existing 1.x projects can keep using `Game.button(...)`, `Game.label(...)`, `UIManager` and `UIContainer` without migration.

```python
from swirengine.core.scene import Scene
from swirengine.ui15 import UIToolkit

scene = Scene()
ui = UIToolkit(scene)
menu = ui.panel("menu", 520, 360, padding=28, gap=18)
ui.label("title", "My Game", parent=menu)
ui.button("play", "Play", parent=menu, on_activate=lambda widget: print(widget.id))
ui.button("quit", "Quit", parent=menu)
ui.layout(1920, 1080)
```

## Retained hierarchy

Every widget has a stable string id and an explicit parent. `stack(...)` and `panel(...)` may own children; labels, buttons and progress bars can be placed inside those retained containers. IDs are unique per toolkit, reparenting rejects cycles, and recursive removal also unregisters the stable rendering controls from the scene.

The authored hierarchy is independent from viewport pixels. Widths, heights, gaps, padding and offsets are specified in reference-resolution units. The default reference canvas is 1280×720.

## Responsive layout

`UIToolkit.layout(width, height)` computes one uniform scale from the configured reference resolution and clamps it to the configured scale limits. Vertical and horizontal containers support:

- start, center, end and stretch cross-axis alignment;
- start, center, end and space-between main-axis justification;
- per-container padding and gaps;
- inherited visibility and enabled state;
- stable centered screen-space coordinates that feed the released 1.x UI controls.

The layout is deterministic: the same retained tree, theme and viewport produce the same geometry and portable fingerprint regardless of callback identity.

## Focus and input

Focusable widgets are enumerated in retained document order while hidden or disabled branches are automatically excluded. Creator code can call `focus(...)`, `focus_next(...)`, `focus_move(...)` or `activate_focused()` directly.

`update(input_manager, width, height)` integrates the same model with:

- mouse press/release activation that requires release on the armed widget;
- `Tab` / `Shift+Tab` sequential traversal;
- arrow-key spatial navigation;
- standardized gamepad D-pad spatial navigation;
- `Enter`, `Space` or gamepad `A` activation.

Directional focus uses current laid-out widget centers and deterministic primary-axis scoring rather than registration-time coordinates.

## Themes

`UITheme` centralizes panel, text, button state and progress colors. `set_theme(...)` updates existing renderer controls immediately; `UITheme.high_contrast()` is provided as a built-in accessibility-oriented preset. The retained layer does not modify global 1.x UI defaults.

## Diagnostics and reproducibility

`diagnostics()` reports retained node count, visible/focusable counts, layout generation, activation count, pointer hits, current focus, effective scale and last viewport.

`snapshot()` returns a portable creator-state document and `fingerprint()` returns its SHA-256 digest. Runtime callbacks and transient pointer/focus state are intentionally excluded so fingerprints remain useful in CI, replay and regression tooling.

## Performance contract

`tools/benchmark_ui_toolkit_2_1_5.py` exercises 240 focusable buttons across nested retained containers for 320 responsive layout/focus passes. The CI guard is a deliberately generous 5.0-second host-side budget. This is a regression contract for layout/control synchronization only and is not an FPS claim or GPU-rendering benchmark.

## Compatibility contract

UI Toolkit 2.0 is opt-in through `swirengine.ui15`. Stable 1.x UI classes and factory behavior remain unchanged. Milestone completion requires the focused Python 3.10/3.13/3.14 gate, Ruff, compile validation, demo, workload contract and the normal repository compatibility/runtime/export gates to pass on the exact milestone head before `ROADMAP_1_5.md` can move from 6/10 to 7/10.
