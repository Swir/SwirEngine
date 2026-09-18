from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .multiplayer14 import WorldSnapshot
from .multiplayer16 import InterestManager, InterestView, ReplicationStreamServer, ReplicationUpdate
from .server16 import (
    DedicatedServerConfig,
    DedicatedServerRuntime,
    HeadlessRuntimeBoundary,
    ServerComponent,
    ServerTick,
)
from .session16 import (
    SessionJoinResult,
    SessionLifecycle,
    SessionMember,
    SessionPhase,
    SessionSnapshot,
)

SnapshotFactory = Callable[[ServerTick], WorldSnapshot]

_LOCAL_ONLY_FIELDS = frozenset(
    {
        "accessibility",
        "controls",
        "display",
        "input_bindings",
        "profile",
        "save",
        "settings",
    }
)


class MultiplayerContractError(RuntimeError):
    """Creator-facing 2.0 multiplayer production-contract failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _bounded_text(value: object, label: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{label} must not exceed {maximum} characters")
    return normalized


def _portable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("multiplayer state floats must be finite")
        return value
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("multiplayer state mapping keys must be strings")
            result[key] = _portable(item)
        return result
    raise TypeError(f"unsupported multiplayer state value: {type(value).__name__}")


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        _portable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _local_only_paths(value: Any, *, prefix: str = "") -> tuple[str, ...]:
    matches: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            path = f"{prefix}.{key}" if prefix else key
            if key.casefold() in _LOCAL_ONLY_FIELDS:
                matches.append(path)
            matches.extend(_local_only_paths(item, prefix=path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            matches.extend(_local_only_paths(item, prefix=path))
    return tuple(matches)


@dataclass(slots=True, frozen=True)
class MultiplayerCompatibility:
    """Deterministic join contract shared by clients and authoritative servers."""

    project_id: str
    protocol_version: str
    build_id: str
    replication_schema: str
    content_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", _bounded_text(self.project_id, "project_id", maximum=128))
        object.__setattr__(
            self,
            "protocol_version",
            _bounded_text(self.protocol_version, "protocol_version", maximum=64),
        )
        object.__setattr__(self, "build_id", _bounded_text(self.build_id, "build_id", maximum=128))
        object.__setattr__(
            self,
            "replication_schema",
            _bounded_text(self.replication_schema, "replication_schema", maximum=128),
        )
        object.__setattr__(
            self,
            "content_fingerprint",
            _bounded_text(self.content_fingerprint, "content_fingerprint", maximum=128),
        )

    def portable(self) -> dict[str, str]:
        return {
            "project_id": self.project_id,
            "protocol_version": self.protocol_version,
            "build_id": self.build_id,
            "replication_schema": self.replication_schema,
            "content_fingerprint": self.content_fingerprint,
        }

    def fingerprint(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.portable())).hexdigest()

    def mismatches(self, other: MultiplayerCompatibility) -> tuple[str, ...]:
        if not isinstance(other, MultiplayerCompatibility):
            raise TypeError("other must be a MultiplayerCompatibility")
        return tuple(
            field
            for field in (
                "project_id",
                "protocol_version",
                "build_id",
                "replication_schema",
                "content_fingerprint",
            )
            if getattr(self, field) != getattr(other, field)
        )

    def require_compatible(self, other: MultiplayerCompatibility) -> None:
        mismatches = self.mismatches(other)
        if mismatches:
            fields = ", ".join(mismatches)
            raise MultiplayerContractError(
                "compatibility_mismatch",
                f"client multiplayer contract differs from server: {fields}",
            )


@dataclass(slots=True, frozen=True)
class PlayerLocalState:
    """Explicit client-owned state that must never enter authoritative server state."""

    client_id: str
    settings: dict[str, Any]
    save: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "client_id", _bounded_text(self.client_id, "client_id", maximum=128))
        settings = _portable(self.settings)
        save = _portable(self.save)
        if not isinstance(settings, dict) or not isinstance(save, dict):
            raise TypeError("settings and save must be mappings")
        object.__setattr__(self, "settings", settings)
        object.__setattr__(self, "save", save)

    def portable(self) -> dict[str, Any]:
        return copy.deepcopy(
            {
                "client_id": self.client_id,
                "settings": self.settings,
                "save": self.save,
            }
        )


@dataclass(slots=True, frozen=True)
class ReconnectResult:
    join: SessionJoinResult
    resynchronization: ReplicationUpdate | None


class ProductionMultiplayerSession:
    """High-level 2.0 session/replication contract for real-game workflows.

    The server owns session lifecycle and authoritative gameplay state. Player settings,
    controls, accessibility preferences and save/profile data remain client-local.
    """

    def __init__(
        self,
        session_id: str,
        host_client_id: str,
        compatibility: MultiplayerCompatibility,
        *,
        max_members: int = 16,
        interest: InterestManager | None = None,
        token_factory: Callable[[], str] | None = None,
        max_authoritative_state_bytes: int = 64 * 1024,
    ) -> None:
        if not isinstance(compatibility, MultiplayerCompatibility):
            raise TypeError("compatibility must be a MultiplayerCompatibility")
        if not isinstance(max_authoritative_state_bytes, int) or isinstance(
            max_authoritative_state_bytes, bool
        ):
            raise TypeError("max_authoritative_state_bytes must be an integer")
        if max_authoritative_state_bytes < 256:
            raise ValueError("max_authoritative_state_bytes must be at least 256")
        self.compatibility = compatibility
        self.lifecycle = SessionLifecycle(
            session_id,
            host_client_id,
            max_members=max_members,
            token_factory=token_factory,
        )
        self.replication = ReplicationStreamServer(interest=interest)
        self.replication.register_client(host_client_id)
        self.max_authoritative_state_bytes = max_authoritative_state_bytes
        self._authoritative_player_state: dict[str, dict[str, Any]] = {host_client_id: {}}

    @property
    def host_resume_token(self) -> str:
        return self.lifecycle.resume_token_for(self.lifecycle.host_client_id)

    def join(
        self,
        client_id: str,
        compatibility: MultiplayerCompatibility,
        *,
        view: InterestView | None = None,
    ) -> SessionJoinResult:
        self.compatibility.require_compatible(compatibility)
        result = self.lifecycle.join(client_id)
        try:
            self.replication.register_client(result.member.client_id, view)
        except (TypeError, ValueError):
            self.lifecycle.leave(result.member.client_id)
            raise
        self._authoritative_player_state[result.member.client_id] = {}
        return result

    def disconnect(self, client_id: str) -> SessionMember:
        return self.lifecycle.disconnect(client_id)

    def resume(
        self,
        resume_token: str,
        compatibility: MultiplayerCompatibility,
        *,
        view: InterestView | None = None,
    ) -> ReconnectResult:
        self.compatibility.require_compatible(compatibility)
        result = self.lifecycle.resume(resume_token)
        if view is not None:
            self.replication.update_view(result.member.client_id, view)
        update = None
        if self.replication.latest_tick is not None:
            update = self.replication.resynchronize(result.member.client_id)
        return ReconnectResult(result, update)

    def leave(self, client_id: str) -> None:
        self.lifecycle.leave(client_id)
        self.replication.unregister_client(client_id)
        self._authoritative_player_state.pop(client_id, None)

    def set_ready(self, client_id: str, ready: bool = True) -> SessionMember:
        return self.lifecycle.set_ready(client_id, ready)

    def start_match(self, requester_id: str) -> SessionSnapshot:
        return self.lifecycle.start_match(requester_id)

    def end_match(self, requester_id: str) -> SessionSnapshot:
        return self.lifecycle.end_match(requester_id)

    def update_view(self, client_id: str, view: InterestView) -> None:
        self.replication.update_view(client_id, view)

    def publish_authoritative(self, snapshot: WorldSnapshot) -> None:
        if self.lifecycle.phase is not SessionPhase.MATCH:
            raise MultiplayerContractError(
                "match_not_running",
                "authoritative world snapshots may only be published during an active match",
            )
        self.replication.publish(snapshot)

    def build_update(self, client_id: str) -> ReplicationUpdate:
        return self.replication.build_update(client_id)

    def acknowledge(self, client_id: str, tick: int) -> bool:
        return self.replication.acknowledge(client_id, tick)

    def set_authoritative_player_state(
        self,
        client_id: str,
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.lifecycle.member(client_id)
        normalized = _portable(state)
        if not isinstance(normalized, dict):
            raise TypeError("authoritative player state must be a mapping")
        forbidden = sorted(_local_only_paths(normalized))
        if forbidden:
            raise MultiplayerContractError(
                "player_local_state_forbidden",
                "authoritative state cannot contain client-local fields: " + ", ".join(forbidden),
            )
        encoded = _canonical_bytes(normalized)
        if len(encoded) > self.max_authoritative_state_bytes:
            raise MultiplayerContractError(
                "authoritative_state_too_large",
                "authoritative player state exceeds the configured byte limit",
            )
        self._authoritative_player_state[client_id] = normalized
        return copy.deepcopy(normalized)

    def authoritative_player_state(self, client_id: str) -> dict[str, Any]:
        self.lifecycle.member(client_id)
        return copy.deepcopy(self._authoritative_player_state.get(client_id, {}))

    def status(self) -> dict[str, Any]:
        snapshot = self.lifecycle.snapshot()
        return {
            "session_id": snapshot.session_id,
            "phase": snapshot.phase.value,
            "revision": snapshot.revision,
            "host_client_id": snapshot.host_client_id,
            "members": [
                {
                    "client_id": member.client_id,
                    "connected": member.connected,
                    "ready": member.ready,
                    "roles": list(member.roles),
                }
                for member in snapshot.members
            ],
            "replication_clients": list(self.replication.client_ids),
            "compatibility_fingerprint": self.compatibility.fingerprint(),
            "authoritative_player_state": {
                client_id: copy.deepcopy(self._authoritative_player_state.get(client_id, {}))
                for client_id in sorted(self._authoritative_player_state)
            },
        }

    def diagnostics(self) -> dict[str, Any]:
        return {
            "session": self.lifecycle.diagnostics(),
            "replication": {
                client_id: self.replication.diagnostics(client_id)
                for client_id in self.replication.client_ids
            },
            "compatibility_fingerprint": self.compatibility.fingerprint(),
        }


class DedicatedMultiplayerServer:
    """Validated headless runtime adapter for a production multiplayer session."""

    def __init__(
        self,
        session: ProductionMultiplayerSession,
        snapshot_factory: SnapshotFactory,
        *,
        config: DedicatedServerConfig | None = None,
    ) -> None:
        if not isinstance(session, ProductionMultiplayerSession):
            raise TypeError("session must be a ProductionMultiplayerSession")
        if not callable(snapshot_factory):
            raise TypeError("snapshot_factory must be callable")
        self.session = session
        self.snapshot_factory = snapshot_factory
        self.runtime = DedicatedServerRuntime(
            config=config or DedicatedServerConfig(),
            boundary=HeadlessRuntimeBoundary(),
        )
        self.runtime.register(
            ServerComponent(
                name="multiplayer-authority",
                tick=self._tick,
                capabilities=("network", "storage"),
                ready_check=lambda: self.session.lifecycle.phase is not SessionPhase.CLOSED,
                health_check=lambda: self.session.lifecycle.phase is not SessionPhase.CLOSED,
            )
        )

    def _tick(self, tick: ServerTick) -> None:
        if self.session.lifecycle.phase is not SessionPhase.MATCH:
            return
        snapshot = self.snapshot_factory(tick)
        if not isinstance(snapshot, WorldSnapshot):
            raise TypeError("snapshot_factory must return WorldSnapshot")
        if snapshot.tick != tick.tick:
            raise MultiplayerContractError(
                "snapshot_tick_mismatch",
                "snapshot_factory must preserve the dedicated-server authoritative tick",
            )
        self.session.publish_authoritative(snapshot)

    def validate_startup(self) -> dict[str, Any]:
        report = self.runtime.validate_startup()
        return {
            "components": list(report.component_order),
            "required_assets": [
                {"path": item.path, "kind": item.kind, "required": item.required}
                for item in report.required_assets
            ],
            "compatibility_fingerprint": self.session.compatibility.fingerprint(),
            "headless": True,
        }

    def deployment_manifest(self) -> dict[str, Any]:
        return {
            "headless": True,
            "compatibility": self.session.compatibility.portable(),
            "compatibility_fingerprint": self.session.compatibility.fingerprint(),
            "server": self.runtime.config.portable(),
            "capabilities": sorted(self.runtime.boundary.allowed_capabilities),
            "forbidden_player_local_fields": sorted(_LOCAL_ONLY_FIELDS),
        }


__all__ = [
    "DedicatedMultiplayerServer",
    "MultiplayerCompatibility",
    "MultiplayerContractError",
    "PlayerLocalState",
    "ProductionMultiplayerSession",
    "ReconnectResult",
]
