from __future__ import annotations

"""SwirEngine 1.9 production input/UI/settings flow.

This source-only example keeps rendering out of the way so the complete shipping contract can be
validated headlessly. A 2D or 3D game can attach the same semantic action map and settings stores to
its real title/settings/gameplay scenes.
"""

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from swirengine.input import InputBinding
from swirengine.shipping19 import (
    FocusActionRouter,
    InputOverrideStore,
    ProjectShippingDefaults,
    SettingsStore,
    apply_display_settings,
)
from swirengine.ui_navigation import UIFocusManager


@dataclass
class MenuButton:
    name: str
    enabled: bool = True
    visible: bool = True
    focusable: bool = True
    on_click: object | None = None


class DemoInput:
    def __init__(self) -> None:
        self.keys: set[str] = set()

    def key(self, name: str) -> bool:
        return name.lower() in self.keys

    def mouse_button(self, _button: int) -> bool:
        return False

    def gamepad_button(self, _name: str, *, gamepad_id: int = 0) -> bool:
        del gamepad_id
        return False

    def gamepad_axis(self, _name: str, *, gamepad_id: int = 0) -> float:
        del gamepad_id
        return 0.0


def main() -> int:
    with TemporaryDirectory(prefix="swirengine-production-flow-") as temporary:
        project = Path(temporary)
        defaults = ProjectShippingDefaults.load(project)
        defaults.write_templates()

        # User files live outside version-controlled project defaults in a real game.
        user = project / ".demo-user"
        input_store = InputOverrideStore(defaults.actions, user / "controls.json")
        settings_store = SettingsStore(defaults.settings, user / "settings.json")

        # A settings screen can rebind semantic actions without touching gameplay code.
        controls = input_store.load().replace_action(
            "ui_accept",
            [
                InputBinding("key", "enter"),
                InputBinding("gamepad_button", "A"),
            ],
        )
        input_store.save(controls)

        # The same screen persists validated display/accessibility choices.
        settings = settings_store.load().with_display(
            width=1600,
            height=900,
            vsync=True,
            ui_scale=1.1,
        )
        settings = settings.with_accessibility(
            subtitles=True,
            reduced_motion=True,
        )
        settings_store.save(settings)

        applied: list[str] = []
        result = apply_display_settings(
            None,
            settings.display,
            resize=lambda width, height: applied.append(f"resize:{width}x{height}"),
            fullscreen=lambda enabled, borderless: applied.append(
                f"fullscreen:{enabled}:{borderless}"
            ),
            vsync=lambda enabled: applied.append(f"vsync:{enabled}"),
            frame_limit=lambda limit: applied.append(f"max_fps:{limit}"),
            ui_scale=lambda scale: applied.append(f"ui_scale:{scale}"),
        )
        assert not result.unsupported

        # Title -> settings -> gameplay uses one semantic navigation contract.
        transitions: list[str] = []
        play = MenuButton("play", on_click=lambda _button: transitions.append("gameplay"))
        settings_button = MenuButton(
            "settings",
            on_click=lambda _button: transitions.append("settings"),
        )
        quit_button = MenuButton("quit", on_click=lambda _button: transitions.append("quit"))
        focus = UIFocusManager([play, settings_button, quit_button])

        live_input = DemoInput()
        actions = input_store.load().install(live_input)
        router = FocusActionRouter(
            focus,
            actions,
            on_back=lambda: transitions.append("back"),
        )

        live_input.keys.add("down")
        assert router.update().focused is play
        live_input.keys.clear()
        router.update()
        live_input.keys.add("down")
        assert router.update().focused is settings_button
        live_input.keys.clear()
        router.update()
        live_input.keys.add("enter")
        assert router.update().activated
        assert transitions == ["settings"]

        print("project fingerprint:", defaults.fingerprint)
        print("controls fingerprint:", input_store.load().fingerprint)
        print("settings fingerprint:", settings_store.load().fingerprint)
        print("display operations:", ", ".join(applied))
        print("flow: title -> settings -> gameplay contract verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
