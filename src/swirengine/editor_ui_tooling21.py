from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .core.scene import Scene
from .math.types import Color
from .ui import UIManager

UI_HUD_ASSET_FORMAT = "swirengine.ui-hud"
UI_HUD_ASSET_VERSION = 1
DEFAULT_UI_HUD_PATH = "config/ui-hud.json"
_UI_KINDS = {"label", "panel", "button", "progress"}


class EditorUIHudToolingError(ValueError):
    """Raised when project UI/HUD data cannot be authored safely."""


@dataclass(frozen=True, slots=True)
class UIElementSpec21:
    name: str
    kind: str
    x: float = 0.0
    y: float = 0.0
    width: float = 220.0
    height: float = 56.0
    text: str = ""
    value: float = 0.0
    layer: int = 1000
    color: tuple[float, float, float, float] | None = None
    text_color: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        name = _name(self.name, "UI element name")
        kind = str(self.kind).strip().lower()
        if kind not in _UI_KINDS:
            raise EditorUIHudToolingError(
                f"UI element kind must be one of {tuple(sorted(_UI_KINDS))!r}"
            )
        x = _finite(self.x, "UI element x")
        y = _finite(self.y, "UI element y")
        width = _positive(self.width, "UI element width")
        height = _positive(self.height, "UI element height")
        value = _unit(self.value, "UI progress value")
        if isinstance(self.layer, bool) or not isinstance(self.layer, int):
            raise TypeError("UI element layer must be an integer")
        if self.layer < 0:
            raise EditorUIHudToolingError("UI element layer must not be negative")
        color = None if self.color is None else _color(self.color, "UI element color")
        text_color = (
            None if self.text_color is None else _color(self.text_color, "UI text color")
        )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "text", str(self.text))
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "color", color)
        object.__setattr__(self, "text_color", text_color)


@dataclass(frozen=True, slots=True)
class EditorUIHudSnapshot21:
    path: str
    elements: tuple[UIElementSpec21, ...]
    dirty: bool

    @property
    def element_count(self) -> int:
        return len(self.elements)


class EditorUIHudTooling21:
    """Deterministic UI/HUD authoring backed by the shipping ``UIManager`` runtime."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        path: str = DEFAULT_UI_HUD_PATH,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.relative_path = _relative_path(path)
        self._elements: dict[str, UIElementSpec21] = {}
        self._saved_fingerprint = self._fingerprint()
        if self.target.is_file():
            self.load()

    @property
    def target(self) -> Path:
        return _target(self.project_root, self.relative_path)

    @property
    def dirty(self) -> bool:
        return self._fingerprint() != self._saved_fingerprint

    def snapshot(self) -> EditorUIHudSnapshot21:
        return EditorUIHudSnapshot21(
            self.relative_path,
            self._ordered_elements(),
            self.dirty,
        )

    def create_element(self, name: str, kind: str, **settings: Any) -> EditorUIHudSnapshot21:
        spec = UIElementSpec21(name=name, kind=kind, **settings)
        if spec.name in self._elements:
            raise EditorUIHudToolingError(f"UI element {spec.name!r} already exists")
        self._elements[spec.name] = spec
        return self.snapshot()

    def update_element(self, name: str, **changes: Any) -> EditorUIHudSnapshot21:
        if "name" in changes:
            raise EditorUIHudToolingError("UI element name changes require remove/create")
        current = self._require(name)
        updated = replace(current, **changes)
        self._elements[name] = updated
        return self.snapshot()

    def remove_element(self, name: str) -> EditorUIHudSnapshot21:
        self._require(name)
        del self._elements[name]
        return self.snapshot()

    def duplicate_element(
        self,
        name: str,
        new_name: str,
        *,
        offset: tuple[float, float] = (24.0, 24.0),
    ) -> EditorUIHudSnapshot21:
        current = self._require(name)
        normalized_name = _name(new_name, "UI element name")
        if normalized_name in self._elements:
            raise EditorUIHudToolingError(f"UI element {normalized_name!r} already exists")
        if len(offset) != 2:
            raise EditorUIHudToolingError("UI duplicate offset must contain two values")
        dx = _finite(offset[0], "UI duplicate x offset")
        dy = _finite(offset[1], "UI duplicate y offset")
        duplicate = replace(current, name=normalized_name, x=current.x + dx, y=current.y + dy)
        self._elements[duplicate.name] = duplicate
        return self.snapshot()

    def build_runtime(self, scene: Scene | None = None) -> UIManager:
        """Instantiate authored elements through the public runtime UI API."""

        runtime_scene = Scene() if scene is None else scene
        if not isinstance(runtime_scene, Scene):
            raise TypeError("scene must be a Scene")
        manager = UIManager(runtime_scene)
        for spec in self._ordered_elements():
            color = _runtime_color(spec.color)
            text_color = _runtime_color(spec.text_color)
            if spec.kind == "label":
                manager.label(
                    spec.text,
                    spec.x,
                    spec.y,
                    color=text_color or color,
                    layer=spec.layer,
                )
            elif spec.kind == "panel":
                manager.panel(
                    spec.x,
                    spec.y,
                    spec.width,
                    spec.height,
                    color=color,
                    layer=spec.layer,
                )
            elif spec.kind == "button":
                manager.button(
                    spec.text,
                    spec.x,
                    spec.y,
                    spec.width,
                    spec.height,
                    color=color,
                    text_color=text_color,
                    layer=spec.layer,
                )
            elif spec.kind == "progress":
                manager.progress_bar(
                    spec.x,
                    spec.y,
                    spec.width,
                    spec.height,
                    value=spec.value,
                    fill_color=color,
                    layer=spec.layer,
                )
            else:  # pragma: no cover - guarded by dataclass validation
                raise EditorUIHudToolingError(f"unsupported UI element kind {spec.kind!r}")
        return manager

    def save(self) -> EditorUIHudSnapshot21:
        target = self.target
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", newline="\n", dir=target.parent, delete=False
            ) as handle:
                handle.write(self._serialized_text())
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, target)
            temporary = None
        except OSError as exc:
            raise EditorUIHudToolingError(f"cannot save UI/HUD configuration: {exc}") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self._saved_fingerprint = self._fingerprint()
        return self.snapshot()

    def load(self) -> EditorUIHudSnapshot21:
        try:
            payload = json.loads(self.target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise EditorUIHudToolingError(f"cannot load UI/HUD configuration: {exc}") from exc
        elements = _decode(payload)
        self._elements = {item.name: item for item in elements}
        if len(self._elements) != len(elements):
            raise EditorUIHudToolingError("duplicate UI element name")
        self._saved_fingerprint = self._fingerprint()
        return self.snapshot()

    def _require(self, name: str) -> UIElementSpec21:
        try:
            return self._elements[str(name)]
        except KeyError as exc:
            raise EditorUIHudToolingError(f"unknown UI element {name!r}") from exc

    def _ordered_elements(self) -> tuple[UIElementSpec21, ...]:
        return tuple(self._elements[name] for name in sorted(self._elements))

    def _payload(self) -> dict[str, Any]:
        return {
            "format": UI_HUD_ASSET_FORMAT,
            "version": UI_HUD_ASSET_VERSION,
            "elements": [asdict(item) for item in self._ordered_elements()],
        }

    def _serialized_text(self) -> str:
        return json.dumps(
            self._payload(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"

    def _fingerprint(self) -> str:
        payload = json.dumps(
            self._payload(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        return hashlib.sha256(payload).hexdigest()


def _decode(payload: Any) -> tuple[UIElementSpec21, ...]:
    if not isinstance(payload, dict):
        raise EditorUIHudToolingError("UI/HUD configuration must be an object")
    if set(payload) != {"format", "version", "elements"}:
        raise EditorUIHudToolingError("UI/HUD configuration fields do not match schema")
    if (
        payload["format"] != UI_HUD_ASSET_FORMAT
        or payload["version"] != UI_HUD_ASSET_VERSION
    ):
        raise EditorUIHudToolingError("unsupported UI/HUD configuration")
    raw = payload["elements"]
    if not isinstance(raw, list):
        raise EditorUIHudToolingError("UI/HUD elements must be an array")
    fields = set(UIElementSpec21.__dataclass_fields__)
    result: list[UIElementSpec21] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) - fields:
            raise EditorUIHudToolingError("invalid UI/HUD element entry")
        try:
            result.append(UIElementSpec21(**item))
        except (TypeError, ValueError) as exc:
            raise EditorUIHudToolingError(f"invalid UI/HUD element entry: {exc}") from exc
    return tuple(result)


def _name(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    value = value.strip()
    if not value:
        raise EditorUIHudToolingError(f"{label} cannot be empty")
    if len(value) > 96:
        raise EditorUIHudToolingError(f"{label} must not exceed 96 characters")
    return value


def _finite(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise EditorUIHudToolingError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise EditorUIHudToolingError(f"{label} must be finite")
    return result


def _positive(value: Any, label: str) -> float:
    result = _finite(value, label)
    if result <= 0.0:
        raise EditorUIHudToolingError(f"{label} must be greater than zero")
    return result


def _unit(value: Any, label: str) -> float:
    result = _finite(value, label)
    if result < 0.0 or result > 1.0:
        raise EditorUIHudToolingError(f"{label} must be between 0 and 1")
    return result


def _color(value: Any, label: str) -> tuple[float, float, float, float]:
    if isinstance(value, (str, bytes)):
        raise EditorUIHudToolingError(f"{label} must contain four values")
    try:
        result = tuple(float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise EditorUIHudToolingError(f"{label} must contain four numeric values") from exc
    if len(result) != 4 or not all(math.isfinite(item) for item in result):
        raise EditorUIHudToolingError(f"{label} must contain four finite values")
    if any(item < 0.0 or item > 1.0 for item in result):
        raise EditorUIHudToolingError(f"{label} values must be between 0 and 1")
    return result


def _runtime_color(value: tuple[float, float, float, float] | None) -> Color | None:
    return None if value is None else Color(*value)


def _relative_path(value: str | Path) -> str:
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        not normalized
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
    ):
        raise EditorUIHudToolingError("UI/HUD configuration path must stay project-relative")
    return posix.as_posix()


def _target(root: Path, relative: str) -> Path:
    target = (root / PurePosixPath(relative)).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise EditorUIHudToolingError("UI/HUD configuration path escapes the project root") from exc
    return target
