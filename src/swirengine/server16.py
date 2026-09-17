from __future__ import annotations

import math
import os
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Any


TickCallback = Callable[["ServerTick"], None]
LifecycleCallback = Callable[["ServerContext"], None]
ProbeCallback = Callable[[], bool]
AssetProbe = Callable[["ServerAssetRequirement"], bool]
MonotonicClock = Callable[[], float]
Sleeper = Callable[[float], None]


class ServerState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"


class ServerRuntimeError(RuntimeError):
    """Creator-facing dedicated-server failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _bounded_text(value: object, label: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{label} must not exceed {maximum} characters")
    return normalized


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be positive")
    return value


def _positive_float(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
    return numeric


def _string_tuple(values: Iterable[str], label: str, *, maximum: int = 96) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _bounded_text(value, label, maximum=maximum)
        if item in seen:
            raise ValueError(f"{label} values must be unique")
        seen.add(item)
        normalized.append(item)
    return tuple(normalized)


@dataclass(slots=True, frozen=True)
class DedicatedServerConfig:
    """Validated configuration for the additive SwirEngine 1.6 headless server runtime."""

    tick_rate_hz: float = 30.0
    max_catchup_ticks: int = 4
    max_sleep_seconds: float = 0.05
    shutdown_grace_seconds: float = 5.0
    instance_id: str = "default"
    environment: str = "production"

    def __post_init__(self) -> None:
        object.__setattr__(self, "tick_rate_hz", _positive_float(self.tick_rate_hz, "tick_rate_hz"))
        object.__setattr__(
            self,
            "max_catchup_ticks",
            _positive_int(self.max_catchup_ticks, "max_catchup_ticks"),
        )
        object.__setattr__(
            self,
            "max_sleep_seconds",
            _positive_float(self.max_sleep_seconds, "max_sleep_seconds"),
        )
        object.__setattr__(
            self,
            "shutdown_grace_seconds",
            _positive_float(self.shutdown_grace_seconds, "shutdown_grace_seconds"),
        )
        object.__setattr__(self, "instance_id", _bounded_text(self.instance_id, "instance_id", maximum=96))
        object.__setattr__(self, "environment", _bounded_text(self.environment, "environment", maximum=48))

    @property
    def tick_seconds(self) -> float:
        return 1.0 / self.tick_rate_hz

    def portable(self) -> dict[str, Any]:
        return {
            "tick_rate_hz": self.tick_rate_hz,
            "tick_seconds": self.tick_seconds,
            "max_catchup_ticks": self.max_catchup_ticks,
            "max_sleep_seconds": self.max_sleep_seconds,
            "shutdown_grace_seconds": self.shutdown_grace_seconds,
            "instance_id": self.instance_id,
            "environment": self.environment,
        }

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> DedicatedServerConfig:
        if not isinstance(values, Mapping):
            raise TypeError("values must be a mapping")
        allowed = {
            "tick_rate_hz",
            "max_catchup_ticks",
            "max_sleep_seconds",
            "shutdown_grace_seconds",
            "instance_id",
            "environment",
        }
        unknown = sorted(str(key) for key in values if key not in allowed)
        if unknown:
            raise ValueError(f"unknown dedicated server config keys: {', '.join(unknown)}")
        return cls(**dict(values))

    @classmethod
    def from_env(
        cls,
        *,
        prefix: str = "SWIRENGINE_SERVER_",
        environ: Mapping[str, str] | None = None,
    ) -> DedicatedServerConfig:
        prefix = _bounded_text(prefix, "prefix", maximum=96)
        source = os.environ if environ is None else environ
        mapping: dict[str, object] = {}
        parsers: dict[str, tuple[str, Callable[[str], object]]] = {
            "TICK_RATE_HZ": ("tick_rate_hz", float),
            "MAX_CATCHUP_TICKS": ("max_catchup_ticks", int),
            "MAX_SLEEP_SECONDS": ("max_sleep_seconds", float),
            "SHUTDOWN_GRACE_SECONDS": ("shutdown_grace_seconds", float),
            "INSTANCE_ID": ("instance_id", str),
            "ENVIRONMENT": ("environment", str),
        }
        for suffix, (field_name, parser) in parsers.items():
            key = f"{prefix}{suffix}"
            if key not in source:
                continue
            raw = source[key]
            try:
                mapping[field_name] = parser(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid environment value for {key}") from exc
        return cls.from_mapping(mapping)


@dataclass(slots=True, frozen=True)
class ServerAssetRequirement:
    """Metadata-only declaration of a server-side asset needed before startup."""

    path: str
    kind: str = "data"
    required: bool = True

    def __post_init__(self) -> None:
        path = _bounded_text(self.path, "asset path", maximum=512).replace("\\", "/")
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts:
            raise ValueError("asset path must be a safe project-relative path")
        if any(part in {"", "."} for part in pure.parts):
            raise ValueError("asset path must not contain empty or current-directory segments")
        object.__setattr__(self, "path", pure.as_posix())
        object.__setattr__(self, "kind", _bounded_text(self.kind, "asset kind", maximum=48).lower())
        if not isinstance(self.required, bool):
            raise TypeError("required must be a boolean")


@dataclass(slots=True, frozen=True)
class HeadlessRuntimeBoundary:
    """Explicit server-safe capability and asset boundary.

    Rendering, window, input, UI, audio and video resources stay outside the dedicated
    server contract. The runtime validates declarations only; it never executes or loads
    creator-supplied content implicitly.
    """

    allowed_capabilities: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"clock", "filesystem", "logging", "metrics", "network", "storage"}
        )
    )
    allowed_asset_kinds: frozenset[str] = field(
        default_factory=lambda: frozenset({"data", "map", "metadata", "navigation", "config"})
    )

    def __post_init__(self) -> None:
        capabilities = frozenset(
            _bounded_text(value, "allowed capability", maximum=48).lower()
            for value in self.allowed_capabilities
        )
        asset_kinds = frozenset(
            _bounded_text(value, "allowed asset kind", maximum=48).lower()
            for value in self.allowed_asset_kinds
        )
        if not capabilities:
            raise ValueError("allowed_capabilities must not be empty")
        if not asset_kinds:
            raise ValueError("allowed_asset_kinds must not be empty")
        object.__setattr__(self, "allowed_capabilities", capabilities)
        object.__setattr__(self, "allowed_asset_kinds", asset_kinds)

    def validate_capabilities(self, component_name: str, capabilities: Iterable[str]) -> None:
        for capability in capabilities:
            normalized = _bounded_text(capability, "capability", maximum=48).lower()
            if normalized not in self.allowed_capabilities:
                raise ServerRuntimeError(
                    "headless_capability_forbidden",
                    f"component {component_name!r} requires unsupported headless capability {normalized!r}",
                )

    def validate_asset(self, component_name: str, requirement: ServerAssetRequirement) -> None:
        if requirement.kind not in self.allowed_asset_kinds:
            raise ServerRuntimeError(
                "headless_asset_forbidden",
                f"component {component_name!r} requires unsupported server asset kind {requirement.kind!r}",
            )


@dataclass(slots=True, frozen=True)
class ServerTick:
    tick: int
    dt: float
    simulation_time: float

    def __post_init__(self) -> None:
        if not isinstance(self.tick, int) or isinstance(self.tick, bool) or self.tick < 1:
            raise ValueError("tick must be an integer of at least 1")
        if not math.isfinite(self.dt) or self.dt <= 0.0:
            raise ValueError("dt must be finite and positive")
        if not math.isfinite(self.simulation_time) or self.simulation_time <= 0.0:
            raise ValueError("simulation_time must be finite and positive")


@dataclass(slots=True, frozen=True)
class ServerContext:
    config: DedicatedServerConfig
    boundary: HeadlessRuntimeBoundary


@dataclass(slots=True, frozen=True)
class ServerComponent:
    name: str
    tick: TickCallback
    startup: LifecycleCallback | None = None
    shutdown: LifecycleCallback | None = None
    dependencies: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    assets: tuple[ServerAssetRequirement, ...] = ()
    ready_check: ProbeCallback | None = None
    health_check: ProbeCallback | None = None

    def __post_init__(self) -> None:
        name = _bounded_text(self.name, "component name", maximum=96)
        if not callable(self.tick):
            raise TypeError("tick must be callable")
        for callback_name in ("startup", "shutdown", "ready_check", "health_check"):
            callback = getattr(self, callback_name)
            if callback is not None and not callable(callback):
                raise TypeError(f"{callback_name} must be callable or None")
        dependencies = _string_tuple(self.dependencies, "dependency")
        if name in dependencies:
            raise ValueError("component must not depend on itself")
        capabilities = tuple(
            value.lower()
            for value in _string_tuple(self.capabilities, "capability", maximum=48)
        )
        if len(capabilities) != len(set(capabilities)):
            raise ValueError("capability values must be unique after normalization")
        assets = tuple(self.assets)
        if any(not isinstance(asset, ServerAssetRequirement) for asset in assets):
            raise TypeError("assets must contain ServerAssetRequirement values")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "dependencies", dependencies)
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "assets", assets)


@dataclass(slots=True, frozen=True)
class StartupValidationReport:
    component_order: tuple[str, ...]
    required_assets: tuple[ServerAssetRequirement, ...]

    def portable(self) -> dict[str, Any]:
        return {
            "component_order": list(self.component_order),
            "required_assets": [
                {"path": item.path, "kind": item.kind, "required": item.required}
                for item in self.required_assets
            ],
        }


@dataclass(slots=True, frozen=True)
class ServerHealth:
    state: ServerState
    healthy: bool
    ready: bool
    tick: int
    uptime_seconds: float
    dropped_tick_slots: int
    shutdown_requested: bool
    shutdown_reason: str | None
    last_error_code: str | None
    component_health: tuple[tuple[str, bool], ...]
    component_ready: tuple[tuple[str, bool], ...]

    def portable(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "healthy": self.healthy,
            "ready": self.ready,
            "tick": self.tick,
            "uptime_seconds": self.uptime_seconds,
            "dropped_tick_slots": self.dropped_tick_slots,
            "shutdown_requested": self.shutdown_requested,
            "shutdown_reason": self.shutdown_reason,
            "last_error_code": self.last_error_code,
            "components": {
                name: {
                    "healthy": dict(self.component_health)[name],
                    "ready": dict(self.component_ready)[name],
                }
                for name, _ in self.component_health
            },
        }


class DedicatedServerRuntime:
    """Additive headless fixed-tick runtime for SwirEngine 1.6 source development."""

    def __init__(
        self,
        config: DedicatedServerConfig | None = None,
        *,
        boundary: HeadlessRuntimeBoundary | None = None,
        asset_probe: AssetProbe | None = None,
        monotonic: MonotonicClock = time.monotonic,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        self.config = config or DedicatedServerConfig()
        if not isinstance(self.config, DedicatedServerConfig):
            raise TypeError("config must be a DedicatedServerConfig")
        self.boundary = boundary or HeadlessRuntimeBoundary()
        if not isinstance(self.boundary, HeadlessRuntimeBoundary):
            raise TypeError("boundary must be a HeadlessRuntimeBoundary")
        if asset_probe is not None and not callable(asset_probe):
            raise TypeError("asset_probe must be callable or None")
        if not callable(monotonic) or not callable(sleeper):
            raise TypeError("monotonic and sleeper must be callable")

        self._asset_probe = asset_probe
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._components: dict[str, ServerComponent] = {}
        self._order: tuple[str, ...] = ()
        self._started_components: list[str] = []
        self._context = ServerContext(self.config, self.boundary)
        self._state = ServerState.STOPPED
        self._tick = 0
        self._started_at: float | None = None
        self._stopped_at: float | None = None
        self._shutdown_requested = False
        self._shutdown_reason: str | None = None
        self._last_error_code: str | None = None
        self._last_error_message: str | None = None
        self._dropped_tick_slots = 0
        self._startup_attempts = 0
        self._successful_startups = 0
        self._shutdown_requests = 0
        self._ticks_executed = 0
        self._tick_failures = 0
        self._readiness_failures = 0
        self._health_failures = 0
        self._shutdown_failures = 0
        self._shutdown_grace_exceeded = 0
        self._last_tick_seconds = 0.0
        self._max_tick_seconds = 0.0

    @property
    def state(self) -> ServerState:
        return self._state

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def component_order(self) -> tuple[str, ...]:
        return self._order

    def register(self, component: ServerComponent) -> None:
        if self._state is not ServerState.STOPPED or self._started_at is not None:
            raise ServerRuntimeError(
                "runtime_locked",
                "components can only be registered before the first startup",
            )
        if not isinstance(component, ServerComponent):
            raise TypeError("component must be a ServerComponent")
        if component.name in self._components:
            raise ServerRuntimeError(
                "duplicate_component",
                f"component {component.name!r} is already registered",
            )
        self._components[component.name] = component
        self._order = ()

    def validate_startup(self) -> StartupValidationReport:
        order = self._resolve_component_order()
        required_assets: list[ServerAssetRequirement] = []
        for name in order:
            component = self._components[name]
            self.boundary.validate_capabilities(name, component.capabilities)
            for requirement in component.assets:
                self.boundary.validate_asset(name, requirement)
                if requirement.required:
                    required_assets.append(requirement)
                if self._asset_probe is not None:
                    try:
                        present = bool(self._asset_probe(requirement))
                    except Exception as exc:
                        raise ServerRuntimeError(
                            "asset_probe_failed",
                            f"asset probe failed for {requirement.path!r}: {type(exc).__name__}",
                        ) from exc
                    if requirement.required and not present:
                        raise ServerRuntimeError(
                            "required_asset_missing",
                            f"required server asset is unavailable: {requirement.path}",
                        )
        self._order = order
        return StartupValidationReport(order, tuple(required_assets))

    def start(self) -> StartupValidationReport:
        if self._state is not ServerState.STOPPED:
            raise ServerRuntimeError("invalid_state", f"cannot start from state {self._state.value!r}")
        if self._started_at is not None:
            raise ServerRuntimeError("runtime_locked", "dedicated server runtime instances are single-use")
        report = self.validate_startup()
        self._startup_attempts += 1
        self._state = ServerState.STARTING
        self._started_at = self._monotonic()
        self._stopped_at = None
        self._shutdown_requested = False
        self._shutdown_reason = None
        self._last_error_code = None
        self._last_error_message = None

        try:
            for name in report.component_order:
                component = self._components[name]
                self._started_components.append(name)
                if component.startup is not None:
                    component.startup(self._context)
        except Exception as exc:
            self._record_error("startup_failed", f"component {name!r} startup failed: {exc}")
            self._shutdown_started_components(preserve_failure=True)
            raise ServerRuntimeError("startup_failed", self._last_error_message or "startup failed") from exc

        self._state = ServerState.RUNNING
        self._successful_startups += 1
        return report

    def request_shutdown(self, reason: str = "requested") -> bool:
        normalized = _bounded_text(reason, "shutdown reason", maximum=160)
        if self._shutdown_requested:
            return False
        self._shutdown_requested = True
        self._shutdown_reason = normalized
        self._shutdown_requests += 1
        return True

    def run_ticks(self, count: int) -> tuple[ServerTick, ...]:
        count = _positive_int(count, "count")
        if self._state is not ServerState.RUNNING:
            raise ServerRuntimeError("invalid_state", "server must be running before ticks execute")
        executed: list[ServerTick] = []
        for _ in range(count):
            if self._shutdown_requested:
                break
            executed.append(self._run_single_tick())
        return tuple(executed)

    def serve(self, *, max_ticks: int | None = None) -> ServerHealth:
        if max_ticks is not None:
            max_ticks = _positive_int(max_ticks, "max_ticks")
        if self._state is ServerState.STOPPED and self._started_at is None:
            self.start()
        if self._state is not ServerState.RUNNING:
            raise ServerRuntimeError("invalid_state", "server must be running before serve()")

        next_deadline = self._monotonic()
        served = 0
        failure: ServerRuntimeError | None = None
        try:
            while not self._shutdown_requested and (max_ticks is None or served < max_ticks):
                now = self._monotonic()
                if now < next_deadline:
                    self._sleeper(min(next_deadline - now, self.config.max_sleep_seconds))
                    continue

                overdue = max(0.0, now - next_deadline)
                due_slots = 1 + int(overdue / self.config.tick_seconds)
                execute_slots = min(due_slots, self.config.max_catchup_ticks)
                if max_ticks is not None:
                    execute_slots = min(execute_slots, max_ticks - served)
                for _ in range(execute_slots):
                    self._run_single_tick()
                    served += 1
                    next_deadline += self.config.tick_seconds
                    if self._shutdown_requested or (max_ticks is not None and served >= max_ticks):
                        break

                skipped = due_slots - execute_slots
                if skipped > 0 and not self._shutdown_requested:
                    self._dropped_tick_slots += skipped
                    next_deadline += skipped * self.config.tick_seconds
        except ServerRuntimeError as exc:
            failure = exc
        finally:
            if max_ticks is not None and served >= max_ticks and not self._shutdown_requested:
                self.request_shutdown("max_ticks_reached")
            self.stop()
        if failure is not None:
            raise failure
        return self.health()

    def stop(self, reason: str | None = None) -> ServerHealth:
        if reason is not None:
            self.request_shutdown(reason)
        if self._state is ServerState.STOPPED and not self._started_components:
            return self.health()
        preserve_failure = self._state is ServerState.FAILED
        self._shutdown_started_components(preserve_failure=preserve_failure)
        return self.health()

    def health(self) -> ServerHealth:
        component_health: list[tuple[str, bool]] = []
        component_ready: list[tuple[str, bool]] = []
        for name in self._order:
            component = self._components[name]
            healthy = self._probe_component(component.health_check, kind="health")
            ready = self._probe_component(component.ready_check, kind="readiness")
            component_health.append((name, healthy))
            component_ready.append((name, ready))

        running = self._state is ServerState.RUNNING
        active = self._state in {ServerState.STARTING, ServerState.RUNNING, ServerState.STOPPING}
        healthy = active and all(value for _, value in component_health)
        ready = (
            running
            and not self._shutdown_requested
            and healthy
            and all(value for _, value in component_ready)
        )
        return ServerHealth(
            state=self._state,
            healthy=healthy,
            ready=ready,
            tick=self._tick,
            uptime_seconds=self._uptime_seconds(),
            dropped_tick_slots=self._dropped_tick_slots,
            shutdown_requested=self._shutdown_requested,
            shutdown_reason=self._shutdown_reason,
            last_error_code=self._last_error_code,
            component_health=tuple(component_health),
            component_ready=tuple(component_ready),
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "state": self._state.value,
            "tick": self._tick,
            "component_order": list(self._order),
            "startup_attempts": self._startup_attempts,
            "successful_startups": self._successful_startups,
            "shutdown_requests": self._shutdown_requests,
            "ticks_executed": self._ticks_executed,
            "tick_failures": self._tick_failures,
            "dropped_tick_slots": self._dropped_tick_slots,
            "readiness_failures": self._readiness_failures,
            "health_failures": self._health_failures,
            "shutdown_failures": self._shutdown_failures,
            "shutdown_grace_exceeded": self._shutdown_grace_exceeded,
            "last_tick_seconds": self._last_tick_seconds,
            "max_tick_seconds": self._max_tick_seconds,
            "last_error_code": self._last_error_code,
            "last_error_message": self._last_error_message,
            "shutdown_requested": self._shutdown_requested,
            "shutdown_reason": self._shutdown_reason,
            "config": self.config.portable(),
        }

    def _resolve_component_order(self) -> tuple[str, ...]:
        for component in self._components.values():
            missing = sorted(set(component.dependencies) - self._components.keys())
            if missing:
                raise ServerRuntimeError(
                    "missing_dependency",
                    f"component {component.name!r} requires missing dependencies: {', '.join(missing)}",
                )

        remaining = {name: set(component.dependencies) for name, component in self._components.items()}
        order: list[str] = []
        while remaining:
            ready = sorted(name for name, dependencies in remaining.items() if not dependencies)
            if not ready:
                cycle_members = ", ".join(sorted(remaining))
                raise ServerRuntimeError(
                    "dependency_cycle",
                    f"dedicated server component dependency cycle: {cycle_members}",
                )
            for name in ready:
                order.append(name)
                del remaining[name]
                for dependencies in remaining.values():
                    dependencies.discard(name)
        return tuple(order)

    def _run_single_tick(self) -> ServerTick:
        next_tick = self._tick + 1
        tick = ServerTick(next_tick, self.config.tick_seconds, next_tick * self.config.tick_seconds)
        started = self._monotonic()
        try:
            for name in self._order:
                self._components[name].tick(tick)
        except Exception as exc:
            self._tick_failures += 1
            self._record_error("tick_failed", f"component {name!r} tick failed: {exc}")
            raise ServerRuntimeError("tick_failed", self._last_error_message or "tick failed") from exc
        finally:
            duration = max(0.0, self._monotonic() - started)
            self._last_tick_seconds = duration
            self._max_tick_seconds = max(self._max_tick_seconds, duration)
        self._tick = next_tick
        self._ticks_executed += 1
        return tick

    def _shutdown_started_components(self, *, preserve_failure: bool) -> None:
        if self._started_components:
            previous_error_code = self._last_error_code
            previous_error_message = self._last_error_message
            shutdown_started = self._monotonic()
            self._state = ServerState.STOPPING
            shutdown_error: tuple[str, str] | None = None
            for name in reversed(self._started_components):
                callback = self._components[name].shutdown
                if callback is None:
                    continue
                try:
                    callback(self._context)
                except Exception as exc:
                    self._shutdown_failures += 1
                    if shutdown_error is None:
                        shutdown_error = (
                            "shutdown_failed",
                            f"component {name!r} shutdown failed: {exc}",
                        )
            self._started_components.clear()
            self._stopped_at = self._monotonic()
            if self._stopped_at - shutdown_started > self.config.shutdown_grace_seconds:
                self._shutdown_grace_exceeded += 1
            if shutdown_error is not None:
                self._record_error(*shutdown_error)
            elif preserve_failure:
                self._state = ServerState.FAILED
                self._last_error_code = previous_error_code
                self._last_error_message = previous_error_message
            else:
                self._state = ServerState.STOPPED
        elif self._state is not ServerState.FAILED:
            self._state = ServerState.STOPPED
            self._stopped_at = self._monotonic() if self._started_at is not None else self._stopped_at

    def _probe_component(self, callback: ProbeCallback | None, *, kind: str) -> bool:
        if callback is None:
            return True
        try:
            return bool(callback())
        except Exception:
            if kind == "health":
                self._health_failures += 1
            else:
                self._readiness_failures += 1
            return False

    def _record_error(self, code: str, message: str) -> None:
        self._last_error_code = code
        self._last_error_message = message
        self._state = ServerState.FAILED

    def _uptime_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        end = self._stopped_at if self._stopped_at is not None else self._monotonic()
        return max(0.0, end - self._started_at)


__all__ = [
    "DedicatedServerConfig",
    "DedicatedServerRuntime",
    "HeadlessRuntimeBoundary",
    "ServerAssetRequirement",
    "ServerComponent",
    "ServerContext",
    "ServerHealth",
    "ServerRuntimeError",
    "ServerState",
    "ServerTick",
    "StartupValidationReport",
]
