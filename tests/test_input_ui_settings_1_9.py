from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from swirengine.input import InputBinding
from swirengine.shipping19 import (
    AccessibilitySettings,
    DisplaySettings,
    FocusActionRouter,
    GameSettings,
    InputOverrideStore,
    ProductionActionMap,
    ProjectShippingDefaults,
    REQUIRED_UI_ACTIONS,
    SettingsStore,
    ShippingContractError,
    apply_display_settings,
)
from swirengine.ui_navigation import UIFocusManager


class FakeInput:
    def __init__(self) -> None:
        self.keys: set[str] = set()
        self.mouse: set[int] = set()
        self.buttons: dict[tuple[int, str], bool] = {}
        self.axes: dict[tuple[int, str], float] = {}

    def key(self, name: str) -> bool:
        return name.lower() in self.keys

    def key_pressed(self, name: str) -> bool:
        return self.key(name)

    def key_released(self, name: str) -> bool:
        return False

    def mouse_button(self, button: int) -> bool:
        return button in self.mouse

    def mouse_button_pressed(self, button: int) -> bool:
        return self.mouse_button(button)

    def mouse_button_released(self, button: int) -> bool:
        return False

    def gamepad_button(self, name: str, *, gamepad_id: int = 0) -> bool:
        return bool(self.buttons.get((gamepad_id, name.upper()), False))

    def gamepad_button_pressed(self, name: str, *, gamepad_id: int = 0) -> bool:
        return self.gamepad_button(name, gamepad_id=gamepad_id)

    def gamepad_button_released(self, name: str, *, gamepad_id: int = 0) -> bool:
        return False

    def gamepad_axis(self, name: str, *, gamepad_id: int = 0) -> float:
        return float(self.axes.get((gamepad_id, name.upper()), 0.0))

    def gamepads(self) -> tuple[int, ...]:
        ids = {item[0] for item in self.buttons} | {item[0] for item in self.axes}
        return tuple(sorted(ids))


@dataclass
class FakeButton:
    name: str
    enabled: bool = True
    visible: bool = True
    focusable: bool = True
    focused: bool = False
    on_click: object | None = None


def test_standard_action_map_has_keyboard_gamepad_and_required_navigation() -> None:
    profile = ProductionActionMap.standard()
    profile.require_actions(REQUIRED_UI_ACTIONS)

    assert "pause" in profile.actions()
    assert any(
        binding.kind == "gamepad_button" and binding.control == "A"
        for binding in profile.bindings("ui_accept")
    )
    assert any(
        binding.kind == "gamepad_axis" and binding.control == "LEFT_Y"
        for binding in profile.bindings("ui_up")
    )
    assert profile.fingerprint == ProductionActionMap.standard().fingerprint


def test_action_map_roundtrip_is_canonical_and_deterministic(tmp_path: Path) -> None:
    original = ProductionActionMap.standard().replace_action(
        "jump",
        [
            InputBinding("key", "SPACE"),
            InputBinding("gamepad_button", "a"),
            InputBinding("key", "SPACE"),
        ],
    )
    target = tmp_path / "controls.json"
    original.save(target)
    restored = ProductionActionMap.load(target)

    assert restored.fingerprint == original.fingerprint
    assert restored.bindings("jump") == (
        InputBinding("key", "space"),
        InputBinding("gamepad_button", "A"),
    )
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["format"] == "swirengine-input-profile"
    assert payload["version"] == 1


def test_action_map_rejects_missing_shipping_navigation() -> None:
    payload = ProductionActionMap.standard().to_dict()
    del payload["actions"]["ui_accept"]
    with pytest.raises(ShippingContractError, match="required shipping actions"):
        ProductionActionMap.from_dict(payload)


@pytest.mark.parametrize(
    ("binding", "message"),
    [
        (InputBinding("mouse_button", 50), "mouse button"),
        (InputBinding("gamepad_button", "not-a-button"), "unknown gamepad button"),
        (InputBinding("gamepad_axis", "not-an-axis"), "unknown gamepad axis"),
        (InputBinding("key", ""), "key controls"),
        (InputBinding("key", "x", gamepad_id=99), "gamepad_id"),
        (InputBinding("key", "x", scale=99.0), "scale"),
    ],
)
def test_action_map_rejects_unsafe_or_unknown_bindings(
    binding: InputBinding,
    message: str,
) -> None:
    data = dict(ProductionActionMap.standard().bindings_by_action)
    data["custom"] = (binding,)
    with pytest.raises(ShippingContractError, match=message):
        ProductionActionMap(data)


def test_action_map_conflicts_are_diagnostics_not_rejections() -> None:
    profile = ProductionActionMap.standard()
    conflict = next(item for item in profile.conflicts() if item.control == "key:escape")
    assert conflict.actions == ("pause", "ui_back")


def test_input_override_store_persists_only_user_changes_and_preserves_new_defaults(
    tmp_path: Path,
) -> None:
    defaults = ProductionActionMap.standard().replace_action(
        "jump",
        [InputBinding("key", "space")],
    )
    path = tmp_path / "user" / "controls.json"
    store = InputOverrideStore(defaults, path)

    rebound = defaults.replace_action(
        "jump",
        [
            InputBinding("key", "j"),
            InputBinding("gamepad_button", "X"),
        ],
    )
    store.save(rebound)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert list(payload["actions"]) == ["jump"]

    evolved_defaults = defaults.replace_action(
        "interact",
        [InputBinding("key", "e")],
    )
    loaded = InputOverrideStore(evolved_defaults, path).load()
    assert loaded.bindings("jump")[0].control == "j"
    assert loaded.bindings("interact")[0].control == "e"


def test_input_override_cannot_remove_required_navigation(tmp_path: Path) -> None:
    defaults = ProductionActionMap.standard()
    path = tmp_path / "controls.json"
    path.write_text(
        json.dumps(
            {
                "format": "swirengine-input-overrides",
                "version": 1,
                "actions": {"ui_accept": []},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ShippingContractError, match="required shipping actions"):
        InputOverrideStore(defaults, path).load()


def test_input_override_reset_returns_project_defaults(tmp_path: Path) -> None:
    defaults = ProductionActionMap.standard()
    store = InputOverrideStore(defaults, tmp_path / "controls.json")
    store.save(defaults.replace_action("ui_accept", [InputBinding("key", "e")]))
    assert store.load().bindings("ui_accept")[0].control == "e"
    store.reset()
    assert store.load().fingerprint == defaults.fingerprint


def test_display_and_accessibility_settings_are_strictly_bounded() -> None:
    with pytest.raises(ShippingContractError, match="width"):
        DisplaySettings(width=100)
    with pytest.raises(ShippingContractError, match="borderless"):
        DisplaySettings(borderless=True)
    with pytest.raises(ShippingContractError, match="ui_scale"):
        DisplaySettings(ui_scale=5.0)
    with pytest.raises(ShippingContractError, match="text_scale"):
        AccessibilitySettings(text_scale=3.0)


def test_settings_roundtrip_and_partial_load_use_project_defaults(tmp_path: Path) -> None:
    defaults = GameSettings(
        display=DisplaySettings(width=1920, height=1080, vsync=False, ui_scale=1.25),
        accessibility=AccessibilitySettings(subtitles=False),
    )
    path = tmp_path / "settings.json"
    store = SettingsStore(defaults, path)
    assert store.load() == defaults

    payload = {
        "format": "swirengine-game-settings",
        "version": 1,
        "display": {"fullscreen": True},
        "accessibility": {"subtitles": True, "text_scale": 1.5},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = store.load()

    assert loaded.display.width == 1920
    assert loaded.display.height == 1080
    assert loaded.display.fullscreen is True
    assert loaded.display.vsync is False
    assert loaded.accessibility.subtitles is True
    assert loaded.accessibility.text_scale == 1.5


def test_settings_save_is_atomic_shape_and_reset_is_safe(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "settings.json"
    store = SettingsStore(GameSettings(), target)
    current = GameSettings().with_display(width=1600, height=900)
    store.save(current)

    assert store.load() == current
    assert not tuple(target.parent.glob(".*.tmp"))
    store.reset()
    assert store.load() == GameSettings()
    store.reset()


@pytest.mark.parametrize(
    "payload",
    [
        {"format": "wrong", "version": 1},
        {"format": "swirengine-game-settings", "version": 999},
        {
            "format": "swirengine-game-settings",
            "version": 1,
            "display": {"unknown": True},
        },
        {
            "format": "swirengine-game-settings",
            "version": 1,
            "accessibility": {"text_scale": "large"},
        },
    ],
)
def test_settings_reject_unknown_or_malformed_data(payload: dict[str, object]) -> None:
    with pytest.raises(ShippingContractError):
        GameSettings.from_dict(payload)


def test_settings_fingerprints_change_only_with_effective_settings() -> None:
    default = GameSettings()
    same = GameSettings.from_dict(default.to_dict())
    changed = default.with_accessibility(reduced_motion=True)

    assert default.fingerprint == same.fingerprint
    assert default.fingerprint != changed.fingerprint


def test_display_bridge_applies_only_changes_and_reports_unsupported() -> None:
    calls: list[tuple[object, ...]] = []
    previous = DisplaySettings()
    current = DisplaySettings(
        width=1920,
        height=1080,
        fullscreen=True,
        borderless=True,
        vsync=False,
        max_fps=144,
        ui_scale=1.25,
    )

    result = apply_display_settings(
        previous,
        current,
        resize=lambda width, height: calls.append(("resize", width, height)),
        fullscreen=lambda enabled, borderless: calls.append(
            ("fullscreen", enabled, borderless)
        ),
        vsync=lambda enabled: calls.append(("vsync", enabled)),
        ui_scale=lambda scale: calls.append(("ui_scale", scale)),
    )

    assert result.applied == ("resolution", "fullscreen", "vsync", "ui_scale")
    assert result.unsupported == ("max_fps",)
    assert calls == [
        ("resize", 1920, 1080),
        ("fullscreen", True, True),
        ("vsync", False),
        ("ui_scale", 1.25),
    ]

    unchanged = apply_display_settings(current, current)
    assert unchanged.applied == ()
    assert unchanged.unsupported == ()


def test_display_bridge_initial_apply_is_explicit_about_backend_capabilities() -> None:
    result = apply_display_settings(None, DisplaySettings())
    assert result.applied == ()
    assert result.unsupported == (
        "resolution",
        "fullscreen",
        "vsync",
        "max_fps",
        "ui_scale",
    )


def test_focus_router_uses_semantic_keyboard_actions_and_edges() -> None:
    clicked: list[str] = []
    first = FakeButton("first", on_click=lambda _button: clicked.append("first"))
    second = FakeButton("second", on_click=lambda _button: clicked.append("second"))
    focus = UIFocusManager([first, second])
    input_state = FakeInput()
    actions = ProductionActionMap.standard().install(input_state)
    backed: list[bool] = []
    router = FocusActionRouter(focus, actions, on_back=lambda: backed.append(True))

    input_state.keys.add("down")
    update = router.update()
    assert update.moved == 1
    assert update.focused is first
    assert first.focused is True
    assert second.focused is False

    assert router.update().moved == 0
    input_state.keys.clear()
    router.update()
    input_state.keys.add("down")
    assert router.update().focused is second
    assert first.focused is False
    assert second.focused is True

    input_state.keys.clear()
    router.update()
    input_state.keys.add("enter")
    assert router.update().activated is True
    assert clicked == ["second"]

    input_state.keys.clear()
    router.update()
    input_state.keys.add("escape")
    assert router.update().back is True
    assert backed == [True]


def test_focus_router_supports_analog_stick_navigation() -> None:
    first = FakeButton("first")
    second = FakeButton("second")
    focus = UIFocusManager([first, second])
    input_state = FakeInput()
    actions = ProductionActionMap.standard().install(input_state)
    router = FocusActionRouter(focus, actions)

    input_state.axes[(0, "LEFT_Y")] = 0.8
    assert router.update().focused is first
    assert router.update().moved == 0

    input_state.axes[(0, "LEFT_Y")] = 0.0
    router.update()
    input_state.axes[(0, "LEFT_Y")] = 0.8
    assert router.update().focused is second


def test_project_shipping_defaults_fallback_and_template_roundtrip(tmp_path: Path) -> None:
    defaults = ProjectShippingDefaults.load(tmp_path)
    assert defaults.input_source is None
    assert defaults.settings_source is None
    defaults.actions.require_actions(REQUIRED_UI_ACTIONS)

    controls, settings = defaults.write_templates()
    assert controls == tmp_path / "config" / "controls.json"
    assert settings == tmp_path / "config" / "settings.json"

    restored = ProjectShippingDefaults.load(tmp_path)
    assert restored.input_source == controls
    assert restored.settings_source == settings
    assert restored.fingerprint == defaults.fingerprint


def test_project_shipping_templates_refuse_accidental_overwrite(tmp_path: Path) -> None:
    defaults = ProjectShippingDefaults.load(tmp_path)
    defaults.write_templates()
    with pytest.raises(FileExistsError):
        defaults.write_templates()

    defaults.write_templates(overwrite=True)


@pytest.mark.parametrize(
    "value",
    [
        "../outside.json",
        "/absolute/settings.json",
        r"C:\outside\settings.json",
        r"D:/outside/settings.json",
    ],
)
def test_project_shipping_paths_cannot_escape_project_root(
    tmp_path: Path,
    value: str,
) -> None:
    with pytest.raises(ShippingContractError):
        ProjectShippingDefaults.load(tmp_path, input_path=value)


def test_project_shipping_path_rejects_symlink_escape_when_supported(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available in this environment")

    with pytest.raises(ShippingContractError, match="escapes"):
        ProjectShippingDefaults.load(tmp_path, input_path="linked/controls.json")


def test_project_profile_custom_action_survives_project_load(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    profile = ProductionActionMap.standard().replace_action(
        "jump",
        [
            InputBinding("key", "space"),
            InputBinding("gamepad_button", "A"),
        ],
    )
    profile.save(config / "controls.json")
    SettingsStore(GameSettings(), config / "settings.json").save(
        GameSettings().with_accessibility(high_contrast=True)
    )

    defaults = ProjectShippingDefaults.load(tmp_path)
    assert defaults.actions.bindings("jump")
    assert defaults.settings.accessibility.high_contrast is True


def test_binding_count_and_action_count_are_bounded() -> None:
    profile = ProductionActionMap.standard()
    too_many = [InputBinding("key", f"key-{index}") for index in range(9)]
    with pytest.raises(ShippingContractError, match="at most 8"):
        profile.replace_action("custom", too_many, require_ui_navigation=False)

    many = {
        f"action_{index}": (InputBinding("key", "a"),)
        for index in range(129)
    }
    with pytest.raises(ShippingContractError, match="at most 128"):
        ProductionActionMap(many)


def test_malformed_json_has_stable_contract_error(tmp_path: Path) -> None:
    path = tmp_path / "controls.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ShippingContractError, match="invalid production input profile JSON"):
        ProductionActionMap.load(path)
