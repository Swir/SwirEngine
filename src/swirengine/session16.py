from __future__ import annotations

import math
import secrets
from collections import OrderedDict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .networking import NetworkPacket

SESSION_SNAPSHOT_PACKET_KIND = "swir.session16.snapshot"

TokenFactory = Callable[[], str]


def _bounded_text(value: object, label: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{label} must not exceed {maximum} characters")
    return normalized


def _non_negative_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must not be negative")
    return value


def _positive_int(value: object, label: str) -> int:
    result = _non_negative_int(value, label)
    if result < 1:
        raise ValueError(f"{label} must be positive")
    return result


def _portable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("session metadata floats must be finite")
        return value
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("session metadata mapping keys must be strings")
            result[key] = _portable(item)
        return result
    raise TypeError(f"unsupported session metadata value type: {type(value).__name__}")


class SessionPhase(str, Enum):
    LOBBY = "lobby"
    MATCH = "match"
    CLOSED = "closed"


class SessionOperationError(RuntimeError):
    """Creator-readable lifecycle failure with a stable diagnostic code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(slots=True, frozen=True)
class SessionMember:
    client_id: str
    join_order: int
    connected: bool
    ready: bool
    roles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "client_id", _bounded_text(self.client_id, "client_id", maximum=128))
        object.__setattr__(self, "join_order", _non_negative_int(self.join_order, "join_order"))
        if not isinstance(self.connected, bool):
            raise TypeError("connected must be a boolean")
        if not isinstance(self.ready, bool):
            raise TypeError("ready must be a boolean")
        roles = tuple(sorted(_bounded_text(role, "role", maximum=64) for role in self.roles))
        if len(set(roles)) != len(roles):
            raise ValueError("member roles must be unique")
        object.__setattr__(self, "roles", roles)

    def to_payload(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "join_order": self.join_order,
            "connected": self.connected,
            "ready": self.ready,
            "roles": list(self.roles),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> SessionMember:
        roles = payload.get("roles", [])
        if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
            raise TypeError("session member roles must be a list of strings")
        return cls(
            client_id=payload.get("client_id"),
            join_order=payload.get("join_order"),
            connected=payload.get("connected"),
            ready=payload.get("ready"),
            roles=tuple(roles),
        )


@dataclass(slots=True, frozen=True)
class SessionEvent:
    sequence: int
    kind: str
    client_id: str
    phase: SessionPhase
    details: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _positive_int(self.sequence, "event sequence"))
        object.__setattr__(self, "kind", _bounded_text(self.kind, "event kind", maximum=96))
        object.__setattr__(self, "client_id", _bounded_text(self.client_id, "client_id", maximum=128))
        object.__setattr__(self, "phase", SessionPhase(self.phase))
        details = _portable(self.details)
        if not isinstance(details, dict):
            raise TypeError("event details must be a mapping")
        object.__setattr__(self, "details", details)


@dataclass(slots=True, frozen=True)
class SessionJoinResult:
    member: SessionMember
    resume_token: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "resume_token",
            _bounded_text(self.resume_token, "resume_token", maximum=512),
        )


@dataclass(slots=True, frozen=True)
class SessionSnapshot:
    session_id: str
    revision: int
    phase: SessionPhase
    host_client_id: str
    members: tuple[SessionMember, ...]
    role_owners: dict[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _bounded_text(self.session_id, "session_id", maximum=128))
        object.__setattr__(self, "revision", _non_negative_int(self.revision, "revision"))
        object.__setattr__(self, "phase", SessionPhase(self.phase))
        object.__setattr__(
            self,
            "host_client_id",
            _bounded_text(self.host_client_id, "host_client_id", maximum=128),
        )
        members = tuple(self.members)
        if len({member.client_id for member in members}) != len(members):
            raise ValueError("session snapshot member ids must be unique")
        if [member.join_order for member in members] != sorted(
            member.join_order for member in members
        ):
            raise ValueError("session snapshot members must use deterministic join order")
        member_ids = {member.client_id for member in members}
        if self.phase is not SessionPhase.CLOSED and self.host_client_id not in member_ids:
            raise ValueError("open session snapshot host must be present in roster")

        role_owners: dict[str, str] = {}
        for role, owner in self.role_owners.items():
            normalized_role = _bounded_text(role, "role", maximum=64)
            normalized_owner = _bounded_text(owner, "role owner", maximum=128)
            if normalized_owner not in member_ids:
                raise ValueError("role owner must be present in session roster")
            role_owners[normalized_role] = normalized_owner
        if self.phase is not SessionPhase.CLOSED:
            if role_owners.get("host") != self.host_client_id:
                raise ValueError("open session snapshot must bind the host role to host_client_id")

        expected_roles = {
            (role, owner)
            for role, owner in role_owners.items()
        }
        actual_roles = {
            (role, member.client_id)
            for member in members
            for role in member.roles
        }
        if expected_roles != actual_roles:
            raise ValueError("member roles and role ownership table must agree")
        object.__setattr__(self, "members", members)
        object.__setattr__(self, "role_owners", dict(sorted(role_owners.items())))

    def to_packet(self) -> NetworkPacket:
        return NetworkPacket(
            SESSION_SNAPSHOT_PACKET_KIND,
            {
                "session_id": self.session_id,
                "revision": self.revision,
                "phase": self.phase.value,
                "host_client_id": self.host_client_id,
                "members": [member.to_payload() for member in self.members],
                "role_owners": dict(self.role_owners),
            },
        )

    @classmethod
    def from_packet(cls, packet: NetworkPacket) -> SessionSnapshot:
        if packet.kind != SESSION_SNAPSHOT_PACKET_KIND:
            raise ValueError(f"expected {SESSION_SNAPSHOT_PACKET_KIND}, got {packet.kind}")
        payload = packet.payload
        members_payload = payload.get("members")
        role_owners = payload.get("role_owners")
        if not isinstance(members_payload, list):
            raise TypeError("session snapshot members must be a list")
        if not isinstance(role_owners, Mapping):
            raise TypeError("session snapshot role_owners must be an object")
        members: list[SessionMember] = []
        for item in members_payload:
            if not isinstance(item, Mapping):
                raise TypeError("session snapshot member must be an object")
            members.append(SessionMember.from_payload(item))
        if not all(isinstance(role, str) and isinstance(owner, str) for role, owner in role_owners.items()):
            raise TypeError("session snapshot role ownership must map strings to strings")
        return cls(
            session_id=payload.get("session_id"),
            revision=payload.get("revision"),
            phase=payload.get("phase"),
            host_client_id=payload.get("host_client_id"),
            members=tuple(members),
            role_owners=dict(role_owners),
        )


@dataclass(slots=True)
class _MemberState:
    client_id: str
    join_order: int
    connected: bool = True
    ready: bool = False
    roles: set[str] | None = None

    def __post_init__(self) -> None:
        if self.roles is None:
            self.roles = set()


class SessionLifecycle:
    """Deterministic, bounded lobby/match lifecycle for creator-owned multiplayer sessions."""

    def __init__(
        self,
        session_id: str,
        host_client_id: str,
        *,
        max_members: int = 16,
        max_resume_tokens: int = 32,
        max_events: int = 256,
        token_factory: TokenFactory | None = None,
    ) -> None:
        self.session_id = _bounded_text(session_id, "session_id", maximum=128)
        host_client_id = _bounded_text(host_client_id, "host_client_id", maximum=128)
        self.max_members = _positive_int(max_members, "max_members")
        self.max_resume_tokens = _positive_int(max_resume_tokens, "max_resume_tokens")
        self.max_events = _positive_int(max_events, "max_events")
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(24))
        if not callable(self._token_factory):
            raise TypeError("token_factory must be callable")

        self.phase = SessionPhase.LOBBY
        self._host_client_id = host_client_id
        self._members: dict[str, _MemberState] = {}
        self._role_owners: dict[str, str] = {}
        self._tokens: OrderedDict[str, str] = OrderedDict()
        self._token_by_client: dict[str, str] = {}
        self._events: deque[SessionEvent] = deque(maxlen=self.max_events)
        self._failure_counts: dict[str, int] = {}
        self._revision = 0
        self._event_sequence = 0
        self._next_join_order = 0
        self._token_evictions = 0
        self._event_evictions = 0
        self._successful_mutations = 0

        host = _MemberState(host_client_id, self._next_join_order, roles={"host"})
        self._next_join_order += 1
        token = self._new_token()
        self._members[host_client_id] = host
        self._role_owners["host"] = host_client_id
        self._register_token(host_client_id, token)
        self._record("session.hosted", host_client_id)

    @property
    def host_client_id(self) -> str:
        return self._host_client_id

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def members(self) -> tuple[SessionMember, ...]:
        return tuple(
            self._public_member(state)
            for state in sorted(self._members.values(), key=lambda member: member.join_order)
        )

    @property
    def role_owners(self) -> dict[str, str]:
        return dict(sorted(self._role_owners.items()))

    def member(self, client_id: str) -> SessionMember:
        state = self._require_member(client_id)
        return self._public_member(state)

    def role_owner(self, role: str) -> str | None:
        role = _bounded_text(role, "role", maximum=64)
        return self._role_owners.get(role)

    def resume_token_for(self, client_id: str) -> str:
        client_id = _bounded_text(client_id, "client_id", maximum=128)
        self._require_member(client_id)
        token = self._token_by_client.get(client_id)
        if token is None:
            self._fail("resume_token_unavailable", "client does not have an active resume token")
        return token

    def join(self, client_id: str) -> SessionJoinResult:
        self._require_phase(SessionPhase.LOBBY)
        client_id = _bounded_text(client_id, "client_id", maximum=128)
        if client_id in self._members:
            self._fail("duplicate_member", "client is already part of the session")
        if len(self._members) >= self.max_members:
            self._fail("session_full", "session member limit has been reached")
        token = self._new_token()
        state = _MemberState(client_id, self._next_join_order)
        self._next_join_order += 1
        self._members[client_id] = state
        self._register_token(client_id, token)
        self._record("member.joined", client_id)
        return SessionJoinResult(self._public_member(state), token)

    def leave(self, client_id: str) -> None:
        self._require_open()
        state = self._require_member(client_id)
        if state.client_id == self._host_client_id and len(self._members) > 1:
            self._fail(
                "host_transfer_required",
                "host must transfer ownership before leaving a non-empty session",
            )
        if state.client_id == self._host_client_id:
            self._remove_member(state.client_id)
            self.phase = SessionPhase.CLOSED
            self._record("session.closed", state.client_id)
            return
        self._remove_member(state.client_id)
        self._record("member.left", state.client_id)

    def disconnect(self, client_id: str) -> SessionMember:
        self._require_open()
        state = self._require_member(client_id)
        if not state.connected:
            self._fail("already_disconnected", "client is already disconnected")
        state.connected = False
        state.ready = False
        self._record("member.disconnected", state.client_id)
        return self._public_member(state)

    def resume(self, resume_token: str) -> SessionJoinResult:
        self._require_open()
        resume_token = _bounded_text(resume_token, "resume_token", maximum=512)
        client_id = self._tokens.get(resume_token)
        if client_id is None:
            self._fail("invalid_resume_token", "resume token is unknown or expired")
        state = self._members.get(client_id)
        if state is None:
            self._fail("invalid_resume_token", "resume token does not reference an active member")
        if state.connected:
            self._fail("already_connected", "resume token belongs to an already connected member")
        replacement = self._new_token()
        state.connected = True
        state.ready = False
        self._register_token(client_id, replacement)
        self._record("member.resumed", client_id)
        return SessionJoinResult(self._public_member(state), replacement)

    def set_ready(self, client_id: str, ready: bool = True) -> SessionMember:
        self._require_phase(SessionPhase.LOBBY)
        if not isinstance(ready, bool):
            raise TypeError("ready must be a boolean")
        state = self._require_member(client_id)
        if not state.connected:
            self._fail("member_disconnected", "disconnected member cannot change ready state")
        if state.ready == ready:
            return self._public_member(state)
        state.ready = ready
        self._record("member.ready" if ready else "member.unready", state.client_id)
        return self._public_member(state)

    def claim_role(self, client_id: str, role: str) -> SessionMember:
        self._require_phase(SessionPhase.LOBBY)
        state = self._require_connected_member(client_id)
        role = _bounded_text(role, "role", maximum=64)
        if role == "host":
            self._fail("protected_role", "host role can only change through transfer_host")
        owner = self._role_owners.get(role)
        if owner == state.client_id:
            return self._public_member(state)
        if owner is not None:
            self._fail("role_owned", f"role {role!r} is already owned")
        self._role_owners[role] = state.client_id
        assert state.roles is not None
        state.roles.add(role)
        self._record("role.claimed", state.client_id, {"role": role})
        return self._public_member(state)

    def release_role(self, client_id: str, role: str) -> SessionMember:
        self._require_phase(SessionPhase.LOBBY)
        state = self._require_connected_member(client_id)
        role = _bounded_text(role, "role", maximum=64)
        if role == "host":
            self._fail("protected_role", "host role can only change through transfer_host")
        if self._role_owners.get(role) != state.client_id:
            self._fail("role_not_owned", f"client does not own role {role!r}")
        del self._role_owners[role]
        assert state.roles is not None
        state.roles.remove(role)
        self._record("role.released", state.client_id, {"role": role})
        return self._public_member(state)

    def transfer_host(self, requester_id: str, target_client_id: str) -> SessionMember:
        self._require_phase(SessionPhase.LOBBY)
        self._require_host(requester_id)
        target = self._require_connected_member(target_client_id)
        if target.client_id == self._host_client_id:
            return self._public_member(target)
        previous = self._members[self._host_client_id]
        assert previous.roles is not None
        assert target.roles is not None
        previous.roles.remove("host")
        target.roles.add("host")
        old_host = self._host_client_id
        self._host_client_id = target.client_id
        self._role_owners["host"] = target.client_id
        self._record("host.transferred", target.client_id, {"previous_host": old_host})
        return self._public_member(target)

    def start_match(self, requester_id: str) -> SessionSnapshot:
        self._require_phase(SessionPhase.LOBBY)
        self._require_host(requester_id)
        disconnected = [member.client_id for member in self._members.values() if not member.connected]
        if disconnected:
            self._fail("members_disconnected", "all roster members must be connected before match start")
        unready = [member.client_id for member in self._members.values() if not member.ready]
        if unready:
            self._fail("members_not_ready", "all roster members must be ready before match start")
        self.phase = SessionPhase.MATCH
        self._record("match.started", self._host_client_id)
        return self.snapshot()

    def end_match(self, requester_id: str) -> SessionSnapshot:
        self._require_phase(SessionPhase.MATCH)
        self._require_host(requester_id)
        self.phase = SessionPhase.LOBBY
        for member in self._members.values():
            member.ready = False
        self._record("match.ended", self._host_client_id)
        return self.snapshot()

    def events(self, *, since_sequence: int = 0) -> tuple[SessionEvent, ...]:
        since_sequence = _non_negative_int(since_sequence, "since_sequence")
        return tuple(event for event in self._events if event.sequence > since_sequence)

    def snapshot(self) -> SessionSnapshot:
        return SessionSnapshot(
            session_id=self.session_id,
            revision=self._revision,
            phase=self.phase,
            host_client_id=self._host_client_id,
            members=self.members,
            role_owners=self.role_owners,
        )

    def diagnostics(self) -> dict[str, Any]:
        members = tuple(self._members.values())
        return {
            "revision": self._revision,
            "phase": self.phase.value,
            "members": len(members),
            "connected_members": sum(member.connected for member in members),
            "ready_members": sum(member.ready for member in members),
            "active_resume_tokens": len(self._tokens),
            "token_evictions": self._token_evictions,
            "events_emitted": self._event_sequence,
            "retained_events": len(self._events),
            "event_evictions": self._event_evictions,
            "successful_mutations": self._successful_mutations,
            "failures_total": sum(self._failure_counts.values()),
            "failure_counts": dict(sorted(self._failure_counts.items())),
        }

    def _public_member(self, state: _MemberState) -> SessionMember:
        return SessionMember(
            client_id=state.client_id,
            join_order=state.join_order,
            connected=state.connected,
            ready=state.ready,
            roles=tuple(state.roles or ()),
        )

    def _new_token(self) -> str:
        token = _bounded_text(self._token_factory(), "resume_token", maximum=512)
        if len(token) < 8:
            raise ValueError("resume_token must contain at least 8 characters")
        if token in self._tokens:
            raise ValueError("token_factory returned a duplicate active resume token")
        return token

    def _register_token(self, client_id: str, token: str) -> None:
        previous = self._token_by_client.pop(client_id, None)
        if previous is not None:
            self._tokens.pop(previous, None)
        self._tokens[token] = client_id
        self._token_by_client[client_id] = token
        while len(self._tokens) > self.max_resume_tokens:
            expired, expired_client = self._tokens.popitem(last=False)
            if self._token_by_client.get(expired_client) == expired:
                del self._token_by_client[expired_client]
            self._token_evictions += 1

    def _remove_member(self, client_id: str) -> None:
        state = self._members.pop(client_id)
        for role in tuple(state.roles or ()):
            self._role_owners.pop(role, None)
        token = self._token_by_client.pop(client_id, None)
        if token is not None:
            self._tokens.pop(token, None)

    def _require_open(self) -> None:
        if self.phase is SessionPhase.CLOSED:
            self._fail("session_closed", "session is closed")

    def _require_phase(self, *phases: SessionPhase) -> None:
        if self.phase not in phases:
            expected = ", ".join(phase.value for phase in phases)
            self._fail("invalid_phase", f"operation requires session phase: {expected}")

    def _require_member(self, client_id: str) -> _MemberState:
        client_id = _bounded_text(client_id, "client_id", maximum=128)
        state = self._members.get(client_id)
        if state is None:
            self._fail("member_not_found", "client is not part of the session")
        return state

    def _require_connected_member(self, client_id: str) -> _MemberState:
        state = self._require_member(client_id)
        if not state.connected:
            self._fail("member_disconnected", "operation requires a connected member")
        return state

    def _require_host(self, requester_id: str) -> None:
        requester_id = _bounded_text(requester_id, "requester_id", maximum=128)
        if requester_id != self._host_client_id:
            self._fail("host_required", "operation requires the current host")
        self._require_connected_member(requester_id)

    def _record(
        self,
        kind: str,
        client_id: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self._revision += 1
        self._event_sequence += 1
        self._successful_mutations += 1
        if len(self._events) == self.max_events:
            self._event_evictions += 1
        self._events.append(
            SessionEvent(
                sequence=self._event_sequence,
                kind=kind,
                client_id=client_id,
                phase=self.phase,
                details=dict(details or {}),
            )
        )

    def _fail(self, code: str, message: str) -> None:
        self._failure_counts[code] = self._failure_counts.get(code, 0) + 1
        raise SessionOperationError(code, message)


__all__ = [
    "SESSION_SNAPSHOT_PACKET_KIND",
    "SessionEvent",
    "SessionJoinResult",
    "SessionLifecycle",
    "SessionMember",
    "SessionOperationError",
    "SessionPhase",
    "SessionSnapshot",
    "TokenFactory",
]
