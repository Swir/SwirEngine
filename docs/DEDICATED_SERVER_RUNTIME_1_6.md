# Dedicated Server Runtime — SwirEngine 1.6

SwirEngine 1.6 Milestone 5 adds an **additive, opt-in dedicated-server runtime** in
`swirengine.server16`. It does not replace `Game`, change stable 1.x root imports, or require an
existing client project to migrate. The runtime is intended for authoritative/headless simulation,
multiplayer session hosting, CI soak workloads, and Linux/container hosting where no window or audio
runtime should be required by server-owned components.

SwirEngine 1.6 remains a source-development checkpoint. This work does **not** create a 1.6 tag,
GitHub Release, or PyPI publication; the next public Release/PyPI target is SwirEngine 2.0.

## Runtime model

The server is built around four explicit contracts:

1. `DedicatedServerConfig` validates fixed-tick and deployment settings.
2. `HeadlessRuntimeBoundary` restricts server components to declared headless capabilities and
   server-safe asset classes.
3. `ServerComponent` declares lifecycle hooks, deterministic dependencies, tick work, health and
   readiness probes, and metadata-only asset requirements.
4. `DedicatedServerRuntime` validates the full graph before startup, runs deterministic fixed-delta
   ticks, exposes health/readiness payloads, and shuts components down in reverse dependency order.

The new module uses standard-library scheduling/lifecycle primitives and stays separate from the
renderer/window/audio runtime. Server components cannot silently request those client-only
capabilities through the headless boundary.

## Minimal server

```python
from swirengine.server16 import (
    DedicatedServerConfig,
    DedicatedServerRuntime,
    ServerComponent,
)

world = {"ticks": 0}

server = DedicatedServerRuntime(
    DedicatedServerConfig(
        tick_rate_hz=30.0,
        instance_id="eu-match-17",
        environment="production",
    )
)
server.register(
    ServerComponent(
        "network",
        lambda tick: None,
        capabilities=("network", "metrics"),
    )
)
server.register(
    ServerComponent(
        "world",
        lambda tick: world.__setitem__("ticks", world["ticks"] + 1),
        dependencies=("network",),
        capabilities=("clock", "storage"),
    )
)

server.start()
server.serve()
```

For tests, deterministic simulations, and controlled hosts, `run_ticks(count)` executes fixed-delta
work without wall-clock sleeping. `serve()` is the wall-clock scheduler and applies the configured
catch-up bound.

## Fixed-tick scheduling

`tick_rate_hz` defines a constant simulation delta. Every `ServerTick` contains:

- monotonic integer `tick` starting at 1;
- constant `dt = 1 / tick_rate_hz`;
- deterministic `simulation_time = tick * dt`.

The wall-clock `serve()` loop never changes `dt` to catch up. If the process falls behind, it executes
at most `max_catchup_ticks` overdue slots in one scheduling pass. Excess overdue wall-clock slots are
counted as `dropped_tick_slots` so overload is visible instead of silently turning into an unbounded
catch-up spiral. This is a scheduling/load-shedding contract, not an FPS claim.

## Dependency-safe startup and shutdown

Components declare dependencies by name. Startup performs a complete preflight before any lifecycle
hook runs:

- missing dependencies fail with `ServerRuntimeError.code == "missing_dependency"`;
- dependency cycles fail with `code == "dependency_cycle"`;
- unsupported headless capabilities/assets fail before component startup;
- required metadata-only assets can be checked through an injected `asset_probe` without loading
  them into the runtime;
- startup order is deterministic and dependency-first, with name ordering as the stable tie-breaker.

If a startup hook fails, already-entered components (including the failing component) receive cleanup
in reverse dependency order. Tick failures do not advance the authoritative tick counter. Shutdown
continues through every registered cleanup hook even if one cleanup fails.

`request_shutdown(reason)` is idempotent and immediately removes readiness. The hosting process can
wire SIGINT/SIGTERM, an orchestrator callback, an admin command, or its own service manager to this
method without the engine installing global signal handlers behind the creator's back.

The synchronous cleanup duration is compared with `shutdown_grace_seconds`; an exceeded grace budget
is surfaced in diagnostics. The runtime still attempts every cleanup hook rather than abandoning
later components.

## Health and readiness

`health()` returns `ServerHealth`, a callback-free portable status object. `portable()` is suitable
for an HTTP adapter, process supervisor, container probe, metrics exporter, or test assertion.

A running server is **ready** only when:

- startup completed;
- shutdown has not been requested;
- all component health checks are healthy;
- all component readiness checks report ready.

Probe exceptions are fault-contained and reported as failed health/readiness rather than crashing the
simulation loop. A failed runtime and a cleanly stopped runtime are not reported as healthy.

Useful diagnostics include:

- startup attempts/successes;
- executed ticks and tick failures;
- dropped scheduler slots;
- readiness/health probe failures;
- shutdown requests/failures/grace overruns;
- last/max tick callback duration;
- last stable error code/message;
- validated deployment configuration.

## Server-safe capability boundary

The default boundary allows only:

- `clock`
- `filesystem`
- `logging`
- `metrics`
- `network`
- `storage`

The default server asset kinds are:

- `config`
- `data`
- `map`
- `metadata`
- `navigation`

Client-facing declarations such as `graphics`, `window`, `ui`, `input`, `audio`, `texture`, `shader`,
or `video` are rejected by default. Projects can narrow the allowed sets further for hardened hosts.
Broadening them is explicit and visible in server configuration rather than implied by client code.

`ServerAssetRequirement` accepts only safe project-relative paths and rejects absolute paths and
`..` traversal. Requirements are declarations; the runtime never downloads, executes, or implicitly
loads remote content.

## Configuration from environment

Container/service managers can construct the configuration from environment variables:

```python
from swirengine.server16 import DedicatedServerConfig

config = DedicatedServerConfig.from_env()
```

Supported variables use the `SWIRENGINE_SERVER_` prefix:

- `TICK_RATE_HZ`
- `MAX_CATCHUP_TICKS`
- `MAX_SLEEP_SECONDS`
- `SHUTDOWN_GRACE_SECONDS`
- `INSTANCE_ID`
- `ENVIRONMENT`

The prefix can be changed explicitly. Invalid numeric values fail during configuration instead of
being deferred until the server is already serving a match.

## Linux/container smoke path

The dedicated workflow validates Python 3.10, 3.13 and 3.14, then performs a clean Linux wheel smoke
on Python 3.13:

1. build a wheel from the repository;
2. create a fresh virtual environment;
3. install the built wheel with normal dependencies;
4. remove `DISPLAY` and `WAYLAND_DISPLAY` from the smoke environment;
5. import the installed `swirengine.server16` module;
6. validate readiness, run 256 authoritative fixed ticks, and shut down cleanly.

The smoke is intentionally process/headless focused. It does not claim a published container image or
a public 1.6 package.

## Verification workload

`tools/benchmark_dedicated_server_1_6.py` runs 50,000 deterministic component ticks and validates the
resulting state/counters under a generous 3-second CI budget on the representative Python 3.13 job.
The benchmark protects against accidental scheduler/lifecycle overhead regressions and does not make
an FPS/network-throughput claim.

The runnable creator example is `examples/demo_dedicated_server_1_6.py`.
