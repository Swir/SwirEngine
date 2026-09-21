from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .input import InputBinding
from .shipping19 import (
    AccessibilitySettings,
    BindingConflict,
    DisplaySettings,
    GameSettings,
    ProductionActionMap,
    ProjectShippingDefaults,
    SettingsStore,
)

DEFAULT_CONTROLS_PATH = "config/controls.json"
DEFAULT_SETTINGS_PATH = "config/settings.json"


class EditorGameplayToolingError(ValueError):
    """Raised when creator gameplay configuration cannot be authored safely."""


@dataclass(frozen=True, slots=True)
class EditorGameplaySnapshot21:
    """Immutable creator-facing view of the current gameplay configuration."""

    actions: ProductionActionMap
    settings: GameSettings
    conflicts: tuple[BindingConflict, ...]
    controls_path: str
    settings_path: str
    dirty: bool

    @property
    def action_count(self) -> int:
        return len(self.actions.actions())

    @property
    def fingerprint(self) -> tuple[str, str]:
        return self.actions.fingerprint, self.settings.fingerprint


class EditorGameplayTooling21:
    """Project-scoped input/rebinding and settings authoring for SwirEditor 2.1.

    This layer deliberately builds on the shipping 1.9 contracts instead of inventing an
    editor-only format. Files produced here are the same validated ``controls.json`` and
    ``settings.json`` consumed by ``ProjectShippingDefaults`` at runtime.
    """

    def __init__(
        self,
        project_root: str | Path,
        *,
        controls_path: str = DEFAULT_CONTROLS_PATH,
        settings_path: str = DEFAULT_SETTINGS_PATH,
    ) -> None:
        self.root = Path(project_root).expanduser().resolve()
        self.controls_path = _project_relative_path(controls_path, label="controls path")
        self.settings_path = _project_relative_path(settings_path, label="settings path")
        self._actions = ProductionActionMap.standard()
        self._settings = GameSettings()
        self._saved_fingerprint = (self._actions.fingerprint, self._settings.fingerprint)
        self.reload()

    @property
    def actions(self) -> ProductionActionMap:
        return self._actions

    @property
    def settings(self) -> GameSettings:
        return self._settings

    @property
    def controls_target(self) -> Path:
        return _project_target(self.root, self.controls_path, label="controls path")

    @property
    def settings_target(self) -> Path:
        return _project_target(self.root, self.settings_path, label="settings path")

    @property
    def dirty(self) -> bool:
        return self._fingerprint() != self._saved_fingerprint

    def snapshot(self) -> EditorGameplaySnapshot21:
        return EditorGameplaySnapshot21(
            actions=self._actions,
            settings=self._settings,
            conflicts=self._actions.conflicts(),
            controls_path=self.controls_path,
            settings_path=self.settings_path,
            dirty=self.dirty,
        )

    def reload(self) -> EditorGameplaySnapshot21:
        # Revalidate the physical targets on every disk operation. A project may be opened from
        # an untrusted checkout where a config directory is replaced by a symlink after startup.
        _project_target(self.root, self.controls_path, label="controls path")
        _project_target(self.root, self.settings_path, label="settings path")
        defaults = ProjectShippingDefaults.load(
            self.root,
            input_path=self.controls_path,
            settings_path=self.settings_path,
        )
        self._actions = defaults.actions
        self._settings = defaults.settings
        self._saved_fingerprint = self._fingerprint()
        return self.snapshot()

    def replace_action(
        self,
        action: str,
        bindings: Iterable[InputBinding],
    ) -> EditorGameplaySnapshot21:
        self._actions = self._actions.replace_action(action, tuple(bindings))
        return self.snapshot()

    def add_binding(
        self,
        action: str,
        binding: InputBinding,
    ) -> EditorGameplaySnapshot21:
        """Append one validated binding while preserving the action's existing controls."""

        if not isinstance(binding, InputBinding):
            raise TypeError("binding must be an InputBinding")
        return self.replace_action(action, (*self._actions.bindings(action), binding))

    def remove_binding(self, action: str, index: int) -> EditorGameplaySnapshot21:
        """Remove one binding without bypassing required UI-navigation validation."""

        if isinstance(index, bool) or not isinstance(index, int):
            raise TypeError("binding index must be an integer")
        bindings = list(self._actions.bindings(action))
        if not bindings:
            raise EditorGameplayToolingError(f"{action!r} has no bindings to remove")
        if index < 0 or index >= len(bindings):
            raise IndexError("binding index is outside the action binding list")
        del bindings[index]
        return self.replace_action(action, bindings)

    def bind_key(self, action: str, key: str) -> EditorGameplaySnapshot21:
        return self.replace_action(action, (InputBinding("key", key),))

    def bind_mouse_button(self, action: str, button: int) -> EditorGameplaySnapshot21:
        return self.replace_action(action, (InputBinding("mouse_button", button),))

    def bind_gamepad_button(
        self,
        action: str,
        button: str,
        *,
        gamepad_id: int = 0,
    ) -> EditorGameplaySnapshot21:
        return self.replace_action(
            action,
            (InputBinding("gamepad_button", button, gamepad_id=gamepad_id),),
        )

    def bind_gamepad_axis(
        self,
        action: str,
        axis: str,
        *,
        direction: int = 0,
        threshold: float = 0.5,
        scale: float = 1.0,
        gamepad_id: int = 0,
    ) -> EditorGameplaySnapshot21:
        return self.replace_action(
            action,
            (
                InputBinding(
                    "gamepad_axis",
                    axis,
                    gamepad_id=gamepad_id,
                    direction=direction,
                    threshold=threshold,
                    scale=scale,
                ),
            ),
        )

    def update_display(self, **changes: Any) -> EditorGameplaySnapshot21:
        self._settings = self._settings.with_display(**changes)
        return self.snapshot()

    def update_accessibility(self, **changes: Any) -> EditorGameplaySnapshot21:
        self._settings = self._settings.with_accessibility(**changes)
        return self.snapshot()

    def replace_display(self, settings: DisplaySettings) -> EditorGameplaySnapshot21:
        if not isinstance(settings, DisplaySettings):
            raise TypeError("settings must be DisplaySettings")
        self._settings = GameSettings(
            display=settings,
            accessibility=self._settings.accessibility,
        )
        return self.snapshot()

    def replace_accessibility(
        self,
        settings: AccessibilitySettings,
    ) -> EditorGameplaySnapshot21:
        if not isinstance(settings, AccessibilitySettings):
            raise TypeError("settings must be AccessibilitySettings")
        self._settings = GameSettings(
            display=self._settings.display,
            accessibility=settings,
        )
        return self.snapshot()

    def reset_action(self, action: str) -> EditorGameplaySnapshot21:
        defaults = ProductionActionMap.standard()
        bindings = defaults.bindings(action)
        if not bindings:
            raise EditorGameplayToolingError(
                f"{action!r} has no standard SwirEngine binding to restore"
            )
        return self.replace_action(action, bindings)

    def reset_settings(self) -> EditorGameplaySnapshot21:
        self._settings = GameSettings()
        return self.snapshot()

    def save(self) -> EditorGameplaySnapshot21:
        """Persist creator defaults using the validated shipping formats.

        Each target is written atomically by the underlying shipping implementation. Input is
        written first so malformed bindings cannot leave a newly changed settings file behind.
        Physical targets are resolved immediately before writing to reject symlink escapes.
        """

        controls_target = self.controls_target
        settings_target = self.settings_target
        self._actions.save(controls_target)
        SettingsStore(GameSettings(), settings_target).save(self._settings)
        self._saved_fingerprint = self._fingerprint()
        return self.snapshot()

    def apply(
        self,
        *,
        actions: Mapping[str, Iterable[InputBinding]] | None = None,
        display: Mapping[str, Any] | None = None,
        accessibility: Mapping[str, Any] | None = None,
    ) -> EditorGameplaySnapshot21:
        """Apply a batch of creator changes without writing until ``save()`` is called."""

        if actions is not None:
            current = self._actions
            for action, bindings in actions.items():
                current = current.replace_action(action, tuple(bindings))
            self._actions = current
        if display:
            self._settings = self._settings.with_display(**dict(display))
        if accessibility:
            self._settings = self._settings.with_accessibility(**dict(accessibility))
        return self.snapshot()

    def _fingerprint(self) -> tuple[str, str]:
        return self._actions.fingerprint, self._settings.fingerprint


def _project_relative_path(value: str | Path, *, label: str) -> str:
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    if not normalized or normalized == ".":
        raise EditorGameplayToolingError(f"{label} cannot be empty")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
    ):
        raise EditorGameplayToolingError(f"{label} must stay project-relative")
    return posix.as_posix()


def _project_target(root: Path, relative: str, *, label: str) -> Path:
    """Resolve a project config target while rejecting symlink/physical root escapes."""

    resolved = (root / PurePosixPath(relative)).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise EditorGameplayToolingError(f"{label} escapes the project root") from exc
    return resolved