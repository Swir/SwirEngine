from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path, PureWindowsPath
from types import MappingProxyType
from typing import Any

from .input import (
    InputActions,
    InputBinding,
    normalize_gamepad_axis,
    normalize_gamepad_button,
)
from .ui_navigation import UIFocusManager

_ACTION_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_INPUT_FORMAT = "swirengine-input-profile"
_INPUT_OVERRIDE_FORMAT = "swirengine-input-overrides"
_SETTINGS_FORMAT = "swirengine-game-settings"
_FORMAT_VERSION = 1
_MAX_ACTIONS = 128
_MAX_BINDINGS_PER_ACTION = 8
_MAX_CONFIG_BYTES = 256 * 1024

REQUIRED_UI_ACTIONS = (
    "ui_up",
    "ui_down",
    "ui_left",
    "ui_right",
    "ui_accept",
    "ui_back",
)


class ShippingContractError(ValueError):
    """Raised when production input/settings data is malformed or unsafe."""


@dataclass(slots=True, frozen=True)
class BindingConflict:
    control: str
    actions: tuple[str, ...]


def _portable_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _fingerprint(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_portable_json_bytes(value)).hexdigest()


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> Path:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    if len(encoded) > _MAX_CONFIG_BYTES:
        raise ShippingContractError(
            f"production configuration payload exceeds {_MAX_CONFIG_BYTES} bytes"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ShippingContractError(f"cannot read {label}: {path}") from exc
    if len(raw) > _MAX_CONFIG_BYTES:
        raise ShippingContractError(f"{label} exceeds {_MAX_CONFIG_BYTES} bytes")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShippingContractError(f"invalid {label} JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ShippingContractError(f"{label} root must be a JSON object")
    return value


def _action_name(value: str) -> str:
    name = str(value).strip().lower()
    if not _ACTION_RE.fullmatch(name):
        raise ShippingContractError(
            "action names must start with a letter and use 1-64 lowercase "
            "letters, digits, '.', '_' or '-'"
        )
    return name


def _normalize_binding(binding: InputBinding) -> InputBinding:
    gamepad_id = int(binding.gamepad_id)
    if not 0 <= gamepad_id <= 15:
        raise ShippingContractError("gamepad_id must be between 0 and 15")
    scale = float(binding.scale)
    if not math.isfinite(scale) or abs(scale) > 8.0:
        raise ShippingContractError("binding scale must be finite and between -8.0 and 8.0")
    threshold = float(binding.threshold)
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ShippingContractError("binding threshold must be between 0.0 and 1.0")

    if binding.kind == "key":
        control = str(binding.control).strip().lower()
        if not control or len(control) > 64:
            raise ShippingContractError("key controls must contain 1-64 characters")
        return InputBinding(
            "key",
            control,
            gamepad_id=gamepad_id,
            direction=int(binding.direction),
            threshold=threshold,
            scale=scale,
        )
    if binding.kind == "mouse_button":
        try:
            control = int(binding.control)
        except (TypeError, ValueError) as exc:
            raise ShippingContractError("mouse button controls must be integers") from exc
        if not 0 <= control <= 31:
            raise ShippingContractError("mouse button controls must be between 0 and 31")
        return InputBinding(
            "mouse_button",
            control,
            gamepad_id=gamepad_id,
            direction=int(binding.direction),
            threshold=threshold,
            scale=scale,
        )
    if binding.kind == "gamepad_button":
        try:
            control = normalize_gamepad_button(str(binding.control))
        except ValueError as exc:
            raise ShippingContractError(str(exc)) from exc
        return InputBinding(
            "gamepad_button",
            control,
            gamepad_id=gamepad_id,
            direction=int(binding.direction),
            threshold=threshold,
            scale=scale,
        )
    if binding.kind == "gamepad_axis":
        try:
            control = normalize_gamepad_axis(str(binding.control))
        except ValueError as exc:
            raise ShippingContractError(str(exc)) from exc
        return InputBinding(
            "gamepad_axis",
            control,
            gamepad_id=gamepad_id,
            direction=int(binding.direction),
            threshold=threshold,
            scale=scale,
        )
    raise ShippingContractError(f"unsupported input binding kind: {binding.kind!r}")


def _binding_identity(binding: InputBinding) -> str:
    value = _normalize_binding(binding)
    if value.kind in {"gamepad_button", "gamepad_axis"}:
        return (
            f"{value.kind}:{value.gamepad_id}:{value.control}:"
            f"{value.direction if value.kind == 'gamepad_axis' else 0}"
        )
    return f"{value.kind}:{value.control}"


@dataclass(slots=True, frozen=True)
class ProductionActionMap:
    """Validated project-level semantic action map suitable for shipping.

    The map is deliberately separate from live input state. Creators keep one version-controlled
    project default and may layer user overrides on top without mutating the project files.
    """

    bindings_by_action: Mapping[str, tuple[InputBinding, ...]]

    def __post_init__(self) -> None:
        if len(self.bindings_by_action) > _MAX_ACTIONS:
            raise ShippingContractError(f"action map supports at most {_MAX_ACTIONS} actions")
        normalized: dict[str, tuple[InputBinding, ...]] = {}
        for raw_name, raw_bindings in self.bindings_by_action.items():
            name = _action_name(raw_name)
            bindings = tuple(_normalize_binding(binding) for binding in raw_bindings)
            if len(bindings) > _MAX_BINDINGS_PER_ACTION:
                raise ShippingContractError(
                    f"{name!r} supports at most {_MAX_BINDINGS_PER_ACTION} bindings"
                )
            deduplicated: list[InputBinding] = []
            for binding in bindings:
                if binding not in deduplicated:
                    deduplicated.append(binding)
            normalized[name] = tuple(deduplicated)
        object.__setattr__(
            self,
            "bindings_by_action",
            MappingProxyType(dict(sorted(normalized.items()))),
        )

    @classmethod
    def standard(cls) -> ProductionActionMap:
        return cls(
            {
                "ui_up": (
                    InputBinding("key", "up"),
                    InputBinding("key", "w"),
                    InputBinding("gamepad_button", "DPAD_UP"),
                    InputBinding("gamepad_axis", "LEFT_Y", direction=-1, threshold=0.55),
                ),
                "ui_down": (
                    InputBinding("key", "down"),
                    InputBinding("key", "s"),
                    InputBinding("gamepad_button", "DPAD_DOWN"),
                    InputBinding("gamepad_axis", "LEFT_Y", direction=1, threshold=0.55),
                ),
                "ui_left": (
                    InputBinding("key", "left"),
                    InputBinding("key", "a"),
                    InputBinding("gamepad_button", "DPAD_LEFT"),
                    InputBinding("gamepad_axis", "LEFT_X", direction=-1, threshold=0.55),
                ),
                "ui_right": (
                    InputBinding("key", "right"),
                    InputBinding("key", "d"),
                    InputBinding("gamepad_button", "DPAD_RIGHT"),
                    InputBinding("gamepad_axis", "LEFT_X", direction=1, threshold=0.55),
                ),
                "ui_accept": (
                    InputBinding("key", "enter"),
                    InputBinding("key", "space"),
                    InputBinding("gamepad_button", "A"),
                ),
                "ui_back": (
                    InputBinding("key", "escape"),
                    InputBinding("gamepad_button", "B"),
                ),
                "pause": (
                    InputBinding("key", "escape"),
                    InputBinding("gamepad_button", "START"),
                ),
            }
        )

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        require_ui_navigation: bool = True,
    ) -> ProductionActionMap:
        if data.get("format") != _INPUT_FORMAT:
            raise ShippingContractError("unsupported production input profile format")
        if data.get("version") != _FORMAT_VERSION:
            raise ShippingContractError("unsupported production input profile version")
        actions = data.get("actions")
        if not isinstance(actions, dict):
            raise ShippingContractError("production input profile requires an 'actions' object")
        if len(actions) > _MAX_ACTIONS:
            raise ShippingContractError(f"action map supports at most {_MAX_ACTIONS} actions")
        parsed: dict[str, tuple[InputBinding, ...]] = {}
        for raw_name, raw_bindings in actions.items():
            name = _action_name(str(raw_name))
            if not isinstance(raw_bindings, list):
                raise ShippingContractError(f"bindings for {name!r} must be a list")
            if len(raw_bindings) > _MAX_BINDINGS_PER_ACTION:
                raise ShippingContractError(
                    f"{name!r} supports at most {_MAX_BINDINGS_PER_ACTION} bindings"
                )
            bindings: list[InputBinding] = []
            for item in raw_bindings:
                if not isinstance(item, dict):
                    raise ShippingContractError(f"bindings for {name!r} must be objects")
                try:
                    binding = InputBinding.from_dict(item)
                except (KeyError, TypeError, ValueError) as exc:
                    raise ShippingContractError(f"invalid binding for {name!r}: {exc}") from exc
                bindings.append(_normalize_binding(binding))
            parsed[name] = tuple(bindings)
        profile = cls(parsed)
        if require_ui_navigation:
            profile.require_actions(REQUIRED_UI_ACTIONS)
        return profile

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        require_ui_navigation: bool = True,
    ) -> ProductionActionMap:
        payload = _read_json_object(Path(path), label="production input profile")
        return cls.from_dict(payload, require_ui_navigation=require_ui_navigation)

    def save(self, path: str | Path) -> Path:
        return _atomic_write(Path(path), self.to_dict())

    def actions(self) -> tuple[str, ...]:
        return tuple(self.bindings_by_action)

    def bindings(self, action: str) -> tuple[InputBinding, ...]:
        return self.bindings_by_action.get(_action_name(action), ())

    def require_actions(self, actions: Iterable[str]) -> None:
        missing = [
            name
            for name in (_action_name(action) for action in actions)
            if not self.bindings_by_action.get(name)
        ]
        if missing:
            raise ShippingContractError(
                "required shipping actions have no bindings: " + ", ".join(sorted(missing))
            )

    def replace_action(
        self,
        action: str,
        bindings: Iterable[InputBinding],
        *,
        require_ui_navigation: bool = True,
    ) -> ProductionActionMap:
        name = _action_name(action)
        data = dict(self.bindings_by_action)
        data[name] = tuple(bindings)
        result = ProductionActionMap(data)
        if require_ui_navigation:
            result.require_actions(REQUIRED_UI_ACTIONS)
        return result

    def install(self, input_manager: Any) -> InputActions:
        actions = InputActions(input_manager)
        for name, bindings in self.bindings_by_action.items():
            actions.bind_many(name, bindings, replace=True)
        return actions

    def conflicts(self) -> tuple[BindingConflict, ...]:
        owners: dict[str, set[str]] = {}
        for action, bindings in self.bindings_by_action.items():
            for binding in bindings:
                owners.setdefault(_binding_identity(binding), set()).add(action)
        return tuple(
            BindingConflict(control, tuple(sorted(actions)))
            for control, actions in sorted(owners.items())
            if len(actions) > 1
        )

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": _INPUT_FORMAT,
            "version": _FORMAT_VERSION,
            "actions": {
                name: [
                    {
                        "kind": binding.kind,
                        "control": binding.control,
                        "gamepad_id": binding.gamepad_id,
                        "direction": binding.direction,
                        "threshold": binding.threshold,
                        "scale": binding.scale,
                    }
                    for binding in bindings
                ]
                for name, bindings in self.bindings_by_action.items()
            },
        }


class InputOverrideStore:
    """Persist only user-modified actions so newer project defaults can still flow through."""

    def __init__(self, defaults: ProductionActionMap, path: str | Path) -> None:
        defaults.require_actions(REQUIRED_UI_ACTIONS)
        self.defaults = defaults
        self.path = Path(path)

    def load(self) -> ProductionActionMap:
        if not self.path.exists():
            return self.defaults
        payload = _read_json_object(self.path, label="input override profile")
        if payload.get("format") != _INPUT_OVERRIDE_FORMAT:
            raise ShippingContractError("unsupported input override format")
        if payload.get("version") != _FORMAT_VERSION:
            raise ShippingContractError("unsupported input override version")
        actions = payload.get("actions")
        if not isinstance(actions, dict):
            raise ShippingContractError("input override profile requires an 'actions' object")
        if len(actions) > _MAX_ACTIONS:
            raise ShippingContractError(f"input overrides support at most {_MAX_ACTIONS} actions")
        current = self.defaults
        for name, raw_bindings in sorted(actions.items()):
            if not isinstance(raw_bindings, list):
                raise ShippingContractError(f"bindings for {name!r} must be a list")
            parsed: list[InputBinding] = []
            for item in raw_bindings:
                if not isinstance(item, dict):
                    raise ShippingContractError(f"bindings for {name!r} must be objects")
                try:
                    parsed.append(_normalize_binding(InputBinding.from_dict(item)))
                except (KeyError, TypeError, ValueError) as exc:
                    raise ShippingContractError(f"invalid override binding for {name!r}") from exc
            current = current.replace_action(name, parsed, require_ui_navigation=False)
        current.require_actions(REQUIRED_UI_ACTIONS)
        return current

    def save(self, current: ProductionActionMap) -> Path:
        current.require_actions(REQUIRED_UI_ACTIONS)
        changed: dict[str, list[dict[str, Any]]] = {}
        names = sorted(set(self.defaults.actions()) | set(current.actions()))
        for name in names:
            defaults = self.defaults.bindings(name)
            bindings = current.bindings(name)
            if bindings == defaults:
                continue
            changed[name] = [
                {
                    "kind": binding.kind,
                    "control": binding.control,
                    "gamepad_id": binding.gamepad_id,
                    "direction": binding.direction,
                    "threshold": binding.threshold,
                    "scale": binding.scale,
                }
                for binding in bindings
            ]
        payload = {
            "format": _INPUT_OVERRIDE_FORMAT,
            "version": _FORMAT_VERSION,
            "actions": changed,
        }
        return _atomic_write(self.path, payload)

    def reset(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


@dataclass(slots=True, frozen=True)
class DisplaySettings:
    width: int = 1280
    height: int = 720
    fullscreen: bool = False
    borderless: bool = False
    vsync: bool = True
    max_fps: int = 0
    ui_scale: float = 1.0

    def __post_init__(self) -> None:
        if not 320 <= int(self.width) <= 16384:
            raise ShippingContractError("display width must be between 320 and 16384")
        if not 240 <= int(self.height) <= 8640:
            raise ShippingContractError("display height must be between 240 and 8640")
        if bool(self.borderless) and not bool(self.fullscreen):
            raise ShippingContractError("borderless display mode requires fullscreen=true")
        if not 0 <= int(self.max_fps) <= 1000:
            raise ShippingContractError("max_fps must be between 0 and 1000")
        if not math.isfinite(float(self.ui_scale)) or not 0.5 <= float(self.ui_scale) <= 3.0:
            raise ShippingContractError("ui_scale must be between 0.5 and 3.0")

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        fallback: DisplaySettings | None = None,
    ) -> DisplaySettings:
        base = fallback or cls()
        allowed = {
            "width",
            "height",
            "fullscreen",
            "borderless",
            "vsync",
            "max_fps",
            "ui_scale",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ShippingContractError("unknown display settings: " + ", ".join(unknown))
        return cls(
            width=_strict_int(value.get("width", base.width), "display.width"),
            height=_strict_int(value.get("height", base.height), "display.height"),
            fullscreen=_strict_bool(
                value.get("fullscreen", base.fullscreen), "display.fullscreen"
            ),
            borderless=_strict_bool(
                value.get("borderless", base.borderless), "display.borderless"
            ),
            vsync=_strict_bool(value.get("vsync", base.vsync), "display.vsync"),
            max_fps=_strict_int(value.get("max_fps", base.max_fps), "display.max_fps"),
            ui_scale=_strict_float(value.get("ui_scale", base.ui_scale), "display.ui_scale"),
        )


@dataclass(slots=True, frozen=True)
class AccessibilitySettings:
    text_scale: float = 1.0
    reduced_motion: bool = False
    high_contrast: bool = False
    subtitles: bool = True
    hold_to_confirm: bool = False

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.text_scale)) or not 0.75 <= float(self.text_scale) <= 2.5:
            raise ShippingContractError("text_scale must be between 0.75 and 2.5")

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        fallback: AccessibilitySettings | None = None,
    ) -> AccessibilitySettings:
        base = fallback or cls()
        allowed = {
            "text_scale",
            "reduced_motion",
            "high_contrast",
            "subtitles",
            "hold_to_confirm",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ShippingContractError("unknown accessibility settings: " + ", ".join(unknown))
        return cls(
            text_scale=_strict_float(
                value.get("text_scale", base.text_scale), "accessibility.text_scale"
            ),
            reduced_motion=_strict_bool(
                value.get("reduced_motion", base.reduced_motion),
                "accessibility.reduced_motion",
            ),
            high_contrast=_strict_bool(
                value.get("high_contrast", base.high_contrast),
                "accessibility.high_contrast",
            ),
            subtitles=_strict_bool(
                value.get("subtitles", base.subtitles), "accessibility.subtitles"
            ),
            hold_to_confirm=_strict_bool(
                value.get("hold_to_confirm", base.hold_to_confirm),
                "accessibility.hold_to_confirm",
            ),
        )


@dataclass(slots=True, frozen=True)
class GameSettings:
    display: DisplaySettings = DisplaySettings()
    accessibility: AccessibilitySettings = AccessibilitySettings()

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        fallback: GameSettings | None = None,
        require_envelope: bool = True,
    ) -> GameSettings:
        base = fallback or cls()
        if require_envelope:
            if data.get("format") != _SETTINGS_FORMAT:
                raise ShippingContractError("unsupported game settings format")
            if data.get("version") != _FORMAT_VERSION:
                raise ShippingContractError("unsupported game settings version")
        allowed = {"format", "version", "display", "accessibility"}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ShippingContractError("unknown game settings sections: " + ", ".join(unknown))
        display = data.get("display", {})
        accessibility = data.get("accessibility", {})
        if not isinstance(display, dict):
            raise ShippingContractError("display settings must be an object")
        if not isinstance(accessibility, dict):
            raise ShippingContractError("accessibility settings must be an object")
        return cls(
            display=DisplaySettings.from_dict(display, fallback=base.display),
            accessibility=AccessibilitySettings.from_dict(
                accessibility,
                fallback=base.accessibility,
            ),
        )

    def with_display(self, **changes: Any) -> GameSettings:
        return replace(self, display=replace(self.display, **changes))

    def with_accessibility(self, **changes: Any) -> GameSettings:
        return replace(self, accessibility=replace(self.accessibility, **changes))

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": _SETTINGS_FORMAT,
            "version": _FORMAT_VERSION,
            "display": {
                "width": self.display.width,
                "height": self.display.height,
                "fullscreen": self.display.fullscreen,
                "borderless": self.display.borderless,
                "vsync": self.display.vsync,
                "max_fps": self.display.max_fps,
                "ui_scale": self.display.ui_scale,
            },
            "accessibility": {
                "text_scale": self.accessibility.text_scale,
                "reduced_motion": self.accessibility.reduced_motion,
                "high_contrast": self.accessibility.high_contrast,
                "subtitles": self.accessibility.subtitles,
                "hold_to_confirm": self.accessibility.hold_to_confirm,
            },
        }


class SettingsStore:
    """Atomic, validated game settings persistence with project defaults as fallback."""

    def __init__(self, defaults: GameSettings, path: str | Path) -> None:
        self.defaults = defaults
        self.path = Path(path)

    def load(self) -> GameSettings:
        if not self.path.exists():
            return self.defaults
        payload = _read_json_object(self.path, label="game settings")
        return GameSettings.from_dict(payload, fallback=self.defaults)

    def save(self, settings: GameSettings) -> Path:
        return _atomic_write(self.path, settings.to_dict())

    def reset(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


@dataclass(slots=True, frozen=True)
class ProjectShippingDefaults:
    root: Path
    actions: ProductionActionMap
    settings: GameSettings
    input_source: Path | None
    settings_source: Path | None

    @classmethod
    def load(
        cls,
        project_root: str | Path,
        *,
        input_path: str = "config/controls.json",
        settings_path: str = "config/settings.json",
    ) -> ProjectShippingDefaults:
        root = Path(project_root).expanduser().resolve()
        input_source = _project_file(root, input_path)
        settings_source = _project_file(root, settings_path)
        actions = (
            ProductionActionMap.load(input_source)
            if input_source.is_file()
            else ProductionActionMap.standard()
        )
        if settings_source.is_file():
            settings_payload = _read_json_object(settings_source, label="project settings defaults")
            settings = GameSettings.from_dict(settings_payload)
        else:
            settings = GameSettings()
        return cls(
            root=root,
            actions=actions,
            settings=settings,
            input_source=input_source if input_source.is_file() else None,
            settings_source=settings_source if settings_source.is_file() else None,
        )

    def write_templates(
        self,
        *,
        input_path: str = "config/controls.json",
        settings_path: str = "config/settings.json",
        overwrite: bool = False,
    ) -> tuple[Path, Path]:
        input_target = _project_file(self.root, input_path)
        settings_target = _project_file(self.root, settings_path)
        for target in (input_target, settings_target):
            if target.exists() and not overwrite:
                raise FileExistsError(target)
        self.actions.save(input_target)
        _atomic_write(settings_target, self.settings.to_dict())
        return input_target, settings_target

    @property
    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "actions": self.actions.to_dict(),
                "settings": self.settings.to_dict(),
            }
        )


@dataclass(slots=True, frozen=True)
class DisplayApplyResult:
    applied: tuple[str, ...]
    unsupported: tuple[str, ...]


def apply_display_settings(
    previous: DisplaySettings | None,
    current: DisplaySettings,
    *,
    resize: Callable[[int, int], None] | None = None,
    fullscreen: Callable[[bool, bool], None] | None = None,
    vsync: Callable[[bool], None] | None = None,
    frame_limit: Callable[[int], None] | None = None,
    ui_scale: Callable[[float], None] | None = None,
) -> DisplayApplyResult:
    """Apply changed display values through creator/backend callbacks.

    Missing callbacks are reported rather than guessed, keeping the contract portable across
    render/window backends. ``previous=None`` applies every value for initial startup.
    """

    changed = {
        "resolution": previous is None
        or (previous.width, previous.height) != (current.width, current.height),
        "fullscreen": previous is None
        or (previous.fullscreen, previous.borderless)
        != (current.fullscreen, current.borderless),
        "vsync": previous is None or previous.vsync != current.vsync,
        "max_fps": previous is None or previous.max_fps != current.max_fps,
        "ui_scale": previous is None or previous.ui_scale != current.ui_scale,
    }
    callbacks: dict[str, tuple[Callable[..., None] | None, tuple[Any, ...]]] = {
        "resolution": (resize, (current.width, current.height)),
        "fullscreen": (fullscreen, (current.fullscreen, current.borderless)),
        "vsync": (vsync, (current.vsync,)),
        "max_fps": (frame_limit, (current.max_fps,)),
        "ui_scale": (ui_scale, (current.ui_scale,)),
    }
    applied: list[str] = []
    unsupported: list[str] = []
    for name in ("resolution", "fullscreen", "vsync", "max_fps", "ui_scale"):
        if not changed[name]:
            continue
        callback, arguments = callbacks[name]
        if callback is None:
            unsupported.append(name)
            continue
        callback(*arguments)
        applied.append(name)
    return DisplayApplyResult(tuple(applied), tuple(unsupported))


@dataclass(slots=True, frozen=True)
class NavigationUpdate:
    focused: Any | None
    moved: int = 0
    activated: bool = False
    back: bool = False


class FocusActionRouter:
    """Drive ``UIFocusManager`` from semantic actions, including analog bindings.

    The router edge-detects action *state* rather than relying on digital key events, allowing
    keyboard, d-pad and stick bindings to share the same shipping menu contract.
    """

    def __init__(
        self,
        focus: UIFocusManager,
        actions: InputActions,
        *,
        on_back: Callable[[], None] | None = None,
    ) -> None:
        self.focus = focus
        self.actions = actions
        self.on_back = on_back
        self._held: set[str] = set()

    def _pressed(self, name: str) -> bool:
        down = bool(self.actions.down(name))
        was_down = name in self._held
        if down:
            self._held.add(name)
        else:
            self._held.discard(name)
        return down and not was_down

    def update(self) -> NavigationUpdate:
        down = self._pressed("ui_down")
        right = self._pressed("ui_right")
        up = self._pressed("ui_up")
        left = self._pressed("ui_left")
        accept = self._pressed("ui_accept")
        back = self._pressed("ui_back")
        forward = down or right
        backward = up or left

        moved = 0
        if forward:
            self.focus.move(1)
            moved = 1
        elif backward:
            self.focus.move(-1)
            moved = -1

        activated = bool(self.focus.activate()) if accept else False
        if back and self.on_back is not None:
            self.on_back()
        return NavigationUpdate(
            focused=self.focus.focused,
            moved=moved,
            activated=activated,
            back=back,
        )


def _project_file(root: Path, relative: str) -> Path:
    value = str(relative).replace("\\", "/")
    candidate = Path(value)
    windows_candidate = PureWindowsPath(value)
    if (
        candidate.is_absolute()
        or windows_candidate.is_absolute()
        or windows_candidate.drive
        or not value
        or "\x00" in value
    ):
        raise ShippingContractError("project configuration path must be relative and non-empty")
    root_resolved = root.resolve()
    resolved = (root_resolved / candidate).resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ShippingContractError("project configuration path escapes the project root") from exc
    return resolved


def _strict_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ShippingContractError(f"{label} must be a boolean")
    return value


def _strict_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ShippingContractError(f"{label} must be an integer")
    return value


def _strict_float(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ShippingContractError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ShippingContractError(f"{label} must be finite")
    return result


__all__ = [
    "AccessibilitySettings",
    "BindingConflict",
    "DisplayApplyResult",
    "DisplaySettings",
    "FocusActionRouter",
    "GameSettings",
    "InputOverrideStore",
    "NavigationUpdate",
    "ProductionActionMap",
    "ProjectShippingDefaults",
    "REQUIRED_UI_ACTIONS",
    "SettingsStore",
    "ShippingContractError",
    "apply_display_settings",
]
