from __future__ import annotations

import json
import math
import os
import re
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .game_state19 import (
    ProductionGameStateSession,
    SaveProductionPolicy,
    project_app_id,
)

DEFAULT_SAVE_PROFILE_PATH = "config/save-profile.json"
_FORMAT = "swirengine.save-profile"
_FORMAT_VERSION = 1
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_APP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")


class EditorSaveProfileToolingError(ValueError):
    """Raised when creator save/profile configuration is unsafe or invalid."""


@dataclass(frozen=True, slots=True)
class SaveProfileConfig21:
    """Runtime-backed save/profile policy authored by SwirEditor 2.1."""

    app_id: str
    default_profile: str = "default"
    version: int = 1
    policy: SaveProductionPolicy = field(default_factory=SaveProductionPolicy)
    defaults: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        _validate_token(self.app_id, label="app_id", pattern=_APP_ID_RE)
        _validate_token(self.default_profile, label="default profile", pattern=_TOKEN_RE)
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise EditorSaveProfileToolingError("version must be an integer >= 1")
        if not isinstance(self.policy, SaveProductionPolicy):
            raise TypeError("policy must be a SaveProductionPolicy")
        normalized = _portable_mapping(self.defaults or {})
        object.__setattr__(self, "defaults", normalized)

    def portable(self) -> dict[str, Any]:
        return {
            "format": _FORMAT,
            "format_version": _FORMAT_VERSION,
            "app_id": self.app_id,
            "default_profile": self.default_profile,
            "version": self.version,
            "policy": asdict(self.policy),
            "defaults": dict(self.defaults or {}),
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> SaveProfileConfig21:
        if payload.get("format") != _FORMAT:
            raise EditorSaveProfileToolingError("unsupported save/profile configuration format")
        if payload.get("format_version") != _FORMAT_VERSION:
            raise EditorSaveProfileToolingError("unsupported save/profile configuration version")
        policy_raw = payload.get("policy", {})
        if not isinstance(policy_raw, Mapping):
            raise EditorSaveProfileToolingError("policy must be an object")
        allowed = set(asdict(SaveProductionPolicy()))
        unknown = set(policy_raw) - allowed
        if unknown:
            names = ", ".join(sorted(str(item) for item in unknown))
            raise EditorSaveProfileToolingError(f"unknown save policy fields: {names}")
        policy_values = asdict(SaveProductionPolicy())
        policy_values.update(dict(policy_raw))
        defaults = payload.get("defaults", {})
        if not isinstance(defaults, Mapping):
            raise EditorSaveProfileToolingError("defaults must be an object")
        try:
            policy = SaveProductionPolicy(**policy_values)
        except (TypeError, ValueError) as exc:
            raise EditorSaveProfileToolingError(str(exc)) from exc
        return cls(
            app_id=str(payload.get("app_id", "")),
            default_profile=str(payload.get("default_profile", "default")),
            version=payload.get("version", 1),
            policy=policy,
            defaults=defaults,
        )

    def open_runtime(
        self,
        *,
        user_data_root: str | Path | None = None,
        profile: str | None = None,
    ) -> ProductionGameStateSession:
        """Open the shipping save/profile runtime using exactly this creator policy."""
        selected_profile = self.default_profile if profile is None else profile
        _validate_token(selected_profile, label="profile", pattern=_TOKEN_RE)
        return ProductionGameStateSession(
            self.app_id,
            profile=selected_profile,
            user_data_root=user_data_root,
            version=self.version,
            defaults=self.defaults,
            policy=self.policy,
        )


@dataclass(frozen=True, slots=True)
class EditorSaveProfileSnapshot21:
    path: str
    config: SaveProfileConfig21
    dirty: bool


class EditorSaveProfileTooling21:
    """Creator workflow for production save slots, profiles and autosave policy."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        project_name: str | None = None,
        path: str = DEFAULT_SAVE_PROFILE_PATH,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.relative_path = _project_relative_path(path, label="save/profile path")
        name = project_name or self.project_root.name
        self._config = SaveProfileConfig21(app_id=project_app_id(name))
        self._saved_fingerprint = self._fingerprint(self._config)
        self.reload()

    @property
    def target(self) -> Path:
        return _project_target(self.project_root, self.relative_path, label="save/profile path")

    @property
    def config(self) -> SaveProfileConfig21:
        return self._config

    @property
    def dirty(self) -> bool:
        return self._fingerprint(self._config) != self._saved_fingerprint

    def snapshot(self) -> EditorSaveProfileSnapshot21:
        return EditorSaveProfileSnapshot21(self.relative_path, self._config, self.dirty)

    def update_identity(
        self,
        *,
        app_id: str | None = None,
        default_profile: str | None = None,
        version: int | None = None,
    ) -> EditorSaveProfileSnapshot21:
        changes: dict[str, Any] = {}
        if app_id is not None:
            changes["app_id"] = app_id
        if default_profile is not None:
            changes["default_profile"] = default_profile
        if version is not None:
            changes["version"] = version
        self._config = replace(self._config, **changes)
        return self.snapshot()

    def update_policy(self, **changes: Any) -> EditorSaveProfileSnapshot21:
        values = asdict(self._config.policy)
        unknown = set(changes) - set(values)
        if unknown:
            names = ", ".join(sorted(unknown))
            raise EditorSaveProfileToolingError(f"unknown save policy fields: {names}")
        values.update(changes)
        try:
            policy = SaveProductionPolicy(**values)
        except (TypeError, ValueError) as exc:
            raise EditorSaveProfileToolingError(str(exc)) from exc
        self._config = replace(self._config, policy=policy)
        return self.snapshot()

    def replace_defaults(self, defaults: Mapping[str, Any]) -> EditorSaveProfileSnapshot21:
        self._config = replace(self._config, defaults=_portable_mapping(defaults))
        return self.snapshot()

    def validate_runtime(
        self,
        user_data_root: str | Path,
        *,
        profile: str | None = None,
    ) -> EditorSaveProfileSnapshot21:
        """Exercise real background save/load using the shipping runtime."""
        runtime = self._config.open_runtime(user_data_root=user_data_root, profile=profile)
        probe = {"editor_probe": True, "format_version": _FORMAT_VERSION}
        try:
            runtime.submit_manual(
                "editor-preview",
                probe,
                metadata={"source": "SwirEditor 2.1"},
            )
            runtime.run_until_idle(timeout=5.0)
            loaded = runtime.load("editor-preview")
            if loaded.data != probe:
                raise EditorSaveProfileToolingError("runtime save/profile validation mismatch")
        finally:
            runtime.shutdown(wait=True, cancel_pending=True)
        return self.snapshot()

    def save(self) -> EditorSaveProfileSnapshot21:
        target = self.target
        target.parent.mkdir(parents=True, exist_ok=True)
        text = _canonical_text(self._config.portable())
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        self._saved_fingerprint = self._fingerprint(self._config)
        return self.snapshot()

    def reload(self) -> EditorSaveProfileSnapshot21:
        target = self.target
        if target.exists():
            try:
                payload = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise EditorSaveProfileToolingError(
                    f"cannot read save/profile configuration: {exc}"
                ) from exc
            if not isinstance(payload, Mapping):
                raise EditorSaveProfileToolingError("save/profile configuration must be an object")
            self._config = SaveProfileConfig21.from_mapping(payload)
        self._saved_fingerprint = self._fingerprint(self._config)
        return self.snapshot()

    @staticmethod
    def _fingerprint(config: SaveProfileConfig21) -> str:
        return _canonical_text(config.portable())


def _canonical_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        _portable_mapping(payload),
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _portable_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _portable(value)
    if not isinstance(normalized, dict):
        raise TypeError("value must be a mapping")
    return normalized


def _portable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EditorSaveProfileToolingError("floating point values must be finite")
        return 0.0 if value == 0.0 else value
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("mapping keys must be strings")
            result[key] = _portable(item)
        return result
    raise TypeError(f"unsupported configuration value type: {type(value).__name__}")


def _validate_token(value: str, *, label: str, pattern: re.Pattern[str]) -> None:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise EditorSaveProfileToolingError(
            f"{label} must start alphanumeric and use only letters, digits, underscore, dot or dash"
        )


def _project_relative_path(value: str | Path, *, label: str) -> str:
    raw = str(value).strip()
    normalized = raw.replace("\\", "/")
    if not normalized or normalized == ".":
        raise EditorSaveProfileToolingError(f"{label} cannot be empty")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(raw)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or ".." in posix.parts
    ):
        raise EditorSaveProfileToolingError(f"{label} must stay project-relative")
    return posix.as_posix()


def _project_target(root: Path, relative: str, *, label: str) -> Path:
    resolved = (root / PurePosixPath(relative)).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise EditorSaveProfileToolingError(f"{label} escapes the project root") from exc
    return resolved
