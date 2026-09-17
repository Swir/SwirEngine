from __future__ import annotations

import time

from swirengine.multiplayer14 import ReplicatedEntity, WorldSnapshot
from swirengine.multiplayer16 import (
    EntityInterest,
    InterestManager,
    InterestView,
    ReplicationStreamServer,
)

ENTITY_COUNT = 2_500
CLIENT_COUNT = 24
TICKS = 24
MAX_SECONDS = 6.0


def _world(tick: int) -> WorldSnapshot:
    entities = tuple(
        ReplicatedEntity(
            net_id,
            {
                "transform": {
                    "x": float(net_id) + (0.25 if net_id % 17 == tick % 17 else 0.0),
                    "lane": net_id % 4,
                },
                "health": {"hp": 100 - ((tick + net_id) % 3 if net_id % 29 == 0 else 0)},
            },
        )
        for net_id in range(1, ENTITY_COUNT + 1)
    )
    return WorldSnapshot(tick=tick, server_time=tick / 30.0, entities=entities)


def main() -> None:
    interest = InterestManager()
    for net_id in range(1, ENTITY_COUNT + 1):
        interest.upsert(
            EntityInterest(
                net_id,
                (float(net_id), 0.0, 0.0),
                priority=net_id % 7,
                always_relevant=net_id % 500 == 0,
            )
        )

    server = ReplicationStreamServer(
        interest,
        max_entities_per_client=256,
        max_client_history=8,
    )
    for client_index in range(CLIENT_COUNT):
        server.register_client(
            f"client-{client_index}",
            InterestView(
                position=(float(80 + client_index * 90), 0.0, 0.0),
                radius=180.0,
            ),
        )

    encoded_bytes = 0
    updates = 0
    started = time.perf_counter()
    for tick in range(1, TICKS + 1):
        server.publish(_world(tick))
        for client_id in server.client_ids:
            update = server.build_update(client_id)
            encoded_bytes += len(update.to_packet().to_bytes())
            updates += 1
            server.acknowledge(client_id, update.tick)
    elapsed = time.perf_counter() - started

    diagnostics = [server.diagnostics(client_id) for client_id in server.client_ids]
    full_updates = sum(item["full_updates"] for item in diagnostics)
    delta_updates = sum(item["delta_updates"] for item in diagnostics)
    fallbacks = sum(item["snapshot_fallbacks"] for item in diagnostics)

    assert updates == CLIENT_COUNT * TICKS
    assert full_updates == CLIENT_COUNT
    assert delta_updates == CLIENT_COUNT * (TICKS - 1)
    assert fallbacks == 0
    assert encoded_bytes > 0
    if elapsed > MAX_SECONDS:
        raise SystemExit(
            f"replication workload exceeded {MAX_SECONDS:.1f}s budget: {elapsed:.3f}s"
        )

    print(
        "replication16 benchmark: "
        f"entities={ENTITY_COUNT} clients={CLIENT_COUNT} ticks={TICKS} "
        f"updates={updates} bytes={encoded_bytes} elapsed={elapsed:.3f}s"
    )


if __name__ == "__main__":
    main()
