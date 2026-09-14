from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_JSONScalar = str | int | float | bool | None
Migration = Callable[[dict[str, Any]], Mapping[str, Any]]


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label} JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise TypeError(f"{label} root must be a JSON object")
    return raw


class SaveStore:
    """Small JSON save-data store with atomic writes and dict-like helpers.

    The 1.x on-disk format remains the original plain JSON object. New 1.2
    profile/settings helpers are additive and do not change SaveStore files.
    """

    def __init__(
        self,
        path: str | Path = "save.json",
        *,
        defaults: Mapping[str, Any] | None = None,
        autoload: bool = True,
    ) -> None:
        self.path = Path(path).expanduser()
        self._defaults = dict(defaults or {})
        self._data: dict[str, Any] = dict(self._defaults)
        if autoload and self.path.exists():
            self.load()

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> SaveStore:
        self._data[key] = value
        return self

    def update(self, values: Mapping[str, Any]) -> SaveStore:
        self._data.update(values)
        return self

    def delete(self, key: str) -> bool:
        if key not in self._data:
            return False
        del self._data[key]
        return True

    def clear(self, *, keep_defaults: bool = True) -> SaveStore:
        self._data = dict(self._defaults) if keep_defaults else {}
        return self

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def load(self) -> SaveStore:
        raw = _load_json_object(self.path, label="save data")
        self._data = dict(self._defaults)
        self._data.update(raw)
        return self

    def save(self) -> SaveStore:
        _atomic_write_json(self.path, self._data)
        return self


@dataclass(frozen=True, slots=True)
class SettingSpec:
    """One typed setting definition used by :class:`SettingsSchema`."""

    default: _JSONScalar
    value_type: type | tuple[type, ...]
    choices: tuple[_JSONScalar, ...] = ()
    minimum: float | None = None
    maximum: float | None = None

    def validate(self, key: str, value: Any) -> _JSONScalar:
        expected = self.value_type
        if not isinstance(value, expected) or (
            isinstance(value, bool) and expected in (int, float)
        ):
            if isinstance(expected, tuple):
                names = ", ".join(item.__name__ for item in expected)
            else:
                names = expected.__name__
            raise TypeError(f"setting {key!r} must be {names}")
        if self.choices and value not in self.choices:
            raise ValueError(f"setting {key!r} must be one of {self.choices!r}")
        if self.minimum is not None and isinstance(value, (int, float)):
            if value < self.minimum:
                raise ValueError(f"setting {key!r} must be >= {self.minimum}")
        if self.maximum is not None and isinstance(value, (int, float)):
            if value > self.maximum:
                raise ValueError(f"setting {key!r} must be <= {self.maximum}")
        return value


class SettingsSchema:
    """Deterministic typed settings schema with defaults and unknown-key policy."""

    def __init__(
        self,
        fields: Mapping[str, SettingSpec],
        *,
        allow_unknown: bool = False,
    ) -> None:
        if not fields:
            raise ValueError("settings schema must define at least one field")
        self._fields = dict(fields)
        self.allow_unknown = bool(allow_unknown)
        for key, spec in self._fields.items():
            spec.validate(key, spec.default)

    @property
    def fields(self) -> Mapping[str, SettingSpec]:
        return self._fields

    def defaults(self) -> dict[str, _JSONScalar]:
        return {key: spec.default for key, spec in self._fields.items()}

    def validate(self, values: Mapping[str, Any], *, partial: bool = False) -> dict[str, Any]:
        validated: dict[str, Any] = {} if partial else self.defaults()
        for key, value in values.items():
            spec = self._fields.get(key)
            if spec is None:
                if self.allow_unknown:
                    validated[key] = value
                    continue
                raise KeyError(f"unknown setting: {key}")
            validated[key] = spec.validate(key, value)
        return validated


class MigrationRegistry:
    """Ordered one-version-at-a-time JSON migrations."""

    def __init__(self) -> None:
        self._steps: dict[int, Migration] = {}

    def register(self, from_version: int, migration: Migration) -> MigrationRegistry:
        if from_version < 0:
            raise ValueError("from_version must be >= 0")
        if from_version in self._steps:
            raise ValueError(f"migration from version {from_version} is already registered")
        self._steps[from_version] = migration
        return self

    def migrate(
        self,
        values: Mapping[str, Any],
        from_version: int,
        to_version: int,
    ) -> tuple[dict[str, Any], int]:
        if from_version > to_version:
            raise ValueError("downgrade migrations are not supported")
        current = dict(values)
        applied = 0
        version = from_version
        while version < to_version:
            migration = self._steps.get(version)
            if migration is None:
                raise ValueError(f"missing migration {version} -> {version + 1}")
            migrated = migration(dict(current))
            if not isinstance(migrated, Mapping):
                raise TypeError("migration must return a mapping")
            current = dict(migrated)
            version += 1
            applied += 1
        return current, applied


@dataclass(frozen=True, slots=True)
class StorageDiagnostics:
    loads: int = 0
    saves: int = 0
    migrations: int = 0
    validation_failures: int = 0


class SettingsStore:
    """Typed, versioned settings store with migration support and atomic writes."""

    FORMAT = "swirengine-settings"

    def __init__(
        self,
        path: str | Path,
        schema: SettingsSchema,
        *,
        version: int = 1,
        migrations: MigrationRegistry | None = None,
        autoload: bool = True,
    ) -> None:
        if version < 1:
            raise ValueError("settings version must be >= 1")
        self.path = Path(path).expanduser()
        self.schema = schema
        self.version = version
        self.migrations = migrations or MigrationRegistry()
        self._values: dict[str, Any] = schema.defaults()
        self._loads = 0
        self._saves = 0
        self._migrations = 0
        self._validation_failures = 0
        if autoload and self.path.exists():
            self.load()

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> SettingsStore:
        try:
            validated = self.schema.validate({key: value}, partial=True)
        except (KeyError, TypeError, ValueError):
            self._validation_failures += 1
            raise
        self._values.update(validated)
        return self

    def update(self, values: Mapping[str, Any]) -> SettingsStore:
        try:
            validated = self.schema.validate(values, partial=True)
        except (KeyError, TypeError, ValueError):
            self._validation_failures += 1
            raise
        self._values.update(validated)
        return self

    def reset(self, key: str | None = None) -> SettingsStore:
        defaults = self.schema.defaults()
        if key is None:
            self._values = defaults
        else:
            if key not in defaults:
                raise KeyError(f"unknown setting: {key}")
            self._values[key] = defaults[key]
        return self

    def as_dict(self) -> dict[str, Any]:
        return dict(self._values)

    @property
    def diagnostics(self) -> StorageDiagnostics:
        return StorageDiagnostics(
            loads=self._loads,
            saves=self._saves,
            migrations=self._migrations,
            validation_failures=self._validation_failures,
        )

    def load(self) -> SettingsStore:
        envelope = _load_json_object(self.path, label="settings")
        if envelope.get("format") != self.FORMAT:
            raise ValueError(f"unsupported settings format: {self.path}")
        stored_version = envelope.get("version")
        if not isinstance(stored_version, int) or isinstance(stored_version, bool):
            raise TypeError("settings version must be an integer")
        values = envelope.get("values")
        if not isinstance(values, dict):
            raise TypeError("settings values must be a JSON object")
        if stored_version > self.version:
            raise ValueError(
                f"settings file version {stored_version} is newer than supported {self.version}"
            )
        if stored_version < self.version:
            values, applied = self.migrations.migrate(values, stored_version, self.version)
            self._migrations += applied
        try:
            self._values = self.schema.validate(values)
        except (KeyError, TypeError, ValueError):
            self._validation_failures += 1
            raise
        self._loads += 1
        return self

    def save(self) -> SettingsStore:
        _atomic_write_json(
            self.path,
            {"format": self.FORMAT, "version": self.version, "values": self._values},
        )
        self._saves += 1
        return self


_PROFILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


@dataclass(frozen=True, slots=True)
class ProfilePaths:
    """Cloud-sync-friendly deterministic paths for one local player profile."""

    root: Path
    profile: str

    @property
    def directory(self) -> Path:
        return self.root / "profiles" / self.profile

    @property
    def settings(self) -> Path:
        return self.directory / "settings.json"

    @property
    def saves(self) -> Path:
        return self.directory / "saves"

    def save_slot(self, slot: str = "autosave") -> Path:
        _validate_profile_token(slot, label="save slot")
        return self.saves / f"{slot}.json"


class ProfileStore:
    """Profile-oriented storage layout separating settings from save slots.

    Keeping small settings and independent save-slot files under a stable profile
    directory avoids a monolithic mutable blob and makes external cloud-sync
    tools able to synchronize individual files predictably.
    """

    def __init__(self, root: str | Path, profile: str = "default") -> None:
        _validate_profile_token(profile, label="profile")
        self.paths = ProfilePaths(Path(root).expanduser(), profile)

    @property
    def name(self) -> str:
        return self.paths.profile

    def settings(
        self,
        schema: SettingsSchema,
        *,
        version: int = 1,
        migrations: MigrationRegistry | None = None,
        autoload: bool = True,
    ) -> SettingsStore:
        return SettingsStore(
            self.paths.settings,
            schema,
            version=version,
            migrations=migrations,
            autoload=autoload,
        )

    def save_slot(
        self,
        slot: str = "autosave",
        *,
        defaults: Mapping[str, Any] | None = None,
        autoload: bool = True,
    ) -> SaveStore:
        return SaveStore(
            self.paths.save_slot(slot),
            defaults=defaults,
            autoload=autoload,
        )

    def list_slots(self) -> tuple[str, ...]:
        if not self.paths.saves.exists():
            return ()
        return tuple(sorted(path.stem for path in self.paths.saves.glob("*.json") if path.is_file()))


def _validate_profile_token(value: str, *, label: str) -> None:
    if not _PROFILE_NAME.fullmatch(value):
        raise ValueError(
            f"{label} must be 1-64 characters using letters, digits, underscore, dot or dash"
        )
