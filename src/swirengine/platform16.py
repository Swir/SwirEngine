from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class PlatformCapability(str, Enum):
    IDENTITY = "identity"
    CLOUD_SAVE = "cloud_save"
    ACHIEVEMENTS = "achievements"
    STATS = "stats"
    ENTITLEMENTS = "entitlements"


class PlatformServiceError(RuntimeError):
    """Creator-facing platform-service failure with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        capability: PlatformCapability | None = None,
    ) -> None:
        super().__init__(message)
        self.code = _text(code, "code", maximum=64).lower()
        self.capability = capability


def _text(value: object, label: str, *, maximum: int = 128) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{label} must not exceed {maximum} characters")
    return normalized


def _slot(value: object) -> str:
    normalized = _text(value, "slot", maximum=128)
    if normalized in {".", ".."} or "/" in normalized or "\\" in normalized:
        raise ValueError("slot must be a portable single-segment identifier")
    return normalized


def _finite(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _non_negative_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be non-negative")
    return value


@dataclass(slots=True, frozen=True)
class PlatformIdentity:
    account_id: str
    display_name: str
    provider: str = "local"

    def __post_init__(self) -> None:
        object.__setattr__(self, "account_id", _text(self.account_id, "account_id", maximum=128))
        object.__setattr__(
            self,
            "display_name",
            _text(self.display_name, "display_name", maximum=128),
        )
        object.__setattr__(self, "provider", _text(self.provider, "provider", maximum=64).lower())

    def portable(self) -> dict[str, str]:
        return {
            "account_id": self.account_id,
            "display_name": self.display_name,
            "provider": self.provider,
        }


@dataclass(slots=True, frozen=True)
class CloudSaveRecord:
    slot: str
    revision: int
    payload: bytes
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "slot", _slot(self.slot))
        if (
            not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 1
        ):
            raise ValueError("revision must be an integer of at least 1")
        payload = bytes(self.payload)
        digest = hashlib.sha256(payload).hexdigest()
        if self.sha256 != digest:
            raise ValueError("sha256 does not match payload")
        object.__setattr__(self, "payload", payload)

    @property
    def size(self) -> int:
        return len(self.payload)

    def portable(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "revision": self.revision,
            "size": self.size,
            "sha256": self.sha256,
        }


@dataclass(slots=True, frozen=True)
class AchievementRecord:
    achievement_id: str
    progress: float
    unlocked: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "achievement_id",
            _text(self.achievement_id, "achievement_id", maximum=128),
        )
        progress = _finite(self.progress, "progress")
        if not 0.0 <= progress <= 1.0:
            raise ValueError("progress must be between 0.0 and 1.0")
        object.__setattr__(self, "progress", progress)
        if not isinstance(self.unlocked, bool):
            raise TypeError("unlocked must be a boolean")
        if self.unlocked and progress < 1.0:
            raise ValueError("unlocked achievements must have progress 1.0")

    def portable(self) -> dict[str, Any]:
        return {
            "achievement_id": self.achievement_id,
            "progress": self.progress,
            "unlocked": self.unlocked,
        }


@dataclass(slots=True, frozen=True)
class StatRecord:
    stat_id: str
    value: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "stat_id", _text(self.stat_id, "stat_id", maximum=128))
        object.__setattr__(self, "value", _finite(self.value, "value"))

    def portable(self) -> dict[str, Any]:
        return {"stat_id": self.stat_id, "value": self.value}


@dataclass(slots=True, frozen=True)
class EntitlementRecord:
    entitlement_id: str
    granted: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "entitlement_id",
            _text(self.entitlement_id, "entitlement_id", maximum=128),
        )
        if not isinstance(self.granted, bool):
            raise TypeError("granted must be a boolean")

    def portable(self) -> dict[str, Any]:
        return {"entitlement_id": self.entitlement_id, "granted": self.granted}


@dataclass(slots=True, frozen=True)
class PlatformCallResult:
    ok: bool
    value: Any = None
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.ok, bool):
            raise TypeError("ok must be a boolean")
        if self.ok:
            if self.error_code is not None or self.error_message is not None:
                raise ValueError("successful results cannot contain error details")
        elif self.error_code is None or self.error_message is None:
            raise ValueError("failed results require error details")


class IdentityProvider(Protocol):
    provider_name: str

    def identity(self) -> PlatformIdentity: ...


class CloudSaveProvider(Protocol):
    provider_name: str

    def cloud_save(
        self,
        slot: str,
        payload: bytes,
        *,
        expected_revision: int | None = None,
    ) -> CloudSaveRecord: ...

    def cloud_load(self, slot: str) -> CloudSaveRecord | None: ...

    def cloud_delete(self, slot: str, *, expected_revision: int | None = None) -> bool: ...

    def cloud_slots(self) -> tuple[str, ...]: ...


class AchievementProvider(Protocol):
    provider_name: str

    def achievement(self, achievement_id: str) -> AchievementRecord: ...

    def achievement_progress(self, achievement_id: str, progress: float) -> AchievementRecord: ...

    def achievements(self) -> tuple[AchievementRecord, ...]: ...


class StatsProvider(Protocol):
    provider_name: str

    def stat(self, stat_id: str) -> StatRecord: ...

    def stat_set(self, stat_id: str, value: float) -> StatRecord: ...

    def stat_add(self, stat_id: str, delta: float) -> StatRecord: ...

    def stats(self) -> tuple[StatRecord, ...]: ...


class EntitlementProvider(Protocol):
    provider_name: str

    def entitlement(self, entitlement_id: str) -> EntitlementRecord: ...

    def entitlements(self) -> tuple[EntitlementRecord, ...]: ...


class LocalPlatformProvider:
    """Dependency-free offline provider suitable for tests and creator development."""

    provider_name = "local"

    def __init__(
        self,
        identity: PlatformIdentity | None = None,
        *,
        max_cloud_slots: int = 64,
        max_cloud_save_bytes: int = 8 * 1024 * 1024,
        entitlements: Iterable[str] = (),
    ) -> None:
        self._identity = identity or PlatformIdentity("local-player", "Local Player")
        self._max_cloud_slots = _non_negative_int(max_cloud_slots, "max_cloud_slots")
        self._max_cloud_save_bytes = _non_negative_int(
            max_cloud_save_bytes,
            "max_cloud_save_bytes",
        )
        if self._max_cloud_slots < 1:
            raise ValueError("max_cloud_slots must be positive")
        if self._max_cloud_save_bytes < 1:
            raise ValueError("max_cloud_save_bytes must be positive")
        self._saves: dict[str, CloudSaveRecord] = {}
        self._save_revisions: dict[str, int] = {}
        self._achievements: dict[str, AchievementRecord] = {}
        self._stats: dict[str, StatRecord] = {}
        self._entitlements: dict[str, EntitlementRecord] = {}
        for entitlement_id in entitlements:
            self.grant_entitlement(entitlement_id)

    def identity(self) -> PlatformIdentity:
        return self._identity

    def cloud_save(
        self,
        slot: str,
        payload: bytes,
        *,
        expected_revision: int | None = None,
    ) -> CloudSaveRecord:
        slot = _slot(slot)
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise TypeError("payload must be bytes-like")
        data = bytes(payload)
        if len(data) > self._max_cloud_save_bytes:
            raise PlatformServiceError(
                "cloud_save_too_large",
                f"cloud save exceeds {self._max_cloud_save_bytes} bytes",
                capability=PlatformCapability.CLOUD_SAVE,
            )
        current = self._saves.get(slot)
        self._check_revision(current, expected_revision)
        if (
            current is None
            and slot not in self._saves
            and len(self._saves) >= self._max_cloud_slots
        ):
            raise PlatformServiceError(
                "cloud_slot_limit",
                f"cloud save slot limit of {self._max_cloud_slots} reached",
                capability=PlatformCapability.CLOUD_SAVE,
            )
        revision = self._save_revisions.get(slot, 0) + 1
        record = CloudSaveRecord(slot, revision, data, hashlib.sha256(data).hexdigest())
        self._saves[slot] = record
        self._save_revisions[slot] = revision
        return record

    def cloud_load(self, slot: str) -> CloudSaveRecord | None:
        return self._saves.get(_slot(slot))

    def cloud_delete(self, slot: str, *, expected_revision: int | None = None) -> bool:
        slot = _slot(slot)
        current = self._saves.get(slot)
        if current is None:
            if expected_revision is not None:
                self._check_revision(None, expected_revision)
            return False
        self._check_revision(current, expected_revision)
        del self._saves[slot]
        return True

    def cloud_slots(self) -> tuple[str, ...]:
        return tuple(sorted(self._saves))

    def achievement(self, achievement_id: str) -> AchievementRecord:
        achievement_id = _text(achievement_id, "achievement_id", maximum=128)
        return self._achievements.get(
            achievement_id,
            AchievementRecord(achievement_id, 0.0, False),
        )

    def achievement_progress(self, achievement_id: str, progress: float) -> AchievementRecord:
        achievement_id = _text(achievement_id, "achievement_id", maximum=128)
        progress = _finite(progress, "progress")
        if not 0.0 <= progress <= 1.0:
            raise ValueError("progress must be between 0.0 and 1.0")
        previous = self.achievement(achievement_id)
        if progress < previous.progress:
            raise PlatformServiceError(
                "achievement_regression",
                "achievement progress cannot move backwards",
                capability=PlatformCapability.ACHIEVEMENTS,
            )
        record = AchievementRecord(achievement_id, progress, progress >= 1.0)
        self._achievements[achievement_id] = record
        return record

    def achievements(self) -> tuple[AchievementRecord, ...]:
        return tuple(self._achievements[key] for key in sorted(self._achievements))

    def stat(self, stat_id: str) -> StatRecord:
        stat_id = _text(stat_id, "stat_id", maximum=128)
        return self._stats.get(stat_id, StatRecord(stat_id, 0.0))

    def stat_set(self, stat_id: str, value: float) -> StatRecord:
        stat_id = _text(stat_id, "stat_id", maximum=128)
        record = StatRecord(stat_id, _finite(value, "value"))
        self._stats[stat_id] = record
        return record

    def stat_add(self, stat_id: str, delta: float) -> StatRecord:
        current = self.stat(stat_id)
        return self.stat_set(current.stat_id, current.value + _finite(delta, "delta"))

    def stats(self) -> tuple[StatRecord, ...]:
        return tuple(self._stats[key] for key in sorted(self._stats))

    def entitlement(self, entitlement_id: str) -> EntitlementRecord:
        entitlement_id = _text(entitlement_id, "entitlement_id", maximum=128)
        return self._entitlements.get(
            entitlement_id,
            EntitlementRecord(entitlement_id, False),
        )

    def entitlements(self) -> tuple[EntitlementRecord, ...]:
        return tuple(self._entitlements[key] for key in sorted(self._entitlements))

    def grant_entitlement(self, entitlement_id: str) -> EntitlementRecord:
        entitlement_id = _text(entitlement_id, "entitlement_id", maximum=128)
        record = EntitlementRecord(entitlement_id, True)
        self._entitlements[entitlement_id] = record
        return record

    def revoke_entitlement(self, entitlement_id: str) -> EntitlementRecord:
        entitlement_id = _text(entitlement_id, "entitlement_id", maximum=128)
        record = EntitlementRecord(entitlement_id, False)
        self._entitlements[entitlement_id] = record
        return record

    @staticmethod
    def _check_revision(
        current: CloudSaveRecord | None,
        expected_revision: int | None,
    ) -> None:
        if expected_revision is None:
            return
        expected_revision = _non_negative_int(expected_revision, "expected_revision")
        actual = 0 if current is None else current.revision
        if expected_revision != actual:
            raise PlatformServiceError(
                "cloud_revision_conflict",
                f"expected cloud revision {expected_revision}, found {actual}",
                capability=PlatformCapability.CLOUD_SAVE,
            )


class PlatformServices:
    """Opt-in capability facade with per-service provider isolation."""

    _METHODS: Mapping[PlatformCapability, frozenset[str]] = {
        PlatformCapability.IDENTITY: frozenset({"identity"}),
        PlatformCapability.CLOUD_SAVE: frozenset(
            {"cloud_save", "cloud_load", "cloud_delete", "cloud_slots"}
        ),
        PlatformCapability.ACHIEVEMENTS: frozenset(
            {"achievement", "achievement_progress", "achievements"}
        ),
        PlatformCapability.STATS: frozenset({"stat", "stat_set", "stat_add", "stats"}),
        PlatformCapability.ENTITLEMENTS: frozenset({"entitlement", "entitlements"}),
    }

    def __init__(
        self,
        providers: Mapping[PlatformCapability | str, object] | None = None,
    ) -> None:
        self._providers: dict[PlatformCapability, object] = {}
        self._calls: dict[PlatformCapability, int] = {
            capability: 0 for capability in PlatformCapability
        }
        self._failures: dict[PlatformCapability, int] = {
            capability: 0 for capability in PlatformCapability
        }
        self._last_error_code: dict[PlatformCapability, str | None] = {
            capability: None for capability in PlatformCapability
        }
        if providers is not None:
            for capability, provider in providers.items():
                self.register(capability, provider)

    @classmethod
    def local(
        cls,
        identity: PlatformIdentity | None = None,
        *,
        max_cloud_slots: int = 64,
        max_cloud_save_bytes: int = 8 * 1024 * 1024,
        entitlements: Iterable[str] = (),
    ) -> PlatformServices:
        provider = LocalPlatformProvider(
            identity,
            max_cloud_slots=max_cloud_slots,
            max_cloud_save_bytes=max_cloud_save_bytes,
            entitlements=entitlements,
        )
        return cls({capability: provider for capability in PlatformCapability})

    def register(self, capability: PlatformCapability | str, provider: object) -> None:
        capability = self._capability(capability)
        if provider is None:
            raise TypeError("provider must not be None")
        required = self._METHODS[capability]
        missing = sorted(name for name in required if not callable(getattr(provider, name, None)))
        if missing:
            raise TypeError(
                f"provider for {capability.value!r} is missing methods: {', '.join(missing)}"
            )
        provider_name = getattr(provider, "provider_name", None)
        _text(provider_name, "provider_name", maximum=64)
        self._providers[capability] = provider

    def unregister(self, capability: PlatformCapability | str) -> bool:
        capability = self._capability(capability)
        return self._providers.pop(capability, None) is not None

    def capabilities(self) -> tuple[PlatformCapability, ...]:
        return tuple(
            capability for capability in PlatformCapability if capability in self._providers
        )

    def supports(self, capability: PlatformCapability | str) -> bool:
        return self._capability(capability) in self._providers

    def provider_name(self, capability: PlatformCapability | str) -> str | None:
        capability = self._capability(capability)
        provider = self._providers.get(capability)
        if provider is None:
            return None
        return str(getattr(provider, "provider_name"))

    def call(self, capability: PlatformCapability | str, operation: str, *args, **kwargs) -> Any:
        capability = self._capability(capability)
        operation = _text(operation, "operation", maximum=64)
        if operation not in self._METHODS[capability]:
            raise PlatformServiceError(
                "unsupported_operation",
                f"operation {operation!r} is not part of {capability.value!r}",
                capability=capability,
            )
        provider = self._providers.get(capability)
        if provider is None:
            raise PlatformServiceError(
                "capability_unavailable",
                f"platform capability {capability.value!r} is unavailable",
                capability=capability,
            )
        self._calls[capability] += 1
        try:
            return getattr(provider, operation)(*args, **kwargs)
        except PlatformServiceError as exc:
            self._failures[capability] += 1
            self._last_error_code[capability] = exc.code
            raise
        except Exception as exc:
            self._failures[capability] += 1
            self._last_error_code[capability] = "provider_failure"
            raise PlatformServiceError(
                "provider_failure",
                f"{capability.value} provider operation {operation!r} failed with "
                f"{type(exc).__name__}",
                capability=capability,
            ) from exc

    def try_call(
        self,
        capability: PlatformCapability | str,
        operation: str,
        *args,
        **kwargs,
    ) -> PlatformCallResult:
        try:
            return PlatformCallResult(True, self.call(capability, operation, *args, **kwargs))
        except PlatformServiceError as exc:
            return PlatformCallResult(False, error_code=exc.code, error_message=str(exc))

    def identity(self) -> PlatformIdentity:
        return self.call(PlatformCapability.IDENTITY, "identity")

    def cloud_save(
        self,
        slot: str,
        payload: bytes,
        *,
        expected_revision: int | None = None,
    ) -> CloudSaveRecord:
        return self.call(
            PlatformCapability.CLOUD_SAVE,
            "cloud_save",
            slot,
            payload,
            expected_revision=expected_revision,
        )

    def cloud_load(self, slot: str) -> CloudSaveRecord | None:
        return self.call(PlatformCapability.CLOUD_SAVE, "cloud_load", slot)

    def cloud_delete(self, slot: str, *, expected_revision: int | None = None) -> bool:
        return self.call(
            PlatformCapability.CLOUD_SAVE,
            "cloud_delete",
            slot,
            expected_revision=expected_revision,
        )

    def cloud_slots(self) -> tuple[str, ...]:
        return self.call(PlatformCapability.CLOUD_SAVE, "cloud_slots")

    def achievement(self, achievement_id: str) -> AchievementRecord:
        return self.call(PlatformCapability.ACHIEVEMENTS, "achievement", achievement_id)

    def achievement_progress(self, achievement_id: str, progress: float) -> AchievementRecord:
        return self.call(
            PlatformCapability.ACHIEVEMENTS,
            "achievement_progress",
            achievement_id,
            progress,
        )

    def achievements(self) -> tuple[AchievementRecord, ...]:
        return self.call(PlatformCapability.ACHIEVEMENTS, "achievements")

    def stat(self, stat_id: str) -> StatRecord:
        return self.call(PlatformCapability.STATS, "stat", stat_id)

    def stat_set(self, stat_id: str, value: float) -> StatRecord:
        return self.call(PlatformCapability.STATS, "stat_set", stat_id, value)

    def stat_add(self, stat_id: str, delta: float) -> StatRecord:
        return self.call(PlatformCapability.STATS, "stat_add", stat_id, delta)

    def stats(self) -> tuple[StatRecord, ...]:
        return self.call(PlatformCapability.STATS, "stats")

    def entitlement(self, entitlement_id: str) -> EntitlementRecord:
        return self.call(PlatformCapability.ENTITLEMENTS, "entitlement", entitlement_id)

    def entitlements(self) -> tuple[EntitlementRecord, ...]:
        return self.call(PlatformCapability.ENTITLEMENTS, "entitlements")

    def portable_diagnostics(self) -> dict[str, Any]:
        capabilities: dict[str, Any] = {}
        for capability in PlatformCapability:
            provider = self._providers.get(capability)
            capabilities[capability.value] = {
                "available": provider is not None,
                "provider": None if provider is None else str(getattr(provider, "provider_name")),
                "calls": self._calls[capability],
                "failures": self._failures[capability],
                "last_error_code": self._last_error_code[capability],
            }
        return {"capabilities": capabilities}

    def fingerprint(self) -> str:
        payload = json.dumps(
            self.portable_diagnostics(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _capability(value: PlatformCapability | str) -> PlatformCapability:
        if isinstance(value, PlatformCapability):
            return value
        if not isinstance(value, str):
            raise TypeError("capability must be a PlatformCapability or string")
        try:
            return PlatformCapability(value.strip().lower())
        except ValueError as exc:
            raise ValueError(f"unknown platform capability {value!r}") from exc


__all__ = [
    "AchievementProvider",
    "AchievementRecord",
    "CloudSaveProvider",
    "CloudSaveRecord",
    "EntitlementProvider",
    "EntitlementRecord",
    "IdentityProvider",
    "LocalPlatformProvider",
    "PlatformCallResult",
    "PlatformCapability",
    "PlatformIdentity",
    "PlatformServiceError",
    "PlatformServices",
    "StatRecord",
    "StatsProvider",
]
