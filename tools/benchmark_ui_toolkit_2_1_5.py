from __future__ import annotations

from time import perf_counter

from swirengine.core.scene import Scene
from swirengine.ui15 import UIAxis, UIToolkit


WIDGETS = 240
LAYOUT_PASSES = 320
BUDGET_SECONDS = 5.0


def build_toolkit() -> UIToolkit:
    ui = UIToolkit(Scene(), min_scale=0.4, max_scale=2.5)
    grid = ui.stack("grid", 1180, 680, axis=UIAxis.HORIZONTAL, gap=8)
    for column_index in range(6):
        column = ui.stack(
            f"column-{column_index}",
            184,
            650,
            parent=grid,
            gap=4,
        )
        for row_index in range(WIDGETS // 6):
            ui.button(
                f"button-{column_index}-{row_index}",
                f"Action {column_index}:{row_index}",
                parent=column,
                width=176,
                height=12,
            )
    return ui


def main() -> None:
    ui = build_toolkit()
    started = perf_counter()
    for index in range(LAYOUT_PASSES):
        width = 1280 + (index % 5) * 160
        height = 720 + (index % 3) * 90
        ui.layout(width, height)
        if index % 2:
            ui.focus_next(1)
        else:
            ui.focus_next(-1)
    elapsed = perf_counter() - started
    diagnostics = ui.diagnostics()
    print(
        "UI Toolkit 2.0 workload: "
        f"{WIDGETS} buttons, {LAYOUT_PASSES} responsive layouts, "
        f"elapsed={elapsed:.3f}s, layouts={diagnostics.layout_generation}"
    )
    if elapsed > BUDGET_SECONDS:
        raise SystemExit(
            f"UI Toolkit 2.0 workload exceeded {BUDGET_SECONDS:.1f}s CI budget: {elapsed:.3f}s"
        )


if __name__ == "__main__":
    main()
