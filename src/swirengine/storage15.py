from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage import MigrationRegistry, ProfileStore

SAVE_FORMAT = "swirengine-save-slot"
SAVE_FORMAT_VERSION = 1

JSONValue = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]


class SaveIntegrityError(ValueError):
    """Raised when a save envelope does not match its recorded digest."""


class SaveRecoveryError(RuntimeError):
    """Raised when neither the primary save nor its backup can be trusted."""


@dataclass(slots=True, frozen=True)
class SaveSlotDiagnostics:
    loads: int = 0
    saves: int = 0
    recoveries: int = 0
    migrations: int = 0
    integrity_failures: int = 0


@dataclass(slots=True, frozen=True)
class SaveLoadResult:
    data: dict[str, JSONValue]
    metadata: dict[str, JSONValue]
    stored_version: int
    target_version: int
    revision: int
    source: str
    migrations_applied: int = 0

    @property
    def migrated(self) -> bool:
        return self.stored_version != self.target_version

    @property
    def recovered(self) -> bool:
        return self.source == "backup"


@dataclass(slots=True, frozen=True)
class SaveSlotInfo:
    name: str
    path: Path
    healthy: bool
    recovery_available: bool
    version: int | None = None
    revision: int | None = None
    metadata: dict[str, JSONValue] | None = None


@dataclass(slots=True, frozen=True)
class AutosavePolicy:
    keep: int = 3
    prefix: str = "autosave"

    def __post_init__(self) -> None:
        if self.keep < 1:
            raise ValueError("autosave keep must be at least 1")
        _validate_token(self.prefix, label="autosave prefix")

    def slot_name(self, index: int) -> str:
        if not 1 <= index <= self.keep:
            raise ValueError(f"autosave index must be between 1 and {self.keep}")
        return f"{self.prefix}-{index}"


_DEFAULT_AUTOSAVE_POLICY = AutosavePolicy()


def _portable(value: Any) -> JSONValue:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("save floats must be finite")
        return 0.0 if value == 0.0 else value
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    if isinstance(value, Mapping):
        result: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("save mapping keys must be strings")
            result[key] = _portable(item)
        return result
    raise TypeError(f"unsupported save value type: {type(value).__name__}")


def _portable_mapping(value: Mapping[str, Any], *, label: str) -> dict[str, JSONValue]:
    normalized = _portable(value)
    if not isinstance(normalized, dict):
        raise TypeError(f"{label} must be a mapping")
    return normalized


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    normalized = _portable_mapping(value, label="save payload")
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_bytes(value: Mapping[str, Any]) -> bytes:
    normalized = _portable_mapping(value, label="save payload")
    text = json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    )
    return f"{text}\n".encode()


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        return
    finally:
        os.close(descriptor)


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _backup_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.bak")


def _validate_token(value: str, *, label: str) -> None:
    if not value or len(value) > 64:
        raise ValueError(f"{label} must contain 1-64 characters")
    if not value[0].isalnum() or any(
        not (character.isalnum() or character in "_.-") for character in value
    ):
        raise ValueError(
            f"{label} must use letters, digits, underscore, dot or dash and start alphanumeric"
        )


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid save JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise TypeError("save root must be a JSON object")
    return payload


def _verified_envelope(path: Path) -> dict[str, Any]:
    envelope = _read_json_object(path)
    if envelope.get("format") != SAVE_FORMAT:
        raise ValueError(f"unsupported save format: {path}")
    format_version = envelope.get("format_version")
    if format_version != SAVE_FORMAT_VERSION:
        raise ValueError(f"unsupported save format version: {format_version!r}")
    integrity = envelope.get("integrity")
    if not isinstance(integrity, dict):
        raise SaveIntegrityError("save integrity record is missing")
    if integrity.get("algorithm") != "sha256":
        raise SaveIntegrityError("unsupported save integrity algorithm")
    expected = integrity.get("digest")
    if not isinstance(expected, str) or len(expected) != 64:
        raise SaveIntegrityError("save integrity digest is invalid")
    body = dict(envelope)
    del body["integrity"]
    if _digest(body) != expected:
        raise SaveIntegrityError(f"save integrity check failed: {path}")
    return envelope


def _decode_envelope(
    path: Path,
    *,
    target_version: int,
    migrations: MigrationRegistry,
    defaults: Mapping[str, Any],
) -> SaveLoadResult:
    envelope = _verified_envelope(path)
    stored_version = envelope.get("version")
    if not isinstance(stored_version, int) or isinstance(stored_version, bool):
        raise TypeError("save version must be an integer")
    if stored_version < 1:
        raise ValueError("save version must be at least 1")
    if stored_version > target_version:
        raise ValueError(
            f"save version {stored_version} is newer than supported {target_version}"
        )

    revision = envelope.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise TypeError("save revision must be a positive integer")
    raw_data = envelope.get("data")
    raw_metadata = envelope.get("metadata", {})
    if not isinstance(raw_data, dict):
        raise TypeError("save data must be a JSON object")
    if not isinstance(raw_metadata, dict):
        raise TypeError("save metadata must be a JSON object")

    data: dict[str, Any] = dict(raw_data)
    applied = 0
    if stored_version < target_version:
        data, applied = migrations.migrate(data, stored_version, target_version)
    merged = _portable_mapping(defaults, label="save defaults")
    merged.update(_portable_mapping(data, label="save data"))
    metadata = _portable_mapping(raw_metadata, label="save metadata")
    return SaveLoadResult(
        data=merged,
        metadata=metadata,
        stored_version=stored_version,
        target_version=target_version,
        revision=revision,
        source="primary",
        migrations_applied=applied,
    )


class SaveSlotStore2:
    """Versioned, integrity-checked save slot with atomic primary/backup writes."""

    def __init__(
        self,
        path: str | Path,
        *,
        version: int = 1,
        migrations: MigrationRegistry | None = None,
        defaults: Mapping[str, Any] | None = None,
    ) -> None:
        if version < 1:
            raise ValueError("save version must be at least 1")
        self.path = Path(path).expanduser()
        self.version = int(version)
        self.migrations = migrations or MigrationRegistry()
        self.defaults = _portable_mapping(defaults or {}, label="save defaults")
        self._loads = 0
        self._saves = 0
        self._recoveries = 0
        self._migrations = 0
        self._integrity_failures = 0

    @property
    def backup_path(self) -> Path:
        return _backup_path(self.path)

    @property
    def diagnostics(self) -> SaveSlotDiagnostics:
        return SaveSlotDiagnostics(
            loads=self._loads,
            saves=self._saves,
            recoveries=self._recoveries,
            migrations=self._migrations,
            integrity_failures=self._integrity_failures,
        )

    def exists(self) -> bool:
        return self.path.exists() or self.backup_path.exists()

    def _load_path(self, path: Path) -> SaveLoadResult:
        try:
            result = _decode_envelope(
                path,
                target_version=self.version,
                migrations=self.migrations,
                defaults=self.defaults,
            )
        except SaveIntegrityError:
            self._integrity_failures += 1
            raise
        self._migrations += result.migrations_applied
        return result

    def load(self, *, repair: bool = False, upgrade: bool = False) -> SaveLoadResult:
        primary_error: Exception | None
        if self.path.exists():
            try:
                result = self._load_path(self.path)
                self._loads += 1
                if upgrade and result.migrated:
                    self.save(result.data, metadata=result.metadata)
                return result
            except (OSError, TypeError, ValueError) as exc:
                primary_error = exc
        else:
            primary_error = FileNotFoundError(self.path)

        if self.backup_path.exists():
            try:
                backup = self._load_path(self.backup_path)
            except (OSError, TypeError, ValueError) as backup_error:
                raise SaveRecoveryError(
                    f"save primary and backup are unreadable: {self.path}"
                ) from backup_error
            self._loads += 1
            self._recoveries += 1
            result = SaveLoadResult(
                data=backup.data,
                metadata=backup.metadata,
                stored_version=backup.stored_version,
                target_version=backup.target_version,
                revision=backup.revision,
                source="backup",
                migrations_applied=backup.migrations_applied,
            )
            if repair:
                self.recover()
            if upgrade and result.migrated:
                self.save(result.data, metadata=result.metadata)
            return result

        if isinstance(primary_error, FileNotFoundError):
            raise primary_error
        raise SaveRecoveryError(f"save is unreadable and no backup exists: {self.path}") from primary_error

    def _current_revision(self) -> int:
        if not self.exists():
            return 0
        try:
            return self.load().revision
        except FileNotFoundError:
            return 0

    def _ensure_primary_safe_for_overwrite(self) -> None:
        if not self.path.exists():
            if self.backup_path.exists():
                self.recover()
            return
        try:
            _verified_envelope(self.path)
        except (OSError, TypeError, ValueError) as primary_error:
            if not self.backup_path.exists():
                raise SaveRecoveryError(
                    f"refusing to overwrite unreadable save without a valid backup: {self.path}"
                ) from primary_error
            try:
                _verified_envelope(self.backup_path)
            except (OSError, TypeError, ValueError) as backup_error:
                raise SaveRecoveryError(
                    f"refusing to overwrite save because primary and backup are unreadable: {self.path}"
                ) from backup_error
            self.recover()

    def save(
        self,
        data: Mapping[str, Any],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> SaveSlotInfo:
        portable_data = _portable_mapping(data, label="save data")
        portable_metadata = _portable_mapping(metadata or {}, label="save metadata")
        self._ensure_primary_safe_for_overwrite()
        revision = self._current_revision() + 1
        body: dict[str, Any] = {
            "format": SAVE_FORMAT,
            "format_version": SAVE_FORMAT_VERSION,
            "version": self.version,
            "revision": revision,
            "metadata": portable_metadata,
            "data": portable_data,
        }
        envelope = {
            **body,
            "integrity": {"algorithm": "sha256", "digest": _digest(body)},
        }
        encoded = _file_bytes(envelope)

        if self.path.exists():
            current = self.path.read_bytes()
            _verified_envelope(self.path)
            _atomic_write_bytes(self.backup_path, current)
        _atomic_write_bytes(self.path, encoded)
        self._saves += 1
        return SaveSlotInfo(
            name=self.path.stem,
            path=self.path,
            healthy=True,
            recovery_available=self.backup_path.exists(),
            version=self.version,
            revision=revision,
            metadata=portable_metadata,
        )

    def recover(self) -> SaveLoadResult:
        if not self.backup_path.exists():
            raise FileNotFoundError(self.backup_path)
        result = self._load_path(self.backup_path)
        _atomic_write_bytes(self.path, self.backup_path.read_bytes())
        self._recoveries += 1
        return SaveLoadResult(
            data=result.data,
            metadata=result.metadata,
            stored_version=result.stored_version,
            target_version=result.target_version,
            revision=result.revision,
            source="backup",
            migrations_applied=result.migrations_applied,
        )

    def inspect(self, *, name: str | None = None) -> SaveSlotInfo:
        slot_name = name or self.path.stem
        backup_result = self._inspect_backup()
        try:
            result = _decode_envelope(
                self.path,
                target_version=self.version,
                migrations=self.migrations,
                defaults=self.defaults,
            )
        except (OSError, TypeError, ValueError):
            return SaveSlotInfo(
                name=slot_name,
                path=self.path,
                healthy=False,
                recovery_available=backup_result is not None,
                version=backup_result.stored_version if backup_result else None,
                revision=backup_result.revision if backup_result else None,
                metadata=backup_result.metadata if backup_result else None,
            )
        return SaveSlotInfo(
            name=slot_name,
            path=self.path,
            healthy=True,
            recovery_available=backup_result is not None,
            version=result.stored_version,
            revision=result.revision,
            metadata=result.metadata,
        )

    def _inspect_backup(self) -> SaveLoadResult | None:
        if not self.backup_path.exists():
            return None
        try:
            return _decode_envelope(
                self.backup_path,
                target_version=self.version,
                migrations=self.migrations,
                defaults=self.defaults,
            )
        except (OSError, TypeError, ValueError):
            return None


class ProfileSaveManager2:
    """Additive 1.5 profile save manager isolated from legacy 1.x save-slot files."""

    def __init__(
        self,
        root: str | Path,
        profile: str = "default",
        *,
        version: int = 1,
        migrations: MigrationRegistry | None = None,
        defaults: Mapping[str, Any] | None = None,
    ) -> None:
        self.legacy_profile = ProfileStore(root, profile)
        self.version = version
        self.migrations = migrations or MigrationRegistry()
        self.defaults = _portable_mapping(defaults or {}, label="save defaults")
        self.directory = self.legacy_profile.paths.directory / "saves-v2"

    @property
    def profile(self) -> str:
        return self.legacy_profile.name

    def slot_path(self, slot: str) -> Path:
        _validate_token(slot, label="save slot")
        return self.directory / f"{slot}.json"

    def slot(self, slot: str) -> SaveSlotStore2:
        return SaveSlotStore2(
            self.slot_path(slot),
            version=self.version,
            migrations=self.migrations,
            defaults=self.defaults,
        )

    def save(
        self,
        slot: str,
        data: Mapping[str, Any],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> SaveSlotInfo:
        return self.slot(slot).save(data, metadata=metadata)

    def load(self, slot: str, *, repair: bool = False, upgrade: bool = False) -> SaveLoadResult:
        return self.slot(slot).load(repair=repair, upgrade=upgrade)

    def list_slots(self) -> tuple[SaveSlotInfo, ...]:
        if not self.directory.exists():
            return ()
        names = {path.stem for path in self.directory.glob("*.json") if path.is_file()}
        for path in self.directory.glob("*.json.bak"):
            if path.is_file():
                names.add(path.name[: -len(".json.bak")])
        return tuple(self.slot(name).inspect(name=name) for name in sorted(names))

    def delete(self, slot: str, *, include_backup: bool = True) -> bool:
        store = self.slot(slot)
        deleted = False
        if store.path.exists():
            store.path.unlink()
            deleted = True
        if include_backup and store.backup_path.exists():
            store.backup_path.unlink()
            deleted = True
        return deleted

    def import_legacy(
        self,
        slot: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> SaveSlotInfo:
        legacy_path = self.legacy_profile.paths.save_slot(slot)
        if not legacy_path.exists():
            raise FileNotFoundError(legacy_path)
        legacy = self.legacy_profile.save_slot(slot)
        merged_metadata: dict[str, Any] = {"imported_from": "swirengine-1.x"}
        if metadata:
            merged_metadata.update(metadata)
        return self.save(slot, legacy.as_dict(), metadata=merged_metadata)

    def autosave(
        self,
        data: Mapping[str, Any],
        *,
        policy: AutosavePolicy = _DEFAULT_AUTOSAVE_POLICY,
        metadata: Mapping[str, Any] | None = None,
    ) -> SaveSlotInfo:
        generations: list[int] = []
        for index in range(1, policy.keep + 1):
            name = policy.slot_name(index)
            info = self.slot(name).inspect(name=name)
            generation = 0
            if info.metadata is not None:
                candidate = info.metadata.get("autosave_generation", 0)
                if isinstance(candidate, int) and not isinstance(candidate, bool) and candidate >= 0:
                    generation = candidate
            generations.append(generation)
        next_generation = max(generations, default=0) + 1
        target_index = ((next_generation - 1) % policy.keep) + 1
        target = policy.slot_name(target_index)
        autosave_metadata: dict[str, Any] = dict(metadata or {})
        autosave_metadata.update(
            {
                "autosave": True,
                "autosave_generation": next_generation,
                "autosave_index": target_index,
            }
        )
        return self.save(target, data, metadata=autosave_metadata)

    def list_autosaves(
        self,
        *,
        policy: AutosavePolicy = _DEFAULT_AUTOSAVE_POLICY,
    ) -> tuple[SaveSlotInfo, ...]:
        infos: list[SaveSlotInfo] = []
        for index in range(1, policy.keep + 1):
            name = policy.slot_name(index)
            path = self.slot_path(name)
            if path.exists() or _backup_path(path).exists():
                infos.append(self.slot(name).inspect(name=name))

        def generation(info: SaveSlotInfo) -> int:
            if info.metadata is None:
                return -1
            value = info.metadata.get("autosave_generation")
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            return -1

        return tuple(sorted(infos, key=generation, reverse=True))
