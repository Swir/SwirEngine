from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import pairwise
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .animation15 import AnimationClip, AnimationKeyframe, AnimationTrack, InterpolationMode
from .core.scene import Scene
from .math.types import Color
from .ui15 import (
    UIAlign,
    UIAxis,
    UIInsets,
    UIJustify,
    UITheme,
    UIToolkit,
    UIToolkitDiagnostics,
    UIWidget,
    UIWidgetKind,
    UIWidgetStyle,
)
from .ui_layout import UIAnchor

UI_DESIGN_FORMAT_22 = "swirengine.ui-designer"
UI_DESIGN_VERSION_22 = 1
DEFAULT_UI_DESIGN_PATH_22 = "config/ui-designer.json"

MAX_UI_DESIGN_BYTES_22 = 524_288
MAX_UI_DESIGN_WIDGETS_22 = 1_024
MAX_UI_DESIGN_STYLES_22 = 128
MAX_UI_DESIGN_ANIMATIONS_22 = 128
MAX_UI_ANIMATION_TRACKS_22 = 64
MAX_UI_ANIMATION_KEYFRAMES_22 = 256
MAX_UI_ANIMATION_TOTAL_KEYFRAMES_22 = 8_192
MAX_UI_DESIGN_DEPTH_22 = 32

_COLOR_FIELDS = (
    "panel",
    "text",
    "button",
    "button_hover",
    "button_pressed",
    "button_focused",
    "progress_background",
    "progress_fill",
)
_ANIMATABLE_PROPERTIES = {"offset_x", "offset_y", "width", "height", "opacity", "value"}


class EditorUIDesignerError22(ValueError):
    """Invalid, unsafe or unsupported UI Designer 2.2 authoring data."""


def _number(value: object, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EditorUIDesignerError22(f"{label} must be a number")
    try:
        result = float(value)
    except OverflowError as exc:
        raise EditorUIDesignerError22(f"{label} is outside numeric range") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise EditorUIDesignerError22(
            f"{label} must be finite and in [{low:g}, {high:g}]"
        )
    return result


def _integer(value: object, label: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EditorUIDesignerError22(f"{label} must be an integer")
    if not low <= value <= high:
        raise EditorUIDesignerError22(f"{label} must be in [{low}, {high}]")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise EditorUIDesignerError22(f"{label} must be a boolean")
    return value


def _label(value: object, label: str, *, maximum: int = 128) -> str:
    if not isinstance(value, str):
        raise EditorUIDesignerError22(f"{label} must be a string")
    clean = value.strip()
    if (
        not clean
        or len(clean) > maximum
        or any(ord(character) < 32 for character in clean)
        or "\x00" in clean
    ):
        raise EditorUIDesignerError22(
            f"{label} must be a portable 1-{maximum} character label"
        )
    return clean


def _identifier(value: object, label: str) -> str:
    clean = _label(value, label)
    if clean == UIToolkit.ROOT_ID or "/" in clean or "\\" in clean:
        raise EditorUIDesignerError22(f"{label} is reserved or not portable")
    return clean


def _optional_identifier(value: object, label: str) -> str | None:
    return None if value is None else _identifier(value, label)


def _color(value: object, label: str) -> tuple[float, float, float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        raise EditorUIDesignerError22(f"{label} must contain four color channels")
    return tuple(_number(channel, label, 0.0, 1.0) for channel in value)  # type: ignore[return-value]


def _optional_color(value: object, label: str) -> tuple[float, float, float, float] | None:
    return None if value is None else _color(value, label)


def _padding(value: object) -> tuple[float, float, float, float]:
    if isinstance(value, bool):
        raise EditorUIDesignerError22("widget padding must be a number or four numbers")
    if isinstance(value, (int, float)):
        item = _number(value, "widget padding", 0.0, 1_000_000.0)
        return (item, item, item, item)
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        raise EditorUIDesignerError22("widget padding must contain four numbers")
    return tuple(
        _number(item, "widget padding", 0.0, 1_000_000.0) for item in value
    )  # type: ignore[return-value]


def _expect_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EditorUIDesignerError22(f"{label} must be an object")
    return value


def _fields(
    value: object,
    *,
    allowed: set[str],
    required: set[str] = frozenset(),
    label: str,
) -> dict[str, Any]:
    result = _expect_object(value, label)
    unknown = set(result) - allowed
    missing = required - set(result)
    if unknown:
        raise EditorUIDesignerError22(
            f"{label} has unknown fields: {', '.join(sorted(unknown))}"
        )
    if missing:
        raise EditorUIDesignerError22(
            f"{label} is missing fields: {', '.join(sorted(missing))}"
        )
    return result


def _list(value: object, label: str, maximum: int) -> list[Any]:
    if not isinstance(value, list) or len(value) > maximum:
        raise EditorUIDesignerError22(f"{label} must be a list with at most {maximum} entries")
    return value


def _enum_value(enum_type: type[Any], value: object, label: str) -> str:
    if not isinstance(value, str):
        raise EditorUIDesignerError22(f"{label} must be a string")
    try:
        return str(enum_type(value).value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise EditorUIDesignerError22(f"{label} must be one of: {allowed}") from exc


def _relative_path(value: str | Path) -> str:
    if not isinstance(value, (str, Path)):
        raise EditorUIDesignerError22("UI design path must be a string or Path")
    raw = str(value).strip().replace("\\", "/")
    posix = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    if (
        not raw
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or any(part in {"", ".", ".."} for part in posix.parts)
        or any(ord(character) < 32 for character in raw)
        or ":" in raw
    ):
        raise EditorUIDesignerError22("UI design path must stay project-relative")
    return posix.as_posix()


def _contained(root: Path, relative: str) -> Path:
    try:
        target = (root / PurePosixPath(relative)).resolve()
        target.relative_to(root)
    except (ValueError, OSError, RuntimeError) as exc:
        raise EditorUIDesignerError22(
            f"UI design path {relative!r} resolves outside the project"
        ) from exc
    return target


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EditorUIDesignerError22(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise EditorUIDesignerError22(f"non-finite JSON number {value!r} is not supported")


def _serialize(value: object, *, pretty: bool) -> str:
    options: dict[str, Any] = {
        "sort_keys": True,
        "allow_nan": False,
        "ensure_ascii": True,
    }
    if pretty:
        options["indent"] = 2
    else:
        options["separators"] = (",", ":")
    return json.dumps(value, **options) + ("\n" if pretty else "")


@dataclass(frozen=True, slots=True)
class UIThemeSpec22:
    panel: tuple[float, float, float, float] = (0.07, 0.09, 0.14, 0.96)
    text: tuple[float, float, float, float] = (0.96, 0.97, 1.0, 1.0)
    button: tuple[float, float, float, float] = (0.12, 0.19, 0.31, 1.0)
    button_hover: tuple[float, float, float, float] = (0.18, 0.31, 0.50, 1.0)
    button_pressed: tuple[float, float, float, float] = (0.08, 0.14, 0.25, 1.0)
    button_focused: tuple[float, float, float, float] = (0.22, 0.44, 0.75, 1.0)
    progress_background: tuple[float, float, float, float] = (0.09, 0.11, 0.16, 1.0)
    progress_fill: tuple[float, float, float, float] = (0.22, 0.74, 0.48, 1.0)

    def __post_init__(self) -> None:
        for name in _COLOR_FIELDS:
            object.__setattr__(self, name, _color(getattr(self, name), f"theme {name}"))

    def to_dict(self) -> dict[str, Any]:
        return {name: list(getattr(self, name)) for name in _COLOR_FIELDS}

    @classmethod
    def from_dict(cls, value: object) -> UIThemeSpec22:
        fields = _fields(value, allowed=set(_COLOR_FIELDS), label="UI theme")
        return cls(**fields)

    def runtime(self) -> UITheme:
        return UITheme(**{name: Color(*getattr(self, name)) for name in _COLOR_FIELDS})


@dataclass(frozen=True, slots=True)
class UIStyleSpec22:
    name: str
    panel: tuple[float, float, float, float] | None = None
    text: tuple[float, float, float, float] | None = None
    button: tuple[float, float, float, float] | None = None
    button_hover: tuple[float, float, float, float] | None = None
    button_pressed: tuple[float, float, float, float] | None = None
    button_focused: tuple[float, float, float, float] | None = None
    progress_background: tuple[float, float, float, float] | None = None
    progress_fill: tuple[float, float, float, float] | None = None
    font_size: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _identifier(self.name, "style name"))
        for name in _COLOR_FIELDS:
            object.__setattr__(
                self,
                name,
                _optional_color(getattr(self, name), f"style {self.name} {name}"),
            )
        if self.font_size is not None:
            object.__setattr__(
                self,
                "font_size",
                _number(self.font_size, "style font_size", 1.0, 512.0),
            )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name}
        for name in _COLOR_FIELDS:
            color = getattr(self, name)
            result[name] = None if color is None else list(color)
        result["font_size"] = self.font_size
        return result

    @classmethod
    def from_dict(cls, value: object) -> UIStyleSpec22:
        allowed = {"name", "font_size", *_COLOR_FIELDS}
        fields = _fields(value, allowed=allowed, required={"name"}, label="UI style")
        return cls(**fields)

    def runtime(self) -> UIWidgetStyle:
        values = {
            name: None if getattr(self, name) is None else Color(*getattr(self, name))
            for name in _COLOR_FIELDS
        }
        return UIWidgetStyle(**values, font_size=self.font_size)


@dataclass(frozen=True, slots=True)
class UIWidgetSpec22:
    id: str
    kind: str
    parent: str | None = None
    order: int = 0
    width: float = 100.0
    height: float = 40.0
    text: str = ""
    value: float = 0.0
    axis: str = UIAxis.VERTICAL.value
    gap: float = 12.0
    padding: tuple[float, float, float, float] | float = (0.0, 0.0, 0.0, 0.0)
    align: str = UIAlign.CENTER.value
    justify: str = UIJustify.CENTER.value
    anchor: str | None = None
    offset_x: float = 0.0
    offset_y: float = 0.0
    visible: bool = True
    enabled: bool = True
    focusable: bool | None = None
    opacity: float = 1.0
    style: str | None = None
    action: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _identifier(self.id, "widget id"))
        object.__setattr__(self, "kind", _enum_value(UIWidgetKind, self.kind, "widget kind"))
        object.__setattr__(self, "parent", _optional_identifier(self.parent, "widget parent"))
        object.__setattr__(self, "order", _integer(self.order, "widget order", -2**31, 2**31 - 1))
        object.__setattr__(self, "width", _number(self.width, "widget width", 0.001, 1_000_000.0))
        object.__setattr__(self, "height", _number(self.height, "widget height", 0.001, 1_000_000.0))
        if not isinstance(self.text, str) or len(self.text) > 16_384 or "\x00" in self.text:
            raise EditorUIDesignerError22("widget text must be a string of at most 16384 characters")
        object.__setattr__(self, "value", _number(self.value, "widget value", 0.0, 1.0))
        object.__setattr__(self, "axis", _enum_value(UIAxis, self.axis, "widget axis"))
        object.__setattr__(self, "gap", _number(self.gap, "widget gap", 0.0, 1_000_000.0))
        object.__setattr__(self, "padding", _padding(self.padding))
        object.__setattr__(self, "align", _enum_value(UIAlign, self.align, "widget align"))
        object.__setattr__(self, "justify", _enum_value(UIJustify, self.justify, "widget justify"))
        if self.anchor is not None:
            object.__setattr__(self, "anchor", _enum_value(UIAnchor, self.anchor, "widget anchor"))
        object.__setattr__(self, "offset_x", _number(self.offset_x, "widget offset_x", -1_000_000.0, 1_000_000.0))
        object.__setattr__(self, "offset_y", _number(self.offset_y, "widget offset_y", -1_000_000.0, 1_000_000.0))
        _boolean(self.visible, "widget visible")
        _boolean(self.enabled, "widget enabled")
        if self.focusable is not None:
            _boolean(self.focusable, "widget focusable")
        object.__setattr__(self, "opacity", _number(self.opacity, "widget opacity", 0.0, 1.0))
        object.__setattr__(self, "style", _optional_identifier(self.style, "widget style"))
        object.__setattr__(
            self,
            "action",
            None if self.action is None else _label(self.action, "widget action", maximum=256),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "align": self.align,
            "anchor": self.anchor,
            "axis": self.axis,
            "enabled": self.enabled,
            "focusable": self.focusable,
            "gap": self.gap,
            "height": self.height,
            "id": self.id,
            "justify": self.justify,
            "kind": self.kind,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "opacity": self.opacity,
            "order": self.order,
            "padding": list(self.padding),
            "parent": self.parent,
            "style": self.style,
            "text": self.text,
            "value": self.value,
            "visible": self.visible,
            "width": self.width,
        }

    @classmethod
    def from_dict(cls, value: object) -> UIWidgetSpec22:
        allowed = {
            "action", "align", "anchor", "axis", "enabled", "focusable", "gap",
            "height", "id", "justify", "kind", "offset_x", "offset_y", "opacity",
            "order", "padding", "parent", "style", "text", "value", "visible", "width",
        }
        fields = _fields(value, allowed=allowed, required={"id", "kind"}, label="UI widget")
        return cls(**fields)


@dataclass(frozen=True, slots=True)
class UIAnimationKeyframeSpec22:
    time: float
    value: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "time", _number(self.time, "keyframe time", 0.0, 86_400.0))
        object.__setattr__(self, "value", _number(self.value, "keyframe value", -1_000_000.0, 1_000_000.0))

    def to_dict(self) -> dict[str, float]:
        return {"time": self.time, "value": self.value}

    @classmethod
    def from_dict(cls, value: object) -> UIAnimationKeyframeSpec22:
        fields = _fields(
            value,
            allowed={"time", "value"},
            required={"time", "value"},
            label="UI animation keyframe",
        )
        return cls(**fields)


@dataclass(frozen=True, slots=True)
class UIAnimationTrackSpec22:
    widget_id: str
    property: str
    keyframes: tuple[UIAnimationKeyframeSpec22, ...]
    interpolation: str = InterpolationMode.LINEAR.value

    def __post_init__(self) -> None:
        object.__setattr__(self, "widget_id", _identifier(self.widget_id, "track widget_id"))
        if not isinstance(self.property, str) or self.property not in _ANIMATABLE_PROPERTIES:
            raise EditorUIDesignerError22(
                "track property must be one of: " + ", ".join(sorted(_ANIMATABLE_PROPERTIES))
            )
        if not isinstance(self.keyframes, (tuple, list)):
            raise EditorUIDesignerError22("track keyframes must be a tuple or list")
        keyframes = tuple(self.keyframes)
        if not 1 <= len(keyframes) <= MAX_UI_ANIMATION_KEYFRAMES_22:
            raise EditorUIDesignerError22(
                f"track must contain 1-{MAX_UI_ANIMATION_KEYFRAMES_22} keyframes"
            )
        if not all(isinstance(item, UIAnimationKeyframeSpec22) for item in keyframes):
            raise EditorUIDesignerError22("track keyframes must be UIAnimationKeyframeSpec22 values")
        if any(right.time <= left.time for left, right in pairwise(keyframes)):
            raise EditorUIDesignerError22("track keyframe times must be strictly increasing")
        if self.property in {"opacity", "value"} and any(
            not 0.0 <= item.value <= 1.0 for item in keyframes
        ):
            raise EditorUIDesignerError22(f"{self.property} keyframes must stay within 0..1")
        if self.property in {"width", "height"} and any(item.value <= 0.0 for item in keyframes):
            raise EditorUIDesignerError22(f"{self.property} keyframes must be greater than zero")
        object.__setattr__(self, "keyframes", keyframes)
        object.__setattr__(
            self,
            "interpolation",
            _enum_value(InterpolationMode, self.interpolation, "track interpolation"),
        )

    @property
    def binding(self) -> str:
        return f"{self.widget_id}.{self.property}"

    @property
    def target(self) -> str:
        return self.widget_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "interpolation": self.interpolation,
            "keyframes": [item.to_dict() for item in self.keyframes],
            "property": self.property,
            "widget_id": self.widget_id,
        }

    @classmethod
    def from_dict(cls, value: object) -> UIAnimationTrackSpec22:
        fields = _fields(
            value,
            allowed={"widget_id", "target", "property", "keyframes", "interpolation"},
            required={"property", "keyframes"},
            label="UI animation track",
        )
        if "widget_id" in fields and "target" in fields:
            raise EditorUIDesignerError22("track cannot contain both widget_id and target")
        widget_id = fields.get("widget_id", fields.get("target"))
        if widget_id is None:
            raise EditorUIDesignerError22("UI animation track is missing widget_id")
        keyframes = _list(fields["keyframes"], "track keyframes", MAX_UI_ANIMATION_KEYFRAMES_22)
        return cls(
            widget_id=widget_id,
            property=fields["property"],
            keyframes=tuple(UIAnimationKeyframeSpec22.from_dict(item) for item in keyframes),
            interpolation=fields.get("interpolation", InterpolationMode.LINEAR.value),
        )

    def runtime(self) -> AnimationTrack:
        return AnimationTrack(
            self.binding,
            tuple(AnimationKeyframe(item.time, item.value) for item in self.keyframes),
            self.interpolation,
        )


@dataclass(frozen=True, slots=True)
class UIAnimationSpec22:
    name: str
    duration: float
    tracks: tuple[UIAnimationTrackSpec22, ...]
    loop: bool = False
    autoplay: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _identifier(self.name, "animation name"))
        object.__setattr__(self, "duration", _number(self.duration, "animation duration", 0.001, 86_400.0))
        if not isinstance(self.tracks, (tuple, list)):
            raise EditorUIDesignerError22("animation tracks must be a tuple or list")
        tracks = tuple(self.tracks)
        if not 1 <= len(tracks) <= MAX_UI_ANIMATION_TRACKS_22:
            raise EditorUIDesignerError22(
                f"animation must contain 1-{MAX_UI_ANIMATION_TRACKS_22} tracks"
            )
        if not all(isinstance(item, UIAnimationTrackSpec22) for item in tracks):
            raise EditorUIDesignerError22("animation tracks must be UIAnimationTrackSpec22 values")
        tracks = tuple(sorted(tracks, key=lambda item: (item.widget_id, item.property)))
        bindings = tuple(item.binding for item in tracks)
        if len(set(bindings)) != len(bindings):
            raise EditorUIDesignerError22("animation contains duplicate widget property tracks")
        if any(item.keyframes[-1].time > self.duration for item in tracks):
            raise EditorUIDesignerError22("animation keyframes must not exceed duration")
        _boolean(self.loop, "animation loop")
        _boolean(self.autoplay, "animation autoplay")
        object.__setattr__(self, "tracks", tracks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "autoplay": self.autoplay,
            "duration": self.duration,
            "loop": self.loop,
            "name": self.name,
            "tracks": [item.to_dict() for item in self.tracks],
        }

    @classmethod
    def from_dict(cls, value: object) -> UIAnimationSpec22:
        fields = _fields(
            value,
            allowed={"name", "duration", "tracks", "loop", "autoplay"},
            required={"name", "duration", "tracks"},
            label="UI animation",
        )
        tracks = _list(fields["tracks"], "animation tracks", MAX_UI_ANIMATION_TRACKS_22)
        return cls(
            name=fields["name"],
            duration=fields["duration"],
            tracks=tuple(UIAnimationTrackSpec22.from_dict(item) for item in tracks),
            loop=fields.get("loop", False),
            autoplay=fields.get("autoplay", False),
        )

    def runtime(self) -> AnimationClip:
        return AnimationClip(self.name, self.duration, tuple(item.runtime() for item in self.tracks))


@dataclass(frozen=True, slots=True)
class UIDesignAsset22:
    reference_width: float = 1280.0
    reference_height: float = 720.0
    min_scale: float = 0.5
    max_scale: float = 2.0
    theme: UIThemeSpec22 = field(default_factory=UIThemeSpec22)
    styles: tuple[UIStyleSpec22, ...] = ()
    widgets: tuple[UIWidgetSpec22, ...] = ()
    animations: tuple[UIAnimationSpec22, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reference_width",
            _number(self.reference_width, "reference_width", 1.0, 1_000_000.0),
        )
        object.__setattr__(
            self,
            "reference_height",
            _number(self.reference_height, "reference_height", 1.0, 1_000_000.0),
        )
        object.__setattr__(self, "min_scale", _number(self.min_scale, "min_scale", 0.001, 1_000.0))
        object.__setattr__(self, "max_scale", _number(self.max_scale, "max_scale", 0.001, 1_000.0))
        if self.min_scale > self.max_scale:
            raise EditorUIDesignerError22("min_scale must not exceed max_scale")
        if not isinstance(self.theme, UIThemeSpec22):
            raise EditorUIDesignerError22("theme must be a UIThemeSpec22")
        styles = self._spec_tuple(self.styles, UIStyleSpec22, MAX_UI_DESIGN_STYLES_22, "styles")
        widgets = self._spec_tuple(self.widgets, UIWidgetSpec22, MAX_UI_DESIGN_WIDGETS_22, "widgets")
        animations = self._spec_tuple(
            self.animations,
            UIAnimationSpec22,
            MAX_UI_DESIGN_ANIMATIONS_22,
            "animations",
        )
        styles = tuple(sorted(styles, key=lambda item: item.name))
        widgets = tuple(sorted(widgets, key=lambda item: item.id))
        animations = tuple(sorted(animations, key=lambda item: item.name))
        self._unique(styles, "name", "style name")
        self._unique(widgets, "id", "widget id")
        self._unique(animations, "name", "animation name")
        self._validate_hierarchy(widgets, styles)
        widget_ids = {item.id for item in widgets}
        total_keyframes = 0
        for animation in animations:
            for track in animation.tracks:
                if track.widget_id not in widget_ids:
                    raise EditorUIDesignerError22(
                        f"animation {animation.name!r} targets unknown widget {track.widget_id!r}"
                    )
                total_keyframes += len(track.keyframes)
        if total_keyframes > MAX_UI_ANIMATION_TOTAL_KEYFRAMES_22:
            raise EditorUIDesignerError22(
                f"UI design exceeds {MAX_UI_ANIMATION_TOTAL_KEYFRAMES_22} total keyframes"
            )
        if sum(item.autoplay for item in animations) > 1:
            raise EditorUIDesignerError22("UI design may contain at most one autoplay animation")
        object.__setattr__(self, "styles", styles)
        object.__setattr__(self, "widgets", widgets)
        object.__setattr__(self, "animations", animations)

    @staticmethod
    def _spec_tuple(
        values: object,
        expected: type[Any],
        maximum: int,
        label: str,
    ) -> tuple[Any, ...]:
        if not isinstance(values, (tuple, list)):
            raise EditorUIDesignerError22(f"{label} must be a tuple or list")
        result = tuple(values)
        if len(result) > maximum:
            raise EditorUIDesignerError22(f"UI design exceeds {maximum} {label}")
        if not all(isinstance(item, expected) for item in result):
            raise EditorUIDesignerError22(f"{label} contain invalid values")
        return result

    @staticmethod
    def _unique(values: Sequence[Any], attribute: str, label: str) -> None:
        keys = tuple(getattr(item, attribute) for item in values)
        if len(set(keys)) != len(keys):
            raise EditorUIDesignerError22(f"duplicate {label}")

    @staticmethod
    def _validate_hierarchy(
        widgets: tuple[UIWidgetSpec22, ...],
        styles: tuple[UIStyleSpec22, ...],
    ) -> None:
        by_id = {item.id: item for item in widgets}
        style_names = {item.name for item in styles}
        for widget in widgets:
            if widget.style is not None and widget.style not in style_names:
                raise EditorUIDesignerError22(
                    f"widget {widget.id!r} references unknown style {widget.style!r}"
                )
            if widget.parent is not None:
                parent = by_id.get(widget.parent)
                if parent is None:
                    raise EditorUIDesignerError22(
                        f"widget {widget.id!r} references unknown parent {widget.parent!r}"
                    )
                if parent.kind not in {UIWidgetKind.STACK.value, UIWidgetKind.PANEL.value}:
                    raise EditorUIDesignerError22(
                        f"widget parent {parent.id!r} must be a stack or panel"
                    )
        for widget in widgets:
            seen: set[str] = set()
            current: UIWidgetSpec22 | None = widget
            depth = 0
            while current is not None:
                if current.id in seen:
                    raise EditorUIDesignerError22("UI widget hierarchy contains a cycle")
                seen.add(current.id)
                depth += 1
                if depth > MAX_UI_DESIGN_DEPTH_22:
                    raise EditorUIDesignerError22(
                        f"UI widget hierarchy exceeds depth {MAX_UI_DESIGN_DEPTH_22}"
                    )
                current = None if current.parent is None else by_id[current.parent]

    def to_dict(self) -> dict[str, Any]:
        return {
            "animations": [item.to_dict() for item in self.animations],
            "max_scale": self.max_scale,
            "min_scale": self.min_scale,
            "reference_height": self.reference_height,
            "reference_width": self.reference_width,
            "styles": [item.to_dict() for item in self.styles],
            "theme": self.theme.to_dict(),
            "widgets": [item.to_dict() for item in self.widgets],
        }

    @classmethod
    def from_dict(cls, value: object) -> UIDesignAsset22:
        allowed = {
            "reference_width", "reference_height", "min_scale", "max_scale",
            "theme", "styles", "widgets", "animations",
        }
        fields = _fields(value, allowed=allowed, label="UI design asset")
        styles = _list(fields.get("styles", []), "UI styles", MAX_UI_DESIGN_STYLES_22)
        widgets = _list(fields.get("widgets", []), "UI widgets", MAX_UI_DESIGN_WIDGETS_22)
        animations = _list(
            fields.get("animations", []),
            "UI animations",
            MAX_UI_DESIGN_ANIMATIONS_22,
        )
        return cls(
            reference_width=fields.get("reference_width", 1280.0),
            reference_height=fields.get("reference_height", 720.0),
            min_scale=fields.get("min_scale", 0.5),
            max_scale=fields.get("max_scale", 2.0),
            theme=UIThemeSpec22.from_dict(fields.get("theme", {})),
            styles=tuple(UIStyleSpec22.from_dict(item) for item in styles),
            widgets=tuple(UIWidgetSpec22.from_dict(item) for item in widgets),
            animations=tuple(UIAnimationSpec22.from_dict(item) for item in animations),
        )

    def fingerprint(self) -> str:
        data = _serialize(self.to_dict(), pretty=False).encode("ascii")
        return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class UIDesignerSnapshot22:
    path: str
    asset: UIDesignAsset22
    dirty: bool
    fingerprint: str

    @property
    def theme(self) -> UIThemeSpec22:
        return self.asset.theme

    @property
    def styles(self) -> tuple[UIStyleSpec22, ...]:
        return self.asset.styles

    @property
    def widgets(self) -> tuple[UIWidgetSpec22, ...]:
        return self.asset.widgets

    @property
    def animations(self) -> tuple[UIAnimationSpec22, ...]:
        return self.asset.animations


@dataclass(frozen=True, slots=True)
class UIDesignRuntimeDiagnostics22:
    active_animation: str | None
    time: float
    paused: bool
    playing: bool
    source_fingerprint: str
    toolkit: UIToolkitDiagnostics


class UIDesignRuntime22:
    """A UI Designer asset instantiated through UIToolkit and animation15."""

    def __init__(
        self,
        asset: UIDesignAsset22,
        scene: Scene,
        toolkit: UIToolkit,
        clips: Mapping[str, AnimationClip],
        *,
        source_fingerprint: str,
    ) -> None:
        self.asset = asset
        self.scene = scene
        self.toolkit = toolkit
        self.source_fingerprint = source_fingerprint
        self._clips = dict(clips)
        self._animation_specs = {item.name: item for item in asset.animations}
        self._base_values = {
            track.binding: getattr(self.toolkit.find(track.widget_id), track.property)
            for animation in asset.animations
            for track in animation.tracks
        }
        self.active_animation: str | None = None
        self.time = 0.0
        self.paused = False
        self.playing = False
        self.closed = False
        autoplay = next((item.name for item in asset.animations if item.autoplay), None)
        if autoplay is not None:
            self.play(autoplay)

    def _open(self) -> None:
        if self.closed:
            raise EditorUIDesignerError22("UI design runtime is closed")

    def _require_animation(self, name: str) -> tuple[UIAnimationSpec22, AnimationClip]:
        self._open()
        key = _identifier(name, "animation name")
        try:
            return self._animation_specs[key], self._clips[key]
        except KeyError as exc:
            raise EditorUIDesignerError22(f"unknown UI animation {key!r}") from exc

    def _refresh(self) -> None:
        viewport = self.toolkit.diagnostics().viewport
        if viewport is not None:
            self.toolkit.layout(*viewport)

    def _restore_base(self) -> None:
        for binding, value in self._base_values.items():
            widget_id, property_name = binding.rsplit(".", 1)
            widget = self.toolkit.find(widget_id)
            if widget is not None:
                setattr(widget, property_name, value)

    def _apply(self, animation: UIAnimationSpec22, clip: AnimationClip, time: float) -> None:
        pose = clip.sample(time, loop=animation.loop)
        for binding, value in pose.values.items():
            widget_id, property_name = binding.rsplit(".", 1)
            widget = self.toolkit.find(widget_id)
            if widget is None or property_name not in _ANIMATABLE_PROPERTIES:
                raise EditorUIDesignerError22(f"invalid runtime animation binding {binding!r}")
            setattr(widget, property_name, float(value))
        self._refresh()

    def play(self, name: str, restart: bool = True) -> UIDesignRuntimeDiagnostics22:
        animation, clip = self._require_animation(name)
        if self.active_animation == animation.name and not restart:
            self.paused = False
            self.playing = True
            return self.diagnostics()
        self._restore_base()
        self.active_animation = animation.name
        self.time = 0.0
        self.paused = False
        self.playing = True
        self._apply(animation, clip, 0.0)
        return self.diagnostics()

    def pause(self) -> UIDesignRuntimeDiagnostics22:
        self._open()
        if self.active_animation is not None and self.playing:
            self.paused = True
        return self.diagnostics()

    def resume(self) -> UIDesignRuntimeDiagnostics22:
        self._open()
        if self.active_animation is None:
            raise EditorUIDesignerError22("no UI animation is active")
        self.paused = False
        self.playing = True
        return self.diagnostics()

    def stop(self, restore: bool = True) -> UIDesignRuntimeDiagnostics22:
        self._open()
        _boolean(restore, "restore")
        if restore:
            self._restore_base()
        self.active_animation = None
        self.time = 0.0
        self.paused = False
        self.playing = False
        if restore:
            self._refresh()
        return self.diagnostics()

    def seek(self, seconds: float) -> UIDesignRuntimeDiagnostics22:
        self._open()
        if self.active_animation is None:
            raise EditorUIDesignerError22("no UI animation is active")
        requested = _number(seconds, "animation seek time", 0.0, 86_400.0 * 1_000.0)
        animation = self._animation_specs[self.active_animation]
        clip = self._clips[self.active_animation]
        self.time = requested % animation.duration if animation.loop else min(requested, animation.duration)
        self._apply(animation, clip, self.time)
        if not animation.loop and self.time >= animation.duration:
            self.playing = False
            self.paused = False
        return self.diagnostics()

    def _advance(self, dt: float, *, respect_state: bool) -> UIDesignRuntimeDiagnostics22:
        self._open()
        delta = _number(dt, "animation step", 0.0, 86_400.0)
        if self.active_animation is None:
            return self.diagnostics()
        if respect_state and (self.paused or not self.playing):
            return self.diagnostics()
        animation = self._animation_specs[self.active_animation]
        clip = self._clips[self.active_animation]
        next_time = self.time + delta
        if animation.loop:
            self.time = next_time % animation.duration
        else:
            self.time = min(next_time, animation.duration)
        self._apply(animation, clip, self.time)
        if not animation.loop and self.time >= animation.duration:
            self.playing = False
        return self.diagnostics()

    def step(self, dt: float) -> UIDesignRuntimeDiagnostics22:
        """Manually sample forward, including while normal playback is paused."""

        return self._advance(dt, respect_state=False)

    def update(
        self,
        input_manager: Any,
        width: int | None = None,
        height: int | None = None,
        *,
        dt: float = 0.0,
    ) -> UIDesignRuntimeDiagnostics22:
        """Update input/navigation and animation through one runtime entry point.

        ``update(dt)`` remains accepted for callers that only drive authored animation. Supplying
        an input manager requires both viewport dimensions and delegates focus/navigation to the
        unchanged UIToolkit path before advancing animation by the keyword-only ``dt``.
        """

        self._open()
        if width is None and height is None and isinstance(input_manager, (int, float)):
            return self._advance(input_manager, respect_state=True)
        if width is None or height is None:
            raise EditorUIDesignerError22(
                "UI runtime input update requires width and height"
            )
        self.toolkit.update(input_manager, int(width), int(height))
        return self._advance(dt, respect_state=True)

    def layout(self, width: int, height: int) -> float:
        self._open()
        return self.toolkit.layout(width, height)

    def diagnostics(self) -> UIDesignRuntimeDiagnostics22:
        return UIDesignRuntimeDiagnostics22(
            self.active_animation,
            self.time,
            self.paused,
            self.playing,
            self.source_fingerprint,
            self.toolkit.diagnostics(),
        )

    def close(self) -> None:
        if self.closed:
            return
        self.toolkit.manager.clear()
        self.active_animation = None
        self.time = 0.0
        self.paused = False
        self.playing = False
        self.closed = True


def _widget_depth(widget: UIWidgetSpec22, widgets: Mapping[str, UIWidgetSpec22]) -> int:
    depth = 0
    current = widget
    while current.parent is not None:
        depth += 1
        current = widgets[current.parent]
    return depth


def build_ui_runtime22(
    asset: UIDesignAsset22,
    scene: Scene | None = None,
    handlers: Mapping[str, Callable[[UIWidget], None]] | None = None,
    *,
    source_fingerprint: str | None = None,
) -> UIDesignRuntime22:
    if not isinstance(asset, UIDesignAsset22):
        raise EditorUIDesignerError22("asset must be a UIDesignAsset22")
    runtime_scene = Scene() if scene is None else scene
    if not isinstance(runtime_scene, Scene):
        raise EditorUIDesignerError22("scene must be a Scene")
    actions = {widget.action for widget in asset.widgets if widget.action is not None}
    if handlers is None:
        if actions:
            raise EditorUIDesignerError22("UI actions require explicit handlers")
        callbacks: dict[str, Callable[[UIWidget], None]] = {}
    else:
        if not isinstance(handlers, Mapping):
            raise EditorUIDesignerError22("handlers must be a mapping")
        callbacks = dict(handlers)
        if not all(
            isinstance(name, str) and callable(callback)
            for name, callback in callbacks.items()
        ):
            raise EditorUIDesignerError22(
                "UI action handler names must be strings and values must be callable"
            )
        if set(callbacks) != actions:
            missing = actions - set(callbacks)
            unknown = set(callbacks) - actions
            details = []
            if missing:
                details.append("missing " + ", ".join(sorted(missing)))
            if unknown:
                details.append("unknown " + ", ".join(sorted(unknown)))
            raise EditorUIDesignerError22("UI action handlers do not match: " + "; ".join(details))

    toolkit = UIToolkit(
        runtime_scene,
        reference_width=asset.reference_width,
        reference_height=asset.reference_height,
        min_scale=asset.min_scale,
        max_scale=asset.max_scale,
        theme=asset.theme.runtime(),
    )
    styles = {style.name: style.runtime() for style in asset.styles}
    widgets = {widget.id: widget for widget in asset.widgets}
    ordered = sorted(
        asset.widgets,
        key=lambda widget: (_widget_depth(widget, widgets), widget.parent or "", widget.order, widget.id),
    )
    for spec in ordered:
        callback = None
        if spec.action is not None:
            handler = callbacks[spec.action]

            def callback(widget: UIWidget, *, _handler: Callable[[UIWidget], None] = handler) -> None:
                _handler(widget)

        widget = UIWidget(
            spec.id,
            spec.kind,
            width=spec.width,
            height=spec.height,
            text=spec.text,
            value=spec.value,
            axis=spec.axis,
            gap=spec.gap,
            padding=UIInsets(*spec.padding),
            align=spec.align,
            justify=spec.justify,
            anchor=spec.anchor,
            offset_x=spec.offset_x,
            offset_y=spec.offset_y,
            visible=spec.visible,
            enabled=spec.enabled,
            focusable=spec.focusable,
            opacity=spec.opacity,
            style=None if spec.style is None else styles[spec.style],
            on_activate=callback,
        )
        toolkit.add(widget, parent=spec.parent or UIToolkit.ROOT_ID)
    clips = {animation.name: animation.runtime() for animation in asset.animations}
    return UIDesignRuntime22(
        asset,
        runtime_scene,
        toolkit,
        clips,
        source_fingerprint=source_fingerprint or asset.fingerprint(),
    )


class EditorUIDesignerTooling22:
    """Project-confined, deterministic storage and runtime construction for UI designs."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        relative_path: str = DEFAULT_UI_DESIGN_PATH_22,
        path: str | Path | None = None,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        if path is not None:
            candidate = _relative_path(path)
            if relative_path != DEFAULT_UI_DESIGN_PATH_22 and candidate != _relative_path(relative_path):
                raise EditorUIDesignerError22("path and relative_path disagree")
            relative_path = candidate
        self.relative_path = _relative_path(relative_path)
        self._asset = UIDesignAsset22()
        self._saved_fingerprint = self._asset.fingerprint()
        source = self.project_root / PurePosixPath(self.relative_path)
        target = self.target
        if source.exists() or source.is_symlink():
            if not target.is_file():
                raise EditorUIDesignerError22(
                    "UI design path must resolve to a regular file"
                )
            self.load()

    @classmethod
    def open(
        cls,
        project_root: str | Path,
        *,
        relative_path: str = DEFAULT_UI_DESIGN_PATH_22,
        path: str | Path | None = None,
    ) -> EditorUIDesignerTooling22:
        return cls(project_root, relative_path=relative_path, path=path)

    @property
    def target(self) -> Path:
        return _contained(self.project_root, self.relative_path)

    @property
    def root(self) -> Path:
        return self.project_root

    @property
    def path(self) -> Path:
        return self.target

    @property
    def asset(self) -> UIDesignAsset22:
        return self._asset

    @property
    def dirty(self) -> bool:
        return self._asset.fingerprint() != self._saved_fingerprint

    def snapshot(self) -> UIDesignerSnapshot22:
        return UIDesignerSnapshot22(
            self.relative_path,
            self._asset,
            self.dirty,
            self._asset.fingerprint(),
        )

    def _commit(self, candidate: UIDesignAsset22) -> UIDesignerSnapshot22:
        if not isinstance(candidate, UIDesignAsset22):
            raise EditorUIDesignerError22("asset must be a UIDesignAsset22")
        if len(self._serialized(candidate).encode("ascii")) > MAX_UI_DESIGN_BYTES_22:
            raise EditorUIDesignerError22("UI design exceeds byte budget")
        self._asset = candidate
        return self.snapshot()

    def set_asset(self, asset: UIDesignAsset22) -> UIDesignerSnapshot22:
        return self._commit(asset)

    replace_asset = set_asset

    def set_theme(self, theme: UIThemeSpec22) -> UIDesignerSnapshot22:
        if not isinstance(theme, UIThemeSpec22):
            raise EditorUIDesignerError22("theme must be a UIThemeSpec22")
        return self._commit(replace(self._asset, theme=theme))

    def upsert_style(self, spec: UIStyleSpec22) -> UIDesignerSnapshot22:
        if not isinstance(spec, UIStyleSpec22):
            raise EditorUIDesignerError22("style must be a UIStyleSpec22")
        values = {item.name: item for item in self._asset.styles}
        values[spec.name] = spec
        return self._commit(replace(self._asset, styles=tuple(values.values())))

    def create_style(self, name: str, **settings: Any) -> UIDesignerSnapshot22:
        if any(item.name == str(name).strip() for item in self._asset.styles):
            raise EditorUIDesignerError22(f"UI style {name!r} already exists")
        return self.upsert_style(UIStyleSpec22(name, **settings))

    def update_style(self, name: str, **changes: Any) -> UIDesignerSnapshot22:
        if "name" in changes:
            raise EditorUIDesignerError22("style name changes require remove/create")
        current = self.require_style(name)
        return self.upsert_style(replace(current, **changes))

    def remove_style(self, name: str) -> UIDesignerSnapshot22:
        current = self.require_style(name)
        if any(widget.style == current.name for widget in self._asset.widgets):
            raise EditorUIDesignerError22(f"UI style {current.name!r} is still referenced")
        return self._commit(
            replace(self._asset, styles=tuple(item for item in self._asset.styles if item != current))
        )

    def require_style(self, name: str) -> UIStyleSpec22:
        key = _identifier(name, "style name")
        for item in self._asset.styles:
            if item.name == key:
                return item
        raise EditorUIDesignerError22(f"unknown UI style {key!r}")

    def upsert_widget(self, spec: UIWidgetSpec22) -> UIDesignerSnapshot22:
        if not isinstance(spec, UIWidgetSpec22):
            raise EditorUIDesignerError22("widget must be a UIWidgetSpec22")
        values = {item.id: item for item in self._asset.widgets}
        values[spec.id] = spec
        return self._commit(replace(self._asset, widgets=tuple(values.values())))

    set_widget = upsert_widget

    def create_widget(self, widget_id: str, kind: str, **settings: Any) -> UIDesignerSnapshot22:
        if any(item.id == str(widget_id).strip() for item in self._asset.widgets):
            raise EditorUIDesignerError22(f"UI widget {widget_id!r} already exists")
        return self.upsert_widget(UIWidgetSpec22(widget_id, kind, **settings))

    def update_widget(self, widget_id: str, **changes: Any) -> UIDesignerSnapshot22:
        if "id" in changes:
            raise EditorUIDesignerError22("widget id changes require remove/create")
        current = self.require_widget(widget_id)
        return self.upsert_widget(replace(current, **changes))

    def remove_widget(self, widget_id: str, *, recursive: bool = False) -> UIDesignerSnapshot22:
        current = self.require_widget(widget_id)
        children = {current.id}
        changed = True
        while changed:
            changed = False
            for widget in self._asset.widgets:
                if widget.parent in children and widget.id not in children:
                    children.add(widget.id)
                    changed = True
        if len(children) > 1 and not recursive:
            raise EditorUIDesignerError22("widget has children; recursive removal is required")
        if any(
            track.widget_id in children
            for animation in self._asset.animations
            for track in animation.tracks
        ):
            raise EditorUIDesignerError22("widget is targeted by an animation")
        return self._commit(
            replace(
                self._asset,
                widgets=tuple(item for item in self._asset.widgets if item.id not in children),
            )
        )

    def require_widget(self, widget_id: str) -> UIWidgetSpec22:
        key = _identifier(widget_id, "widget id")
        for item in self._asset.widgets:
            if item.id == key:
                return item
        raise EditorUIDesignerError22(f"unknown UI widget {key!r}")

    def upsert_animation(self, spec: UIAnimationSpec22) -> UIDesignerSnapshot22:
        if not isinstance(spec, UIAnimationSpec22):
            raise EditorUIDesignerError22("animation must be a UIAnimationSpec22")
        values = {item.name: item for item in self._asset.animations}
        values[spec.name] = spec
        return self._commit(replace(self._asset, animations=tuple(values.values())))

    set_animation = upsert_animation

    def create_animation(
        self,
        name: str,
        duration: float,
        tracks: Sequence[UIAnimationTrackSpec22],
        **settings: Any,
    ) -> UIDesignerSnapshot22:
        if any(item.name == str(name).strip() for item in self._asset.animations):
            raise EditorUIDesignerError22(f"UI animation {name!r} already exists")
        return self.upsert_animation(UIAnimationSpec22(name, duration, tuple(tracks), **settings))

    def update_animation(self, name: str, **changes: Any) -> UIDesignerSnapshot22:
        if "name" in changes:
            raise EditorUIDesignerError22("animation name changes require remove/create")
        current = self.require_animation(name)
        return self.upsert_animation(replace(current, **changes))

    def remove_animation(self, name: str) -> UIDesignerSnapshot22:
        current = self.require_animation(name)
        return self._commit(
            replace(
                self._asset,
                animations=tuple(item for item in self._asset.animations if item != current),
            )
        )

    def require_animation(self, name: str) -> UIAnimationSpec22:
        key = _identifier(name, "animation name")
        for item in self._asset.animations:
            if item.name == key:
                return item
        raise EditorUIDesignerError22(f"unknown UI animation {key!r}")

    def build_runtime(
        self,
        scene: Scene | None = None,
        handlers: Mapping[str, Callable[[UIWidget], None]] | None = None,
    ) -> UIDesignRuntime22:
        return build_ui_runtime22(
            self._asset,
            scene,
            handlers,
            source_fingerprint=self._asset.fingerprint(),
        )

    def _payload(self, asset: UIDesignAsset22 | None = None) -> dict[str, Any]:
        payload = (self._asset if asset is None else asset).to_dict()
        return {
            "format": UI_DESIGN_FORMAT_22,
            "version": UI_DESIGN_VERSION_22,
            **payload,
        }

    def _serialized(self, asset: UIDesignAsset22 | None = None) -> str:
        return _serialize(self._payload(asset), pretty=True)

    def save(self) -> UIDesignerSnapshot22:
        data = self._serialized()
        encoded = data.encode("ascii")
        if len(encoded) > MAX_UI_DESIGN_BYTES_22:
            raise EditorUIDesignerError22("UI design exceeds byte budget")
        target = self.target
        target.parent.mkdir(parents=True, exist_ok=True)
        target = self.target
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="ascii",
                newline="\n",
                dir=target.parent,
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            target = self.target
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self._saved_fingerprint = self._asset.fingerprint()
        return self.snapshot()

    def load(self) -> UIDesignerSnapshot22:
        try:
            with self.target.open("rb") as handle:
                raw = handle.read(MAX_UI_DESIGN_BYTES_22 + 1)
            if len(raw) > MAX_UI_DESIGN_BYTES_22:
                raise EditorUIDesignerError22("UI design exceeds byte budget")
            payload = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_invalid_constant,
            )
            fields = _fields(
                payload,
                allowed={
                    "format", "version", "reference_width", "reference_height",
                    "min_scale", "max_scale", "theme", "styles", "widgets", "animations",
                },
                required={"format", "version"},
                label="UI design document",
            )
            if fields["format"] != UI_DESIGN_FORMAT_22:
                raise EditorUIDesignerError22("unsupported UI design format")
            if type(fields["version"]) is not int or fields["version"] != UI_DESIGN_VERSION_22:
                raise EditorUIDesignerError22("unsupported UI design version")
            asset_fields = {key: value for key, value in fields.items() if key not in {"format", "version"}}
            candidate = UIDesignAsset22.from_dict(asset_fields)
            if len(self._serialized(candidate).encode("ascii")) > MAX_UI_DESIGN_BYTES_22:
                raise EditorUIDesignerError22("expanded UI design exceeds byte budget")
        except EditorUIDesignerError22:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise EditorUIDesignerError22(f"cannot load UI design: {exc}") from exc
        self._asset = candidate
        self._saved_fingerprint = candidate.fingerprint()
        return self.snapshot()

    reload = load


__all__ = [
    "DEFAULT_UI_DESIGN_PATH_22",
    "MAX_UI_ANIMATION_KEYFRAMES_22",
    "MAX_UI_ANIMATION_TOTAL_KEYFRAMES_22",
    "MAX_UI_ANIMATION_TRACKS_22",
    "MAX_UI_DESIGN_ANIMATIONS_22",
    "MAX_UI_DESIGN_BYTES_22",
    "MAX_UI_DESIGN_DEPTH_22",
    "MAX_UI_DESIGN_STYLES_22",
    "MAX_UI_DESIGN_WIDGETS_22",
    "UI_DESIGN_FORMAT_22",
    "UI_DESIGN_VERSION_22",
    "EditorUIDesignerError22",
    "EditorUIDesignerTooling22",
    "UIAnimationKeyframeSpec22",
    "UIAnimationSpec22",
    "UIAnimationTrackSpec22",
    "UIDesignAsset22",
    "UIDesignRuntime22",
    "UIDesignRuntimeDiagnostics22",
    "UIDesignerSnapshot22",
    "UIStyleSpec22",
    "UIThemeSpec22",
    "UIWidgetSpec22",
    "build_ui_runtime22",
]
