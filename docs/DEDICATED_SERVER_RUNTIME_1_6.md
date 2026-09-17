# Dedicated Server Runtime — SwirEngine 1.6

SwirEngine 1.6 adds an **additive, headless dedicated-server runtime** in `swirengine.server16`. It is designed for authoritative multiplayer processes that need deterministic fixed-step simulation, bounded catch-up behavior, explicit startup validation, graceful shutdown, health/readiness reporting, and a server-safe asset manifest without changing stable 1.x `Game` or networking APIs.

The module deliberately does not open a window, initialize a renderer, create an audio device, or own a network transport. Creators compose it with the verified 1.6 replication, prediction, session, and transport-QoS layers as needed.

## Configuration

```python
from swirengine.server16 import ServerConfig

config = ServerConfig(
    server_name="EU-1",
    tick_rate_hz=60,
    max_catch_up_ticks=4,
    ready_after_ticks=2,
    max_events=256,
    max_assets=4096,
)
```

`ServerConfig` validates every bound and exposes a constant `fixed_dt = 1 / tick_rate_hz`. Tick rates must be finite and between 0.001 Hz and 1000 Hz.

Container/process configuration can be loaded from environment variables:

```python
config = ServerConfig.from_env()
```

Recognized variables use the `SWIR_SERVER_` prefix:

- `SWIR_SERVER_NAME`
- `SWIR_SERVER_TICK_RATE_HZ`
- `SWIR_SERVER_MAX_CATCH_UP_TICKS`
- `SWIR_SERVER_READY_AFTER_TICKS`
- `SWIR_SERVER_MAX_EVENTS`
- `SWIR_SERVER_MAX_ASSETS`

A custom prefix or explicit mapping can be supplied for tests and orchestration adapters.

## Headless asset boundary

A dedicated server should not accidentally declare client-only presentation resources as startup dependencies. The optional manifest makes that boundary explicit:

```python
from swirengine.server16 import ServerAssetKind, ServerAssetReference

assets = (
    ServerAssetReference("config/server.json", ServerAssetKind.CONFIG),
    ServerAssetReference("maps/arena.json", ServerAssetKind.MAP),
)
```

Server-safe kinds are `data`, `map`, `script`, and `config`. Presentation-only kinds (`texture`, `shader`, `audio`, `video`, and `font`) are rejected during startup with `ServerRuntimeError(code="client_only_asset")`.

Paths must be normalized relative project paths. Absolute paths, `..`, redundant path components, and duplicate manifest entries are rejected. The runtime validates and sorts the manifest deterministically without loading asset contents itself.

This is a safety/architecture boundary, not a claim that every file listed by a creator is semantically valid. Projects can add startup checks for content hashes, schema validation, database reachability, port binding, or other deployment-specific requirements.

## Deterministic startup checks

```python
from swirengine.server16 import ServerStartupCheck

checks = (
    ServerStartupCheck("content-manifest", verify_content),
    ServerStartupCheck("database", verify_database),
)
```

Checks execute in declaration order before the creator `on_start` callback. A check passes when it returns `None` or `True`. Returning `False` raises `startup_check_failed`; an unexpected exception becomes `startup_failed`. Later checks and creator startup do not run after failure.

Health snapshots report both the number of passed checks and the configured total.

## Fixed-step simulation

```python
from swirengine.server16 import DedicatedServerRuntime


def tick(runtime: DedicatedServerRuntime, dt: float) -> None:
    world.step(dt)


runtime = DedicatedServerRuntime(config=config, on_tick=tick)
runtime.run()
```

Every successful tick receives the same fixed `dt`. Real-time pacing uses `time.monotonic()` by default. If the process falls behind, the runtime executes at most `max_catch_up_ticks` in one scheduler cycle. Excess overdue ticks are intentionally dropped from wall-clock catch-up and counted in `dropped_ticks`, preventing an unbounded spiral-of-death loop.

For deterministic tests, soak harnesses, and simulation tooling, `run_ticks(count)` advances an already-created/running server without sleeping while preserving the same fixed `dt` contract.

The runtime does not claim deterministic game state by itself: creator simulation code still needs deterministic inputs/state transitions where that matters. The contract here is deterministic step size, bounded scheduler work, and explicit diagnostics.

## Readiness and health

```python
health = runtime.health()
print(health.portable())
```

`ServerHealthSnapshot` includes:

- lifecycle phase;
- successful simulation tick count;
- readiness and health flags;
- process-local uptime;
- last callback duration;
- current scheduler lag;
- dropped-tick count;
- startup check progress;
- stable failure code and stop reason.

Readiness becomes true only while the runtime is `running` and after `ready_after_ticks` successful ticks. It clears as soon as shutdown starts or a failure occurs. This supports load-balancer/readiness probes without declaring a just-started process ready before its configured warm-up.

`diagnostics()` adds bounded lifecycle events and aggregate counts without including creator packet payloads or secret session tokens.

## Graceful shutdown

`run()` can install SIGINT/SIGTERM handlers on hosts that permit Python signal handlers. A signal requests a normal transition from `running` to `stopping`, clears readiness, invokes `on_stop` once, and ends as `stopped`.

Creators can request the same path explicitly:

```python
runtime.request_stop("maintenance")
```

or synchronously finish it with:

```python
runtime.shutdown("maintenance")
```

`on_stop` is called at most once. A creator `on_tick` exception becomes `tick_failed`, a creator startup exception becomes `startup_failed`, and a stop callback exception becomes `shutdown_failed`. Tick/start failures perform best-effort creator cleanup before the runtime remains in `failed`.

## Bounded scheduler behavior

The wall scheduler does not run an unlimited number of catch-up ticks after a stall. Given a fixed `dt` and `max_catch_up_ticks`, each scheduler cycle:

1. sleeps until the next deadline when ahead;
2. calculates how many fixed ticks are due;
3. records and skips excess wall-clock catch-up beyond the configured bound;
4. executes at most the bounded number of fixed ticks;
5. advances deadlines deterministically.

This protects a hosted server from making an old stall worse by attempting unbounded catch-up work.

## Creator example

A runnable source example lives at:

```text
examples/dedicated_server_1_6/run_server.py
```

It uses environment configuration, startup checks, a server-safe asset manifest, real monotonic pacing, readiness warm-up, bounded diagnostics, and an automatic smoke-test tick limit controlled by `SWIR_SERVER_MAX_TICKS`.

Run it locally:

```bash
SWIR_SERVER_MAX_TICKS=12 python examples/dedicated_server_1_6/run_server.py
```

The process prints a canonical JSON-style diagnostics payload after graceful stop.

## Linux/container smoke

The source example includes a minimal container definition:

```text
examples/dedicated_server_1_6/Dockerfile
```

The dedicated 1.6 CI gate builds the repository package inside `python:3.13-slim`, launches the headless example, and requires a successful bounded server run. This verifies a realistic Linux/container packaging path without publishing an image or introducing a hosted service dependency.

Build/run manually from the repository root:

```bash
docker build -f examples/dedicated_server_1_6/Dockerfile -t swirengine-server16 .
docker run --rm swirengine-server16
```

## Verification contract

The dedicated gate covers Python 3.10, 3.13, and 3.14 and verifies:

- strict config/environment parsing;
- normalized server-safe asset manifests and client-only rejection before creator startup;
- ordered startup checks and atomic startup failure;
- constant fixed-step `dt` and readiness warm-up;
- bounded real-time catch-up with explicit dropped-tick accounting;
- graceful stop and exactly-once cleanup;
- startup/tick/shutdown failure isolation;
- bounded lifecycle diagnostics;
- a 100,000-tick deterministic headless workload within a generous CI budget;
- creator example execution;
- Linux wheel/container build and smoke;
- verified 1.6 replication, prediction, session, transport-QoS and locked 1.4 multiplayer regressions.

SwirEngine 1.6 remains a source-development checkpoint. No 1.6 GitHub Release, tag, or PyPI publication is created; the next public Release/PyPI target is SwirEngine 2.0.
