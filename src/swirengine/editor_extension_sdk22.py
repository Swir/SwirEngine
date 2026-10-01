"""Bounded SwirEditor extension contracts for SwirEngine 2.2.

This module is an explicit API boundary for trusted, installed Python extensions. It is
not an operating-system sandbox: extension code still runs in the editor process and can
use normal Python imports. The boundary limits what the editor passes to an extension and
what an extension can publish through this API. In particular, it never supplies a raw app,
session, root window, scene, renderer, or :class:`swirengine.plugins.PluginManager`.

Extensions are registered as objects by the host. There is deliberately no module discovery,
autoload, or bridge to the general-purpose plugin manager. Published UI is immutable,
declarative, bounded, and copied into deterministic snapshots. Action callbacks receive no
editor object, and callback failures are converted to a fixed, non-sensitive result.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from itertools import islice
from threading import RLock
from typing import Protocol

MAX_EDITOR_EXTENSIONS_22 = 32
MAX_EXTENSION_ID_LENGTH_22 = 64
MAX_EXTENSION_NAME_LENGTH_22 = 96
MAX_EXTENSION_VERSION_LENGTH_22 = 32
MAX_EXTENSION_TEXT_LENGTH_22 = 512
MAX_EXTENSION_PANELS_22 = 12
MAX_EXTENSION_ROWS_PER_PANEL_22 = 64
MAX_EXTENSION_ACTIONS_PER_PANEL_22 = 16
MAX_EXTENSION_ACTIONS_22 = 64


class EditorExtensionError22(RuntimeError):
    """Base error for the restricted editor extension API."""


class EditorExtensionValidationError22(EditorExtensionError22, ValueError):
    """Raised when a manifest or declarative contribution violates the API contract."""


class EditorExtensionLifecycleError22(EditorExtensionError22):
    """Raised with a sanitized message when extension lifecycle code fails."""


class EditorExtensionCapability22(str, Enum):
    """Capabilities that an extension must request before using related context methods."""

    PANELS = "editor.panels"
    ACTIONS = "editor.actions"


class EditorExtensionRowTone22(str, Enum):
    """Portable semantic tone for a declarative row."""

    DEFAULT = "default"
    INFO = "info"
    GOOD = "good"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class EditorExtensionManifest22:
    """Immutable identity and least-privilege capability request for one extension."""

    extension_id: str
    name: str
    version: str
    capabilities: tuple[EditorExtensionCapability22, ...] = ()

    def __post_init__(self) -> None:
        _validate_identifier(self.extension_id, "extension_id")
        _validate_text(self.name, "name", MAX_EXTENSION_NAME_LENGTH_22)
        _validate_text(self.version, "version", MAX_EXTENSION_VERSION_LENGTH_22)
        _validate_tuple(self.capabilities, "capabilities", len(EditorExtensionCapability22))
        if any(not isinstance(item, EditorExtensionCapability22) for item in self.capabilities):
            raise EditorExtensionValidationError22(
                "capabilities must contain EditorExtensionCapability22 values"
            )
        if len(set(self.capabilities)) != len(self.capabilities):
            raise EditorExtensionValidationError22("capabilities must not contain duplicates")
        object.__setattr__(
            self,
            "capabilities",
            tuple(sorted(self.capabilities, key=lambda item: item.value)),
        )


@dataclass(frozen=True, slots=True)
class EditorExtensionRow22:
    """One bounded, display-only key/value row in an extension panel."""

    row_id: str
    label: str
    value: str
    tone: EditorExtensionRowTone22 = EditorExtensionRowTone22.DEFAULT

    def __post_init__(self) -> None:
        _validate_identifier(self.row_id, "row_id")
        _validate_text(self.label, "label", MAX_EXTENSION_NAME_LENGTH_22)
        _validate_text(
            self.value,
            "value",
            MAX_EXTENSION_TEXT_LENGTH_22,
            allow_empty=True,
        )
        if not isinstance(self.tone, EditorExtensionRowTone22):
            raise EditorExtensionValidationError22("tone must be an EditorExtensionRowTone22 value")


@dataclass(frozen=True, slots=True)
class EditorExtensionAction22:
    """Declarative action metadata; callback objects are never exposed in snapshots."""

    action_id: str
    label: str
    description: str = ""
    enabled: bool = True

    def __post_init__(self) -> None:
        _validate_identifier(self.action_id, "action_id")
        _validate_text(self.label, "label", MAX_EXTENSION_NAME_LENGTH_22)
        _validate_text(
            self.description,
            "description",
            MAX_EXTENSION_TEXT_LENGTH_22,
            allow_empty=True,
        )
        if not isinstance(self.enabled, bool):
            raise EditorExtensionValidationError22("enabled must be a bool")


@dataclass(frozen=True, slots=True)
class EditorExtensionPanel22:
    """Immutable panel made only from bounded rows and action descriptions."""

    panel_id: str
    title: str
    description: str = ""
    rows: tuple[EditorExtensionRow22, ...] = ()
    actions: tuple[EditorExtensionAction22, ...] = ()

    def __post_init__(self) -> None:
        _validate_identifier(self.panel_id, "panel_id")
        _validate_text(self.title, "title", MAX_EXTENSION_NAME_LENGTH_22)
        _validate_text(
            self.description,
            "description",
            MAX_EXTENSION_TEXT_LENGTH_22,
            allow_empty=True,
        )
        _validate_tuple(self.rows, "rows", MAX_EXTENSION_ROWS_PER_PANEL_22)
        _validate_tuple(self.actions, "actions", MAX_EXTENSION_ACTIONS_PER_PANEL_22)
        if any(not isinstance(row, EditorExtensionRow22) for row in self.rows):
            raise EditorExtensionValidationError22("rows must contain EditorExtensionRow22 values")
        if any(not isinstance(action, EditorExtensionAction22) for action in self.actions):
            raise EditorExtensionValidationError22(
                "actions must contain EditorExtensionAction22 values"
            )
        _reject_casefold_collisions((row.row_id for row in self.rows), "row_id")
        _reject_casefold_collisions(
            (action.action_id for action in self.actions),
            "action_id",
        )


@dataclass(frozen=True, slots=True)
class EditorExtensionView22:
    """Callback-free, immutable snapshot of a registered extension."""

    manifest: EditorExtensionManifest22
    panels: tuple[EditorExtensionPanel22, ...]


@dataclass(frozen=True, slots=True)
class EditorExtensionRegistrySnapshot22:
    """Deterministically ordered registry state suitable for an editor frontend."""

    extensions: tuple[EditorExtensionView22, ...]


@dataclass(frozen=True, slots=True)
class EditorExtensionActionResult22:
    """Sanitized outcome of invoking one extension action."""

    ok: bool
    code: str
    message: str


EditorExtensionActionCallback22 = Callable[[], None]


class EditorExtension22(Protocol):
    """Structural contract accepted by :meth:`EditorExtensionRegistry22.register`.

    ``on_load`` receives only the restricted context below. An optional no-argument
    ``on_unload`` hook may release resources owned by the extension itself.
    """

    manifest: EditorExtensionManifest22

    def on_load(self, context: EditorExtensionContext22) -> None:
        """Publish initial declarative contributions through ``context``."""


class EditorExtensionContext22:
    """Narrow capability-gated surface passed to trusted installed extensions."""

    __slots__ = (
        "__active",
        "__capabilities",
        "__extension_id",
        "__publish_panel",
        "__remove_panel",
    )

    def __init__(
        self,
        *,
        extension_id: str,
        capabilities: tuple[EditorExtensionCapability22, ...],
        publish_panel: Callable[
            [EditorExtensionPanel22, Mapping[str, EditorExtensionActionCallback22]],
            None,
        ],
        remove_panel: Callable[[str], bool],
    ) -> None:
        self.__extension_id = extension_id
        self.__capabilities = capabilities
        self.__publish_panel = publish_panel
        self.__remove_panel = remove_panel
        self.__active = True

    @property
    def extension_id(self) -> str:
        """Stable public ID for the owning extension."""
        return self.__extension_id

    @property
    def capabilities(self) -> tuple[EditorExtensionCapability22, ...]:
        """Approved immutable capabilities for the owning extension."""
        return self.__capabilities

    @property
    def active(self) -> bool:
        """Whether this context still belongs to a registered extension."""
        return self.__active

    def publish_panel(
        self,
        panel: EditorExtensionPanel22,
        *,
        handlers: Mapping[str, EditorExtensionActionCallback22] | None = None,
    ) -> None:
        """Add or replace one panel after capability and bound checks.

        Handler keys must match the panel's declared action IDs. Callbacks take no
        arguments, so the registry never needs to pass editor internals to extension code.
        """
        self._require_active()
        self.__publish_panel(panel, {} if handlers is None else handlers)

    def remove_panel(self, panel_id: str) -> bool:
        """Remove one panel owned by this extension."""
        self._require_active()
        _validate_identifier(panel_id, "panel_id")
        return self.__remove_panel(panel_id)

    def _retire(self) -> None:
        self.__active = False

    def _require_active(self) -> None:
        if not self.__active:
            raise EditorExtensionLifecycleError22("extension context is no longer active")


@dataclass(slots=True)
class _ExtensionEntry22:
    manifest: EditorExtensionManifest22
    extension: object
    context: EditorExtensionContext22
    panels: dict[str, EditorExtensionPanel22] = field(default_factory=dict)
    handlers: dict[str, EditorExtensionActionCallback22] = field(default_factory=dict)


class EditorExtensionRegistry22:
    """Explicit, deterministic registry for restricted editor extensions.

    The registry accepts already-instantiated extension objects only. It intentionally has
    no discovery, module loading, autoload, service locator, or general plugin-manager API.
    """

    def __init__(
        self,
        *,
        allowed_capabilities: Iterable[EditorExtensionCapability22] = tuple(
            EditorExtensionCapability22
        ),
    ) -> None:
        failure: EditorExtensionValidationError22 | None = None
        capability_values: tuple[object, ...] = ()
        try:
            capability_values = tuple(
                islice(allowed_capabilities, len(EditorExtensionCapability22) + 1)
            )
        except Exception:  # noqa: BLE001 - custom iterable failures stay inside the boundary.
            failure = EditorExtensionValidationError22(
                "allowed_capabilities must be an iterable of capabilities"
            )
        if failure is not None:
            raise failure
        if len(capability_values) > len(EditorExtensionCapability22):
            raise EditorExtensionValidationError22(
                "allowed_capabilities exceeds the capability item limit"
            )
        if any(
            not isinstance(item, EditorExtensionCapability22) for item in capability_values
        ):
            raise EditorExtensionValidationError22(
                "allowed_capabilities contains an unknown capability"
            )
        resolved = frozenset(capability_values)
        self._allowed_capabilities = resolved
        self._entries: dict[str, _ExtensionEntry22] = {}
        self._lock = RLock()

    @property
    def allowed_capabilities(self) -> tuple[EditorExtensionCapability22, ...]:
        """Capabilities the host permits extensions to request."""
        return tuple(sorted(self._allowed_capabilities, key=lambda item: item.value))

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def register(self, extension: EditorExtension22) -> EditorExtensionManifest22:
        """Register and load an explicitly supplied extension object.

        Lifecycle failures are rolled back and exposed only as a fixed message. The original
        exception and its potentially sensitive text are deliberately not chained.
        """
        with self._lock:
            if len(self._entries) >= MAX_EDITOR_EXTENSIONS_22:
                raise EditorExtensionValidationError22("extension registry is full")
            manifest = self._read_manifest(extension)
            missing = set(manifest.capabilities) - self._allowed_capabilities
            if missing:
                raise EditorExtensionValidationError22(
                    "extension requests a capability that the host did not allow"
                )
            key = manifest.extension_id.casefold()
            if key in self._entries:
                raise EditorExtensionValidationError22(
                    "extension_id collides with a registered extension"
                )

            entry_ref: list[_ExtensionEntry22] = []
            context = EditorExtensionContext22(
                extension_id=manifest.extension_id,
                capabilities=manifest.capabilities,
                publish_panel=lambda panel, handlers: self._publish_panel(
                    entry_ref[0], panel, handlers
                ),
                remove_panel=lambda panel_id: self._remove_panel(entry_ref[0], panel_id),
            )
            entry = _ExtensionEntry22(manifest, extension, context)
            entry_ref.append(entry)
            self._entries[key] = entry
            failure: EditorExtensionLifecycleError22 | None = None
            try:
                hook = extension.on_load
                if not callable(hook):
                    raise TypeError
                hook(context)
            except Exception:  # noqa: BLE001 - extension code is an intentional boundary.
                self._entries.pop(key, None)
                self._clear_entry(entry)
                self._cleanup_failed_load(entry)
                failure = EditorExtensionLifecycleError22("extension load failed")
            if failure is not None:
                raise failure
            return manifest

    def unregister(self, extension_id: str) -> EditorExtensionManifest22:
        """Unload an extension and always remove its panels and callbacks first."""
        with self._lock:
            entry = self._entry(extension_id)
            key = entry.manifest.extension_id.casefold()
            self._entries.pop(key)
            self._clear_entry(entry)
            failure: EditorExtensionLifecycleError22 | None = None
            try:
                hook = getattr(entry.extension, "on_unload", None)
                if hook is not None:
                    if not callable(hook):
                        raise TypeError
                    hook()
            except Exception:  # noqa: BLE001 - extension code is an intentional boundary.
                failure = EditorExtensionLifecycleError22("extension unload failed")
            if failure is not None:
                raise failure
            return entry.manifest

    def shutdown(self) -> None:
        """Unload every extension while guaranteeing registry cleanup after hook failures."""
        with self._lock:
            identifiers = tuple(
                entry.manifest.extension_id
                for entry in sorted(
                    self._entries.values(),
                    key=lambda item: _deterministic_key(item.manifest.extension_id),
                    reverse=True,
                )
            )
            failed = False
            for extension_id in identifiers:
                try:
                    self.unregister(extension_id)
                except EditorExtensionLifecycleError22:
                    failed = True
            if failed:
                raise EditorExtensionLifecycleError22("one or more extension unloads failed")

    def is_registered(self, extension_id: str) -> bool:
        """Return whether an ID is registered, using the collision-safe casefold key."""
        _validate_identifier(extension_id, "extension_id")
        with self._lock:
            return extension_id.casefold() in self._entries

    def snapshot(self) -> EditorExtensionRegistrySnapshot22:
        """Return a callback-free snapshot in deterministic ID order."""
        with self._lock:
            views = tuple(
                EditorExtensionView22(
                    manifest=entry.manifest,
                    panels=tuple(
                        sorted(
                            entry.panels.values(),
                            key=lambda panel: _deterministic_key(panel.panel_id),
                        )
                    ),
                )
                for entry in sorted(
                    self._entries.values(),
                    key=lambda item: _deterministic_key(item.manifest.extension_id),
                )
            )
        return EditorExtensionRegistrySnapshot22(views)

    def invoke_action(
        self,
        extension_id: str,
        action_id: str,
    ) -> EditorExtensionActionResult22:
        """Invoke an action without passing editor objects or exposing callback failures."""
        _validate_identifier(action_id, "action_id")
        with self._lock:
            entry = self._entry(extension_id)
            action_key = action_id.casefold()
            action = next(
                (
                    candidate
                    for panel in entry.panels.values()
                    for candidate in panel.actions
                    if candidate.action_id.casefold() == action_key
                ),
                None,
            )
            if action is None:
                raise EditorExtensionValidationError22("extension action is not registered")
            if not action.enabled:
                return EditorExtensionActionResult22(
                    False,
                    "disabled",
                    "Extension action is disabled.",
                )
            callback = entry.handlers[action_key]
            try:
                callback()
            except Exception:  # noqa: BLE001 - callback details must not cross the boundary.
                return EditorExtensionActionResult22(
                    False,
                    "callback_failed",
                    "Extension action failed.",
                )
            return EditorExtensionActionResult22(True, "ok", "Extension action completed.")

    @staticmethod
    def _read_manifest(extension: object) -> EditorExtensionManifest22:
        failure: EditorExtensionLifecycleError22 | None = None
        manifest: object | None = None
        try:
            manifest = extension.manifest
        except Exception:  # noqa: BLE001 - extension property failures are sanitized.
            failure = EditorExtensionLifecycleError22("extension manifest could not be read")
        if failure is not None:
            raise failure
        if not isinstance(manifest, EditorExtensionManifest22):
            raise EditorExtensionValidationError22(
                "extension manifest must be EditorExtensionManifest22"
            )
        return manifest

    def _entry(self, extension_id: str) -> _ExtensionEntry22:
        _validate_identifier(extension_id, "extension_id")
        entry = self._entries.get(extension_id.casefold())
        if entry is None:
            raise EditorExtensionValidationError22("extension is not registered")
        return entry

    def _publish_panel(
        self,
        entry: _ExtensionEntry22,
        panel: EditorExtensionPanel22,
        handlers: Mapping[str, EditorExtensionActionCallback22],
    ) -> None:
        with self._lock:
            self._require_current_entry(entry)
            if EditorExtensionCapability22.PANELS not in entry.manifest.capabilities:
                raise EditorExtensionValidationError22(
                    "extension did not request the panels capability"
                )
            if not isinstance(panel, EditorExtensionPanel22):
                raise EditorExtensionValidationError22("panel must be an EditorExtensionPanel22")
            if (
                panel.actions
                and EditorExtensionCapability22.ACTIONS not in entry.manifest.capabilities
            ):
                raise EditorExtensionValidationError22(
                    "extension did not request the actions capability"
                )

            panel_key = panel.panel_id.casefold()
            existing_panel = entry.panels.get(panel_key)
            if existing_panel is not None and existing_panel.panel_id != panel.panel_id:
                raise EditorExtensionValidationError22(
                    "panel_id collides by casefold with an existing panel"
                )
            if existing_panel is None and len(entry.panels) >= MAX_EXTENSION_PANELS_22:
                raise EditorExtensionValidationError22("extension panel limit exceeded")

            resolved_handlers = _validate_handlers(panel, handlers)
            other_action_keys = {
                action.action_id.casefold()
                for key, candidate in entry.panels.items()
                if key != panel_key
                for action in candidate.actions
            }
            new_action_keys = {action.action_id.casefold() for action in panel.actions}
            if other_action_keys & new_action_keys:
                raise EditorExtensionValidationError22(
                    "action_id collides with another extension panel"
                )
            total_actions = len(other_action_keys) + len(new_action_keys)
            if total_actions > MAX_EXTENSION_ACTIONS_22:
                raise EditorExtensionValidationError22("extension action limit exceeded")

            if existing_panel is not None:
                for action in existing_panel.actions:
                    entry.handlers.pop(action.action_id.casefold(), None)
            entry.panels[panel_key] = panel
            entry.handlers.update(resolved_handlers)

    def _remove_panel(self, entry: _ExtensionEntry22, panel_id: str) -> bool:
        with self._lock:
            self._require_current_entry(entry)
            panel = entry.panels.pop(panel_id.casefold(), None)
            if panel is None:
                return False
            for action in panel.actions:
                entry.handlers.pop(action.action_id.casefold(), None)
            return True

    def _require_current_entry(self, entry: _ExtensionEntry22) -> None:
        current = self._entries.get(entry.manifest.extension_id.casefold())
        if current is not entry:
            raise EditorExtensionLifecycleError22("extension context is no longer active")

    @staticmethod
    def _clear_entry(entry: _ExtensionEntry22) -> None:
        entry.context._retire()
        entry.panels.clear()
        entry.handlers.clear()

    @staticmethod
    def _cleanup_failed_load(entry: _ExtensionEntry22) -> None:
        """Best-effort cleanup for resources acquired by a partial ``on_load``."""
        try:
            hook = getattr(entry.extension, "on_unload", None)
            if hook is not None:
                if not callable(hook):
                    raise TypeError
                hook()
        except Exception:  # noqa: BLE001, S110 - the fixed load error stays sanitized.
            pass


def _validate_handlers(
    panel: EditorExtensionPanel22,
    handlers: Mapping[str, EditorExtensionActionCallback22],
) -> dict[str, EditorExtensionActionCallback22]:
    if not isinstance(handlers, Mapping):
        raise EditorExtensionValidationError22("handlers must be a mapping")
    failure: EditorExtensionValidationError22 | None = None
    handler_count = 0
    try:
        handler_count = len(handlers)
    except Exception:  # noqa: BLE001 - custom mapping failures stay inside the boundary.
        failure = EditorExtensionValidationError22("handlers could not be read")
    if failure is not None:
        raise failure
    if handler_count > MAX_EXTENSION_ACTIONS_PER_PANEL_22:
        raise EditorExtensionValidationError22("handlers exceed the panel action limit")

    items: tuple[tuple[object, object], ...] = ()
    try:
        items = tuple(islice(handlers.items(), MAX_EXTENSION_ACTIONS_PER_PANEL_22 + 1))
    except Exception:  # noqa: BLE001 - custom mapping failures stay inside the boundary.
        failure = EditorExtensionValidationError22("handlers could not be read")
    if failure is not None:
        raise failure
    if len(items) != handler_count:
        raise EditorExtensionValidationError22("handlers changed while being read")
    resolved: dict[str, EditorExtensionActionCallback22] = {}
    for item in items:
        failure = None
        raw_key: object | None = None
        callback: object | None = None
        try:
            raw_key, callback = item
        except Exception:  # noqa: BLE001 - custom mapping items stay inside the boundary.
            failure = EditorExtensionValidationError22("handler entries are invalid")
        if failure is not None:
            raise failure
        if not isinstance(raw_key, str):
            raise EditorExtensionValidationError22("handler IDs must be strings")
        _validate_identifier(raw_key, "handler action_id")
        key = raw_key.casefold()
        if key in resolved:
            raise EditorExtensionValidationError22("handler IDs collide by casefold")
        if not callable(callback):
            raise EditorExtensionValidationError22("action handlers must be callable")
        resolved[key] = callback
    declared = {action.action_id.casefold() for action in panel.actions}
    if set(resolved) != declared:
        raise EditorExtensionValidationError22("handlers must match the panel action IDs exactly")
    return resolved


def _validate_identifier(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise EditorExtensionValidationError22(f"{name} must be a string")
    if not value or value != value.strip():
        raise EditorExtensionValidationError22(f"{name} must be non-empty without padding")
    if len(value) > MAX_EXTENSION_ID_LENGTH_22:
        raise EditorExtensionValidationError22(f"{name} is too long")
    if not value[0].isascii() or not value[0].isalpha():
        raise EditorExtensionValidationError22(f"{name} must begin with an ASCII letter")
    if any(
        not (character.isascii() and (character.isalnum() or character in "_.-"))
        for character in value
    ):
        raise EditorExtensionValidationError22(
            f"{name} may contain only ASCII letters, numbers, dot, dash, and underscore"
        )


def _validate_text(
    value: object,
    name: str,
    maximum: int,
    *,
    allow_empty: bool = False,
) -> None:
    if not isinstance(value, str):
        raise EditorExtensionValidationError22(f"{name} must be a string")
    if not allow_empty and not value:
        raise EditorExtensionValidationError22(f"{name} must not be empty")
    if len(value) > maximum:
        raise EditorExtensionValidationError22(f"{name} is too long")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise EditorExtensionValidationError22(f"{name} must not contain control characters")


def _validate_tuple(value: object, name: str, maximum: int) -> None:
    if not isinstance(value, tuple):
        raise EditorExtensionValidationError22(f"{name} must be an immutable tuple")
    if len(value) > maximum:
        raise EditorExtensionValidationError22(f"{name} exceeds its item limit")


def _reject_casefold_collisions(values: Iterable[str], name: str) -> None:
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key in seen:
            raise EditorExtensionValidationError22(f"{name} values collide by casefold")
        seen.add(key)


def _deterministic_key(value: str) -> tuple[str, str]:
    return value.casefold(), value


__all__ = [
    "MAX_EDITOR_EXTENSIONS_22",
    "MAX_EXTENSION_ACTIONS_22",
    "MAX_EXTENSION_ACTIONS_PER_PANEL_22",
    "MAX_EXTENSION_ID_LENGTH_22",
    "MAX_EXTENSION_NAME_LENGTH_22",
    "MAX_EXTENSION_PANELS_22",
    "MAX_EXTENSION_ROWS_PER_PANEL_22",
    "MAX_EXTENSION_TEXT_LENGTH_22",
    "MAX_EXTENSION_VERSION_LENGTH_22",
    "EditorExtension22",
    "EditorExtensionAction22",
    "EditorExtensionActionResult22",
    "EditorExtensionCapability22",
    "EditorExtensionContext22",
    "EditorExtensionError22",
    "EditorExtensionLifecycleError22",
    "EditorExtensionManifest22",
    "EditorExtensionPanel22",
    "EditorExtensionRegistry22",
    "EditorExtensionRegistrySnapshot22",
    "EditorExtensionRow22",
    "EditorExtensionRowTone22",
    "EditorExtensionValidationError22",
    "EditorExtensionView22",
]
