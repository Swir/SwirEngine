from __future__ import annotations

import hashlib
import heapq
import json
from dataclasses import dataclass
from typing import Any

from .multiplayer14 import PredictionCommand, ReplicatedEntity, WorldSnapshot
from .multiplayer16 import (
    EntityInterest,
    InterestManager,
    InterestView,
    ReplicationStreamClient,
    ReplicationStreamServer,
    ReplicationUpdate,
)
from .network_profiler16 import MultiplayerNetworkProfiler
from .networking import NetworkPacket
from .prediction16 import PredictionCorrection, PredictionTimeline
from .server16 import DedicatedServerConfig, DedicatedServerRuntime, ServerComponent, ServerTick
from .session16 import SessionLifecycle
from .transport16 import (
    ChannelPolicy,
    DeliveryPolicy,
    TransportQoSReceiver,
    TransportQoSScheduler,
)

_MASK_64 = (1 << 64) - 1
_DEFAULT_SEED = 0x53574952454E4749


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


def _rate(value: object, label: str) -> int:
    result = _non_negative_int(value, label)
    if result > 1000:
        raise ValueError(f"{label} must be within 0..1000 per-mille")
    return result


def _clone_packet(packet: NetworkPacket) -> NetworkPacket:
    if not isinstance(packet, NetworkPacket):
        raise TypeError("packet must be a NetworkPacket")
    framed = packet.to_bytes()
    return NetworkPacket.from_body(framed[4:])


class _DeterministicRng:
    """Tiny platform-independent 64-bit generator used only by the soak simulator."""

    def __init__(self, seed: int) -> None:
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise TypeError("seed must be an integer")
        self._state = seed & _MASK_64
        if self._state == 0:
            self._state = _DEFAULT_SEED

    def next_u64(self) -> int:
        self._state = (
            self._state * 6364136223846793005 + 1442695040888963407
        ) & _MASK_64
        return self._state

    def below(self, limit: int) -> int:
        limit = _positive_int(limit, "limit")
        return self.next_u64() % limit

    def per_mille(self, threshold: int) -> bool:
        threshold = _rate(threshold, "threshold")
        return threshold > 0 and self.below(1000) < threshold


@dataclass(slots=True, frozen=True)
class NetworkImpairmentProfile:
    """Deterministic packet-loss/jitter profile for source-only multiplayer soak tests."""

    seed: int = 1
    loss_per_mille: int = 35
    duplicate_per_mille: int = 15
    reorder_per_mille: int = 80
    base_latency_ticks: int = 1
    jitter_ticks: int = 3
    reorder_extra_ticks: int = 2
    max_inflight_packets: int = 512

    def __post_init__(self) -> None:
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise TypeError("seed must be an integer")
        object.__setattr__(self, "loss_per_mille", _rate(self.loss_per_mille, "loss_per_mille"))
        object.__setattr__(
            self,
            "duplicate_per_mille",
            _rate(self.duplicate_per_mille, "duplicate_per_mille"),
        )
        object.__setattr__(
            self,
            "reorder_per_mille",
            _rate(self.reorder_per_mille, "reorder_per_mille"),
        )
        object.__setattr__(
            self,
            "base_latency_ticks",
            _non_negative_int(self.base_latency_ticks, "base_latency_ticks"),
        )
        object.__setattr__(self, "jitter_ticks", _non_negative_int(self.jitter_ticks, "jitter_ticks"))
        object.__setattr__(
            self,
            "reorder_extra_ticks",
            _non_negative_int(self.reorder_extra_ticks, "reorder_extra_ticks"),
        )
        object.__setattr__(
            self,
            "max_inflight_packets",
            _positive_int(self.max_inflight_packets, "max_inflight_packets"),
        )

    @property
    def maximum_delay_ticks(self) -> int:
        return self.base_latency_ticks + self.jitter_ticks + self.reorder_extra_ticks


@dataclass(slots=True, frozen=True)
class SimulatedLinkDiagnostics:
    sent_packets: int
    sent_bytes: int
    scheduled_packets: int
    scheduled_bytes: int
    delivered_packets: int
    delivered_bytes: int
    lost_packets: int
    duplicated_packets: int
    reorder_injections: int
    jittered_packets: int
    capacity_drops: int
    peak_inflight_packets: int
    inflight_packets: int

    def portable(self) -> dict[str, int]:
        return {
            "sent_packets": self.sent_packets,
            "sent_bytes": self.sent_bytes,
            "scheduled_packets": self.scheduled_packets,
            "scheduled_bytes": self.scheduled_bytes,
            "delivered_packets": self.delivered_packets,
            "delivered_bytes": self.delivered_bytes,
            "lost_packets": self.lost_packets,
            "duplicated_packets": self.duplicated_packets,
            "reorder_injections": self.reorder_injections,
            "jittered_packets": self.jittered_packets,
            "capacity_drops": self.capacity_drops,
            "peak_inflight_packets": self.peak_inflight_packets,
            "inflight_packets": self.inflight_packets,
        }


@dataclass(slots=True)
class _ScheduledPacket:
    packet: NetworkPacket
    encoded_bytes: int


class DeterministicPacketLink:
    """Bounded deterministic virtual link for regression/soak validation.

    This utility deliberately simulates impairment rather than pretending to benchmark a real
    socket or Internet route. Packets are snapshotted through the stable ``NetworkPacket`` codec
    before entering the queue, and delivery order depends only on the configured seed and inputs.
    """

    def __init__(self, profile: NetworkImpairmentProfile) -> None:
        if not isinstance(profile, NetworkImpairmentProfile):
            raise TypeError("profile must be a NetworkImpairmentProfile")
        self.profile = profile
        self._rng = _DeterministicRng(profile.seed)
        self._heap: list[tuple[int, int, _ScheduledPacket]] = []
        self._order = 0
        self._sent_packets = 0
        self._sent_bytes = 0
        self._scheduled_packets = 0
        self._scheduled_bytes = 0
        self._delivered_packets = 0
        self._delivered_bytes = 0
        self._lost_packets = 0
        self._duplicated_packets = 0
        self._reorder_injections = 0
        self._jittered_packets = 0
        self._capacity_drops = 0
        self._peak_inflight_packets = 0

    @property
    def inflight_packets(self) -> int:
        return len(self._heap)

    def send(self, packet: NetworkPacket, *, tick: int) -> int:
        tick = _non_negative_int(tick, "tick")
        snapshot = _clone_packet(packet)
        encoded_bytes = len(snapshot.to_bytes())
        self._sent_packets += 1
        self._sent_bytes += encoded_bytes
        if self._rng.per_mille(self.profile.loss_per_mille):
            self._lost_packets += 1
            return 0

        copies = 2 if self._rng.per_mille(self.profile.duplicate_per_mille) else 1
        if copies == 2:
            self._duplicated_packets += 1
        accepted = 0
        for copy_index in range(copies):
            if len(self._heap) >= self.profile.max_inflight_packets:
                self._capacity_drops += 1
                continue
            jitter = self._rng.below(self.profile.jitter_ticks + 1)
            if jitter:
                self._jittered_packets += 1
            reorder = self._rng.per_mille(self.profile.reorder_per_mille)
            extra = self.profile.reorder_extra_ticks if reorder else 0
            if reorder:
                self._reorder_injections += 1
            if copy_index:
                # Do not make a duplicate byte-identical in time as well as content; a small
                # deterministic offset gives duplicate/stale suppression realistic exercise.
                extra += self._rng.below(self.profile.jitter_ticks + 2)
            deliver_tick = tick + self.profile.base_latency_ticks + jitter + extra
            self._order += 1
            queued = _ScheduledPacket(_clone_packet(snapshot), encoded_bytes)
            heapq.heappush(self._heap, (deliver_tick, self._order, queued))
            self._scheduled_packets += 1
            self._scheduled_bytes += encoded_bytes
            accepted += 1
        self._peak_inflight_packets = max(self._peak_inflight_packets, len(self._heap))
        return accepted

    def receive(self, *, tick: int, max_packets: int | None = None) -> tuple[NetworkPacket, ...]:
        tick = _non_negative_int(tick, "tick")
        if max_packets is not None:
            max_packets = _positive_int(max_packets, "max_packets")
        delivered: list[NetworkPacket] = []
        while self._heap and self._heap[0][0] <= tick:
            if max_packets is not None and len(delivered) >= max_packets:
                break
            _, _, queued = heapq.heappop(self._heap)
            self._delivered_packets += 1
            self._delivered_bytes += queued.encoded_bytes
            delivered.append(_clone_packet(queued.packet))
        return tuple(delivered)

    def diagnostics(self) -> SimulatedLinkDiagnostics:
        return SimulatedLinkDiagnostics(
            sent_packets=self._sent_packets,
            sent_bytes=self._sent_bytes,
            scheduled_packets=self._scheduled_packets,
            scheduled_bytes=self._scheduled_bytes,
            delivered_packets=self._delivered_packets,
            delivered_bytes=self._delivered_bytes,
            lost_packets=self._lost_packets,
            duplicated_packets=self._duplicated_packets,
            reorder_injections=self._reorder_injections,
            jittered_packets=self._jittered_packets,
            capacity_drops=self._capacity_drops,
            peak_inflight_packets=self._peak_inflight_packets,
            inflight_packets=len(self._heap),
        )


@dataclass(slots=True, frozen=True)
class MultiplayerSoakConfig:
    clients: int = 6
    entities: int = 48
    ticks: int = 360
    entity_budget: int = 24
    tick_rate_hz: int = 30
    prediction_correction_interval: int = 4
    profiler_history: int = 96
    seed: int = 0x51A6
    impairment: NetworkImpairmentProfile | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "clients", _positive_int(self.clients, "clients"))
        object.__setattr__(self, "entities", _positive_int(self.entities, "entities"))
        object.__setattr__(self, "ticks", _positive_int(self.ticks, "ticks"))
        budget = _positive_int(self.entity_budget, "entity_budget")
        if budget > self.entities:
            raise ValueError("entity_budget must not exceed entities")
        object.__setattr__(self, "entity_budget", budget)
        object.__setattr__(self, "tick_rate_hz", _positive_int(self.tick_rate_hz, "tick_rate_hz"))
        object.__setattr__(
            self,
            "prediction_correction_interval",
            _positive_int(
                self.prediction_correction_interval,
                "prediction_correction_interval",
            ),
        )
        object.__setattr__(
            self,
            "profiler_history",
            _positive_int(self.profiler_history, "profiler_history"),
        )
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise TypeError("seed must be an integer")
        if self.impairment is not None and not isinstance(
            self.impairment, NetworkImpairmentProfile
        ):
            raise TypeError("impairment must be a NetworkImpairmentProfile or None")


@dataclass(slots=True, frozen=True)
class MultiplayerSoakReport:
    ticks: int
    clients: int
    entities: int
    applied_updates: int
    stale_updates: int
    resynchronizations: int
    prediction_corrections: int
    final_client_ticks: dict[str, int]
    link_diagnostics: dict[str, dict[str, int]]
    profiler_diagnostics: dict[str, int]
    profiler_fingerprint: str
    server_diagnostics: dict[str, Any]
    session_revision: int

    def portable(self) -> dict[str, Any]:
        return {
            "ticks": self.ticks,
            "clients": self.clients,
            "entities": self.entities,
            "applied_updates": self.applied_updates,
            "stale_updates": self.stale_updates,
            "resynchronizations": self.resynchronizations,
            "prediction_corrections": self.prediction_corrections,
            "final_client_ticks": dict(sorted(self.final_client_ticks.items())),
            "link_diagnostics": {
                client_id: dict(self.link_diagnostics[client_id])
                for client_id in sorted(self.link_diagnostics)
            },
            "profiler_diagnostics": dict(sorted(self.profiler_diagnostics.items())),
            "profiler_fingerprint": self.profiler_fingerprint,
            "server_diagnostics": self.server_diagnostics,
            "session_revision": self.session_revision,
        }

    def fingerprint(self) -> str:
        payload = json.dumps(
            self.portable(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class _ClientHarness:
    client_id: str
    replication: ReplicationStreamClient
    prediction: PredictionTimeline
    outbound: TransportQoSScheduler
    inbound: TransportQoSReceiver
    link: DeterministicPacketLink
    sent_bytes: int = 0
    received_bytes: int = 0


class MultiplayerSoakRunner:
    """Headless deterministic integration gate for SwirEngine 1.6 multiplayer systems."""

    def __init__(self, config: MultiplayerSoakConfig | None = None) -> None:
        self.config = config or MultiplayerSoakConfig()
        self.interest = InterestManager()
        self.server = ReplicationStreamServer(
            self.interest,
            max_world_history=max(64, self.config.prediction_correction_interval * 4),
            max_client_history=32,
            max_entities_per_client=self.config.entity_budget,
            strict_metadata=True,
        )
        token_counter = {"value": 0}

        def token_factory() -> str:
            token_counter["value"] += 1
            return f"showcase-token-{token_counter['value']:08d}"

        self.session = SessionLifecycle(
            "swirengine-1.6-showcase",
            "client-000",
            max_members=max(16, self.config.clients),
            max_resume_tokens=max(32, self.config.clients * 2),
            token_factory=token_factory,
        )
        self.profiler = MultiplayerNetworkProfiler(
            max_samples_per_client=self.config.profiler_history,
            max_events=max(256, self.config.clients * 8),
        )
        self.clients: dict[str, _ClientHarness] = {}
        self._applied_updates = 0
        self._stale_updates = 0
        self._resynchronizations = 0
        self._prediction_corrections = 0
        self._authoritative_prediction: dict[str, float] = {}
        self._prepare_session_and_clients()

        self.runtime = DedicatedServerRuntime(
            DedicatedServerConfig(
                tick_rate_hz=float(self.config.tick_rate_hz),
                max_catchup_ticks=4,
                instance_id="multiplayer-showcase",
                environment="test",
            )
        )
        self.runtime.register(
            ServerComponent(
                "multiplayer-showcase",
                self._tick,
                capabilities=("clock", "metrics", "network"),
                ready_check=lambda: True,
                health_check=lambda: True,
            )
        )

    def _prepare_session_and_clients(self) -> None:
        policy = ChannelPolicy(
            "state",
            delivery=DeliveryPolicy.UNRELIABLE,
            priority=100,
            max_packet_bytes=256 * 1024,
            max_queue_packets=64,
            max_queue_bytes=2 * 1024 * 1024,
        )
        impairment = self.config.impairment or NetworkImpairmentProfile(seed=self.config.seed)
        for index in range(self.config.clients):
            client_id = f"client-{index:03d}"
            if index:
                self.session.join(client_id)
            self.session.set_ready(client_id, True)
            view_x = (index - (self.config.clients - 1) / 2.0) * 18.0
            self.server.register_client(
                client_id,
                InterestView(position=(view_x, 0.0, 0.0), radius=72.0),
            )
            initial_x = float(index)
            self._authoritative_prediction[client_id] = initial_x

            def simulate(
                state: dict[str, Any],
                command: PredictionCommand,
            ) -> dict[str, Any]:
                return {"x": float(state["x"]) + float(command.payload.get("dx", 0.0))}

            link_profile = NetworkImpairmentProfile(
                seed=(impairment.seed + index * 0x9E3779B97F4A7C15) & _MASK_64,
                loss_per_mille=impairment.loss_per_mille,
                duplicate_per_mille=impairment.duplicate_per_mille,
                reorder_per_mille=impairment.reorder_per_mille,
                base_latency_ticks=impairment.base_latency_ticks,
                jitter_ticks=impairment.jitter_ticks,
                reorder_extra_ticks=impairment.reorder_extra_ticks,
                max_inflight_packets=impairment.max_inflight_packets,
            )
            self.clients[client_id] = _ClientHarness(
                client_id=client_id,
                replication=ReplicationStreamClient(max_history=32),
                prediction=PredictionTimeline(
                    {"x": initial_x},
                    simulate,
                    initial_authoritative_tick=0,
                    max_prediction_ticks=max(8, self.config.prediction_correction_interval * 2),
                    max_replay_commands=max(16, self.config.prediction_correction_interval * 2),
                ),
                outbound=TransportQoSScheduler([policy]),
                inbound=TransportQoSReceiver([policy]),
                link=DeterministicPacketLink(link_profile),
            )
        self.session.start_match("client-000")

    def _entity(self, net_id: int, tick: int) -> tuple[ReplicatedEntity, EntityInterest]:
        lane = (net_id % 9) - 4
        x = float(((net_id * 17 + tick * (1 + net_id % 3)) % 240) - 120)
        z = float(lane * 4)
        entity = ReplicatedEntity(
            net_id,
            {
                "transform": {"x": x, "y": 0.0, "z": z},
                "state": {"energy": 100 - ((tick + net_id) % 17)},
            },
        )
        interest = EntityInterest(
            net_id,
            position=(x, 0.0, z),
            channel="default",
            priority=2 if net_id % 11 == 0 else 0,
            always_relevant=net_id == 1,
        )
        return entity, interest

    def _tick(self, server_tick: ServerTick) -> None:
        tick = server_tick.tick
        entities: list[ReplicatedEntity] = []
        for net_id in range(1, self.config.entities + 1):
            entity, metadata = self._entity(net_id, tick)
            entities.append(entity)
            self.interest.upsert(metadata)
        self.server.publish(WorldSnapshot(tick, server_tick.simulation_time, tuple(entities)))

        for client_id in sorted(self.clients):
            client = self.clients[client_id]
            command = PredictionCommand(tick, tick, {"dx": 1.0})
            client.prediction.predict(command)
            self._authoritative_prediction[client_id] += 1.0
            if tick % self.config.prediction_correction_interval == 0:
                correction = PredictionCorrection(
                    tick,
                    tick,
                    {
                        "x": self._authoritative_prediction[client_id]
                        + (0.125 if (tick // self.config.prediction_correction_interval) % 2 else 0.0)
                    },
                )
                client.prediction.reconcile_packet(correction.to_packet())
                self._prediction_corrections += 1

            update = self.server.build_update(client_id)
            client.outbound.enqueue("state", update.to_packet())
            outgoing = client.outbound.drain(max_packets=4, max_bytes=512 * 1024)
            sent_this_tick = 0
            for packet in outgoing:
                encoded = len(packet.to_bytes())
                sent_this_tick += encoded
                client.link.send(packet, tick=tick)
            client.sent_bytes += sent_this_tick

            received_this_tick = self._deliver(client, tick)
            current = client.replication.current
            replicated_entities = 0 if current is None else len(current.entities)
            self.profiler.sample_runtime(
                client_id,
                tick,
                replication=self.server,
                prediction=client.prediction,
                transport_outbound=client.outbound,
                transport_inbound=client.inbound,
                session=self.session,
                sent_bytes=sent_this_tick,
                received_bytes=received_this_tick,
                replicated_entities=replicated_entities,
                entity_budget=self.config.entity_budget,
            )

    def _deliver(self, client: _ClientHarness, tick: int) -> int:
        received_bytes = 0
        for packet in client.link.receive(tick=tick):
            received_bytes += len(packet.to_bytes())
            inner = client.inbound.accept(packet)
            if inner is None:
                continue
            update = ReplicationUpdate.from_packet(inner)
            current_tick = client.replication.tick
            if current_tick is not None and update.tick <= current_tick:
                self._stale_updates += 1
                continue
            try:
                client.replication.apply(update)
            except LookupError:
                self._resynchronizations += 1
                full = self.server.resynchronize(client.client_id)
                client.outbound.enqueue("state", full.to_packet())
                continue
            self.server.acknowledge(client.client_id, update.tick)
            self._applied_updates += 1
        client.received_bytes += received_bytes
        return received_bytes

    def _stable_server_diagnostics(self) -> dict[str, Any]:
        raw = self.runtime.diagnostics()
        keys = (
            "state",
            "tick",
            "component_order",
            "startup_attempts",
            "successful_startups",
            "shutdown_requests",
            "ticks_executed",
            "tick_failures",
            "dropped_tick_slots",
            "readiness_failures",
            "health_failures",
            "shutdown_failures",
            "shutdown_grace_exceeded",
            "last_error_code",
            "shutdown_requested",
            "shutdown_reason",
            "config",
        )
        return {key: raw[key] for key in keys}

    def run(self) -> MultiplayerSoakReport:
        self.runtime.start()
        self.runtime.run_ticks(self.config.ticks)
        impairment = self.config.impairment or NetworkImpairmentProfile(seed=self.config.seed)
        flush_until = self.config.ticks + impairment.maximum_delay_ticks + 4
        for tick in range(self.config.ticks + 1, flush_until + 1):
            for client_id in sorted(self.clients):
                self._deliver(self.clients[client_id], tick)
        self.runtime.stop("showcase_complete")

        final_ticks = {
            client_id: (client.replication.tick if client.replication.tick is not None else -1)
            for client_id, client in self.clients.items()
        }
        link_diagnostics = {
            client_id: client.link.diagnostics().portable()
            for client_id, client in self.clients.items()
        }
        return MultiplayerSoakReport(
            ticks=self.config.ticks,
            clients=self.config.clients,
            entities=self.config.entities,
            applied_updates=self._applied_updates,
            stale_updates=self._stale_updates,
            resynchronizations=self._resynchronizations,
            prediction_corrections=self._prediction_corrections,
            final_client_ticks=final_ticks,
            link_diagnostics=link_diagnostics,
            profiler_diagnostics=self.profiler.diagnostics(),
            profiler_fingerprint=self.profiler.fingerprint(),
            server_diagnostics=self._stable_server_diagnostics(),
            session_revision=self.session.revision,
        )


def run_multiplayer_soak(config: MultiplayerSoakConfig | None = None) -> MultiplayerSoakReport:
    return MultiplayerSoakRunner(config).run()


__all__ = [
    "DeterministicPacketLink",
    "MultiplayerSoakConfig",
    "MultiplayerSoakReport",
    "MultiplayerSoakRunner",
    "NetworkImpairmentProfile",
    "SimulatedLinkDiagnostics",
    "run_multiplayer_soak",
]
