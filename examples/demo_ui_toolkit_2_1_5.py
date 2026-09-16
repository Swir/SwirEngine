from __future__ import annotations

from swirengine.core.scene import Scene
from swirengine.ui15 import UITheme, UIToolkit


def main() -> None:
    scene = Scene()
    ui = UIToolkit(scene)
    menu = ui.panel("main-menu", 520, 360, padding=28, gap=20)
    ui.label("title", "SwirEngine 1.5", parent=menu, height=48)
    status = ui.label("status", "Ready", parent=menu, height=36)

    def play(_widget) -> None:
        status.text = "Play selected"

    ui.button("play", "Play", parent=menu, on_activate=play)
    ui.button("settings", "Settings", parent=menu)
    ui.progress("loading", parent=menu, value=0.65)

    print("SwirEngine 1.5 UI Toolkit 2.0 creator demo")
    for viewport in ((1280, 720), (1920, 1080), (960, 540)):
        scale = ui.layout(*viewport)
        ui.focus_next()
        print(
            f"viewport={viewport} scale={scale:.2f} "
            f"focus={ui.diagnostics().focused_id} scene_objects={len(scene)}"
        )

    ui.focus("play")
    ui.activate_focused()
    ui.set_theme(UITheme.high_contrast())
    ui.layout(1280, 720)
    print("status:", status.text)
    print("fingerprint:", ui.fingerprint())
    print("diagnostics:", ui.diagnostics())


if __name__ == "__main__":
    main()
