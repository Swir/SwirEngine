from __future__ import annotations

import math
import os
import re
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .background_save17 import (
    BackgroundSaveDiagnostics,
    BackgroundSaveOutcome,
    BackgroundSavePipeline,
    BackgroundSaveState,
    PreparedSaveSnapshot,
)
from .shipping19 import GameSettings, SettingsStore
from .storage import MigrationRegistry
from .storage15 import AutosavePolicy, ProfileSaveManager2, SaveLoadResult, SaveSlotInfo

_APP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
_PROFILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_RESERVED_MANUAL_PREFIX = "swir-autosave"
_DEFAULT_MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024


class GameStateProductionError(ValueError):
    """Raised when production save/profile configuration is unsafe or inconsistent."""


@dataclass(frozen=True, slots=True)
class UserDataLocation:
    """Resolved per-project user-data root and the policy source that selected it."""

    root: Path
    platform: str
    source: str

    def portable(self) -> Mapping[str, str]:
        return MappingProxyType(
            {
                "root": str(self.root),
                "platform": self.platform,
                "source": self.source,
            }
        )


@dataclass(frozen=True, slots=True)
class SaveProductionPolicy:
    """Bounded production policy for manual saves, autosaves and background I/O."""

    autosave_keep: int = 3
    autosave_interval_seconds: float = 120.0
    max_manual_slots: int = 16
    max_snapshot_bytes: int = _DEFAULT_MAX_SNAPSHOT_BYTES
    max_background_requests: int = 16
    max_workers: int = 2

    def __post_init__(self) -> None:
        _bounded_int(self.autosave_keep, "autosave_keep", minimum=1, maximum=16)
        _finite_number(
            self.autosave_interval_seconds,
            "autosave_interval_seconds",
            minimum=0.0,
            maximum=86_400.0,
        )
        _bounded_int(self.max_manual_slots, "max_manual_slots", minimum=1, maximum=64)
        _bounded_int(
            self.max_snapshot_bytes,
            "max_snapshot_bytes",
            minimum=1_024,
            maximum=64 * 1024 * 1024,
        )
        _bounded_int(
            self.max_background_requests,
            "max_background_requests",
            minimum=1,
            maximum=256,
        )
        _bounded_int(self.max_workers, "max_workers", minimum=1, maximum=8)


@dataclass(frozen=True, slots=True)
class GameStateDiagnostics:
    app_id: str
    profile: str
    user_data_root: Path
    manual_submitted: int
    autosave_submitted: int
    loads: int
    recoveries: int
    migrations: int
    snapshot_rejections: int
    pipeline: BackgroundSaveDiagnostics

    def portable(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "app_id": self.app_id,
                "profile": self.profile,
                "user_data_root": str(self.user_data_root),
                "manual_submitted": self.manual_submitted,
                "autosave_submitted": self.autosave_submitted,
                "loads": self.loads,
                "recoveries": self.recoveries,
                "migrations": self.migrations,
                "snapshot_rejections": self.snapshot_rejections,
                "pipeline": dict(self.pipeline.portable()),
            }
        )


def project_app_id(name: str) -> str:
    """Create a stable readable app id from a project name.

    Creators should keep this identifier stable after shipping because it owns the
    desktop user-data directory.
    """

    if not isinstance(name, str):
        raise TypeError("project name must be a string")
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", name.strip()).strip("._-")
    normalized = normalized[:96]
    if not normalized:
        raise GameStateProductionError("project name cannot produce a valid app id")
    _validate_identifier(normalized, label="app_id", pattern=_APP_ID_RE)
    return normalized


def resolve_user_data_root(
    app_id: str,
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: str | Path | None = None,
) -> UserDataLocation:
    """Resolve a portable desktop user-data root without creating directories.

    Windows uses LOCALAPPDATA when it is an absolute path, macOS uses
    ``~/Library/Application Support`` and Linux follows XDG_DATA_HOME when that
    variable is absolute. Relative environment overrides are ignored.
    """

    _validate_identifier(app_id, label="app_id", pattern=_APP_ID_RE)
    selected_platform = (platform or sys.platform).lower()
    values = os.environ if environ is None else environ
    home_path = Path.home() if home is None else Path(home).expanduser()

    if selected_platform.startswith("win"):
        override = values.get("LOCALAPPDATA", "")
        candidate = Path(override).expanduser() if override else Path()
        if override and candidate.is_absolute():
            base = candidate
            source = "LOCALAPPDATA"
        else:
            base = home_path / "AppData" / "Local"
            source = "home-fallback"
        return UserDataLocation(base / "SwirEngine" / app_id, "windows", source)

    if selected_platform == "darwin":
        return UserDataLocation(
            home_path / "Library" / "Application Support" / "SwirEngine" / app_id,
            "macos",
            "home",
        )

    if selected_platform.startswith("linux"):
        override = values.get("XDG_DATA_HOME", "")
        candidate = Path(override).expanduser() if override else Path()
        if override and candidate.is_absolute():
            base = candidate
            source = "XDG_DATA_HOME"
        else:
            base = home_path / ".local" / "share"
            source = "xdg-fallback"
        return UserDataLocation(base / "swirengine" / app_id, "linux", source)

    raise GameStateProductionError(
        f"unsupported desktop platform for user-data policy: {selected_platform!r}"
    )


class ProductionGameStateSession:
    """Production orchestration around stable save/profile/background-save systems.

    The session owns no gameplay objects. Creator state is captured into an immutable
    portable JSON snapshot on the caller thread before any background write begins.
    """

    def __init__(
        self,
        app_id: str,
        *,
        profile: str = "default",
        user_data_root: str | Path | None = None,
        platform: str | None = None,
        environ: Mapping[str, str] | None = None,
        home: str | Path | None = None,
        version: int = 1,
        migrations: MigrationRegistry | None = None,
        defaults: Mapping[str, Any] | None = None,
        policy: SaveProductionPolicy | None = None,
    ) -> None:
        _validate_identifier(app_id, label="app_id", pattern=_APP_ID_RE)
        _validate_identifier(profile, label="profile", pattern=_PROFILE_RE)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise GameStateProductionError("version must be an integer >= 1")

        self.app_id = app_id
        self.profile = profile
        self.policy = policy or SaveProductionPolicy()
        if user_data_root is None:
            location = resolve_user_data_root(
                app_id,
                platform=platform,
                environ=environ,
                home=home,
            )
        else:
            location = UserDataLocation(
                Path(user_data_root).expanduser().resolve(strict=False),
                (platform or sys.platform).lower(),
                "explicit",
            )
        self.location = location
        self.manager = ProfileSaveManager2(
            location.root,
            profile,
            version=version,
            migrations=migrations,
            defaults=defaults,
        )
        self.pipeline = BackgroundSavePipeline(
            max_workers=self.policy.max_workers,
            max_requests=self.policy.max_background_requests,
            thread_name_prefix="swir-game-save",
        )
        self._autosave_policy = AutosavePolicy(
            keep=self.policy.autosave_keep,
            prefix=_RESERVED_MANUAL_PREFIX,
        )
        self._manual_slots = {
            info.name for info in self.manager.list_slots() if not self._is_autosave_slot(info.name)
        }
        self._request_counter = 0
        self._active_autosave: str | None = None
        self._last_autosave_at: float | None = None
        self._manual_submitted = 0
        self._autosave_submitted = 0
        self._loads = 0
        self._recoveries = 0
        self._migrations = 0
        self._snapshot_rejections = 0
        self._closed = False

    @classmethod
    def for_project(
        cls,
        project: Any,
        **kwargs: Any,
    ) -> ProductionGameStateSession:
        """Create a session for a loaded ``ProjectManifest`` without schema coupling."""

        name = getattr(project, "name", None)
        if not isinstance(name, str):
            raise TypeError("project must expose a string name")
        return cls(project_app_id(name), **kwargs)

    @property
    def profile_directory(self) -> Path:
        return self.manager.legacy_profile.paths.directory

    @property
    def settings_path(self) -> Path:
        return self.profile_directory / "config" / "game-settings.json"

    def settings_store(self, defaults: GameSettings | None = None) -> SettingsStore:
        """Return the 1.9 shipping settings store inside this profile's user data."""

        return SettingsStore(defaults or GameSettings(), self.settings_path)

    def submit_manual(
        self,
        slot: str,
        snapshot: Mapping[str, Any],
        *,
        metadata: Mapping[str, Any] | None = None,
        priority: int = 0,
    ) -> str:
        self._require_open()
        self._validate_manual_slot(slot)
        is_new = slot not in self._manual_slots
        if is_new and len(self._manual_slots) >= self.policy.max_manual_slots:
            raise GameStateProductionError("manual save-slot budget reached")
        request_id = self._next_request_id("manual", slot)
        merged_metadata = dict(metadata or {})
        merged_metadata.update(
            {"save_kind": "manual", "profile": self.profile, "slot": slot}
        )
        self._preflight_snapshot(request_id, snapshot, merged_metadata)
        self.pipeline.submit_profile(
            request_id,
            self.manager,
            slot,
            snapshot,
            metadata=merged_metadata,
            priority=priority,
        )
        self._manual_slots.add(slot)
        self._manual_submitted += 1
        return request_id

    def should_autosave(self, *, now: float | None = None) -> bool:
        self._require_open()
        current = time.monotonic() if now is None else _finite_number(now, "now", minimum=0.0)
        if self._active_autosave is not None:
            state = self.pipeline.state(self._active_autosave)
            if state not in {
                BackgroundSaveState.SUCCEEDED,
                BackgroundSaveState.FAILED,
                BackgroundSaveState.CANCELLED,
            }:
                return False
            self._active_autosave = None
        interval = self.policy.autosave_interval_seconds
        if interval <= 0.0 or self._last_autosave_at is None:
            return True
        return current - self._last_autosave_at >= interval

    def submit_autosave(
        self,
        snapshot: Mapping[str, Any],
        *,
        now: float | None = None,
        force: bool = False,
        metadata: Mapping[str, Any] | None = None,
        priority: int = -10,
    ) -> str | None:
        self._require_open()
        current = time.monotonic() if now is None else _finite_number(now, "now", minimum=0.0)
        if not force and not self.should_autosave(now=current):
            return None
        if self._active_autosave is not None:
            state = self.pipeline.state(self._active_autosave)
            if state not in {
                BackgroundSaveState.SUCCEEDED,
                BackgroundSaveState.FAILED,
                BackgroundSaveState.CANCELLED,
            }:
                if force:
                    raise RuntimeError("an autosave request is already in flight")
                return None
            self._active_autosave = None

        slot, generation, index = self._next_autosave_slot()
        request_id = self._next_request_id("autosave", slot)
        merged_metadata = dict(metadata or {})
        merged_metadata.update(
            {
                "save_kind": "autosave",
                "profile": self.profile,
                "autosave": True,
                "autosave_generation": generation,
                "autosave_index": index,
            }
        )
        self._preflight_snapshot(request_id, snapshot, merged_metadata)
        self.pipeline.submit_profile(
            request_id,
            self.manager,
            slot,
            snapshot,
            metadata=merged_metadata,
            priority=priority,
        )
        self._active_autosave = request_id
        self._last_autosave_at = current
        self._autosave_submitted += 1
        return request_id

    def load(
        self,
        slot: str,
        *,
        repair: bool = True,
        upgrade: bool = False,
    ) -> SaveLoadResult:
        self._require_open()
        result = self.manager.load(slot, repair=repair, upgrade=upgrade)
        self._record_load(result)
        return result

    def load_latest_autosave(
        self,
        *,
        repair: bool = True,
        upgrade: bool = False,
    ) -> SaveLoadResult:
        self._require_open()
        infos = self.manager.list_autosaves(policy=self._autosave_policy)
        if not infos:
            raise FileNotFoundError("no autosave slots exist")
        errors: list[Exception] = []
        for info in infos:
            try:
                return self.load(info.name, repair=repair, upgrade=upgrade)
            except (OSError, TypeError, ValueError, RuntimeError) as exc:
                errors.append(exc)
        raise RuntimeError("no autosave slot could be recovered") from errors[-1]

    def list_manual_slots(self) -> tuple[SaveSlotInfo, ...]:
        self._require_open()
        return tuple(
            info
            for info in self.manager.list_slots()
            if not self._is_autosave_slot(info.name)
        )

    def list_autosaves(self) -> tuple[SaveSlotInfo, ...]:
        self._require_open()
        return self.manager.list_autosaves(policy=self._autosave_policy)

    def poll(self, max_items: int | None = None) -> tuple[BackgroundSaveOutcome, ...]:
        self._require_open()
        outcomes = self.pipeline.poll(max_items=max_items)
        self._consume_outcomes(outcomes)
        return outcomes

    def run_until_idle(
        self,
        *,
        timeout: float | None = None,
        max_items_per_poll: int = 64,
    ) -> tuple[BackgroundSaveOutcome, ...]:
        self._require_open()
        outcomes = self.pipeline.run_until_idle(
            timeout=timeout,
            max_items_per_poll=max_items_per_poll,
        )
        self._consume_outcomes(outcomes)
        return outcomes

    def cancel(self, request_id: str) -> bool:
        self._require_open()
        return self.pipeline.cancel(request_id)

    @property
    def diagnostics(self) -> GameStateDiagnostics:
        return GameStateDiagnostics(
            app_id=self.app_id,
            profile=self.profile,
            user_data_root=self.location.root,
            manual_submitted=self._manual_submitted,
            autosave_submitted=self._autosave_submitted,
            loads=self._loads,
            recoveries=self._recoveries,
            migrations=self._migrations,
            snapshot_rejections=self._snapshot_rejections,
            pipeline=self.pipeline.diagnostics(),
        )

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = False) -> None:
        if self._closed:
            return
        self.pipeline.shutdown(wait=wait, cancel_pending=cancel_pending)
        self._closed = True

    def __enter__(self) -> ProductionGameStateSession:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.shutdown(wait=True, cancel_pending=exc is not None)

    def _preflight_snapshot(
        self,
        request_id: str,
        snapshot: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> None:
        try:
            prepared = PreparedSaveSnapshot.capture(request_id, snapshot, metadata)
        except (TypeError, ValueError):
            self._snapshot_rejections += 1
            raise
        if prepared.byte_size > self.policy.max_snapshot_bytes:
            self._snapshot_rejections += 1
            raise GameStateProductionError(
                "save snapshot exceeds max_snapshot_bytes "
                f"({prepared.byte_size} > {self.policy.max_snapshot_bytes})"
            )

    def _record_load(self, result: SaveLoadResult) -> None:
        self._loads += 1
        self._migrations += result.migrations_applied
        if result.recovered:
            self._recoveries += 1

    def _consume_outcomes(self, outcomes: tuple[BackgroundSaveOutcome, ...]) -> None:
        if self._active_autosave is None:
            return
        if any(outcome.request_id == self._active_autosave for outcome in outcomes):
            self._active_autosave = None

    def _next_autosave_slot(self) -> tuple[str, int, int]:
        infos = self.manager.list_autosaves(policy=self._autosave_policy)
        generation = max((_autosave_generation(info) for info in infos), default=0) + 1
        index = ((generation - 1) % self._autosave_policy.keep) + 1
        return self._autosave_policy.slot_name(index), generation, index

    def _next_request_id(self, kind: str, slot: str) -> str:
        self._request_counter += 1
        return f"{kind}-{self._request_counter}-{slot}"

    def _validate_manual_slot(self, slot: str) -> None:
        _validate_identifier(slot, label="save slot", pattern=_PROFILE_RE)
        if self._is_autosave_slot(slot):
            raise GameStateProductionError(
                f"manual save slots cannot use reserved prefix {_RESERVED_MANUAL_PREFIX!r}"
            )

    @staticmethod
    def _is_autosave_slot(slot: str) -> bool:
        return slot.startswith(f"{_RESERVED_MANUAL_PREFIX}-")

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("production game-state session is closed")


def _autosave_generation(info: SaveSlotInfo) -> int:
    if info.metadata is None:
        return 0
    value = info.metadata.get("autosave_generation", 0)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _validate_identifier(value: str, *, label: str, pattern: re.Pattern[str]) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not pattern.fullmatch(value):
        raise GameStateProductionError(
            f"{label} must use a safe alphanumeric identifier with '.', '_' or '-'"
        )


def _bounded_int(value: int, label: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise GameStateProductionError(f"{label} must be between {minimum} and {maximum}")
    return value


def _finite_number(
    value: float,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise GameStateProductionError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise GameStateProductionError(f"{label} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise GameStateProductionError(f"{label} must be <= {maximum}")
    return result


__all__ = [
    "GameStateDiagnostics",
    "GameStateProductionError",
    "ProductionGameStateSession",
    "SaveProductionPolicy",
    "UserDataLocation",
    "project_app_id",
    "resolve_user_data_root",
]
