from __future__ import annotations

import pytest

from swirengine.multiplayer14 import ReplicatedEntity, WorldSnapshot
from swirengine.multiplayer16 import (
    EntityInterest,
    InterestManager,
    InterestView,
    ReplicationStreamClient,
    ReplicationStreamServer,
    ReplicationUpdate,
)
from swirengine.networking import NetworkPacket


def _entity(net_id: int, x: int) -> ReplicatedEntity:
    return ReplicatedEntity(net_id, {"transform": {"x": x}, "health": {"hp": 100}})


def _snapshot(tick: int, *entities: ReplicatedEntity) -> WorldSnapshot:
    return WorldSnapshot(tick=tick, server_time=tick / 20.0, entities=tuple(entities))


def _manager() -> InterestManager:
    manager = InterestManager()
    manager.upsert(EntityInterest(1, (0.0, 0.0, 0.0), priority=1))
    manager.upsert(EntityInterest(2, (5.0, 0.0, 0.0), priority=3))
    manager.upsert(EntityInterest(3, (50.0, 0.0, 0.0), priority=99))
    manager.upsert(EntityInterest(4, (1000.0, 0.0, 0.0), always_relevant=True))
    manager.upsert(EntityInterest(5, (1.0, 0.0, 0.0), channel="spectator"))
    return manager


def test_interest_manager_filters_radius_channels_and_is_deterministic() -> None:
    manager = _manager()
    view = InterestView((0.0, 0.0, 0.0), radius=10.0)

    assert manager.query(view) == (4, 1, 2)
    assert manager.query(view, limit=2) == (4, 1)
    assert manager.query(InterestView(radius=10.0, channels=frozenset({"spectator"}))) == (5,)


def test_interest_manager_uses_priority_as_distance_tiebreaker() -> None:
    manager = InterestManager()
    manager.upsert(EntityInterest(10, (1.0, 0.0, 0.0), priority=1))
    manager.upsert(EntityInterest(11, (-1.0, 0.0, 0.0), priority=5))

    assert manager.query(InterestView(radius=2.0)) == (11, 10)


def test_interest_contract_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="radius"):
        InterestView(radius=-1.0)
    with pytest.raises(ValueError, match="finite"):
        EntityInterest(1, (float("nan"), 0.0, 0.0))
    with pytest.raises(ValueError, match="positive"):
        EntityInterest(0)
    with pytest.raises(ValueError, match="channel"):
        EntityInterest(1, channel="   ")


def test_first_update_is_full_then_acknowledged_update_is_delta() -> None:
    manager = _manager()
    server = ReplicationStreamServer(manager)
    server.register_client("alpha", InterestView(radius=10.0))
    server.publish(_snapshot(1, _entity(1, 0), _entity(2, 5), _entity(3, 50), _entity(4, 99)))

    first = server.build_update("alpha")

    assert first.mode == "snapshot"
    assert first.snapshot is not None
    assert [entity.net_id for entity in first.snapshot.entities] == [1, 2, 4]
    assert server.acknowledge("alpha", 1) is True

    server.publish(_snapshot(2, _entity(1, 1), _entity(2, 5), _entity(3, 51), _entity(4, 99)))
    second = server.build_update("alpha")

    assert second.mode == "delta"
    assert second.delta is not None
    assert second.delta.baseline_tick == 1
    assert [entity.net_id for entity in second.delta.upserts] == [1]
    assert second.delta.removed == ()


def test_interest_exit_becomes_delta_removal() -> None:
    manager = _manager()
    server = ReplicationStreamServer(manager)
    server.register_client("alpha", InterestView(radius=10.0))
    server.publish(_snapshot(1, _entity(1, 0), _entity(2, 5), _entity(4, 99)))
    first = server.build_update("alpha")
    server.acknowledge("alpha", first.tick)

    manager.upsert(EntityInterest(2, (25.0, 0.0, 0.0), priority=3))
    server.publish(_snapshot(2, _entity(1, 0), _entity(2, 25), _entity(4, 99)))
    update = server.build_update("alpha")

    assert update.delta is not None
    assert update.delta.removed == (2,)


def test_lost_packet_never_becomes_implicit_baseline() -> None:
    manager = _manager()
    server = ReplicationStreamServer(manager)
    server.register_client("alpha", InterestView(radius=10.0))
    server.publish(_snapshot(1, _entity(1, 0), _entity(2, 5), _entity(4, 99)))
    first = server.build_update("alpha")
    server.acknowledge("alpha", first.tick)

    server.publish(_snapshot(2, _entity(1, 2), _entity(2, 5), _entity(4, 99)))
    lost = server.build_update("alpha")
    assert lost.delta is not None and lost.delta.baseline_tick == 1

    server.publish(_snapshot(3, _entity(1, 3), _entity(2, 7), _entity(4, 99)))
    next_update = server.build_update("alpha")

    assert next_update.delta is not None
    assert next_update.delta.baseline_tick == 1
    assert [entity.net_id for entity in next_update.delta.upserts] == [1, 2]


def test_server_acknowledgement_is_monotonic_and_only_accepts_sent_ticks() -> None:
    server = ReplicationStreamServer(_manager())
    server.register_client("alpha", InterestView(radius=10.0))
    server.publish(_snapshot(1, _entity(1, 0), _entity(4, 0)))
    server.build_update("alpha")

    with pytest.raises(ValueError, match="unsent"):
        server.acknowledge("alpha", 2)
    assert server.acknowledge("alpha", 1) is True
    assert server.acknowledge("alpha", 1) is False


def test_client_keeps_old_ack_baseline_for_later_delta() -> None:
    manager = _manager()
    server = ReplicationStreamServer(manager)
    server.register_client("alpha", InterestView(radius=10.0))
    client = ReplicationStreamClient(max_history=4)

    server.publish(_snapshot(1, _entity(1, 0), _entity(2, 5), _entity(4, 99)))
    first = server.build_update("alpha")
    client.apply(first)
    server.acknowledge("alpha", 1)

    server.publish(_snapshot(2, _entity(1, 2), _entity(2, 5), _entity(4, 99)))
    intermediate = server.build_update("alpha")
    client.apply(intermediate)

    server.publish(_snapshot(3, _entity(1, 3), _entity(2, 8), _entity(4, 99)))
    later = server.build_update("alpha")
    result = client.apply(later)

    assert later.delta is not None and later.delta.baseline_tick == 1
    assert result.tick == 3
    values = {entity.net_id: entity.components["transform"]["x"] for entity in result.entities}
    assert values == {1: 3, 2: 8, 4: 99}


def test_client_reports_missing_baseline_instead_of_corrupting_state() -> None:
    client = ReplicationStreamClient(max_history=2)
    client.apply(ReplicationUpdate(snapshot=_snapshot(1, _entity(1, 0))))
    client.apply(ReplicationUpdate(snapshot=_snapshot(2, _entity(1, 1))))
    client.apply(ReplicationUpdate(snapshot=_snapshot(3, _entity(1, 2))))

    from swirengine.multiplayer14 import SnapshotDelta

    old_delta = SnapshotDelta.between(
        _snapshot(1, _entity(1, 0)),
        _snapshot(4, _entity(1, 4)),
    )
    with pytest.raises(LookupError, match="baseline 1"):
        client.apply(ReplicationUpdate(delta=old_delta))


def test_server_resynchronizes_after_client_prunes_ack_baseline() -> None:
    manager = _manager()
    server = ReplicationStreamServer(manager)
    server.register_client("alpha", InterestView(radius=10.0))
    client = ReplicationStreamClient(max_history=2)

    server.publish(_snapshot(1, _entity(1, 1), _entity(2, 5), _entity(4, 99)))
    first = server.build_update("alpha")
    client.apply(first)
    server.acknowledge("alpha", 1)

    for tick in (2, 3):
        server.publish(_snapshot(tick, _entity(1, tick), _entity(2, 5), _entity(4, 99)))
        client.apply(server.build_update("alpha"))

    assert client.history_ticks == (2, 3)

    server.publish(_snapshot(4, _entity(1, 4), _entity(2, 6), _entity(4, 99)))
    stale_delta = server.build_update("alpha")
    assert stale_delta.delta is not None and stale_delta.delta.baseline_tick == 1
    with pytest.raises(LookupError, match="baseline 1"):
        client.apply(stale_delta)

    recovery = server.resynchronize("alpha")
    restored = client.apply(recovery)
    assert recovery.mode == "snapshot"
    assert restored.tick == 4

    server.publish(_snapshot(5, _entity(1, 5), _entity(2, 6), _entity(4, 99)))
    unacked_recovery_retry = server.build_update("alpha")
    assert unacked_recovery_retry.mode == "snapshot"

    assert server.acknowledge("alpha", 4) is True
    server.publish(_snapshot(6, _entity(1, 6), _entity(2, 7), _entity(4, 99)))
    after_recovery = server.build_update("alpha")
    assert after_recovery.delta is not None
    assert after_recovery.delta.baseline_tick == 4

    diagnostics = server.diagnostics("alpha")
    assert diagnostics["snapshot_fallbacks"] == 1
    assert diagnostics["full_updates"] == 3


def test_replication_update_packet_round_trips_over_stable_network_packet() -> None:
    update = ReplicationUpdate(snapshot=_snapshot(7, _entity(1, 9)))
    packet = update.to_packet()
    framed = packet.to_bytes()
    body = framed[4:]
    decoded_packet = NetworkPacket.from_body(body)
    decoded = ReplicationUpdate.from_packet(decoded_packet)

    assert decoded == update


def test_server_strict_metadata_prevents_silent_entity_omission() -> None:
    manager = InterestManager()
    manager.upsert(EntityInterest(1))
    server = ReplicationStreamServer(manager)
    server.register_client("alpha")
    server.publish(_snapshot(1, _entity(1, 0), _entity(2, 0)))

    with pytest.raises(KeyError, match="metadata.*2"):
        server.build_update("alpha")


def test_server_can_opt_out_of_strict_metadata_for_custom_interest_sources() -> None:
    manager = InterestManager()
    manager.upsert(EntityInterest(1))
    server = ReplicationStreamServer(manager, strict_metadata=False)
    server.register_client("alpha")
    server.publish(_snapshot(1, _entity(1, 0), _entity(2, 0)))

    update = server.build_update("alpha")

    assert update.snapshot is not None
    assert [entity.net_id for entity in update.snapshot.entities] == [1]


def test_client_entity_budget_is_enforced_deterministically() -> None:
    manager = _manager()
    server = ReplicationStreamServer(manager, max_entities_per_client=2)
    server.register_client("alpha", InterestView(radius=100.0))
    server.publish(
        _snapshot(1, _entity(1, 1), _entity(2, 2), _entity(3, 3), _entity(4, 4))
    )

    update = server.build_update("alpha")

    assert update.snapshot is not None
    assert [entity.net_id for entity in update.snapshot.entities] == [1, 4]


def test_per_client_diagnostics_track_full_delta_ack_and_removal() -> None:
    manager = _manager()
    server = ReplicationStreamServer(manager)
    server.register_client("alpha", InterestView(radius=10.0))
    server.publish(_snapshot(1, _entity(1, 0), _entity(2, 5), _entity(4, 0)))
    server.build_update("alpha")
    server.acknowledge("alpha", 1)

    manager.upsert(EntityInterest(2, (100.0, 0.0, 0.0)))
    server.publish(_snapshot(2, _entity(1, 1), _entity(2, 5), _entity(4, 0)))
    server.build_update("alpha")

    assert server.diagnostics("alpha") == {
        "full_updates": 1,
        "delta_updates": 1,
        "upserted_entities": 1,
        "removed_entities": 1,
        "full_entities": 3,
        "acknowledgements": 1,
        "snapshot_fallbacks": 0,
    }


def test_publish_and_per_client_build_order_are_guarded() -> None:
    server = ReplicationStreamServer(_manager())
    server.register_client("alpha", InterestView(radius=10.0))

    with pytest.raises(LookupError, match="published"):
        server.build_update("alpha")
    with pytest.raises(LookupError, match="published"):
        server.resynchronize("alpha")

    server.publish(_snapshot(1, _entity(1, 0), _entity(4, 0)))
    server.build_update("alpha")
    with pytest.raises(RuntimeError, match="no newer"):
        server.build_update("alpha")
    with pytest.raises(ValueError, match="increase"):
        server.publish(_snapshot(1, _entity(1, 1), _entity(4, 0)))
