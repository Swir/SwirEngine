from __future__ import annotations

from swirengine.multiplayer14 import ReplicatedEntity, WorldSnapshot
from swirengine.multiplayer16 import (
    EntityInterest,
    InterestManager,
    InterestView,
    ReplicationStreamClient,
    ReplicationStreamServer,
)


def entity(net_id: int, x: float) -> ReplicatedEntity:
    return ReplicatedEntity(net_id, {"transform": {"x": x}, "health": {"hp": 100}})


def main() -> None:
    interest = InterestManager()
    interest.upsert(EntityInterest(1, (0.0, 0.0, 0.0), priority=10))
    interest.upsert(EntityInterest(2, (8.0, 0.0, 0.0)))
    interest.upsert(EntityInterest(3, (100.0, 0.0, 0.0)))

    server = ReplicationStreamServer(interest)
    server.register_client("player", InterestView(position=(0.0, 0.0, 0.0), radius=16.0))
    client = ReplicationStreamClient()

    server.publish(WorldSnapshot(1, 0.05, (entity(1, 0.0), entity(2, 8.0), entity(3, 100.0))))
    first = server.build_update("player")
    client.apply_packet(first.to_packet())
    server.acknowledge("player", first.tick)

    assert client.current is not None
    print("tick 1:", first.mode, [item.net_id for item in client.current.entities])

    interest.upsert(EntityInterest(2, (30.0, 0.0, 0.0)))
    interest.upsert(EntityInterest(3, (12.0, 0.0, 0.0)))
    server.publish(WorldSnapshot(2, 0.10, (entity(1, 1.0), entity(2, 30.0), entity(3, 12.0))))
    second = server.build_update("player")
    client.apply_packet(second.to_packet())
    server.acknowledge("player", second.tick)

    assert client.current is not None
    print("tick 2:", second.mode, [item.net_id for item in client.current.entities])
    print("diagnostics:", server.diagnostics("player"))


if __name__ == "__main__":
    main()
