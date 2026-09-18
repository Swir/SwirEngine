"""SwirEngine source-only multiplayer integration fixture.

This is intentionally a deterministic, headless-friendly gameplay/networking fixture rather than
an online service. It exercises the production replication/prediction stack under repeatable hostile
network conditions and the 2.0 session/reconnect contract so CI can detect regressions without opening
sockets or depending on the public internet.
"""

from __future__ import annotations

import json

from swirengine.multiplayer14 import WorldSnapshot
from swirengine.multiplayer20 import (
    MultiplayerCompatibility,
    PlayerLocalState,
    ProductionMultiplayerSession,
)
from swirengine.multiplayer_showcase16 import (
    MultiplayerSoakConfig,
    NetworkImpairmentProfile,
    run_multiplayer_soak,
)


def _production_contract_probe() -> dict[str, object]:
    compatibility = MultiplayerCompatibility(
        project_id="multiplayer-game-demo",
        protocol_version="2.0",
        build_id="source-fixture",
        replication_schema="demo-player-v1",
        content_fingerprint="fixture-content-v1",
    )
    tokens = iter(("host-token-0001", "client-token-0001", "client-token-0002"))
    session = ProductionMultiplayerSession(
        "fixture-session",
        "host",
        compatibility,
        token_factory=lambda: next(tokens),
    )
    joined = session.join("client", compatibility)
    local = PlayerLocalState(
        "client",
        settings={"volume": 0.8, "ui_scale": 1.0},
        save={"checkpoint": "local-only"},
    )
    session.set_authoritative_player_state("host", {"score": 10})
    session.set_authoritative_player_state("client", {"score": 20})
    session.set_ready("host")
    session.set_ready("client")
    session.start_match("host")
    session.publish_authoritative(WorldSnapshot(1, 1 / 30, ()))
    session.disconnect("client")
    resumed = session.resume(joined.resume_token, compatibility)
    if resumed.resynchronization is None or resumed.resynchronization.mode != "snapshot":
        raise RuntimeError("production reconnect did not force a full replication resynchronization")
    status = session.status()
    if "local-only" in repr(status) or "volume" in repr(status):
        raise RuntimeError("player-local settings/save leaked into authoritative session state")

    return {
        "compatibility_fingerprint": compatibility.fingerprint(),
        "phase": status["phase"],
        "members": len(status["members"]),
        "resync_tick": resumed.resynchronization.tick,
        "local_state_client": local.client_id,
        "authoritative_scores": {
            client_id: state["score"]
            for client_id, state in status["authoritative_player_state"].items()
        },
    }


def run_fixture() -> dict[str, object]:
    report = run_multiplayer_soak(
        MultiplayerSoakConfig(
            clients=4,
            entities=32,
            ticks=180,
            entity_budget=16,
            profiler_history=64,
            impairment=NetworkImpairmentProfile(
                seed=20260918,
                loss_per_mille=40,
                duplicate_per_mille=20,
                reorder_per_mille=120,
                base_latency_ticks=1,
                jitter_ticks=3,
                reorder_extra_ticks=2,
                max_inflight_packets=128,
            ),
        )
    )
    final_ticks = dict(sorted(report.final_client_ticks.items()))
    if len(final_ticks) != report.clients:
        raise RuntimeError("multiplayer fixture lost a client timeline")
    if not final_ticks or min(final_ticks.values()) <= 0:
        raise RuntimeError("multiplayer fixture did not advance all client timelines")
    if report.applied_updates <= 0:
        raise RuntimeError("multiplayer fixture did not apply replicated updates")

    return {
        "fingerprint": report.fingerprint(),
        "ticks": report.ticks,
        "clients": report.clients,
        "entities": report.entities,
        "applied_updates": report.applied_updates,
        "stale_updates": report.stale_updates,
        "resynchronizations": report.resynchronizations,
        "prediction_corrections": report.prediction_corrections,
        "final_client_ticks": final_ticks,
        "profiler": report.profiler_diagnostics,
        "links": report.link_diagnostics,
        "production_contract": _production_contract_probe(),
    }


def main() -> int:
    summary = run_fixture()
    print("SwirEngine multiplayer game demo — source-only integration fixture")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
