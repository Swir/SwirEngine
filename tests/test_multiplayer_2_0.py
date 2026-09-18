from __future__ import annotations

import pytest

from swirengine.multiplayer14 import WorldSnapshot
from swirengine.multiplayer16 import InterestView
from swirengine.multiplayer20 import (
    DedicatedMultiplayerServer,
    MultiplayerCompatibility,
    MultiplayerContractError,
    PlayerLocalState,
    ProductionMultiplayerSession,
)
from swirengine.server16 import DedicatedServerConfig, ServerTick
from swirengine.session16 import SessionOperationError


def _contract(*, build_id: str = "build-001") -> MultiplayerCompatibility:
    return MultiplayerCompatibility(
        project_id="arena",
        protocol_version="2.0",
        build_id=build_id,
        replication_schema="player-v3",
        content_fingerprint="content-abc",
    )


def _tokens():
    values = iter(("host-token-0001", "client-token-0001", "client-token-0002"))
    return lambda: next(values)


def test_compatibility_fingerprint_is_deterministic_and_mismatch_is_actionable():
    server = _contract()
    same = _contract()
    different = _contract(build_id="build-002")

    assert server.fingerprint() == same.fingerprint()
    assert server.mismatches(same) == ()
    assert server.mismatches(different) == ("build_id",)

    with pytest.raises(MultiplayerContractError) as exc:
        server.require_compatible(different)
    assert exc.value.code == "compatibility_mismatch"
    assert "build_id" in str(exc.value)


def test_incompatible_join_does_not_mutate_roster_or_replication_clients():
    session = ProductionMultiplayerSession(
        "match-01",
        "host",
        _contract(),
        token_factory=_tokens(),
    )

    with pytest.raises(MultiplayerContractError):
        session.join("client", _contract(build_id="wrong"))

    assert tuple(member.client_id for member in session.lifecycle.members) == ("host",)
    assert session.replication.client_ids == ("host",)


def test_disconnect_resume_rotates_token_and_forces_full_resynchronization():
    session = ProductionMultiplayerSession(
        "match-01",
        "host",
        _contract(),
        token_factory=_tokens(),
    )
    joined = session.join("client", _contract(), view=InterestView())
    session.set_ready("host")
    session.set_ready("client")
    session.start_match("host")
    session.publish_authoritative(WorldSnapshot(1, 1 / 30, ()))

    session.disconnect("client")
    with pytest.raises(MultiplayerContractError):
        session.resume(joined.resume_token, _contract(build_id="wrong"))
    assert session.lifecycle.member("client").connected is False

    resumed = session.resume(joined.resume_token, _contract())

    assert resumed.join.member.connected is True
    assert resumed.join.resume_token != joined.resume_token
    assert resumed.resynchronization is not None
    assert resumed.resynchronization.mode == "snapshot"
    assert resumed.resynchronization.tick == 1

    session.disconnect("client")
    with pytest.raises(SessionOperationError) as exc:
        session.resume(joined.resume_token, _contract())
    assert exc.value.code == "invalid_resume_token"


def test_player_local_state_is_explicitly_separate_from_authoritative_state():
    session = ProductionMultiplayerSession(
        "match-01",
        "host",
        _contract(),
        token_factory=_tokens(),
    )
    local = PlayerLocalState(
        "host",
        settings={"volume": 0.5, "ui_scale": 1.2},
        save={"checkpoint": "intro"},
    )
    session.set_authoritative_player_state("host", {"score": 10, "health": 100})

    status = session.status()
    encoded = repr(status)
    assert local.portable()["settings"]["volume"] == 0.5
    assert status["authoritative_player_state"]["host"] == {"score": 10, "health": 100}
    assert "checkpoint" not in encoded
    assert "volume" not in encoded

    with pytest.raises(MultiplayerContractError) as exc:
        session.set_authoritative_player_state("host", {"settings": {"volume": 1.0}})
    assert exc.value.code == "player_local_state_forbidden"

    with pytest.raises(MultiplayerContractError) as nested:
        session.set_authoritative_player_state(
            "host",
            {"inventory": [{"slot": 1}, {"profile": {"name": "local"}}]},
        )
    assert nested.value.code == "player_local_state_forbidden"
    assert "inventory[1].profile" in str(nested.value)


def test_authoritative_state_is_bounded():
    session = ProductionMultiplayerSession(
        "match-01",
        "host",
        _contract(),
        token_factory=_tokens(),
        max_authoritative_state_bytes=256,
    )
    with pytest.raises(MultiplayerContractError) as exc:
        session.set_authoritative_player_state("host", {"payload": "x" * 300})
    assert exc.value.code == "authoritative_state_too_large"


def test_dedicated_server_plan_is_headless_and_compatibility_pinned():
    session = ProductionMultiplayerSession(
        "match-01",
        "host",
        _contract(),
        token_factory=_tokens(),
    )

    def snapshots(tick: ServerTick) -> WorldSnapshot:
        return WorldSnapshot(tick.tick, tick.simulation_time, ())

    server = DedicatedMultiplayerServer(
        session,
        snapshots,
        config=DedicatedServerConfig(tick_rate_hz=60.0, instance_id="ci-server"),
    )
    startup = server.validate_startup()
    manifest = server.deployment_manifest()

    assert startup["components"] == ["multiplayer-authority"]
    assert startup["headless"] is True
    assert startup["compatibility_fingerprint"] == _contract().fingerprint()
    assert manifest["headless"] is True
    assert manifest["server"]["tick_rate_hz"] == 60.0
    assert "network" in manifest["capabilities"]
    assert "settings" in manifest["forbidden_player_local_fields"]


def test_dedicated_server_tick_rejects_non_authoritative_snapshot_tick():
    session = ProductionMultiplayerSession(
        "match-01",
        "host",
        _contract(),
        token_factory=_tokens(),
    )
    session.set_ready("host")
    session.start_match("host")

    server = DedicatedMultiplayerServer(
        session,
        lambda tick: WorldSnapshot(tick.tick + 1, tick.simulation_time, ()),
    )

    with pytest.raises(MultiplayerContractError) as exc:
        server._tick(ServerTick(tick=1, dt=1 / 30, simulation_time=1 / 30))
    assert exc.value.code == "snapshot_tick_mismatch"
