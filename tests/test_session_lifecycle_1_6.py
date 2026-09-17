from __future__ import annotations

import pytest

from swirengine.networking import NetworkPacket
from swirengine.session16 import (
    SESSION_SNAPSHOT_PACKET_KIND,
    SessionLifecycle,
    SessionMember,
    SessionOperationError,
    SessionPhase,
    SessionSnapshot,
)


class _TokenFactory:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return f"resume-token-{self.value:04d}"


def _session(**kwargs: object) -> SessionLifecycle:
    return SessionLifecycle("room-1", "host", token_factory=_TokenFactory(), **kwargs)


def _ready_all(session: SessionLifecycle) -> None:
    for member in session.members:
        session.set_ready(member.client_id)


def test_host_initializes_deterministic_lobby_and_protected_host_role() -> None:
    session = _session()

    assert session.phase is SessionPhase.LOBBY
    assert session.host_client_id == "host"
    assert [member.client_id for member in session.members] == ["host"]
    assert session.members[0].join_order == 0
    assert session.members[0].roles == ("host",)
    assert session.role_owners == {"host": "host"}
    assert session.resume_token_for("host") == "resume-token-0001"
    assert session.revision == 1


def test_roster_preserves_join_order_instead_of_client_id_sorting() -> None:
    session = _session()
    session.join("zeta")
    session.join("alpha")
    session.join("middle")

    assert [member.client_id for member in session.members] == [
        "host",
        "zeta",
        "alpha",
        "middle",
    ]
    assert [member.join_order for member in session.members] == [0, 1, 2, 3]


def test_duplicate_and_full_join_fail_atomically_with_diagnostics() -> None:
    session = _session(max_members=2)
    session.join("guest")
    before = session.snapshot()

    with pytest.raises(SessionOperationError) as duplicate:
        session.join("guest")
    assert duplicate.value.code == "duplicate_member"
    with pytest.raises(SessionOperationError) as full:
        session.join("other")
    assert full.value.code == "session_full"

    assert session.snapshot() == before
    assert session.diagnostics()["failure_counts"] == {
        "duplicate_member": 1,
        "session_full": 1,
    }


def test_role_ownership_is_unique_and_release_is_explicit() -> None:
    session = _session()
    session.join("a")
    session.join("b")

    assert session.claim_role("a", "pilot").roles == ("pilot",)
    with pytest.raises(SessionOperationError) as owned:
        session.claim_role("b", "pilot")
    assert owned.value.code == "role_owned"
    assert session.role_owner("pilot") == "a"

    session.release_role("a", "pilot")
    assert session.role_owner("pilot") is None
    assert session.claim_role("b", "pilot").roles == ("pilot",)


def test_host_role_can_only_change_through_deterministic_transfer() -> None:
    session = _session()
    session.join("next-host")

    with pytest.raises(SessionOperationError) as protected:
        session.release_role("host", "host")
    assert protected.value.code == "protected_role"

    session.transfer_host("host", "next-host")
    assert session.host_client_id == "next-host"
    assert session.role_owners["host"] == "next-host"
    assert session.member("host").roles == ()
    assert session.member("next-host").roles == ("host",)


def test_only_host_can_transfer_or_start_match() -> None:
    session = _session()
    session.join("guest")

    with pytest.raises(SessionOperationError) as transfer:
        session.transfer_host("guest", "guest")
    assert transfer.value.code == "host_required"

    _ready_all(session)
    with pytest.raises(SessionOperationError) as start:
        session.start_match("guest")
    assert start.value.code == "host_required"
    assert session.phase is SessionPhase.LOBBY


def test_match_start_requires_every_roster_member_connected_and_ready() -> None:
    session = _session()
    guest = session.join("guest")
    session.set_ready("host")

    with pytest.raises(SessionOperationError) as unready:
        session.start_match("host")
    assert unready.value.code == "members_not_ready"

    session.set_ready("guest")
    session.disconnect("guest")
    with pytest.raises(SessionOperationError) as disconnected:
        session.start_match("host")
    assert disconnected.value.code == "members_disconnected"

    session.resume(guest.resume_token)
    session.set_ready("guest")
    snapshot = session.start_match("host")
    assert snapshot.phase is SessionPhase.MATCH


def test_end_match_returns_to_lobby_and_resets_readiness() -> None:
    session = _session()
    session.join("guest")
    _ready_all(session)
    session.start_match("host")

    ended = session.end_match("host")

    assert ended.phase is SessionPhase.LOBBY
    assert all(member.ready is False for member in ended.members)


def test_lobby_mutations_are_rejected_during_match_without_state_change() -> None:
    session = _session()
    session.join("guest")
    _ready_all(session)
    session.start_match("host")
    before = session.snapshot()

    with pytest.raises(SessionOperationError) as join:
        session.join("late")
    assert join.value.code == "invalid_phase"
    with pytest.raises(SessionOperationError) as role:
        session.claim_role("guest", "pilot")
    assert role.value.code == "invalid_phase"
    with pytest.raises(SessionOperationError) as ready:
        session.set_ready("guest", False)
    assert ready.value.code == "invalid_phase"

    assert session.snapshot() == before


def test_host_must_transfer_before_leaving_non_empty_session() -> None:
    session = _session()
    session.join("guest")
    before = session.snapshot()

    with pytest.raises(SessionOperationError) as blocked:
        session.leave("host")
    assert blocked.value.code == "host_transfer_required"
    assert session.snapshot() == before

    session.transfer_host("host", "guest")
    session.leave("host")
    assert [member.client_id for member in session.members] == ["guest"]
    assert session.host_client_id == "guest"


def test_last_host_leave_closes_session_and_invalidates_operations() -> None:
    session = _session()
    token = session.resume_token_for("host")

    session.leave("host")

    assert session.phase is SessionPhase.CLOSED
    assert session.members == ()
    assert session.role_owners == {}
    closed_snapshot = session.snapshot()
    assert closed_snapshot.phase is SessionPhase.CLOSED
    assert closed_snapshot.members == ()
    assert closed_snapshot.role_owners == {}
    with pytest.raises(SessionOperationError) as closed:
        session.resume(token)
    assert closed.value.code == "session_closed"


def test_disconnect_preserves_roster_and_roles_but_clears_ready() -> None:
    session = _session()
    session.join("guest")
    session.claim_role("guest", "pilot")
    session.set_ready("guest")

    member = session.disconnect("guest")

    assert member.connected is False
    assert member.ready is False
    assert member.roles == ("pilot",)
    assert session.role_owner("pilot") == "guest"
    assert [item.client_id for item in session.members] == ["host", "guest"]


def test_resume_rotates_token_and_replay_of_old_token_is_rejected() -> None:
    session = _session()
    joined = session.join("guest")
    session.disconnect("guest")

    resumed = session.resume(joined.resume_token)

    assert resumed.member.connected is True
    assert resumed.resume_token != joined.resume_token
    assert session.resume_token_for("guest") == resumed.resume_token
    session.disconnect("guest")
    with pytest.raises(SessionOperationError) as replay:
        session.resume(joined.resume_token)
    assert replay.value.code == "invalid_resume_token"


def test_resume_token_store_has_deterministic_hard_bound() -> None:
    session = _session(max_resume_tokens=2)
    host_token = session.resume_token_for("host")
    session.join("a")
    session.join("b")

    assert session.diagnostics()["active_resume_tokens"] == 2
    assert session.diagnostics()["token_evictions"] == 1
    session.disconnect("host")
    with pytest.raises(SessionOperationError) as expired:
        session.resume(host_token)
    assert expired.value.code == "invalid_resume_token"


def test_event_history_is_bounded_monotonic_and_queryable_by_sequence() -> None:
    session = _session(max_events=3)
    session.join("a")
    session.set_ready("a")
    session.set_ready("a", False)

    events = session.events()
    assert [event.sequence for event in events] == [2, 3, 4]
    assert [event.kind for event in events] == ["member.joined", "member.ready", "member.unready"]
    assert [event.sequence for event in session.events(since_sequence=2)] == [3, 4]
    assert session.diagnostics()["event_evictions"] == 1


def test_failure_diagnostics_use_stable_codes_without_changing_revision() -> None:
    session = _session()
    revision = session.revision

    with pytest.raises(SessionOperationError):
        session.member("missing")
    with pytest.raises(SessionOperationError):
        session.start_match("not-host")

    diagnostics = session.diagnostics()
    assert session.revision == revision
    assert diagnostics["failures_total"] == 2
    assert diagnostics["failure_counts"] == {"host_required": 1, "member_not_found": 1}


def test_snapshot_round_trips_through_stable_network_packet_framing() -> None:
    session = _session()
    session.join("guest")
    session.claim_role("guest", "pilot")
    snapshot = session.snapshot()

    framed = snapshot.to_packet().to_bytes()
    decoded_packet = NetworkPacket.from_body(framed[4:])
    decoded = SessionSnapshot.from_packet(decoded_packet)

    assert decoded == snapshot
    assert decoded_packet.kind == SESSION_SNAPSHOT_PACKET_KIND


def test_snapshot_decoder_rejects_wrong_kind_and_inconsistent_role_table() -> None:
    with pytest.raises(ValueError, match="expected"):
        SessionSnapshot.from_packet(NetworkPacket("wrong", {}))

    packet = NetworkPacket(
        SESSION_SNAPSHOT_PACKET_KIND,
        {
            "session_id": "room",
            "revision": 1,
            "phase": "lobby",
            "host_client_id": "host",
            "members": [
                {
                    "client_id": "host",
                    "join_order": 0,
                    "connected": True,
                    "ready": False,
                    "roles": [],
                }
            ],
            "role_owners": {"host": "host"},
        },
    )
    with pytest.raises(ValueError, match="agree"):
        SessionSnapshot.from_packet(packet)


def test_snapshot_rejects_duplicate_join_order_and_normalized_role_aliases() -> None:
    host = SessionMember("host", 0, True, False, ("host",))
    guest = SessionMember("guest", 0, True, False)
    with pytest.raises(ValueError, match="join orders must be unique"):
        SessionSnapshot("room", 1, SessionPhase.LOBBY, "host", (host, guest), {"host": "host"})

    host_with_role = SessionMember("host", 0, True, False, ("host", "pilot"))
    with pytest.raises(ValueError, match="unique after normalization"):
        SessionSnapshot(
            "room",
            1,
            SessionPhase.LOBBY,
            "host",
            (host_with_role,),
            {"host": "host", "pilot": "host", " pilot ": "host"},
        )


def test_closed_snapshot_rejects_retained_roster_state() -> None:
    host = SessionMember("host", 0, True, False, ("host",))
    with pytest.raises(ValueError, match="must not retain roster"):
        SessionSnapshot(
            "room",
            2,
            SessionPhase.CLOSED,
            "host",
            (host,),
            {"host": "host"},
        )


def test_member_leave_releases_roles_and_invalidates_resume_token() -> None:
    session = _session()
    joined = session.join("guest")
    session.claim_role("guest", "pilot")

    session.leave("guest")

    assert session.role_owner("pilot") is None
    with pytest.raises(SessionOperationError) as missing:
        session.member("guest")
    assert missing.value.code == "member_not_found"
    with pytest.raises(SessionOperationError) as invalid:
        session.resume(joined.resume_token)
    assert invalid.value.code == "invalid_resume_token"


def test_invalid_configuration_and_boolean_integer_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        SessionLifecycle("room", "host", max_members=0)
    with pytest.raises(TypeError, match="integer"):
        SessionLifecycle("room", "host", max_events=True)
    with pytest.raises(ValueError, match="at least 8"):
        SessionLifecycle("room", "host", token_factory=lambda: "short")


def test_custom_token_factory_duplicate_is_rejected_before_resume_mutation() -> None:
    values = iter(["resume-token-a", "resume-token-b", "resume-token-a"])
    session = SessionLifecycle("room", "host", token_factory=lambda: next(values))
    joined = session.join("guest")
    session.disconnect("guest")
    before = session.snapshot()

    with pytest.raises(ValueError, match="duplicate active"):
        session.resume(joined.resume_token)

    assert session.snapshot() == before
    assert session.member("guest").connected is False
