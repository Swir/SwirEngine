from __future__ import annotations

import math
import os
import signal
import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

TickCallback = Callable[["DedicatedServerRuntime", float], None]
LifecycleCallback = Callable[["DedicatedServerRuntime"], None]
StartupCheckCallback = Callable[[], bool | None]
Clock = Callable[[], float]
Sleeper = Callable[[float], None]


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


def _non_negative_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must not be negative")
    return value


def _finite_float(value: object, label: str, *, minimum: float = 0.0) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    if result < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    return result


def _normalize_project_path(value: object) -> str:
    path = _bounded_text(value, "asset path", maximum=512).replace("\\", "/")
    parsed = PurePosixPath(path)
    normalized = parsed.as_posix()
    if (
        parsed.is_absolute()
        or any(part in {"", ".", ".."} for part in parsed.parts)
        or normalized != path
    ):
        raise ValueError("server asset path must be a normalized relative project path")
    return normalized


class ServerPhase(str, Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class ServerAssetKind(str, Enum):
    DATA = "data"
    MAP = "map"
    SCRIPT = "script"
    CONFIG = "config"
    TEXTURE = "texture"
    SHADER = "shader"
    AUDIO = "audio"
    VIDEO = "video"
    FONT = "font"


SERVER_SAFE_ASSET_KINDS = frozenset(
    {
        ServerAssetKind.DATA,
        ServerAssetKind.MAP,
        ServerAssetKind.SCRIPT,
        ServerAssetKind.CONFIG,
    }
)


class ServerRuntimeError(RuntimeError):
    """Creator-facing dedicated-server failure with a stable diagnostic code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(slots=True, frozen=True)
class ServerConfig:
    server_name: str = "SwirEngine Dedicated Server"
    tick_rate_hz: float = 60.0
    max_catch_up_ticks: int = 4
    ready_after_ticks: int = 1
    max_events: int = 256
    max_assets: int = 4096

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "server_name",
            _bounded_text(self.server_name, "server_name", maximum=128),
        )
        tick_rate = _finite_float(self.tick_rate_hz, "tick_rate_hz", minimum=0.001)
        if tick_rate > 1000.0:
            raise ValueError("tick_rate_hz must not exceed 1000")
        object.__setattr__(self, "tick_rate_hz", tick_rate)
        object.__setattr__(
            self,
            "max_catch_up_ticks",
            _positive_int(self.max_catch_up_ticks, "max_catch_up_ticks"),
        )
        object.__setattr__(
            self,
            "ready_after_ticks",
            _non_negative_int(self.ready_after_ticks, "ready_after_ticks"),
        )
        object.__setattr__(self, "max_events", _positive_int(self.max_events, "max_events"))
        object.__setattr__(self, "max_assets", _positive_int(self.max_assets, "max_assets"))

    @property
    def fixed_dt(self) -> float:
        return 1.0 / self.tick_rate_hz

    @classmethod
    def from_env(
        cls,
        *,
        prefix: str = "SWIR_SERVER_",
        environ: Mapping[str, str] | None = None,
    ) -> ServerConfig:
        source = os.environ if environ is None else environ
        prefix = _bounded_text(prefix, "environment prefix", maximum=64)
        defaults = cls()

        def _value(name: str, default: object, parser: Callable[[str], object]) -> object:
            raw = source.get(f"{prefix}{name}")
            return default if raw is None else parser(raw.strip())

        return cls(
            server_name=str(_value("NAME", defaults.server_name, str)),
            tick_rate_hz=float(_value("TICK_RATE_HZ", defaults.tick_rate_hz, float)),
            max_catch_up_ticks=int(
                _value("MAX_CATCH_UP_TICKS", defaults.max_catch_up_ticks, int)
            ),
            ready_after_ticks=int(
                _value("READY_AFTER_TICKS", defaults.ready_after_ticks, int)
            ),
            max_events=int(_value("MAX_EVENTS", defaults.max_events, int)),
            max_assets=int(_value("MAX_ASSETS", defaults.max_assets, int)),
        )


@dataclass(slots=True, frozen=True)
class ServerAssetReference:
    path: str
    kind: ServerAssetKind = ServerAssetKind.DATA

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _normalize_project_path(self.path))
        object.__setattr__(self, "kind", ServerAssetKind(self.kind))


@dataclass(slots=True, frozen=True)
class ServerStartupCheck:
    name: str
    check: StartupCheckCallback

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _bounded_text(self.name, "startup check name", maximum=96))
        if not callable(self.check):
            raise TypeError("startup check must be callable")


@dataclass(slots=True, frozen=True)
class ServerEvent:
    sequence: int
    kind: str
    tick: int
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _positive_int(self.sequence, "event sequence"))
        object.__setattr__(self, "kind", _bounded_text(self.kind, "event kind", maximum=96))
        object.__setattr__(self, "tick", _non_negative_int(self.tick, "event tick"))
        if not isinstance(self.detail, str):
            raise TypeError("event detail must be a string")
        if len(self.detail) > 512:
            raise ValueError("event detail must not exceed 512 characters")

    def portable(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "kind": self.kind,
            "tick": self.tick,
            "detail": self.detail,
        }


@dataclass(slots=True, frozen=True)
class ServerHealthSnapshot:
    phase: ServerPhase
    tick: int
    ready: bool
    healthy: bool
    uptime_seconds: float
    last_tick_seconds: float
    schedule_lag_seconds: float
    dropped_ticks: int
    startup_checks_passed: int
    startup_checks_total: int
    failure_code: str | None
    stop_reason: str | None

    def portable(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "tick": self.tick,
            "ready": self.ready,
            "healthy": self.healthy,
            "uptime_seconds": self.uptime_seconds,
            "last_tick_seconds": self.last_tick_seconds,
            "schedule_lag_seconds": self.schedule_lag_seconds,
            "dropped_ticks": self.dropped_ticks,
            "startup_checks_passed": self.startup_checks_passed,
            "startup_checks_total": self.startup_checks_total,
            "failure_code": self.failure_code,
            "stop_reason": self.stop_reason,
        }


class DedicatedServerRuntime:
    """Headless fixed-tick runtime with bounded diagnostics and graceful shutdown."""

    def __init__(
        self,
        *,
        config: ServerConfig | None = None,
        on_tick: TickCallback | None = None,
        on_start: LifecycleCallback | None = None,
        on_stop: LifecycleCallback | None = None,
        startup_checks: Iterable[ServerStartupCheck] = (),
        assets: Iterable[ServerAssetReference] = (),
        clock: Clock = time.monotonic,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        self.config = config or ServerConfig()
        if not isinstance(self.config, ServerConfig):
            raise TypeError("config must be a ServerConfig")
        self._on_tick = on_tick or (lambda _runtime, _dt: None)
        self._on_start = on_start
        self._on_stop = on_stop
        for callback, label in (
            (self._on_tick, "on_tick"),
            (self._on_start, "on_start"),
            (self._on_stop, "on_stop"),
            (clock, "clock"),
            (sleeper, "sleeper"),
        ):
            if callback is not None and not callable(callback):
                raise TypeError(f"{label} must be callable")
        self._clock = clock
        self._sleeper = sleeper

        checks = tuple(startup_checks)
        if not all(isinstance(check, ServerStartupCheck) for check in checks):
            raise TypeError("startup_checks must contain ServerStartupCheck values")
        check_names = [check.name for check in checks]
        if len(set(check_names)) != len(check_names):
            raise ValueError("startup check names must be unique")
        self._startup_checks = checks

        raw_assets = tuple(assets)
        if not all(isinstance(asset, ServerAssetReference) for asset in raw_assets):
            raise TypeError("assets must contain ServerAssetReference values")
        normalized_assets = tuple(sorted(raw_assets, key=lambda item: (item.kind.value, item.path)))
        if len(normalized_assets) > self.config.max_assets:
            raise ServerRuntimeError("asset_limit", "server asset manifest exceeds configured limit")
        keys = [(asset.kind.value, asset.path) for asset in normalized_assets]
        if len(set(keys)) != len(keys):
            raise ValueError("server asset manifest contains duplicate entries")
        self._assets = normalized_assets

        self.phase = ServerPhase.CREATED
        self._tick = 0
        self._ready = False
        self._started_at: float | None = None
        self._last_tick_seconds = 0.0
        self._schedule_lag_seconds = 0.0
        self._dropped_ticks = 0
        self._startup_checks_passed = 0
        self._failure_code: str | None = None
        self._stop_reason: str | None = None
        self._events: deque[ServerEvent] = deque(maxlen=self.config.max_events)
        self._event_sequence = 0
        self._event_evictions = 0
        self._stop_callback_called = False
        self._start_callback_entered = False

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def fixed_dt(self) -> float:
        return self.config.fixed_dt

    @property
    def ready(self) -> bool:
        return self.phase is ServerPhase.RUNNING and self._ready

    @property
    def events(self) -> tuple[ServerEvent, ...]:
        return tuple(self._events)

    @property
    def assets(self) -> tuple[ServerAssetReference, ...]:
        return self._assets

    def start(self) -> ServerHealthSnapshot:
        if self.phase is not ServerPhase.CREATED:
            raise ServerRuntimeError("invalid_phase", "server can only start from created state")
        self.phase = ServerPhase.STARTING
        self._emit("runtime.starting")
        try:
            self._validate_assets()
            for startup_check in self._startup_checks:
                result = startup_check.check()
                if result is False:
                    raise ServerRuntimeError(
                        "startup_check_failed",
                        f"startup check {startup_check.name!r} returned false",
                    )
                self._startup_checks_passed += 1
                self._emit("startup_check.passed", startup_check.name)
            self._start_callback_entered = True
            if self._on_start is not None:
                self._on_start(self)
            self._started_at = self._clock()
            self.phase = ServerPhase.RUNNING
            self._ready = self.config.ready_after_ticks == 0
            self._emit("runtime.started")
            if self._ready:
                self._emit("runtime.ready")
            return self.health()
        except ServerRuntimeError as exc:
            self._fail(exc.code, str(exc))
            raise
        except Exception as exc:
            error = ServerRuntimeError("startup_failed", f"server startup failed: {exc}")
            self._fail(error.code, str(error))
            raise error from exc

    def run_ticks(self, count: int) -> ServerHealthSnapshot:
        count = _positive_int(count, "count")
        if self.phase is ServerPhase.CREATED:
            self.start()
        if self.phase is not ServerPhase.RUNNING:
            raise ServerRuntimeError("invalid_phase", "server must be running to execute ticks")
        for _ in range(count):
            if self.phase is not ServerPhase.RUNNING:
                break
            self._tick_once()
        return self.health()

    def run(
        self,
        *,
        max_ticks: int | None = None,
        install_signal_handlers: bool = True,
    ) -> ServerHealthSnapshot:
        if max_ticks is not None:
            max_ticks = _positive_int(max_ticks, "max_ticks")
        restore_handlers: Callable[[], None] | None = None
        if install_signal_handlers:
            restore_handlers = self._install_signal_handlers()
        try:
            if self.phase is ServerPhase.CREATED:
                self.start()
            if self.phase is not ServerPhase.RUNNING:
                raise ServerRuntimeError("invalid_phase", "server must be running to enter run loop")

            target_tick = None if max_ticks is None else self._tick + max_ticks
            next_deadline = self._clock()
            while self.phase is ServerPhase.RUNNING:
                now = self._clock()
                if now < next_deadline:
                    self._sleeper(next_deadline - now)
                    now = self._clock()

                lag = max(0.0, now - next_deadline)
                due = int(lag / self.fixed_dt) + 1
                if due > self.config.max_catch_up_ticks:
                    dropped = due - self.config.max_catch_up_ticks
                    self._dropped_ticks += dropped
                    next_deadline += dropped * self.fixed_dt
                    due = self.config.max_catch_up_ticks
                    self._emit("schedule.ticks_dropped", str(dropped))
                self._schedule_lag_seconds = max(0.0, now - next_deadline)

                for _ in range(due):
                    if self.phase is not ServerPhase.RUNNING:
                        break
                    self._tick_once()
                    next_deadline += self.fixed_dt
                    if target_tick is not None and self._tick >= target_tick:
                        self.request_stop("max_ticks")
                        break

            if self.phase is ServerPhase.STOPPING:
                self._finish_stop()
            return self.health()
        finally:
            if restore_handlers is not None:
                restore_handlers()

    def request_stop(self, reason: str = "requested") -> None:
        reason = _bounded_text(reason, "stop reason", maximum=128)
        if self.phase is ServerPhase.CREATED:
            self._stop_reason = reason
            self.phase = ServerPhase.STOPPED
            self._emit("runtime.stopped", reason)
            return
        if self.phase is ServerPhase.RUNNING:
            self._stop_reason = reason
            self._ready = False
            self.phase = ServerPhase.STOPPING
            self._emit("runtime.stop_requested", reason)
            return
        if self.phase in {ServerPhase.STOPPING, ServerPhase.STOPPED, ServerPhase.FAILED}:
            return
        raise ServerRuntimeError("invalid_phase", "server cannot stop during startup")

    def shutdown(self, reason: str = "shutdown") -> ServerHealthSnapshot:
        if self.phase is ServerPhase.CREATED:
            self.request_stop(reason)
            return self.health()
        if self.phase is ServerPhase.RUNNING:
            self.request_stop(reason)
        if self.phase is ServerPhase.STOPPING:
            self._finish_stop()
        return self.health()

    def health(self) -> ServerHealthSnapshot:
        now = self._clock()
        uptime = 0.0 if self._started_at is None else max(0.0, now - self._started_at)
        return ServerHealthSnapshot(
            phase=self.phase,
            tick=self._tick,
            ready=self.ready,
            healthy=self.phase in {ServerPhase.STARTING, ServerPhase.RUNNING, ServerPhase.STOPPING}
            and self._failure_code is None,
            uptime_seconds=uptime,
            last_tick_seconds=self._last_tick_seconds,
            schedule_lag_seconds=self._schedule_lag_seconds,
            dropped_ticks=self._dropped_ticks,
            startup_checks_passed=self._startup_checks_passed,
            startup_checks_total=len(self._startup_checks),
            failure_code=self._failure_code,
            stop_reason=self._stop_reason,
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "server_name": self.config.server_name,
            "tick_rate_hz": self.config.tick_rate_hz,
            "fixed_dt": self.fixed_dt,
            "phase": self.phase.value,
            "tick": self._tick,
            "ready": self.ready,
            "healthy": self.health().healthy,
            "schedule_lag_seconds": self._schedule_lag_seconds,
            "last_tick_seconds": self._last_tick_seconds,
            "dropped_ticks": self._dropped_ticks,
            "asset_count": len(self._assets),
            "startup_checks_passed": self._startup_checks_passed,
            "startup_checks_total": len(self._startup_checks),
            "event_count": len(self._events),
            "event_evictions": self._event_evictions,
            "failure_code": self._failure_code,
            "stop_reason": self._stop_reason,
            "events": [event.portable() for event in self._events],
        }

    def _tick_once(self) -> None:
        started = self._clock()
        try:
            self._on_tick(self, self.fixed_dt)
        except Exception as exc:
            error = ServerRuntimeError("tick_failed", f"server tick failed at {self._tick}: {exc}")
            self._fail(error.code, str(error))
            raise error from exc
        finished = self._clock()
        self._last_tick_seconds = max(0.0, finished - started)
        self._tick += 1
        if (
            self.phase is ServerPhase.RUNNING
            and not self._ready
            and self._tick >= self.config.ready_after_ticks
        ):
            self._ready = True
            self._emit("runtime.ready")

    def _validate_assets(self) -> None:
        for asset in self._assets:
            if asset.kind not in SERVER_SAFE_ASSET_KINDS:
                raise ServerRuntimeError(
                    "client_only_asset",
                    f"asset {asset.path!r} uses client-only kind {asset.kind.value!r}",
                )
        self._emit("assets.validated", str(len(self._assets)))

    def _finish_stop(self) -> None:
        try:
            self._invoke_stop_once()
        except Exception as exc:
            error = ServerRuntimeError("shutdown_failed", f"server shutdown failed: {exc}")
            self._failure_code = error.code
            self.phase = ServerPhase.FAILED
            self._ready = False
            self._emit("runtime.failed", error.code)
            raise error from exc
        self.phase = ServerPhase.STOPPED
        self._ready = False
        self._emit("runtime.stopped", self._stop_reason or "stopped")

    def _fail(self, code: str, detail: str) -> None:
        self._failure_code = _bounded_text(code, "failure code", maximum=96)
        self._ready = False
        self.phase = ServerPhase.FAILED
        self._emit("runtime.failed", self._failure_code)
        if self._start_callback_entered:
            try:
                self._invoke_stop_once()
            except Exception:
                self._emit("runtime.cleanup_failed", "on_stop")

    def _invoke_stop_once(self) -> None:
        if self._stop_callback_called:
            return
        self._stop_callback_called = True
        if self._on_stop is not None:
            self._on_stop(self)

    def _emit(self, kind: str, detail: str = "") -> None:
        if len(self._events) == self.config.max_events:
            self._event_evictions += 1
        self._event_sequence += 1
        self._events.append(ServerEvent(self._event_sequence, kind, self._tick, detail))

    def _install_signal_handlers(self) -> Callable[[], None]:
        previous: dict[signal.Signals, Any] = {}

        def _handler(signum: int, _frame: Any) -> None:
            try:
                signal_name = signal.Signals(signum).name
            except ValueError:
                signal_name = str(signum)
            self.request_stop(f"signal:{signal_name}")

        try:
            for signal_value in (signal.SIGINT, signal.SIGTERM):
                previous[signal_value] = signal.getsignal(signal_value)
                signal.signal(signal_value, _handler)
        except (ValueError, OSError) as exc:
            for signal_value, previous_handler in previous.items():
                signal.signal(signal_value, previous_handler)
            raise ServerRuntimeError(
                "signal_install_failed",
                "signal handlers can only be installed where the host runtime permits them",
            ) from exc

        def _restore() -> None:
            for signal_value, previous_handler in previous.items():
                signal.signal(signal_value, previous_handler)

        return _restore


__all__ = [
    "SERVER_SAFE_ASSET_KINDS",
    "DedicatedServerRuntime",
    "ServerAssetKind",
    "ServerAssetReference",
    "ServerConfig",
    "ServerEvent",
    "ServerHealthSnapshot",
    "ServerPhase",
    "ServerRuntimeError",
    "ServerStartupCheck",
]
